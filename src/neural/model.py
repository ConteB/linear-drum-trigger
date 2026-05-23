"""TCN topology — F0-T4a §3 (Strided Encoder + Dilated Causal TCN Trunk).

Four stages:

1. **Input-Agnostic Projection** — Conv1d k=1, ``8 → C``.
2. **Strided Encoder Stem** — 4 × Conv1d (k=8, stride [4, 4, 4, 2]) bringing the
   44.1 kHz raw audio onto the 344.53 Hz target grid (Π stride = 128 = 2⁷).
3. **Dilated Causal TCN Trunk** — 8 residual blocks; each block is
   ``[Conv1d k=3 dilated → ReLU → Conv1d k=3 dilated → ReLU]`` plus the input
   skip; dilations ``[1, 2, 4, 8, 16, 32, 64, 128]``. Conv1d are *causal*
   (past-only) — RTNeural streams them stateful.
4. **Heads** — 4 × Conv1d k=1 producing onset/velocity/microtiming/hihat,
   concatenated to the F0-T2a flat-25 layout
   (cols ``3b/3b+1/3b+2`` per bus + col 24 = hihat opening).

Baseline ``C = 32`` (F0-T4a §3, tarable). Encoder activations are ReLU
(F0-T4a §3 line ②).

Spec: ``docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md`` §3.
"""
from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

#: F0-T4a §3 — strided-encoder factor (one per layer; product = 128).
ENCODER_STRIDES: tuple[int, ...] = (4, 4, 4, 2)
ENCODER_KERNEL = 8
#: F0-T4a §3 — trunk dilations per residual block.
TRUNK_DILATIONS: tuple[int, ...] = (1, 2, 4, 8, 16, 32, 64, 128)
TRUNK_KERNEL = 3
#: F0-T4a §4 — fixed 8-slot input width (zero-fill for unused slots).
N_INPUT_SLOTS = 8
#: F0-T2a §3.3 — flat-25 = 8 buses × 3 channels + 1 hihat opening.
N_BUSES = 8
TARGET_COLS = 25
HIHAT_OPENING_COL = 24


@dataclass(frozen=True)
class TCNConfig:
    """Hyperparameters of the F0-T4a TCN baseline."""

    channels: int = 32  # F0-T4a §3 baseline C
    encoder_kernel: int = ENCODER_KERNEL
    encoder_strides: tuple[int, ...] = ENCODER_STRIDES
    trunk_kernel: int = TRUNK_KERNEL
    trunk_dilations: tuple[int, ...] = TRUNK_DILATIONS

    @property
    def total_stride(self) -> int:
        out = 1
        for s in self.encoder_strides:
            out *= s
        return out


class CausalConv1d(nn.Module):
    """Conv1d with left-only padding — output at ``t`` depends on inputs ``<= t``.

    PyTorch's :class:`~torch.nn.Conv1d` has no native ``causal`` flag; we
    implement it as a ``padding=0`` conv preceded by an explicit left pad of
    ``(kernel_size - 1) * dilation``. The exported RTNeural graph uses the same
    convolution operator with the same kernel/dilation; the causal padding is a
    streaming property (zero history at ``t = 0``) that RTNeural handles by
    construction.
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        *,
        dilation: int = 1,
        bias: bool = True,
    ) -> None:
        super().__init__()
        self.left_pad = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(
            in_channels,
            out_channels,
            kernel_size,
            padding=0,
            dilation=dilation,
            bias=bias,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, C, T]
        x = nn.functional.pad(x, (self.left_pad, 0))
        out: torch.Tensor = self.conv(x)
        return out


class DilatedTCNBlock(nn.Module):
    """Residual block: ``[CausalConv → ReLU → CausalConv → ReLU] + skip``.

    Same ``in_channels == out_channels == C`` — the skip is identity, no 1×1
    bottleneck (keeps the RTNeural graph trivially serial; ``F0-T4a §8``
    open item).
    """

    def __init__(self, channels: int, kernel_size: int, dilation: int) -> None:
        super().__init__()
        self.conv1 = CausalConv1d(channels, channels, kernel_size, dilation=dilation)
        self.conv2 = CausalConv1d(channels, channels, kernel_size, dilation=dilation)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = nn.functional.relu(self.conv1(x))
        y = nn.functional.relu(self.conv2(y))
        return x + y


class StridedEncoder(nn.Module):
    """Encoder stem — 4 × strided Conv1d bringing 44.1 kHz → 344.53 Hz."""

    def __init__(self, channels: int, kernel_size: int, strides: tuple[int, ...]) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        for stride in strides:
            # Each strided conv consumes ``(kernel-1)`` past samples for
            # causality. We left-pad explicitly per layer.
            layers.append(_StridedCausalConv(channels, channels, kernel_size, stride))
        self.layers = nn.ModuleList(layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        for layer in self.layers:
            x = nn.functional.relu(layer(x))
        return x


class _StridedCausalConv(nn.Module):
    """Internal — causal strided Conv1d."""

    def __init__(
        self, in_channels: int, out_channels: int, kernel_size: int, stride: int
    ) -> None:
        super().__init__()
        self.left_pad = kernel_size - 1
        self.conv = nn.Conv1d(
            in_channels, out_channels, kernel_size, stride=stride, padding=0
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = nn.functional.pad(x, (self.left_pad, 0))
        out: torch.Tensor = self.conv(x)
        return out


class TCNModel(nn.Module):
    """The F0-T4a TCN model.

    Forward shape:
        ``[B, 8, n_sample]`` → ``[B, n_frame, 25]``, with
        ``n_frame = n_sample // 128``.

    The model output is the F0-T2a flat-25 target layout: columns ``3b``
    (onset, sigmoid), ``3b+1`` (velocity, sigmoid), ``3b+2`` (microtiming,
    tanh) for bus ``b ∈ [0, 7]``, and column ``24`` (hihat opening, sigmoid).
    """

    def __init__(self, config: TCNConfig | None = None) -> None:
        super().__init__()
        self.config = config or TCNConfig()
        C = self.config.channels  # noqa: N806 — match the spec notation
        self.projection = nn.Conv1d(N_INPUT_SLOTS, C, kernel_size=1)
        self.encoder = StridedEncoder(
            C, self.config.encoder_kernel, self.config.encoder_strides
        )
        self.trunk = nn.ModuleList(
            [
                DilatedTCNBlock(C, self.config.trunk_kernel, dilation=d)
                for d in self.config.trunk_dilations
            ]
        )
        # Heads are exported as four Conv1d k=1; F0-T4a §8 open item lets us
        # fuse them later into one Conv1d C→25 if RTNeural prefers a single
        # graph.
        self.head_onset = nn.Conv1d(C, N_BUSES, kernel_size=1)
        self.head_velocity = nn.Conv1d(C, N_BUSES, kernel_size=1)
        self.head_microtiming = nn.Conv1d(C, N_BUSES, kernel_size=1)
        self.head_hihat = nn.Conv1d(C, 1, kernel_size=1)

    # NOTE: this is the "training-time" forward. The *streaming-time* forward
    # (one frame at a time, stateful) is implemented by RTNeural in C++; the
    # numerical equivalence between the two is the F0-T4b L3 round-trip gate.
    def forward(self, audio: torch.Tensor) -> torch.Tensor:
        # audio: [B, 8, n_sample] — n_sample must be a multiple of total_stride.
        x = self.projection(audio)
        x = self.encoder(x)
        for block in self.trunk:
            x = block(x)
        # x: [B, C, n_frame]
        onset = torch.sigmoid(self.head_onset(x))
        velocity = torch.sigmoid(self.head_velocity(x))
        microtiming = torch.tanh(self.head_microtiming(x))
        hihat = torch.sigmoid(self.head_hihat(x))
        # Assemble flat-25: interleave bus columns (3b, 3b+1, 3b+2) and append col 24.
        # Build a [B, 25, T] tensor then transpose to [B, T, 25].
        B, _, T = x.shape  # noqa: N806
        flat = torch.empty((B, TARGET_COLS, T), dtype=x.dtype, device=x.device)
        # Interleave columns: for bus b, cols [3b, 3b+1, 3b+2] = onset, vel, mt.
        flat[:, 0:24:3, :] = onset
        flat[:, 1:24:3, :] = velocity
        flat[:, 2:24:3, :] = microtiming
        flat[:, HIHAT_OPENING_COL, :] = hihat.squeeze(1)
        return flat.transpose(1, 2).contiguous()  # [B, T, 25]


def count_parameters(model: nn.Module) -> int:
    """Total number of trainable parameters."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


__all__ = [
    "CausalConv1d",
    "DilatedTCNBlock",
    "ENCODER_KERNEL",
    "ENCODER_STRIDES",
    "HIHAT_OPENING_COL",
    "N_BUSES",
    "N_INPUT_SLOTS",
    "StridedEncoder",
    "TARGET_COLS",
    "TCNConfig",
    "TCNModel",
    "TRUNK_DILATIONS",
    "TRUNK_KERNEL",
    "_StridedCausalConv",
    "count_parameters",
]
