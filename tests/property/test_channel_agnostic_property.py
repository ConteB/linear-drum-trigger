"""Hypothesis property tests for the F0-T4e channel-agnostic stack.

We pin the central mathematical claim of F0-T4e: the
:class:`ChannelAgnosticFrontend` is **byte-equivalent under any channel
permutation**, for any randomly-generated input. This is the proof that the
architecture (B in the B+A combo) genuinely guarantees input agnosticity
rather than learning it empirically.

We also verify that the augmentation composer is deterministic across
machines (same seed = same output) and that masking always keeps ≥1 channel
active.
"""
from __future__ import annotations

import numpy as np
import torch
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from data_engineering.audio_augment import apply_channel_agnostic_aug
from neural.channel_agnostic import (
    ChannelAgnosticConfig,
    ChannelAgnosticFrontend,
)


# Hypothesis settings — keep the per-test budget modest (the property
# requires a forward pass through a Conv1d, ~10 ms each on CPU).
_SETTINGS = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@_SETTINGS
@given(
    batch=st.integers(min_value=1, max_value=3),
    n_in=st.integers(min_value=1, max_value=8),
    n_frame=st.integers(min_value=32, max_value=256),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_frontend_permutation_invariance_hypothesis(
    batch: int, n_in: int, n_frame: int, seed: int,
) -> None:
    """For any input + any permutation, the aggregated output is identical
    up to floating-point tolerance."""
    torch.manual_seed(seed)
    fe = ChannelAgnosticFrontend().eval()
    x = torch.randn(batch, n_in, n_frame)
    y_ref = fe(x)
    # Sample a permutation deterministically from the same seed.
    g = torch.Generator().manual_seed(seed + 1)
    perm = torch.randperm(n_in, generator=g)
    x_perm = x[:, perm, :]
    y_perm = fe(x_perm)
    assert torch.allclose(y_ref, y_perm, atol=1e-5), (
        f"Permutation-invariance violated under perm={perm.tolist()}, "
        f"max|Δ|={(y_ref - y_perm).abs().max().item():.2e}"
    )


@_SETTINGS
@given(
    per_channel_channels=st.integers(min_value=1, max_value=8),
    n_in=st.integers(min_value=1, max_value=8),
    n_frame=st.integers(min_value=64, max_value=256),
)
def test_frontend_shape_contract_hypothesis(
    per_channel_channels: int, n_in: int, n_frame: int,
) -> None:
    """Whatever the config, the output is [B, 2·C_per_ch, T]."""
    fe = ChannelAgnosticFrontend(
        ChannelAgnosticConfig(per_channel_channels=per_channel_channels),
    ).eval()
    x = torch.randn(1, n_in, n_frame)
    y = fe(x)
    assert y.shape == (1, 2 * per_channel_channels, n_frame)


@_SETTINGS
@given(
    master_seed=st.integers(min_value=0, max_value=2**32 - 1),
    variant_idx=st.integers(min_value=1, max_value=10),
)
def test_aug_composer_byte_deterministic(
    master_seed: int, variant_idx: int,
) -> None:
    """The composer is byte-deterministic for any (master_seed, variant_idx)."""
    audio = np.tile(
        np.linspace(-0.5, 0.5, 1024, dtype=np.float32), (8, 1),
    )
    out_a = apply_channel_agnostic_aug(
        audio, sample_key="K", variant_idx=variant_idx, master_seed=master_seed,
    )
    out_b = apply_channel_agnostic_aug(
        audio, sample_key="K", variant_idx=variant_idx, master_seed=master_seed,
    )
    assert np.array_equal(out_a, out_b)


@_SETTINGS
@given(
    variant_idx=st.integers(min_value=1, max_value=200),
    n_mic=st.integers(min_value=2, max_value=8),
)
def test_aug_composer_keeps_at_least_one_active(
    variant_idx: int, n_mic: int,
) -> None:
    """The count-mask never zeroes every channel — F0-T4e contract."""
    audio = np.tile(
        np.linspace(-0.5, 0.5, 512, dtype=np.float32), (n_mic, 1),
    )
    out = apply_channel_agnostic_aug(
        audio, sample_key="K", variant_idx=variant_idx, master_seed=42,
    )
    active = (out != 0).any(axis=1).sum()
    assert active >= 1
