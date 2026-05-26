"""Channel-Agnostic Frontend — F0-T4e (Decision Lock CEO 2026-05-26).

The frontend that sits **before** the F0-T4d preprocessing harness, making the
TCN input-agnostic-by-design rather than input-agnostic-by-zero-fill.

The plugin's v1.0 EA user routes 1-8 audio channels in any order. The pipeline
must therefore satisfy:

1. **Permutation-invariance.** Output identical for any permutation of input
   channels — proven mathematically, not learned empirically.
2. **Variable-count tolerance.** Zero-filled channels act as "no signal" and
   don't perturb the aggregated representation.
3. **Semantic-neutrality.** No assumption that "channel 0 is kick" / etc.

Architecture (F0-T4e §4.4 BA-combo):

    Input: [B, n_in, T]  where n_in ∈ {1..8}
       │
       ▼
    Per-Channel Shared Encoder
       φ : CausalConv1d(1 → C_per_ch, kernel=7) applied independently per channel
       Output: [B, n_in, C_per_ch, T]
       │
       ▼
    Permutation-Invariant Pool
       mean = x.mean(dim=1)  ──┐
       max  = x.max(dim=1)   ──┤── concat dim=1 → [B, 2·C_per_ch, T]
       │
       ▼  (output feeds F0-T4d PreprocessingFrontend)

Causality is preserved end-to-end: the per-channel Conv1d uses left-only
padding (mirrors F0-T4a CausalConv1d). Mean/max are time-pointwise → no
look-ahead introduced.

Real-time C++ port (F4-T0): ~160 LOC, +2 ms PDC. The shared encoder is a
single Conv1d invoked 8× (or fewer if the user wires only N slots), and the
mean/max are SIMD-friendly reductions along the channel axis.

Spec: ``docs/methodology/F0-T4e_INPUT_AGNOSTIC_TRAINING_SPEC.md`` §4.4 + §6.1.
"""
from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

from .model import N_INPUT_SLOTS

#: F0-T4e §4.4 — kernel width of the per-channel encoder. k=7 covers a
#: ~0.16 ms window at 44.1 kHz, sufficient to capture the transient onset
#: signature without introducing look-ahead (causal).
PER_CHANNEL_KERNEL: int = 7

#: F0-T4e §4.4 — internal width emitted by each per-channel encoder branch.
#: Output of the pool is ``2 × PER_CHANNEL_CHANNELS`` (mean ⊕ max concat).
#: Default 4 keeps the post-aggregation tensor at 8 channels — same width as
#: the legacy 8-mic input, so the downstream F0-T4d PreprocessingFrontend
#: (configured with ``n_mic=8``) stays unchanged.
PER_CHANNEL_CHANNELS: int = 4


@dataclass(frozen=True)
class ChannelAgnosticConfig:
    """Hyperparameters of the F0-T4e channel-agnostic frontend.

    The defaults are chosen so the post-aggregation tensor matches the legacy
    8-channel input contract: ``2 × PER_CHANNEL_CHANNELS = 8``. This lets the
    F0-T4d PreprocessingFrontend (configured with ``n_mic=8``) remain
    unchanged — F0-T4e composes *in front of* P1+P2, not in place of.
    """

    n_input_slots: int = N_INPUT_SLOTS
    per_channel_channels: int = PER_CHANNEL_CHANNELS
    per_channel_kernel: int = PER_CHANNEL_KERNEL

    @property
    def aggregated_channels(self) -> int:
        """Output width after mean⊕max concat: ``2 × per_channel_channels``."""
        return 2 * self.per_channel_channels


class PerChannelEncoder(nn.Module):
    """Shared-weight causal Conv1d applied independently to each input channel.

    Implementation note: rather than looping over channels (slow) or using
    ``Conv1d(groups=n_in)`` (which has *per-group* weights, not shared), we
    fold the channel dimension into the batch dimension, run a single
    Conv1d(1→C_per_ch), then unfold back. This guarantees true weight sharing
    while keeping a vectorised forward.

    Causality: left-padded by ``kernel_size - 1`` samples. Output time
    dimension matches input time dimension exactly (no down-sampling — the
    F0-T4a strided encoder downstream handles the 128× decimation).
    """

    def __init__(
        self,
        per_channel_channels: int = PER_CHANNEL_CHANNELS,
        kernel_size: int = PER_CHANNEL_KERNEL,
    ) -> None:
        super().__init__()
        if per_channel_channels <= 0:
            raise ValueError(
                f"per_channel_channels must be > 0, got {per_channel_channels}"
            )
        if kernel_size <= 0:
            raise ValueError(f"kernel_size must be > 0, got {kernel_size}")
        self.per_channel_channels = int(per_channel_channels)
        self.kernel_size = int(kernel_size)
        self.left_pad = self.kernel_size - 1
        # Shared 1→C_per_ch convolution; ``groups=1`` so the same weights
        # apply to every channel after we fold them into the batch dim.
        self.conv = nn.Conv1d(
            in_channels=1,
            out_channels=self.per_channel_channels,
            kernel_size=self.kernel_size,
            padding=0,
            bias=True,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Apply the shared encoder per channel.

        Args:
            x: ``[B, n_in, T]`` audio. Each channel is encoded independently
                with **the same weights** (true weight sharing).

        Returns:
            ``[B, n_in, C_per_ch, T]`` per-channel feature maps.
        """
        if x.dim() != 3:
            raise ValueError(f"PerChannelEncoder expects [B, C, T], got {tuple(x.shape)}")
        B, n_in, T = x.shape  # noqa: N806
        # Fold channel dim into batch: [B*n_in, 1, T].
        folded = x.reshape(B * n_in, 1, T)
        padded = nn.functional.pad(folded, (self.left_pad, 0))
        feats = self.conv(padded)  # [B*n_in, C_per_ch, T]
        # Unfold back: [B, n_in, C_per_ch, T].
        return feats.reshape(B, n_in, self.per_channel_channels, T)


class PermInvariantPool(nn.Module):
    """Permutation-invariant aggregation across the channel dimension.

    Concatenates the *mean* and *max* reductions along ``dim=1`` (channel),
    giving an output of width ``2 × per_channel_channels`` that is provably
    invariant to any permutation of the input channels.

    Mathematical guarantee: ``mean({x_π(1)..x_π(n)}) = mean({x_1..x_n})`` and
    ``max({x_π(1)..x_π(n)}) = max({x_1..x_n})`` for any permutation π.
    Concatenation preserves both properties.

    Zero-channel-input handling: if all input channels are zero (e.g. user
    plugged in only 1 mic but the harness passes 8 slots), mean=0 and max=0.
    The downstream TCN handles this as a "no signal" state.
    """

    def __init__(self) -> None:
        super().__init__()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Pool ``[B, n_in, C_per_ch, T]`` → ``[B, 2·C_per_ch, T]``.

        Args:
            x: per-channel feature maps from :class:`PerChannelEncoder`.

        Returns:
            Aggregated representation, permutation-invariant w.r.t. dim 1.
        """
        if x.dim() != 4:
            raise ValueError(
                f"PermInvariantPool expects [B, n_in, C_per_ch, T], got {tuple(x.shape)}"
            )
        mean = x.mean(dim=1)            # [B, C_per_ch, T]
        # torch.max returns (values, indices); we want only values.
        maximum = x.max(dim=1).values   # [B, C_per_ch, T]
        return torch.cat([mean, maximum], dim=1)  # [B, 2·C_per_ch, T]


class ChannelAgnosticFrontend(nn.Module):
    """Composes PerChannelEncoder + PermInvariantPool.

    This is the **single module** that the TCN composition wraps around.
    Sits *before* the F0-T4d PreprocessingFrontend in the forward pass:

        audio [B, n_in, T]
           ↓ ChannelAgnosticFrontend
        aggregated [B, 2·C_per_ch, T]
           ↓ F0-T4d PreprocessingFrontend (P1 + P2 + ChannelNorm)
        [B, 2·C_per_ch + 1, T]    (+1 for onset envelope channel)
           ↓ TCN (F0-T4a)
        [B, T_frame, 25]    flat-25 target

    The default config (``per_channel_channels=4``) makes
    ``2·C_per_ch = 8`` so the downstream PreprocessingFrontend can be reused
    with ``n_mic=8`` unchanged. The TCN ``in_channels`` becomes 9 (with P2)
    or 8 (without P2) — identical to the legacy contract.
    """

    def __init__(self, config: ChannelAgnosticConfig | None = None) -> None:
        super().__init__()
        self.config = config or ChannelAgnosticConfig()
        self.encoder = PerChannelEncoder(
            per_channel_channels=self.config.per_channel_channels,
            kernel_size=self.config.per_channel_kernel,
        )
        self.pool = PermInvariantPool()

    @property
    def output_channels(self) -> int:
        """Width of the aggregated tensor (`2 × per_channel_channels`)."""
        return self.config.aggregated_channels

    def forward(self, audio: torch.Tensor) -> torch.Tensor:
        """``[B, n_in, T]`` → ``[B, 2·C_per_ch, T]``."""
        if audio.dim() != 3:
            raise ValueError(
                f"ChannelAgnosticFrontend expects [B, C, T], got {tuple(audio.shape)}"
            )
        feats = self.encoder(audio)   # [B, n_in, C_per_ch, T]
        return self.pool(feats)        # [B, 2·C_per_ch, T]


__all__ = [
    "PER_CHANNEL_CHANNELS",
    "PER_CHANNEL_KERNEL",
    "ChannelAgnosticConfig",
    "ChannelAgnosticFrontend",
    "PerChannelEncoder",
    "PermInvariantPool",
]
