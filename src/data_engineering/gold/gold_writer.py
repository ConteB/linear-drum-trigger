"""Gold-tensor writer — FP16 WebDataset sample triple (F0-T2a §3).

SKELETON / CONTRACT INTERFACE.  Public constants are LOCKED here for the F0-T9b
test harness; the logic is owned by **F0-T2d** and raises
:class:`NotImplementedError`.

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §3.
"""
from __future__ import annotations

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

    Note:
        SKELETON — implementation owned by F0-T2d.
    """
    raise NotImplementedError("n_frames — owned by F0-T2d")


def bus_columns(bus: int) -> tuple[int, int, int]:
    """flat-25 column triple ``(3b, 3b+1, 3b+2)`` for ``bus`` ``b``.

    The triple holds onset / velocity / microtiming respectively (F0-T2a §3.3).

    Args:
        bus: Bus index in ``[0, 7]``.

    Returns:
        ``(onset_col, velocity_col, microtiming_col)``.

    Note:
        SKELETON — implementation owned by F0-T2d.
    """
    raise NotImplementedError("bus_columns — owned by F0-T2d")


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
    (F0-T2a §3.2/§3.3). The writer fails loud (:class:`GoldWriterError`) on any
    contract violation — non-finite values, wrong ``target`` width, silent-zero
    audio (ENGINEERING_STANDARDS §6) — and never writes a partial sample.

    Args:
        out_dir: Destination directory for the sample triple.
        key: The DNA barcode key (dot-free).
        audio: Input buffer, shape ``[n_mic, n_sample]``, ``n_mic in [1, 8]``.
        target: Transcription matrix, shape ``[n_frame, 25]`` (flat-25).
        dna: The ``dna.json`` document (see :func:`~.dna_trace.build_dna_json`).

    Returns:
        Path to the written directory.

    Note:
        SKELETON — implementation owned by F0-T2d.
    """
    raise NotImplementedError("gold-tensor writer — owned by F0-T2d")
