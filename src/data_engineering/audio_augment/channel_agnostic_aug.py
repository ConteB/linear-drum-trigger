"""Channel-agnostic data augmentation — F0-T4e §4.4 component A.

Three NumPy voices that *force* the network to be input-agnostic during
training. They pair with the architectural component
(:mod:`src.neural.channel_agnostic`) which guarantees permutation-invariance
by design; the augmentation accelerates convergence and covers degenerate
edge cases (mono, stereo, missing mics).

Voices:

* :func:`apply_channel_permutation` — random permutation of the 8 channel
  slots. With a permutation-invariant pool downstream the output is
  unchanged, but the augmentation forces the upstream feature extraction
  (and any non-invariant layer that might be added later) to not memorise a
  per-slot semantic.
* :func:`apply_random_count_mask` — zero out a uniform-random number of
  channels in ``[0, n_mic-1]``. Simulates the user routing 1-7 channels
  instead of all 8.
* :func:`sample_realistic_mic_config` — sampled mic configuration from the
  empirical distribution of plausible user setups (mono 25 %, stereo-OH
  25 %, 4-ch 20 %, 7-ch multitrack 15 %, full 8-ch 15 %).

Composer :func:`apply_channel_agnostic_aug` chains the three with a
per-sample seed derived from
``sha256(master_seed ‖ sample_key ‖ variant_idx)``.

Determinism: every function takes a ``np.random.Generator``; same seed
produces byte-identical output. Variant 0 is the identity branch (no aug),
mirroring the MVP audio_aug composer.

Audio layout: ``np.ndarray[n_mic, n_sample]`` (F0-T2a §3.2). Channel mask
zeros out a *whole channel* (all samples); permutation reorders along
``axis=0``.
"""
from __future__ import annotations

import hashlib

import numpy as np

#: Empirical distribution of realistic mic configurations.
#:
#: Drawn from F0-T4e §3.1 (UX/UI Impact) reasoning — the user routes
#: whatever they have to whatever slots are convenient. The distribution
#: covers degenerate setups (mono, stereo) more than they appear in our
#: training data so the network sees them often enough to be robust.
REALISTIC_MIC_CONFIGS: tuple[tuple[int, float], ...] = (
    (1, 0.25),   # mono close mic
    (2, 0.25),   # stereo OH
    (4, 0.20),   # kick + snare + stereo OH
    (7, 0.15),   # full multitrack minus 1 room
    (8, 0.15),   # full multitrack
)


class ChannelAgnosticAugError(ValueError):
    """Raised on contract violations (empty audio, invalid n_active)."""


def _check_audio(audio: np.ndarray, label: str) -> None:
    if audio.ndim != 2:
        raise ChannelAgnosticAugError(
            f"{label}: audio must be 2-D [n_mic, n_sample], got shape {audio.shape}"
        )
    if audio.size == 0:
        raise ChannelAgnosticAugError(f"{label}: audio is empty")


def derive_channel_agnostic_seed(
    master_seed: int, sample_key: str, variant_idx: int
) -> int:
    """Seed derivation — same recipe as :func:`derive_audio_seed`.

    ``sha256(master_seed_bytes ‖ sample_key.encode() ‖ variant_idx_bytes)``,
    first 8 bytes as big-endian uint64.

    The composer of :mod:`src.data_engineering.audio_augment.pipeline` uses
    the same family of seeds; we use a *separate namespace* by suffixing the
    sample key with ``"|chagn"`` so the two augmentations don't share entropy.
    """
    if variant_idx < 0:
        raise ChannelAgnosticAugError(
            f"variant_idx must be ≥ 0, got {variant_idx}"
        )
    namespaced_key = sample_key + "|chagn"
    h = hashlib.sha256()
    h.update(master_seed.to_bytes(8, "big", signed=False))
    h.update(namespaced_key.encode("utf-8"))
    h.update(variant_idx.to_bytes(4, "big", signed=False))
    return int.from_bytes(h.digest()[:8], "big", signed=False)


def apply_channel_permutation(
    audio: np.ndarray, *, rng: np.random.Generator
) -> np.ndarray:
    """Random permutation of channels (axis 0).

    Args:
        audio: ``[n_mic, n_sample]``.
        rng: caller-managed Generator.

    Returns:
        Permuted audio, same shape & dtype. With n_mic ≤ 1 the input is
        returned unchanged (no permutation possible).
    """
    _check_audio(audio, "apply_channel_permutation")
    n_mic = audio.shape[0]
    if n_mic <= 1:
        return audio
    perm = rng.permutation(n_mic)
    out: np.ndarray = audio[perm].copy()
    return out


def apply_random_count_mask(
    audio: np.ndarray,
    *,
    rng: np.random.Generator,
    max_zero: int | None = None,
) -> np.ndarray:
    """Zero out a uniform-random number of channels in ``[0, max_zero]``.

    Simulates the user wiring N < n_mic channels and leaving the rest as
    silence. Always keeps **at least 1** non-zero channel — fully-zero
    audio would cause the F0-T4e PermInvariantPool to emit a degenerate
    all-zero feature map and the F0-T4d ChannelNorm to misbehave (peak=0).

    Args:
        audio: ``[n_mic, n_sample]``.
        rng: caller-managed Generator.
        max_zero: max number of channels to zero (default ``n_mic - 1`` so
            at least 1 stays active).

    Returns:
        Audio with a random subset of channels zeroed out.
    """
    _check_audio(audio, "apply_random_count_mask")
    n_mic = audio.shape[0]
    if n_mic <= 1:
        return audio
    cap = n_mic - 1 if max_zero is None else min(max_zero, n_mic - 1)
    if cap < 0:
        raise ChannelAgnosticAugError(
            f"max_zero must be ≥ 0, got {max_zero}"
        )
    n_to_zero = int(rng.integers(0, cap + 1))  # uniform [0, cap]
    if n_to_zero == 0:
        return audio
    targets = rng.choice(n_mic, size=n_to_zero, replace=False)
    out: np.ndarray = audio.copy()
    out[targets] = 0.0
    return out


def sample_realistic_mic_config(
    rng: np.random.Generator,
) -> int:
    """Sample ``n_active`` channels from the empirical distribution.

    Returns the number of *active* channels (the rest are zeroed).
    Distribution: see :data:`REALISTIC_MIC_CONFIGS`.
    """
    n_actives = [n for n, _ in REALISTIC_MIC_CONFIGS]
    probs = np.array([p for _, p in REALISTIC_MIC_CONFIGS], dtype=np.float64)
    probs = probs / probs.sum()  # safety: renormalize if floats drift
    idx = int(rng.choice(len(n_actives), p=probs))
    return n_actives[idx]


def apply_realistic_count_mask(
    audio: np.ndarray, *, rng: np.random.Generator
) -> np.ndarray:
    """Zero out (n_mic − n_active) random channels per :data:`REALISTIC_MIC_CONFIGS`.

    Higher-priority alternative to :func:`apply_random_count_mask` — uses
    the realistic distribution rather than uniform. Default in the composer.
    """
    _check_audio(audio, "apply_realistic_count_mask")
    n_mic = audio.shape[0]
    if n_mic <= 1:
        return audio
    n_active = sample_realistic_mic_config(rng)
    n_active = min(n_active, n_mic)
    n_to_zero = n_mic - n_active
    if n_to_zero == 0:
        return audio
    targets = rng.choice(n_mic, size=n_to_zero, replace=False)
    out: np.ndarray = audio.copy()
    out[targets] = 0.0
    return out


def apply_channel_agnostic_aug(
    audio: np.ndarray,
    *,
    sample_key: str,
    variant_idx: int,
    master_seed: int,
    enable_permutation: bool = True,
    enable_count_mask: bool = True,
    use_realistic_distribution: bool = True,
) -> np.ndarray:
    """Compose channel permutation + count masking.

    Variant 0 is the identity branch (no aug). For variants ≥ 1:

    1. Random channel permutation (axis 0).
    2. Count masking — either realistic distribution (default) or uniform.

    Args:
        audio: ``[n_mic, n_sample]`` audio.
        sample_key: barcode/key — drives the per-sample seed.
        variant_idx: 0 → identity; ≥ 1 → augmented.
        master_seed: run-level seed.
        enable_permutation: toggle channel permutation.
        enable_count_mask: toggle count masking.
        use_realistic_distribution: if True, use
            :func:`apply_realistic_count_mask`; otherwise uniform via
            :func:`apply_random_count_mask`.

    Returns:
        Augmented audio (or input unchanged for variant 0).
    """
    _check_audio(audio, "apply_channel_agnostic_aug")
    if variant_idx == 0:
        return audio
    seed = derive_channel_agnostic_seed(master_seed, sample_key, variant_idx)
    rng = np.random.default_rng(seed)
    out = audio
    if enable_permutation:
        out = apply_channel_permutation(out, rng=rng)
    if enable_count_mask:
        if use_realistic_distribution:
            out = apply_realistic_count_mask(out, rng=rng)
        else:
            out = apply_random_count_mask(out, rng=rng)
    return out


__all__ = [
    "ChannelAgnosticAugError",
    "REALISTIC_MIC_CONFIGS",
    "apply_channel_agnostic_aug",
    "apply_channel_permutation",
    "apply_random_count_mask",
    "apply_realistic_count_mask",
    "derive_channel_agnostic_seed",
    "sample_realistic_mic_config",
]
