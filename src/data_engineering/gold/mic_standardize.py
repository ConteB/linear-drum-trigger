"""Microphone standardisation — Input-Agnostic 8-slot canonicalisation.

A Gold ``audio`` buffer holds ``n_mic in [1, 8]`` channels (F0-T2a §3.2). The
model is Input-Agnostic (DOSSIER §2.1): at data-loading time every buffer is
mapped onto a fixed ``[8, n_sample]`` tensor, with the unused slots zero-filled
and no input channel dropped or re-ordered.

SKELETON / CONTRACT INTERFACE.  The logic is owned by the data-loader
pre-processing stage (consumed by F0-T4b) and raises
:class:`NotImplementedError`.

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §2.3.
"""
from __future__ import annotations

import numpy as np

#: Canonical number of microphone slots (F0-T2a §2.3 — multitrack_full).
CANONICAL_SLOTS = 8


class MicStandardizeError(ValueError):
    """Raised when a buffer cannot be standardised to the 8 canonical slots."""


def standardize_mics(audio: np.ndarray, n_mic: int) -> np.ndarray:
    """Map a ``[n_mic, n_sample]`` buffer onto the canonical ``[8, n_sample]``.

    Slots ``n_mic..7`` are zero-filled; the first ``n_mic`` channels are copied
    verbatim — no channel is dropped or re-ordered. Deterministic.

    Args:
        audio: Input buffer, shape ``[n_mic, n_sample]``.
        n_mic: Declared channel count; must be in ``[1, 8]``.

    Returns:
        A ``[8, n_sample]`` buffer.

    Raises:
        MicStandardizeError: If ``n_mic`` is out of ``[1, 8]`` or inconsistent
            with ``audio``.

    Note:
        SKELETON — implementation owned by the data-loader stage (F0-T4b).
    """
    raise NotImplementedError("mic standardisation — owned by the data-loader stage")
