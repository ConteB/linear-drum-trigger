"""Audio augmentation voices — pure-NumPy implementations.

Three deterministic voices for the F0-T16-post MVP (see ``__init__.py``).
Every function is pure (no global state): the same input + rng state
produces the same output, byte-for-byte.

Audio layout: ``np.ndarray[n_mic, n_sample]`` (matches the Gold contract
F0-T2a §3.2).
"""
from __future__ import annotations

import numpy as np

#: Floor below which a sample is considered "silent" (R2 guard).
_SILENCE_FLOOR: float = 1e-4

#: Pink-noise generator constants — sample-rate independent.
_PINK_FILTER_COEFFS: tuple[float, ...] = (0.0555179, 0.0750759, 0.1538520,
                                            0.3104856, 0.5329522, 0.0168980)


def _check_audio(audio: np.ndarray, label: str) -> None:
    if audio.ndim != 2:
        raise ValueError(f"{label}: audio must be 2-D [n_mic, n_sample], "
                          f"got shape {audio.shape}")
    if audio.size == 0:
        raise ValueError(f"{label}: audio is empty")
    if not np.isfinite(audio).all():
        raise ValueError(f"{label}: audio contains NaN/Inf")


def _generate_pink_noise(
    n_sample: int, rng: np.random.Generator
) -> np.ndarray:
    """Voss-McCartney pink noise — 6 filter rows summed.

    Produces float32 noise with approximate 1/f power spectrum. The signal
    is not normalised here; the caller scales it to the target dBFS.
    """
    n_rows = len(_PINK_FILTER_COEFFS)
    white = rng.standard_normal((n_rows, n_sample)).astype(np.float32)
    # Each row updates every 2^row samples → poor man's pink filter.
    out = np.zeros(n_sample, dtype=np.float32)
    for row in range(n_rows):
        coeff = _PINK_FILTER_COEFFS[row]
        stride = 1 << row
        if stride >= n_sample:
            continue
        # Hold each value for ``stride`` samples (downsample-then-upsample).
        slow = white[row, ::stride]
        held = np.repeat(slow, stride)[:n_sample]
        out += coeff * held
    return out


def apply_noise_floor(
    audio: np.ndarray,
    *,
    noise_db_fs: float = -50.0,
    rng: np.random.Generator,
) -> np.ndarray:
    """Add pink noise at ``noise_db_fs`` dBFS to every channel.

    Args:
        audio: ``[n_mic, n_sample]`` float32/float16 audio.
        noise_db_fs: RMS level of the added noise in dBFS (relative to 1.0
            full-scale). Default -50 dB (gentle hiss).
        rng: caller-managed numpy Generator.

    Returns:
        Augmented audio, same shape & dtype as input.
    """
    _check_audio(audio, "apply_noise_floor")
    if noise_db_fs >= 0:
        raise ValueError(f"noise_db_fs must be < 0, got {noise_db_fs}")
    n_mic, n_sample = audio.shape
    out = audio.astype(np.float32, copy=True)
    target_rms = 10.0 ** (noise_db_fs / 20.0)
    for ch in range(n_mic):
        noise = _generate_pink_noise(n_sample, rng)
        # Normalise to ``target_rms`` and add.
        noise_rms = float(np.sqrt(np.mean(noise * noise)))
        if noise_rms > 0:
            noise = noise * (target_rms / noise_rms)
        out[ch] += noise
    return out.astype(audio.dtype, copy=False)


def apply_gain_perturbation(
    audio: np.ndarray,
    *,
    range_db: tuple[float, float] = (-6.0, 6.0),
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply a single random gain shift (uniform in ``range_db``) to every
    channel — simulates fader-up/down variability without changing mic
    balance.

    Args:
        audio: ``[n_mic, n_sample]`` audio.
        range_db: (low, high) gain bounds in dB, drawn uniformly.
        rng: caller-managed Generator.

    Returns:
        Audio scaled by the same dB factor on every channel.
    """
    _check_audio(audio, "apply_gain_perturbation")
    low, high = range_db
    if low > high:
        raise ValueError(f"range_db {range_db} must have low ≤ high")
    db = float(rng.uniform(low, high))
    factor = 10.0 ** (db / 20.0)
    out: np.ndarray = (audio.astype(np.float32) * factor).astype(audio.dtype, copy=False)
    return out


def apply_mic_balance_jitter(
    audio: np.ndarray,
    *,
    range_db: tuple[float, float] = (-3.0, 3.0),
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply an *independent* gain shift per channel — breaks the rigid
    "balanced kit" assumption and trains the model to listen to the
    relative content, not the absolute mix.

    Args:
        audio: ``[n_mic, n_sample]`` audio.
        range_db: per-channel (low, high) gain bounds in dB.
        rng: caller-managed Generator.

    Returns:
        Audio with each channel scaled by an independent random dB factor.
    """
    _check_audio(audio, "apply_mic_balance_jitter")
    low, high = range_db
    if low > high:
        raise ValueError(f"range_db {range_db} must have low ≤ high")
    n_mic = audio.shape[0]
    dbs = rng.uniform(low, high, size=n_mic)
    factors = (10.0 ** (dbs / 20.0)).astype(np.float32)
    out_f32 = audio.astype(np.float32) * factors[:, None]
    out: np.ndarray = out_f32.astype(audio.dtype, copy=False)
    return out
