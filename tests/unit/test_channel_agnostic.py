"""Layer-1 oracles for ``src.neural.channel_agnostic`` (F0-T4e).

The frontend must guarantee three properties:

* **Shape contract** — input ``[B, n_in, T]``, output ``[B, 2·C_per_ch, T]``.
* **Causality** — output at time ``t`` depends only on inputs ``≤ t``
  (verified by checking that a perturbation at frame ``t`` does not affect
  output frames ``< t``).
* **Permutation-invariance** — for any permutation π of the input channels,
  the aggregated output is identical. *This is the cardinal property F0-T4e
  is built around.*

Plus fail-loud on malformed shapes/configs.
"""
from __future__ import annotations

import pytest
import torch

from neural.channel_agnostic import (
    PER_CHANNEL_CHANNELS,
    PER_CHANNEL_KERNEL,
    ChannelAgnosticConfig,
    ChannelAgnosticFrontend,
    PerChannelEncoder,
    PermInvariantPool,
)


# ----------------------------------------------------------------------------
# PerChannelEncoder
# ----------------------------------------------------------------------------


def test_per_channel_encoder_shape_contract() -> None:
    enc = PerChannelEncoder(per_channel_channels=4, kernel_size=7)
    x = torch.randn(2, 8, 1024)
    y = enc(x)
    assert y.shape == (2, 8, 4, 1024)


def test_per_channel_encoder_weight_sharing() -> None:
    """The same kernel is applied to every channel. We verify by feeding the
    same signal in two different channels and checking the per-channel
    output matches exactly."""
    torch.manual_seed(0)
    enc = PerChannelEncoder(per_channel_channels=4, kernel_size=7).eval()
    signal = torch.randn(1, 1, 512)
    # Build [1, 3, 512] where channel 0 and 2 share the same signal,
    # channel 1 is zero.
    x = torch.cat([signal, torch.zeros(1, 1, 512), signal], dim=1)
    y = enc(x)  # [1, 3, 4, 512]
    assert torch.allclose(y[0, 0], y[0, 2], atol=1e-6), \
        "Same input on different channels must produce identical output."


def test_per_channel_encoder_causality() -> None:
    """Output at frame t must not change when input frames > t are perturbed."""
    torch.manual_seed(1)
    enc = PerChannelEncoder(per_channel_channels=4, kernel_size=7).eval()
    x = torch.randn(1, 2, 256)
    y_ref = enc(x)
    # Perturb the second half of the input.
    x_perturbed = x.clone()
    x_perturbed[..., 128:] += 100.0
    y_perturbed = enc(x_perturbed)
    # First half must be identical (causality).
    assert torch.allclose(y_ref[..., :128], y_perturbed[..., :128], atol=1e-5)


def test_per_channel_encoder_fail_loud_on_2d_input() -> None:
    enc = PerChannelEncoder()
    with pytest.raises(ValueError, match="expects"):
        enc(torch.randn(8, 256))


def test_per_channel_encoder_fail_loud_on_invalid_config() -> None:
    with pytest.raises(ValueError, match="per_channel_channels"):
        PerChannelEncoder(per_channel_channels=0)
    with pytest.raises(ValueError, match="kernel_size"):
        PerChannelEncoder(kernel_size=0)


# ----------------------------------------------------------------------------
# PermInvariantPool
# ----------------------------------------------------------------------------


def test_perm_invariant_pool_shape_contract() -> None:
    pool = PermInvariantPool()
    x = torch.randn(2, 8, 4, 1024)
    y = pool(x)
    assert y.shape == (2, 8, 1024)  # 2 × C_per_ch = 8


def test_perm_invariant_pool_invariance_strict() -> None:
    """The cardinal property: identical output for any input permutation."""
    pool = PermInvariantPool()
    x = torch.randn(2, 8, 4, 1024)
    y_ref = pool(x)
    for _ in range(5):
        perm = torch.randperm(8)
        x_perm = x[:, perm, :, :]
        y_perm = pool(x_perm)
        assert torch.allclose(y_ref, y_perm, atol=1e-6), \
            "PermInvariantPool must be invariant to channel permutation."


def test_perm_invariant_pool_zero_handling() -> None:
    """All-zero input must produce all-zero output (no NaN, no Inf)."""
    pool = PermInvariantPool()
    x = torch.zeros(1, 8, 4, 256)
    y = pool(x)
    assert torch.isfinite(y).all()
    assert (y == 0).all()


def test_perm_invariant_pool_fail_loud_on_3d_input() -> None:
    pool = PermInvariantPool()
    with pytest.raises(ValueError, match="expects"):
        pool(torch.randn(8, 4, 256))


# ----------------------------------------------------------------------------
# ChannelAgnosticFrontend (composed)
# ----------------------------------------------------------------------------


def test_frontend_shape_contract_defaults() -> None:
    fe = ChannelAgnosticFrontend().eval()
    x = torch.randn(2, 8, 1024)
    y = fe(x)
    assert y.shape == (2, 8, 1024)  # default 2 × 4 = 8
    assert fe.output_channels == 8


def test_frontend_shape_contract_wider() -> None:
    fe = ChannelAgnosticFrontend(
        ChannelAgnosticConfig(per_channel_channels=8),
    ).eval()
    x = torch.randn(2, 8, 512)
    y = fe(x)
    assert y.shape == (2, 16, 512)
    assert fe.output_channels == 16


def test_frontend_permutation_invariance_end_to_end() -> None:
    """End-to-end test: arbitrary input + arbitrary permutation = same output.

    This is the proof that the *whole frontend* (not just the pool) preserves
    permutation invariance, because the per-channel encoder has shared
    weights.
    """
    torch.manual_seed(2026)
    fe = ChannelAgnosticFrontend().eval()
    x = torch.randn(3, 8, 2048)
    y_ref = fe(x)
    for seed in range(5):
        g = torch.Generator().manual_seed(seed)
        perm = torch.randperm(8, generator=g)
        x_perm = x[:, perm, :]
        y_perm = fe(x_perm)
        # The output should be byte-identical up to floating-point error.
        assert torch.allclose(y_ref, y_perm, atol=1e-5), \
            f"Frontend not permutation-invariant under perm={perm.tolist()}"


def test_frontend_variable_channel_count() -> None:
    """The frontend processes any number of input channels (≥1)."""
    fe = ChannelAgnosticFrontend().eval()
    # n_in = 1 (mono).
    y = fe(torch.randn(1, 1, 256))
    assert y.shape == (1, 8, 256)
    # n_in = 3 (kick + snare + 1 OH).
    y = fe(torch.randn(1, 3, 256))
    assert y.shape == (1, 8, 256)
    # n_in = 8 (full multitrack).
    y = fe(torch.randn(1, 8, 256))
    assert y.shape == (1, 8, 256)


def test_frontend_fail_loud_on_2d_input() -> None:
    fe = ChannelAgnosticFrontend()
    with pytest.raises(ValueError, match="expects"):
        fe(torch.randn(8, 256))


def test_frontend_zero_channels_dont_perturb() -> None:
    """Zero-filled channels (user routed fewer than 8 mics) should reduce
    mean but not poison max — verifies graceful degradation."""
    fe = ChannelAgnosticFrontend().eval()
    torch.manual_seed(0)
    x_full = torch.randn(1, 8, 256)
    # Zero out the last 6 channels (user wired only 2 mics into slots 0/1).
    x_partial = x_full.clone()
    x_partial[:, 2:, :] = 0.0
    y_full = fe(x_full)
    y_partial = fe(x_partial)
    # Outputs differ (different content), but no NaN/Inf.
    assert torch.isfinite(y_partial).all()
    assert not torch.allclose(y_full, y_partial)


def test_frontend_config_aggregated_channels_property() -> None:
    cfg = ChannelAgnosticConfig(per_channel_channels=6)
    assert cfg.aggregated_channels == 12


def test_module_constants_exposed() -> None:
    assert PER_CHANNEL_CHANNELS == 4
    assert PER_CHANNEL_KERNEL == 7
