"""Sidecar binary export — same model graph, simpler to parse in C++.

The JSON file (``export_tcn``) is the human-readable, version-controlled
artefact; the ``.bin`` sidecar is a packed flat-array form purpose-built for
the C++ smoke-test (``cpp/round_trip_smoke/``).

Format (little-endian):

```
magic           : 4 bytes  = "OPNT"
schema_version  : uint32   = 1
n_layers        : uint32
for each layer:
  id_len        : uint32
  id            : utf-8 bytes (no NUL)
  in_channels   : int32
  out_channels  : int32
  kernel_size   : int32
  stride        : int32
  dilation      : int32
  causal_left_pad : int32
  activation_id : int32  (0=none, 1=relu, 2=sigmoid, 3=tanh)
  residual_kind : int32  (0=none, 1=trunk_input)
  weight: out_channels * in_channels * kernel_size  float32
  bias:   out_channels  float32
```

This is enough to reconstruct the entire model graph; the trunk-block
"residual_from_input" edge is encoded in the layer's ``residual_kind`` field
(C++ side captures the input of any ``trunk_J_conv1`` and re-adds it on the
matching ``trunk_J_conv2``).
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import numpy as np

MAGIC = b"OPNT"
SCHEMA_VERSION = 1

_ACTIVATION_ID = {None: 0, "relu": 1, "sigmoid": 2, "tanh": 3}
_RESIDUAL_KIND = {None: 0, "trunk_input": 1}


def _pack_layer(buf: bytearray, layer: dict[str, Any]) -> None:
    name = layer["id"].encode("utf-8")
    buf.extend(struct.pack("<I", len(name)))
    buf.extend(name)
    buf.extend(
        struct.pack(
            "<iiiiiii",
            int(layer["in_channels"]),
            int(layer["out_channels"]),
            int(layer["kernel_size"]),
            int(layer["stride"]),
            int(layer["dilation"]),
            int(layer["causal_left_pad"]),
            _ACTIVATION_ID[layer.get("post_activation")],
        )
    )
    res = layer.get("residual_add_from")
    residual_kind = "trunk_input" if res and res.endswith("_input") else None
    buf.extend(struct.pack("<i", _RESIDUAL_KIND[residual_kind]))
    weight = np.array(layer["weight"], dtype="<f4")
    bias = np.array(layer["bias"], dtype="<f4")
    expected_n = int(layer["out_channels"]) * int(layer["in_channels"]) * int(layer["kernel_size"])
    if weight.size != expected_n:
        raise ValueError(
            f"layer {layer['id']!r}: weight has {weight.size} elements, "
            f"expected {expected_n}"
        )
    buf.extend(weight.tobytes())
    buf.extend(bias.tobytes())


def export_binary(model_json_path: Path | str, bin_path: Path | str) -> Path:
    """Read the JSON model and write its binary sidecar at ``bin_path``."""
    doc = json.loads(Path(model_json_path).read_text(encoding="utf-8"))
    buf = bytearray()
    buf.extend(MAGIC)
    buf.extend(struct.pack("<II", SCHEMA_VERSION, len(doc["layers"])))
    for layer in doc["layers"]:
        _pack_layer(buf, layer)
    out = Path(bin_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buf)
    return out


__all__ = ["MAGIC", "SCHEMA_VERSION", "export_binary"]
