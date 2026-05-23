"""Layer-1 oracles for ``audio_augment`` (F0-T16-post MVP).

The three voices + composer must be:

* **Deterministic** — same seed ⇒ byte-identical output.
* **Non-saturating** — peak ≤ 1.0 with default params (R3).
* **Non-silencing** — peak ≥ 1e-4 (R2).
* **Fail-loud** — invalid shapes / ranges / variant_idx raise.
"""
from __future__ import annotations

import numpy as np
import pytest

from data_engineering.audio_augment import (
    AudioAugmentError,
    apply_audio_augmentation,
    apply_gain_perturbation,
    apply_mic_balance_jitter,
    apply_noise_floor,
    apply_peak_normalize,
    derive_audio_seed,
)


def _make_audio(n_mic: int = 8, n_sample: int = 4096, peak: float = 0.5) -> np.ndarray:
    """Synthesise [n_mic, n_sample] sine-mix audio at the target peak."""
    t = np.arange(n_sample) / 4096.0
    out = np.zeros((n_mic, n_sample), dtype=np.float32)
    for ch in range(n_mic):
        freq = 5 + ch  # one harmonic per channel
        out[ch] = peak * np.sin(2 * np.pi * freq * t).astype(np.float32)
    return out


# ----------------------------------------------------------------------------
# derive_audio_seed
# ----------------------------------------------------------------------------


def test_seed_deterministic() -> None:
    a = derive_audio_seed(42, "LOCAL_RND001", 1)
    b = derive_audio_seed(42, "LOCAL_RND001", 1)
    assert a == b


def test_seed_differs_for_different_inputs() -> None:
    a = derive_audio_seed(42, "LOCAL_RND001", 1)
    b = derive_audio_seed(42, "LOCAL_RND001", 2)
    c = derive_audio_seed(42, "LOCAL_RND002", 1)
    d = derive_audio_seed(43, "LOCAL_RND001", 1)
    assert len({a, b, c, d}) == 4


def test_seed_is_uint64() -> None:
    s = derive_audio_seed(0, "x", 0)
    assert 0 <= s < (1 << 64)


def test_seed_rejects_negative_variant() -> None:
    with pytest.raises(ValueError, match="variant_idx must be ≥ 0"):
        derive_audio_seed(42, "x", -1)


# ----------------------------------------------------------------------------
# apply_noise_floor
# ----------------------------------------------------------------------------


def test_noise_floor_deterministic() -> None:
    audio = _make_audio()
    rng_a = np.random.default_rng(1)
    rng_b = np.random.default_rng(1)
    a = apply_noise_floor(audio, noise_db_fs=-40.0, rng=rng_a)
    b = apply_noise_floor(audio, noise_db_fs=-40.0, rng=rng_b)
    np.testing.assert_array_equal(a, b)


def test_noise_floor_adds_energy() -> None:
    audio = _make_audio()
    rng = np.random.default_rng(1)
    out = apply_noise_floor(audio, noise_db_fs=-30.0, rng=rng)
    # Output should not equal input (noise was added).
    assert not np.array_equal(audio, out)


def test_noise_floor_silence_input_gets_noise() -> None:
    """Even on a silent input the noise floor should leave the sample audible."""
    audio = np.zeros((4, 1024), dtype=np.float32)
    rng = np.random.default_rng(1)
    out = apply_noise_floor(audio, noise_db_fs=-30.0, rng=rng)
    peak = float(np.abs(out).max())
    assert peak > 0.001, f"noise too quiet: peak={peak}"


def test_noise_floor_rejects_positive_db() -> None:
    audio = _make_audio()
    with pytest.raises(ValueError, match="noise_db_fs must be < 0"):
        apply_noise_floor(audio, noise_db_fs=0.0, rng=np.random.default_rng(1))


def test_noise_floor_rejects_1d_audio() -> None:
    audio = np.zeros(1024, dtype=np.float32)
    with pytest.raises(ValueError, match="must be 2-D"):
        apply_noise_floor(audio, rng=np.random.default_rng(1))


# ----------------------------------------------------------------------------
# apply_gain_perturbation
# ----------------------------------------------------------------------------


def test_gain_perturbation_deterministic() -> None:
    audio = _make_audio()
    rng_a = np.random.default_rng(1)
    rng_b = np.random.default_rng(1)
    a = apply_gain_perturbation(audio, rng=rng_a)
    b = apply_gain_perturbation(audio, rng=rng_b)
    np.testing.assert_array_equal(a, b)


def test_gain_perturbation_scales_uniformly() -> None:
    """The same dB factor must apply to every channel."""
    audio = _make_audio(peak=0.3)
    rng = np.random.default_rng(1)
    out = apply_gain_perturbation(audio, rng=rng, range_db=(-6.0, 6.0))
    # Ratio out/audio should be the same scalar for every channel (where
    # audio is not zero).
    nz = np.abs(audio) > 1e-6
    ratios = out[nz] / audio[nz]
    # Single dB factor → narrow spread.
    assert float(ratios.max() - ratios.min()) < 1e-3, "gain not uniform per channel"


def test_gain_perturbation_within_db_range() -> None:
    """With range_db=(-6, 6) the scale factor stays in [0.501, 1.995]."""
    audio = _make_audio(peak=0.5)
    seen_factors = []
    for seed in range(20):
        rng = np.random.default_rng(seed)
        out = apply_gain_perturbation(audio, rng=rng, range_db=(-6.0, 6.0))
        factor = float(out[0, 100] / audio[0, 100])
        seen_factors.append(factor)
    assert min(seen_factors) >= 0.501
    assert max(seen_factors) <= 1.995


def test_gain_perturbation_rejects_inverted_range() -> None:
    audio = _make_audio()
    with pytest.raises(ValueError, match="low ≤ high"):
        apply_gain_perturbation(audio, range_db=(5.0, -5.0),
                                 rng=np.random.default_rng(1))


# ----------------------------------------------------------------------------
# apply_mic_balance_jitter
# ----------------------------------------------------------------------------


def test_mic_balance_deterministic() -> None:
    audio = _make_audio()
    rng_a = np.random.default_rng(1)
    rng_b = np.random.default_rng(1)
    a = apply_mic_balance_jitter(audio, rng=rng_a)
    b = apply_mic_balance_jitter(audio, rng=rng_b)
    np.testing.assert_array_equal(a, b)


def test_mic_balance_jitter_independent_channels() -> None:
    """Each channel must get its OWN gain factor — the breaks-mix-balance
    intent of F0-T15-post §4.4."""
    audio = _make_audio(n_mic=8, peak=0.3)
    rng = np.random.default_rng(1)
    out = apply_mic_balance_jitter(audio, rng=rng, range_db=(-3.0, 3.0))
    # Compute per-channel scaling factor (sample 100 of each ch as a probe).
    factors = [out[ch, 100] / audio[ch, 100] for ch in range(8)]
    # If the same factor applied to all channels, the spread would be ~0;
    # independent draws should give a much wider spread.
    spread = max(factors) - min(factors)
    assert spread > 0.05, f"per-channel factors too similar: {factors}"


def test_mic_balance_rejects_1d() -> None:
    audio = np.zeros(1024, dtype=np.float32)
    with pytest.raises(ValueError, match="must be 2-D"):
        apply_mic_balance_jitter(audio, rng=np.random.default_rng(1))


# ----------------------------------------------------------------------------
# Pipeline composer
# ----------------------------------------------------------------------------


def test_pipeline_variant_0_is_identity() -> None:
    audio = _make_audio()
    out = apply_audio_augmentation(audio, sample_key="X", variant_idx=0,
                                     master_seed=42)
    assert out is audio  # identity by reference


def test_pipeline_variant_1_changes_audio() -> None:
    audio = _make_audio()
    out = apply_audio_augmentation(audio, sample_key="X", variant_idx=1,
                                     master_seed=42)
    assert not np.array_equal(audio, out)


def test_pipeline_deterministic_per_seed() -> None:
    audio = _make_audio()
    a = apply_audio_augmentation(audio, sample_key="X", variant_idx=1,
                                  master_seed=42)
    b = apply_audio_augmentation(audio, sample_key="X", variant_idx=1,
                                  master_seed=42)
    np.testing.assert_array_equal(a, b)


def test_pipeline_different_variants_differ() -> None:
    audio = _make_audio()
    a = apply_audio_augmentation(audio, sample_key="X", variant_idx=1,
                                  master_seed=42)
    b = apply_audio_augmentation(audio, sample_key="X", variant_idx=2,
                                  master_seed=42)
    assert not np.array_equal(a, b)


def test_pipeline_clipping_guard() -> None:
    """Audio at peak 0.9 with +6 dB gain (×2) should trip the R3 ceiling."""
    audio = _make_audio(peak=0.9)
    # Force a gain near +6 dB by clamping the range.
    with pytest.raises(AudioAugmentError, match="clipped"):
        apply_audio_augmentation(
            audio, sample_key="X", variant_idx=1, master_seed=42,
            gain_range_db=(6.0, 6.0),
        )


def test_pipeline_peak_stays_in_bounds_for_default_params() -> None:
    """The default params (noise -50 dB, gain ±6, mic ±3) should keep
    audio peak < 1.0 for a typical 0.4-peak input."""
    audio = _make_audio(peak=0.4)
    for variant in (1, 2, 3, 4, 5):
        out = apply_audio_augmentation(audio, sample_key="X",
                                         variant_idx=variant, master_seed=42)
        peak = float(np.abs(out).max())
        assert peak <= 1.0, f"variant {variant}: peak {peak}"


def test_pipeline_preserves_shape() -> None:
    audio = _make_audio(n_mic=8, n_sample=2048)
    out = apply_audio_augmentation(audio, sample_key="X", variant_idx=1,
                                     master_seed=42)
    assert out.shape == audio.shape


# ----------------------------------------------------------------------------
# apply_peak_normalize + per-voice toggles
# ----------------------------------------------------------------------------


def test_peak_normalize_scales_to_target() -> None:
    audio = _make_audio(peak=0.5)
    out = apply_peak_normalize(audio, target_peak=0.7)
    peak = float(np.abs(out).max())
    assert abs(peak - 0.7) < 0.01, f"peak={peak} should be ≈ 0.7"


def test_peak_normalize_silent_unchanged() -> None:
    audio = np.zeros((4, 1024), dtype=np.float32)
    out = apply_peak_normalize(audio, target_peak=0.7)
    np.testing.assert_array_equal(out, audio)


def test_peak_normalize_rejects_invalid_target() -> None:
    audio = _make_audio()
    with pytest.raises(ValueError, match="target_peak must be in"):
        apply_peak_normalize(audio, target_peak=0.0)
    with pytest.raises(ValueError, match="target_peak must be in"):
        apply_peak_normalize(audio, target_peak=1.5)


def test_pipeline_pre_normalize_recovers_loud_input() -> None:
    """An input that would have clipped without pre-normalize (peak 0.9 + 3 dB)
    now passes because the input is rescaled to 0.5 first."""
    audio = _make_audio(peak=0.9)
    # Without pre-normalize → fail R3; with default pre_normalize_peak=0.5 → pass.
    out = apply_audio_augmentation(
        audio, sample_key="X", variant_idx=1, master_seed=42,
        gain_range_db=(3.0, 3.0),  # force +3 dB; pre-normalize 0.5 → peak 0.7
        mic_balance_range_db=(-2.0, 2.0),
    )
    peak = float(np.abs(out).max())
    assert peak <= 1.0, f"peak {peak} should stay under 1.0"


def test_pipeline_pre_normalize_can_be_disabled() -> None:
    """Setting pre_normalize_peak=None restores the legacy behaviour where
    loud inputs trip R3."""
    audio = _make_audio(peak=0.95)
    with pytest.raises(AudioAugmentError, match="clipped"):
        apply_audio_augmentation(
            audio, sample_key="X", variant_idx=1, master_seed=42,
            gain_range_db=(6.0, 6.0),
            pre_normalize_peak=None,
        )


def test_pipeline_per_voice_toggles_isolate_voices() -> None:
    """Disabling all voices → the pipeline is the pre-normalize alone (which
    is deterministic and produces non-empty output)."""
    audio = _make_audio(peak=0.4)
    out = apply_audio_augmentation(
        audio, sample_key="X", variant_idx=1, master_seed=42,
        enable_noise=False, enable_gain=False, enable_mic_balance=False,
    )
    # With only pre_normalize the output is a deterministic rescale to the
    # pipeline's default pre_normalize_peak (0.5).
    expected = apply_peak_normalize(audio, target_peak=0.5)
    np.testing.assert_array_equal(out, expected)


def test_pipeline_only_noise_voice() -> None:
    audio = _make_audio(peak=0.4)
    noise_only = apply_audio_augmentation(
        audio, sample_key="X", variant_idx=1, master_seed=42,
        enable_noise=True, enable_gain=False, enable_mic_balance=False,
        pre_normalize_peak=None,
    )
    # Differs from input (noise added) but per-channel scale ratio is 1.0
    # because no gain/mic_balance was applied.
    assert not np.array_equal(audio, noise_only)
    # The first channel of (noise_only - audio) should have non-zero values.
    diff = noise_only - audio
    assert float(np.abs(diff).max()) > 0
