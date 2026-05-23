"""Bit-deterministic seed derivation for MIDI jitter variants.

Spec: F0-T15-pre §4.1 — ``seed = sha256(master_seed ‖ source_midi_id ‖
variant_idx)[:8]`` consumed via ``numpy.random.default_rng``. The 8-byte prefix
is sufficient entropy for `default_rng` (64-bit state) and gives bit-per-bit
replay: same master + same MIDI id + same variant -> same seed -> same RNG ->
same jitter result.

This module is *cheap and pure*: it does not touch ``mido``, ``numpy`` or any
file. It exists in its own translation unit because the recipe-matrix builder
and the jitter pipeline both depend on it, and we want a single source of truth
for the derivation formula.
"""
from __future__ import annotations

import hashlib


def derive_jitter_seed(master_seed: int, source_midi_id: str, variant_idx: int) -> int:
    """Derive the per-variant RNG seed.

    Args:
        master_seed: The run-level seed (e.g. the F2-T1 recipe matrix seed).
            Any non-negative integer; coerced into a 16-byte big-endian payload
            so the formula is invariant to platform endianness.
        source_midi_id: A stable identifier for the source MIDI — for the
            production pipeline this is the ``midi_source.file`` of the recipe
            (e.g. ``"bronze/gmd/.../42_rock_120.mid"``); for tests, any short
            string. UTF-8 encoded.
        variant_idx: The jitter-variant index. ``0`` is the baseline (identity)
            and must still receive its own derived seed (so that downstream
            code paths exercise the same RNG construction); ``1..k`` are the
            augmented variants.

    Returns:
        A non-negative 64-bit integer, suitable for
        ``numpy.random.default_rng(seed)``.

    Raises:
        ValueError: if ``master_seed`` or ``variant_idx`` is negative, or if
            ``source_midi_id`` is empty.
    """
    if master_seed < 0:
        raise ValueError(f"master_seed: must be non-negative, got {master_seed}")
    if variant_idx < 0:
        raise ValueError(f"variant_idx: must be non-negative, got {variant_idx}")
    if not source_midi_id:
        raise ValueError("source_midi_id: must be non-empty")

    # 16-byte big-endian payload for master_seed: covers anything that fits in
    # an int128 (well beyond practical seeds). The separator bytes (``\x1f``,
    # ASCII Unit Separator) keep the three components unambiguous when
    # concatenated.
    payload = (
        master_seed.to_bytes(16, "big", signed=False)
        + b"\x1f"
        + source_midi_id.encode("utf-8")
        + b"\x1f"
        + variant_idx.to_bytes(8, "big", signed=False)
    )
    digest = hashlib.sha256(payload).digest()
    # First 8 bytes -> uint64. `int.from_bytes(..., signed=False)` keeps it
    # non-negative for `numpy.random.default_rng` (which accepts any unsigned
    # 64-bit value but rejects negatives).
    return int.from_bytes(digest[:8], "big", signed=False)
