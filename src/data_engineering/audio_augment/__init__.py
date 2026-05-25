"""OP-NEUROTRIGGER — Audio augmentation pipeline (F0-T16-post MVP).

The R&D-grade subset of the F0-T15-post spec (audio augmentation post-render).
Three deterministic voices, pure-NumPy (no external audio DSP deps for the
MVP — pedalboard / Demucs land in a follow-up):

* :func:`apply_noise_floor` — pink noise additive at ``noise_db_fs``.
* :func:`apply_gain_perturbation` — global gain shift ±range_db.
* :func:`apply_mic_balance_jitter` — per-channel gain offset, breaks the
  rigid "balanced kit" assumption (DOSSIER §3.6 — agnosticità).

Plus the composer:

* :func:`apply_audio_augmentation` — pipeline of the three voices with a
  bit-deterministic ``(master_seed, sample_key, variant_idx)`` derivation.

Doctrine (F0-T15-post §4.5 R1-R3 — copied here as MVP guards):

* **R1** — no time-stretching (timing labels stay valid).
* **R2** — augmentation must not silence a sample (peak ≥ 1e-4 after).
* **R3** — peak after augmentation ≤ 1.0 (no clipping).
"""
from __future__ import annotations

from .pipeline import (
    AudioAugmentError,
    apply_audio_augmentation,
    derive_audio_seed,
)
from .voices import (
    apply_channel_mask,
    apply_gain_perturbation,
    apply_mic_balance_jitter,
    apply_noise_floor,
    apply_peak_normalize,
)

__all__ = [
    "AudioAugmentError",
    "apply_audio_augmentation",
    "apply_channel_mask",
    "apply_gain_perturbation",
    "apply_mic_balance_jitter",
    "apply_noise_floor",
    "apply_peak_normalize",
    "derive_audio_seed",
]
