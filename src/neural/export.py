"""PyTorch → RTNeural-style JSON export + a NumPy reference forward.

The L3 round-trip gate (F0-T4a §7-§8) needs two things:

1. Write the trained weights into a portable JSON the C++ side can load.
2. Show that *exactly* the same sequence of operations, applied to the same
   input, produces the same output up to fp32 rounding.

This module owns (1) and a pure-NumPy reference (2). The C++ binary that
consumes the JSON lives under ``cpp/`` (F0-T4b smoke-test).

**Why a custom JSON, not RTNeural's stock loader?** RTNeural's stock loader is
sequential — it does not natively absorb a *residual additive skip*
(F0-T4a §8 open item). We side-step the problem by emitting one JSON document
that lists every layer in execution order plus the explicit ``residual_add``
edges of the trunk. The C++ smoke-test follows the same order; both implementations
use only operations RTNeural exposes natively: ``Conv1D`` (strided, dilated),
``ReLU``, ``sigmoid``, ``tanh``, and additive merge.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from neural.model import (
    HIHAT_OPENING_COL,
    N_BUSES,
    N_INPUT_SLOTS,
    TARGET_COLS,
    TCNModel,
)

#: JSON schema version — bump if the layer/edge convention ever changes.
EXPORT_SCHEMA_VERSION = "1.0"


def _conv1d_to_dict(layer: torch.nn.Conv1d) -> dict[str, Any]:
    """Serialise a ``torch.nn.Conv1d`` into a portable dict.

    Stride / dilation / padding are kept zero-padded; the C++ side applies the
    causal left-pad explicitly (it owns the streaming state).
    """
    w = layer.weight.detach().cpu().numpy().astype(np.float32)  # [Cout, Cin, k]
    b = (
        layer.bias.detach().cpu().numpy().astype(np.float32)
        if layer.bias is not None
        else np.zeros(layer.out_channels, dtype=np.float32)
    )
    return {
        "type": "conv1d",
        "in_channels": int(layer.in_channels),
        "out_channels": int(layer.out_channels),
        "kernel_size": int(layer.kernel_size[0]),
        "stride": int(layer.stride[0]),
        "dilation": int(layer.dilation[0]),
        # The C++ side knows the conv is causal by construction; the JSON
        # records the left-pad it must apply (``(k-1)*dilation`` for stride=1
        # conv, ``k-1`` for strided conv) for self-documentation.
        "causal_left_pad": int((layer.kernel_size[0] - 1) * layer.dilation[0]),
        "weight": w.tolist(),
        "bias": b.tolist(),
    }


def export_tcn(model: TCNModel, path: Path | str) -> Path:
    """Write ``model`` to a portable JSON at ``path`` and return ``path``.

    The document lists every layer in execution order; the C++ side walks the
    list and applies the same operations.
    """
    cfg = model.config
    layers: list[dict[str, Any]] = []

    layers.append({"id": "projection", **_conv1d_to_dict(model.projection)})

    from neural.model import DilatedTCNBlock, _StridedCausalConv  # local — narrow types

    for i, stride in enumerate(cfg.encoder_strides):
        sub = model.encoder.layers[i]
        assert isinstance(sub, _StridedCausalConv)
        layers.append(
            {
                "id": f"encoder_{i}",
                **_conv1d_to_dict(sub.conv),
                "_stride_override": stride,  # documentary; conv1d dict already has it
                "post_activation": "relu",
            }
        )

    for j in range(len(cfg.trunk_dilations)):
        block = model.trunk[j]
        assert isinstance(block, DilatedTCNBlock)
        layers.append(
            {
                "id": f"trunk_{j}_conv1",
                **_conv1d_to_dict(block.conv1.conv),
                "post_activation": "relu",
            }
        )
        layers.append(
            {
                "id": f"trunk_{j}_conv2",
                **_conv1d_to_dict(block.conv2.conv),
                "post_activation": "relu",
                "residual_add_from": f"trunk_{j}_input",
            }
        )

    layers.append(
        {"id": "head_onset", **_conv1d_to_dict(model.head_onset), "post_activation": "sigmoid"}
    )
    layers.append(
        {
            "id": "head_velocity",
            **_conv1d_to_dict(model.head_velocity),
            "post_activation": "sigmoid",
        }
    )
    layers.append(
        {
            "id": "head_microtiming",
            **_conv1d_to_dict(model.head_microtiming),
            "post_activation": "tanh",
        }
    )
    layers.append(
        {"id": "head_hihat", **_conv1d_to_dict(model.head_hihat), "post_activation": "sigmoid"}
    )

    doc = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "model": "F0-T4a-TCN",
        "input": {
            "n_slots": N_INPUT_SLOTS,
            "sample_rate_hz": 44100,
            "dtype": "float32",
        },
        "output": {
            "layout": "flat-25",
            "frame_rate_hz": 44100 / 128,
            "n_columns": TARGET_COLS,
            "n_buses": N_BUSES,
            "hihat_opening_col": HIHAT_OPENING_COL,
        },
        "topology": {
            "channels": cfg.channels,
            "encoder_kernel": cfg.encoder_kernel,
            "encoder_strides": list(cfg.encoder_strides),
            "trunk_kernel": cfg.trunk_kernel,
            "trunk_dilations": list(cfg.trunk_dilations),
            "total_stride": cfg.total_stride,
        },
        "layers": layers,
    }

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    return out


# ----------------------------------------------------------------------------
# NumPy reference forward.
# ----------------------------------------------------------------------------


def _conv1d_causal(
    x: np.ndarray,
    weight: np.ndarray,
    bias: np.ndarray,
    *,
    stride: int,
    dilation: int,
) -> np.ndarray:
    """1-D causal convolution in pure NumPy.

    Args:
        x: ``[C_in, T]`` input.
        weight: ``[C_out, C_in, K]`` filter.
        bias: ``[C_out]`` bias.
        stride: Conv stride.
        dilation: Conv dilation.

    Returns:
        ``[C_out, T_out]`` output with causal padding applied on the left.
    """
    c_in, t = x.shape
    c_out, c_in_w, k = weight.shape
    assert c_in == c_in_w, f"channel mismatch: x has {c_in}, weight expects {c_in_w}"
    left_pad = (k - 1) * dilation
    padded = np.zeros((c_in, t + left_pad), dtype=x.dtype)
    padded[:, left_pad:] = x
    t_padded = padded.shape[1]
    # Output time axis: every `stride`-th valid position.
    t_out = (t_padded - (k - 1) * dilation - 1) // stride + 1
    out = np.zeros((c_out, t_out), dtype=np.float32)
    # Reshape weight for matmul: [C_out, C_in*K]
    w_flat = weight.reshape(c_out, c_in * k)
    for n in range(t_out):
        start = n * stride
        # Gather the K samples (with dilation) for every input channel.
        cols = padded[:, start : start + (k - 1) * dilation + 1 : dilation]
        # cols: [C_in, K]
        out[:, n] = w_flat @ cols.reshape(-1) + bias
    return out


def _apply_activation(x: np.ndarray, kind: str | None) -> np.ndarray:
    if kind is None:
        return x
    if kind == "relu":
        return np.asarray(np.maximum(x, 0.0))
    if kind == "sigmoid":
        return np.asarray(1.0 / (1.0 + np.exp(-x)))
    if kind == "tanh":
        return np.asarray(np.tanh(x))
    raise ValueError(f"unknown activation: {kind}")


def numpy_reference_forward(doc: dict[str, Any], audio: np.ndarray) -> np.ndarray:
    """Run the same model in pure NumPy, op-by-op, on ``audio``.

    Args:
        doc: The JSON dict written by :func:`export_tcn`.
        audio: ``[8, n_sample]`` input.

    Returns:
        ``[n_frame, 25]`` flat-25 output, in the same layout as the PyTorch model.
    """
    if audio.ndim != 2 or audio.shape[0] != N_INPUT_SLOTS:
        raise ValueError(
            f"audio must be [{N_INPUT_SLOTS}, n_sample], got {audio.shape}"
        )
    layers = doc["layers"]
    # Activations keyed by layer id.
    activations: dict[str, np.ndarray] = {}
    x = audio.astype(np.float32, copy=False)
    last_trunk_input: np.ndarray | None = None  # holds the block input before conv1.
    trunk_features: np.ndarray | None = None  # the trunk output the 4 heads share.

    head_ids = {"head_onset", "head_velocity", "head_microtiming", "head_hihat"}

    for layer in layers:
        lid = layer["id"]
        weight = np.array(layer["weight"], dtype=np.float32)
        bias = np.array(layer["bias"], dtype=np.float32)
        stride = int(layer["stride"])
        dilation = int(layer["dilation"])

        # Trunk: capture the input of each block as its skip source. The first
        # conv of a trunk block has id "trunk_J_conv1"; its input *is* the
        # block input (= the trunk output before the block runs).
        if lid.startswith("trunk_") and lid.endswith("_conv1"):
            last_trunk_input = x.copy()

        # All four heads consume the SAME trunk output (the "feature tensor").
        # Capture it on the first head we encounter, then reset ``x`` to it
        # before processing each head.
        if lid in head_ids:
            if trunk_features is None:
                trunk_features = x.copy()
            x = trunk_features.copy()

        x = _conv1d_causal(x, weight, bias, stride=stride, dilation=dilation)

        post = layer.get("post_activation")
        x = _apply_activation(x, post)

        # If this layer's spec carries a residual add edge, sum the source.
        residual_src = layer.get("residual_add_from")
        if residual_src is not None:
            if residual_src.endswith("_input"):
                if last_trunk_input is None:
                    raise RuntimeError(f"missing residual source for {lid}")
                source = last_trunk_input
            else:
                source = activations[residual_src]
            x = x + source

        activations[lid] = x

    onset = activations["head_onset"]  # [8, T]
    velocity = activations["head_velocity"]
    microtiming = activations["head_microtiming"]
    hihat = activations["head_hihat"]  # [1, T]
    t_out = onset.shape[1]
    flat = np.zeros((TARGET_COLS, t_out), dtype=np.float32)
    flat[0:24:3, :] = onset
    flat[1:24:3, :] = velocity
    flat[2:24:3, :] = microtiming
    flat[HIHAT_OPENING_COL, :] = hihat[0]
    return flat.T  # [T, 25]


__all__ = [
    "EXPORT_SCHEMA_VERSION",
    "export_tcn",
    "numpy_reference_forward",
]
