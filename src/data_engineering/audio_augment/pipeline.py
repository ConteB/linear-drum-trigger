"""Audio augmentation pipeline composer + seed derivation.

The composer chains the three MVP voices (``noise_floor → gain →
mic_balance``) using a single per-sample seed derived from
``sha256(master ‖ sample_key ‖ variant_idx)``. Variant 0 is the *identity*
branch (no augmentation), mirroring the MIDI jitter pipeline of F0-T16-pre.

Guards (F0-T15-post §4.5):

* **R2** silence-guard — if the post-augmentation peak < 1e-4, abort.
* **R3** clipping-guard — if peak > 1.0, raise (caller should retry with a
  lower noise / gain budget).
"""
from __future__ import annotations

import hashlib

import numpy as np

from .voices import (
    apply_gain_perturbation,
    apply_mic_balance_jitter,
    apply_noise_floor,
)

#: R2 floor: a Gold sample must keep peak ≥ 1e-4 after augmentation.
_SILENCE_FLOOR: float = 1e-4

#: R3 ceiling: a Gold sample's peak must stay ≤ 1.0.
_CLIPPING_CEILING: float = 1.0


class AudioAugmentError(ValueError):
    """Raised when the pipeline produces an out-of-bounds sample."""


def derive_audio_seed(
    master_seed: int, sample_key: str, variant_idx: int
) -> int:
    """Bit-deterministic seed derivation, mirrors :func:`midi_augment.seed`.

    ``sha256(master_seed_bytes ‖ sample_key.encode() ‖ variant_idx_bytes)``,
    take the first 8 bytes as a big-endian uint64.
    """
    if variant_idx < 0:
        raise ValueError(f"variant_idx must be ≥ 0, got {variant_idx}")
    h = hashlib.sha256()
    h.update(master_seed.to_bytes(8, "big", signed=False))
    h.update(sample_key.encode("utf-8"))
    h.update(variant_idx.to_bytes(4, "big", signed=False))
    return int.from_bytes(h.digest()[:8], "big", signed=False)


def apply_audio_augmentation(
    audio: np.ndarray,
    *,
    sample_key: str,
    variant_idx: int,
    master_seed: int,
    noise_db_fs: float = -50.0,
    gain_range_db: tuple[float, float] = (-6.0, 6.0),
    mic_balance_range_db: tuple[float, float] = (-3.0, 3.0),
) -> np.ndarray:
    """Run the full ``noise_floor → gain → mic_balance`` pipeline.

    Variant 0 is the *baseline* (identity transform). Variants ≥ 1 apply
    the pipeline with seed ``derive_audio_seed(master_seed, sample_key,
    variant_idx)``.

    Args:
        audio: ``[n_mic, n_sample]`` audio.
        sample_key: barcode key — drives the per-sample seed.
        variant_idx: 0 → identity; ≥ 1 → augmented variant.
        master_seed: run-level seed.
        noise_db_fs: dBFS for the noise floor voice.
        gain_range_db: dB bounds for the global gain voice.
        mic_balance_range_db: dB bounds for the per-channel jitter voice.

    Returns:
        Augmented audio (or input unchanged for variant 0).

    Raises:
        AudioAugmentError: if R2 (silence) or R3 (clipping) is violated.
    """
    if variant_idx == 0:
        return audio
    seed = derive_audio_seed(master_seed, sample_key, variant_idx)
    rng = np.random.default_rng(seed)
    out = audio
    out = apply_noise_floor(out, noise_db_fs=noise_db_fs, rng=rng)
    out = apply_gain_perturbation(out, range_db=gain_range_db, rng=rng)
    out = apply_mic_balance_jitter(out, range_db=mic_balance_range_db, rng=rng)

    peak = float(np.abs(out.astype(np.float32)).max())
    if peak < _SILENCE_FLOOR:
        raise AudioAugmentError(
            f"pipeline produced silent audio (peak={peak:.2e} < "
            f"{_SILENCE_FLOOR:.0e}) for {sample_key!r} variant {variant_idx}"
        )
    if peak > _CLIPPING_CEILING:
        raise AudioAugmentError(
            f"pipeline produced clipped audio (peak={peak:.3f} > "
            f"{_CLIPPING_CEILING:.1f}) for {sample_key!r} variant {variant_idx}"
        )
    return out
