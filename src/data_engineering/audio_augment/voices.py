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


def apply_peak_normalize(
    audio: np.ndarray,
    *,
    target_peak: float = 0.7,
) -> np.ndarray:
    """Rescale ``audio`` so its peak absolute value equals ``target_peak``.

    Pure, deterministic — no RNG. Headroom-preserving step that must run
    *before* the gain stages of the pipeline. Without it, samples whose
    native peak is already > 0.5 (e.g. the chaos layer) clip the R3
    ceiling at +3 dB of gain and the pipeline rejects them. With it,
    every sample lands at the same peak before the random gains, so the
    R3 guard is back to being a safety net rather than a dataset filter.

    Args:
        audio: ``[n_mic, n_sample]`` audio.
        target_peak: post-normalize peak absolute value in [0, 1].
            Default 0.7 leaves ~3 dB of headroom for the gain stage.

    Returns:
        Rescaled audio, same shape & dtype. Silent input (peak ≈ 0) is
        returned unchanged (no division by zero).
    """
    _check_audio(audio, "apply_peak_normalize")
    if not 0.0 < target_peak <= 1.0:
        raise ValueError(
            f"target_peak must be in (0, 1], got {target_peak}"
        )
    f32 = audio.astype(np.float32, copy=False)
    peak = float(np.abs(f32).max())
    if peak <= 1e-9:
        return audio  # silent → leave alone, no scale to apply.
    factor = target_peak / peak
    out: np.ndarray = (f32 * factor).astype(audio.dtype, copy=False)
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


def apply_channel_mask(
    audio: np.ndarray,
    *,
    prob: float = 0.20,
    rng: np.random.Generator,
) -> np.ndarray:
    """Random zero su 1 canale (F0-T15-post §4.4 B3 — agnosticità ingresso).

    Decision Lock CEO 2026-05-25. Simula "uno dei microfoni è morto" →
    forza la rete a essere robusta all'assenza di un canale specifico.
    **Direttamente collegato al fix cross-kit del mini-L3** (ShittyKit non
    aveva mic Hihat dedicato; con channel masking la rete impara a non
    fare affidamento su quel singolo canale).

    Args:
        audio: ``[n_mic, n_sample]`` audio.
        prob: probabilità di applicare il masking (default 0.20 — F0-T15-post §4.4).
        rng: caller-managed Generator.

    Returns:
        Audio con un canale azzerato (con prob ``prob``) o input unchanged.
        Mai applicato se ``n_mic ≤ 1`` (mono).
    """
    _check_audio(audio, "apply_channel_mask")
    if not 0.0 <= prob <= 1.0:
        raise ValueError(f"prob must be in [0, 1], got {prob}")
    n_mic = audio.shape[0]
    if n_mic <= 1:
        return audio
    if float(rng.random()) >= prob:
        return audio
    mask_ch = int(rng.integers(0, n_mic))
    out: np.ndarray = audio.copy()
    out[mask_ch] = 0.0
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
