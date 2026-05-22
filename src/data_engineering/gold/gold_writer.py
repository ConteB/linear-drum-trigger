"""Gold-tensor writer — FP16 WebDataset sample triple (F0-T2a §3).

Implements the F0-T2a §3 data contract: the ``flat-25`` target layout, the
frame-count formula, and the writer of the ``audio.f16`` / ``target.f16`` /
``dna.json`` sample triple. Buffers are written as raw little-endian float16,
C-contiguous (F0-T2a §3.2/§3.3).

Critical module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3). The
writer fails loud with :class:`GoldWriterError` on any contract violation and
never writes a partial sample (ENGINEERING_STANDARDS §6).

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §3.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

#: Fixed render sample rate (F0-T2a §3.2).
SAMPLE_RATE = 44100
#: Target frame-rate, ratified by F0-T4a: 44100 / 128 (F0-T2a §3.4).
R_TARGET_HZ = 344.53125
#: Number of logical transcription buses (F0-T2a §3.3, midi_mapping_table.yaml).
N_BUSES = 8
#: flat-25 layout width: 8 buses x 3 channels + 1 Hi-Hat opening head.
TARGET_COLS = 25
#: Column index of the continuous Hi-Hat opening head (F0-T2a §3.3).
HIHAT_OPENING_COL = 24
#: Maximum microphone channels in an ``audio`` buffer (F0-T2a §3.2 — n_mic in [1,8]).
MAX_MIC_CHANNELS = 8
#: Raw buffer dtype — little-endian float16 (F0-T2a §3.2/§3.3).
_LE_FLOAT16 = np.dtype("<f2")


class GoldWriterError(ValueError):
    """Raised when audio/target buffers violate the F0-T2a §3 data contract."""


def n_frames(duration_s: float, r_target_hz: float = R_TARGET_HZ) -> int:
    """Frame count of the target matrix: ``ceil(duration_s * r_target_hz)``.

    F0-T2a §3.4.

    Args:
        duration_s: Sample duration in seconds (``>= 0``).
        r_target_hz: Target frame-rate; defaults to the ratified value.

    Returns:
        The number of target frames.

    Raises:
        GoldWriterError: If ``duration_s`` is negative.
    """
    if duration_s < 0.0:
        raise GoldWriterError(f"duration_s must be >= 0, got {duration_s}")
    return math.ceil(duration_s * r_target_hz)


def bus_columns(bus: int) -> tuple[int, int, int]:
    """flat-25 column triple ``(3b, 3b+1, 3b+2)`` for ``bus`` ``b``.

    The triple holds onset / velocity / microtiming respectively (F0-T2a §3.3).

    Args:
        bus: Bus index in ``[0, 7]``.

    Returns:
        ``(onset_col, velocity_col, microtiming_col)``.

    Raises:
        GoldWriterError: If ``bus`` is outside ``[0, 7]``.
    """
    if not 0 <= bus < N_BUSES:
        raise GoldWriterError(f"bus index must be in [0, {N_BUSES - 1}], got {bus}")
    base = 3 * bus
    return (base, base + 1, base + 2)


def _validate_audio(audio: np.ndarray) -> None:
    """Fail loud on any ``audio`` buffer that violates F0-T2a §3.2."""
    if audio.ndim != 2:
        raise GoldWriterError(f"audio must be 2-D [n_mic, n_sample], got {audio.ndim}-D")
    n_mic = audio.shape[0]
    if not 1 <= n_mic <= MAX_MIC_CHANNELS:
        raise GoldWriterError(
            f"audio n_mic must be in [1, {MAX_MIC_CHANNELS}], got {n_mic}"
        )
    if audio.shape[1] == 0:
        raise GoldWriterError("audio has zero samples")
    if audio.dtype != np.float16:
        raise GoldWriterError(f"audio must be float16 (FP16 contract), got {audio.dtype}")
    if not bool(np.isfinite(audio).all()):
        raise GoldWriterError(
            "audio contains NaN/Inf — fail loud (ENGINEERING_STANDARDS §6, F0-T2a §3.7)"
        )
    if not bool(np.any(audio)):
        raise GoldWriterError(
            "silent-zero audio — an identically-zero render is a structural defect "
            "(ENGINEERING_STANDARDS §6)"
        )


def _validate_target(target: np.ndarray) -> None:
    """Fail loud on any ``target`` matrix that violates F0-T2a §3.3."""
    if target.ndim != 2:
        raise GoldWriterError(f"target must be 2-D [n_frame, 25], got {target.ndim}-D")
    if target.shape[1] != TARGET_COLS:
        raise GoldWriterError(
            f"target must have {TARGET_COLS} columns (flat-25), got {target.shape[1]}"
        )
    if target.dtype != np.float16:
        raise GoldWriterError(f"target must be float16 (FP16 contract), got {target.dtype}")
    if not bool(np.isfinite(target).all()):
        raise GoldWriterError(
            "target contains NaN/Inf — fail loud (ENGINEERING_STANDARDS §6, F0-T2a §3.7)"
        )


def _raw_le_f16(arr: np.ndarray) -> bytes:
    """Serialise ``arr`` to raw C-contiguous little-endian float16 bytes."""
    return np.ascontiguousarray(arr, dtype=_LE_FLOAT16).tobytes()


def write_gold_sample(
    out_dir: str | Path,
    key: str,
    *,
    audio: np.ndarray,
    target: np.ndarray,
    dna: dict[str, Any],
) -> Path:
    """Write the ``{key}.audio.f16`` / ``.target.f16`` / ``.dna.json`` triple.

    The buffers are written as raw little-endian float16, C-contiguous
    (F0-T2a §3.2/§3.3). Both buffers are validated *before* any file is
    written, so a contract violation never leaves a partial sample on disk
    (ENGINEERING_STANDARDS §6).

    Args:
        out_dir: Destination directory for the sample triple.
        key: The DNA barcode key (dot-free).
        audio: Input buffer, shape ``[n_mic, n_sample]``, ``n_mic in [1, 8]``.
        target: Transcription matrix, shape ``[n_frame, 25]`` (flat-25).
        dna: The ``dna.json`` document (see :func:`~.dna_trace.build_dna_json`).

    Returns:
        Path to the directory the triple was written to.

    Raises:
        GoldWriterError: On any contract violation — wrong rank/width/dtype,
            non-finite values, or silent-zero audio.
    """
    _validate_audio(audio)
    _validate_target(target)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{key}.audio.f16").write_bytes(_raw_le_f16(audio))
    (out / f"{key}.target.f16").write_bytes(_raw_le_f16(target))
    (out / f"{key}.dna.json").write_text(
        json.dumps(dna, indent=2, sort_keys=True), encoding="utf-8"
    )
    return out
