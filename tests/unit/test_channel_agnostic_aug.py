"""Layer-1 oracles for ``channel_agnostic_aug`` (F0-T4e component A).

Three voices + composer + seed must be:

* **Deterministic** — same seed ⇒ byte-identical output.
* **Shape-preserving** — output shape == input shape.
* **At least 1 active channel** — count masking never produces an all-zero
  audio (would poison the F0-T4d ChannelNorm peak).
* **Fail-loud** — invalid inputs raise.
"""
from __future__ import annotations

import numpy as np
import pytest

from data_engineering.audio_augment import (
    REALISTIC_MIC_CONFIGS,
    ChannelAgnosticAugError,
    apply_channel_agnostic_aug,
    apply_channel_permutation,
    apply_random_count_mask,
    apply_realistic_count_mask,
    derive_channel_agnostic_seed,
    sample_realistic_mic_config,
)


def _make_audio(n_mic: int = 8, n_sample: int = 1024) -> np.ndarray:
    """Distinct per-channel constant audio so permutation is observable."""
    out = np.zeros((n_mic, n_sample), dtype=np.float32)
    for ch in range(n_mic):
        out[ch] = float(ch + 1) * 0.1  # ch 0 = 0.1, ch 1 = 0.2, …
    return out


# ----------------------------------------------------------------------------
# derive_channel_agnostic_seed
# ----------------------------------------------------------------------------


def test_seed_deterministic() -> None:
    a = derive_channel_agnostic_seed(42, "key", 1)
    b = derive_channel_agnostic_seed(42, "key", 1)
    assert a == b


def test_seed_differs_for_different_inputs() -> None:
    a = derive_channel_agnostic_seed(42, "key", 1)
    b = derive_channel_agnostic_seed(42, "key", 2)
    c = derive_channel_agnostic_seed(42, "other", 1)
    d = derive_channel_agnostic_seed(43, "key", 1)
    assert len({a, b, c, d}) == 4


def test_seed_namespace_separate_from_audio_aug() -> None:
    """The channel-agnostic seed namespace is separated by ``|chagn`` suffix
    so the two augmentations don't share entropy with the same key."""
    from data_engineering.audio_augment import derive_audio_seed
    a_audio = derive_audio_seed(42, "key", 1)
    a_chagn = derive_channel_agnostic_seed(42, "key", 1)
    assert a_audio != a_chagn


def test_seed_fail_loud_on_negative_variant() -> None:
    with pytest.raises(ChannelAgnosticAugError, match="variant_idx"):
        derive_channel_agnostic_seed(42, "k", -1)


# ----------------------------------------------------------------------------
# apply_channel_permutation
# ----------------------------------------------------------------------------


def test_permutation_shape_preserved() -> None:
    audio = _make_audio()
    rng = np.random.default_rng(0)
    out = apply_channel_permutation(audio, rng=rng)
    assert out.shape == audio.shape
    assert out.dtype == audio.dtype


def test_permutation_preserves_content_set() -> None:
    """Channel content is just reordered, never modified."""
    audio = _make_audio()
    rng = np.random.default_rng(0)
    out = apply_channel_permutation(audio, rng=rng)
    # The first sample of each channel was a unique constant (0.1, 0.2, …).
    # After permutation, the same set of first-samples appears, possibly reordered.
    assert sorted(out[:, 0].tolist()) == sorted(audio[:, 0].tolist())


def test_permutation_deterministic_under_same_seed() -> None:
    audio = _make_audio()
    out_a = apply_channel_permutation(audio, rng=np.random.default_rng(123))
    out_b = apply_channel_permutation(audio, rng=np.random.default_rng(123))
    assert np.array_equal(out_a, out_b)


def test_permutation_mono_passthrough() -> None:
    audio = _make_audio(n_mic=1)
    rng = np.random.default_rng(0)
    out = apply_channel_permutation(audio, rng=rng)
    assert np.array_equal(out, audio)


def test_permutation_fail_loud_on_1d() -> None:
    with pytest.raises(ChannelAgnosticAugError, match="2-D"):
        apply_channel_permutation(np.zeros(100), rng=np.random.default_rng(0))


# ----------------------------------------------------------------------------
# apply_random_count_mask
# ----------------------------------------------------------------------------


def test_count_mask_keeps_at_least_one_channel() -> None:
    """At least 1 channel must remain non-zero in every realisation."""
    audio = _make_audio()
    for seed in range(50):
        out = apply_random_count_mask(audio, rng=np.random.default_rng(seed))
        active = (out != 0).any(axis=1).sum()
        assert active >= 1, f"seed={seed}: all channels zeroed"


def test_count_mask_deterministic_under_same_seed() -> None:
    audio = _make_audio()
    out_a = apply_random_count_mask(audio, rng=np.random.default_rng(42))
    out_b = apply_random_count_mask(audio, rng=np.random.default_rng(42))
    assert np.array_equal(out_a, out_b)


def test_count_mask_mono_passthrough() -> None:
    audio = _make_audio(n_mic=1)
    out = apply_random_count_mask(audio, rng=np.random.default_rng(0))
    assert np.array_equal(out, audio)


def test_count_mask_max_zero_bound() -> None:
    audio = _make_audio()
    # max_zero=0 → no masking ever.
    for seed in range(20):
        out = apply_random_count_mask(
            audio, rng=np.random.default_rng(seed), max_zero=0,
        )
        assert np.array_equal(out, audio)


def test_count_mask_fail_loud_on_negative_max_zero() -> None:
    with pytest.raises(ChannelAgnosticAugError, match="max_zero"):
        apply_random_count_mask(
            _make_audio(), rng=np.random.default_rng(0), max_zero=-1,
        )


# ----------------------------------------------------------------------------
# sample_realistic_mic_config / apply_realistic_count_mask
# ----------------------------------------------------------------------------


def test_realistic_config_distribution_in_valid_range() -> None:
    rng = np.random.default_rng(0)
    for _ in range(200):
        n_active = sample_realistic_mic_config(rng)
        assert 1 <= n_active <= 8


def test_realistic_config_distribution_probs_sum_to_one() -> None:
    total = sum(p for _, p in REALISTIC_MIC_CONFIGS)
    assert abs(total - 1.0) < 1e-9


def test_realistic_mask_keeps_at_least_one_channel() -> None:
    audio = _make_audio()
    for seed in range(50):
        out = apply_realistic_count_mask(audio, rng=np.random.default_rng(seed))
        active = (out != 0).any(axis=1).sum()
        assert active >= 1


def test_realistic_mask_deterministic() -> None:
    audio = _make_audio()
    out_a = apply_realistic_count_mask(audio, rng=np.random.default_rng(7))
    out_b = apply_realistic_count_mask(audio, rng=np.random.default_rng(7))
    assert np.array_equal(out_a, out_b)


# ----------------------------------------------------------------------------
# apply_channel_agnostic_aug (composer)
# ----------------------------------------------------------------------------


def test_composer_variant_zero_is_identity() -> None:
    audio = _make_audio()
    out = apply_channel_agnostic_aug(
        audio, sample_key="k", variant_idx=0, master_seed=42,
    )
    assert np.array_equal(out, audio)


def test_composer_variant_one_is_deterministic() -> None:
    audio = _make_audio()
    out_a = apply_channel_agnostic_aug(
        audio, sample_key="k", variant_idx=1, master_seed=42,
    )
    out_b = apply_channel_agnostic_aug(
        audio, sample_key="k", variant_idx=1, master_seed=42,
    )
    assert np.array_equal(out_a, out_b)


def test_composer_different_keys_produce_different_outputs() -> None:
    """Same variant + master, different sample_key → different seeds → different outputs."""
    audio = _make_audio()
    out_a = apply_channel_agnostic_aug(
        audio, sample_key="key_A", variant_idx=1, master_seed=42,
    )
    out_b = apply_channel_agnostic_aug(
        audio, sample_key="key_B", variant_idx=1, master_seed=42,
    )
    # Statistically virtually impossible to coincide unless seeds match.
    assert not np.array_equal(out_a, out_b)


def test_composer_preserves_shape() -> None:
    audio = _make_audio()
    out = apply_channel_agnostic_aug(
        audio, sample_key="k", variant_idx=1, master_seed=42,
    )
    assert out.shape == audio.shape


def test_composer_at_least_one_channel_active() -> None:
    audio = _make_audio()
    for variant in range(1, 100):
        out = apply_channel_agnostic_aug(
            audio, sample_key="k", variant_idx=variant, master_seed=42,
        )
        active = (out != 0).any(axis=1).sum()
        assert active >= 1, f"variant={variant}: all channels zeroed"


def test_composer_toggle_permutation_off_keeps_order() -> None:
    audio = _make_audio()
    out = apply_channel_agnostic_aug(
        audio, sample_key="k", variant_idx=1, master_seed=42,
        enable_permutation=False, enable_count_mask=False,
    )
    # Both toggles off → identity (regardless of variant_idx).
    assert np.array_equal(out, audio)


def test_composer_fail_loud_on_invalid_audio() -> None:
    with pytest.raises(ChannelAgnosticAugError, match="2-D"):
        apply_channel_agnostic_aug(
            np.zeros(100), sample_key="k", variant_idx=1, master_seed=42,
        )


def test_composer_fail_loud_on_negative_variant() -> None:
    with pytest.raises(ChannelAgnosticAugError, match="variant_idx"):
        apply_channel_agnostic_aug(
            _make_audio(), sample_key="k", variant_idx=-1, master_seed=42,
        )
