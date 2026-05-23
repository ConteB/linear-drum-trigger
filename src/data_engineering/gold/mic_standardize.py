"""Microphone standardisation — Input-Agnostic 8-slot canonicalisation.

A Gold ``audio`` buffer holds ``n_mic in [1, 8]`` channels (F0-T2a §3.2). The
model is Input-Agnostic (DOSSIER §2.1): at data-loading time every buffer is
mapped onto a fixed ``[8, n_sample]`` tensor, with the unused slots zero-filled
and no input channel dropped or re-ordered.

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §2.3 — *positional
fallback*. The richer semantic mapping per F0-T4a §4 (``solo_stereo`` →
oh_L/oh_R, ``glyn_johns`` → kick/snare/oh_L/oh_R) lives in the F0-T4b data
loader, which calls this routine for ``mono`` and ``multitrack_full`` and the
explicit slot table for the other configurations.
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
    verbatim — no channel is dropped or re-ordered. Deterministic
    (ENGINEERING_STANDARDS §1).

    Args:
        audio: Input buffer, shape ``[n_mic, n_sample]``.
        n_mic: Declared channel count; must be in ``[1, 8]``.

    Returns:
        A ``[8, n_sample]`` buffer in the same dtype as ``audio``.

    Raises:
        MicStandardizeError: If ``n_mic`` is out of ``[1, 8]`` or inconsistent
            with ``audio``'s first axis.
    """
    if not 1 <= n_mic <= CANONICAL_SLOTS:
        raise MicStandardizeError(
            f"n_mic must be in [1, {CANONICAL_SLOTS}], got {n_mic}"
        )
    if audio.ndim != 2:
        raise MicStandardizeError(
            f"audio must be 2-D [n_mic, n_sample], got {audio.ndim}-D"
        )
    if audio.shape[0] != n_mic:
        raise MicStandardizeError(
            f"audio first axis {audio.shape[0]} does not match n_mic={n_mic}"
        )
    out = np.zeros((CANONICAL_SLOTS, audio.shape[1]), dtype=audio.dtype)
    out[:n_mic] = audio
    return out
