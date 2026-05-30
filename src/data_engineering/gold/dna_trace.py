"""DNA-Trace — sample lineage barcode + ``dna.json`` "Libretto Sanitario".

Implements the F0-T2a §4 contract: the seven-segment barcode codec (a strict
bijection — 7-segment from the Decision Lock CEO 2026-05-23, B3) and the
``dna.json`` document that permits full reverse-engineering of a Gold sample —
lineage plus the ``sha256`` / non-finite integrity of both buffers
(F0-T2a §3.7).

Critical module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3). Every
function fails loud with :class:`DnaTraceError` and never returns partial state
(ENGINEERING_STANDARDS §6).

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §4.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np

from data_engineering.gold.recipe import Recipe

#: ``dna.json`` schema version (F0-T2a §4.2).
DNA_VERSION = "1.0"

#: Ordered barcode segments (F0-T2a §4.1 — 7-segment amendment, Decision Lock CEO
#: 2026-05-23, bivio B3 of F0-T15-pre). The ``jittervar`` segment encodes the
#: jitter-variant index (``J{idx:02d}``); it sits *after* ``midialt`` to
#: preserve the lexical ordering MIDI-source → MIDI-transformation →
#: MIDI-variant → render-side segments.
BARCODE_SEGMENTS: tuple[str, ...] = (
    "midisrc",
    "midialt",
    "jittervar",
    "engine",
    "reverb",
    "audioalt",
    "saboteur",
)

#: Barcode segment separator — also the reason segments may not contain it.
_SEPARATOR = "-"
#: Reserved by WebDataset for the extension split (F0-T2a §3.1).
_RESERVED = "."


class DnaTraceError(ValueError):
    """Raised on a malformed barcode key or an inconsistent ``dna.json``."""


@dataclass(frozen=True)
class Barcode:
    """The seven-segment DNA barcode (F0-T2a §4.1 — Decision Lock CEO 2026-05-23).

    Segments are joined by ``-`` to form the WebDataset sample ``key``. The key
    is dot-free by construction so it survives WebDataset's extension splitting
    (F0-T2a §3.1).

    The ``jittervar`` segment (``J{idx:02d}``) distinguishes the ``k+1``
    jittered variants produced by the MIDI augmentation pipeline (F0-T15-pre).
    ``J00`` is always the baseline (identity); ``J01..Jkk`` are the augmented
    branches. The segment is orthogonal to ``midialt`` (which records *which*
    transformations are active as binary flags): two variants with the same
    ``midialt`` can still differ via their seed-driven RNG draws, and the
    ``jittervar`` segment is what disambiguates them in the manifest.
    """

    midisrc: str
    midialt: str
    jittervar: str
    engine: str
    reverb: str
    audioalt: str
    saboteur: str


def _check_segment(segment: object, field: str) -> str:
    """Return ``segment`` if it is a valid barcode segment, else fail loud."""
    if not isinstance(segment, str) or not segment:
        raise DnaTraceError(f"barcode segment '{field}' must be a non-empty string")
    if _SEPARATOR in segment:
        raise DnaTraceError(
            f"barcode segment '{field}'={segment!r} must not contain "
            f"the separator {_SEPARATOR!r}"
        )
    if _RESERVED in segment:
        raise DnaTraceError(
            f"barcode segment '{field}'={segment!r} must not contain "
            f"the WebDataset-reserved {_RESERVED!r}"
        )
    return segment


def encode_barcode(barcode: Barcode) -> str:
    """Encode a :class:`Barcode` into its ``-``-joined string key.

    Args:
        barcode: The seven-segment barcode (F0-T2a §4.1, 7-segment amendment).

    Returns:
        The WebDataset sample key (dot-free).

    Raises:
        DnaTraceError: If any segment is empty or contains ``-`` or ``.``.
    """
    segments = dataclasses.astuple(barcode)
    return _SEPARATOR.join(
        _check_segment(seg, field)
        for field, seg in zip(BARCODE_SEGMENTS, segments, strict=True)
    )


def decode_barcode(key: str) -> Barcode:
    """Decode a barcode string key back into a :class:`Barcode`.

    ``decode_barcode`` is the exact inverse of :func:`encode_barcode`: the pair
    is a bijection (TESTING_DOCTRINE §6.2).

    Args:
        key: A seven-segment, ``-``-joined barcode key.

    Returns:
        The decoded :class:`Barcode`.

    Raises:
        DnaTraceError: If ``key`` is not a well-formed seven-segment barcode.
    """
    if not isinstance(key, str):
        raise DnaTraceError(f"barcode key must be a string, got {type(key).__name__}")
    if _RESERVED in key:
        raise DnaTraceError(
            f"barcode key {key!r} must not contain the WebDataset-reserved {_RESERVED!r}"
        )
    segments = key.split(_SEPARATOR)
    if len(segments) != len(BARCODE_SEGMENTS):
        raise DnaTraceError(
            f"barcode key {key!r} has {len(segments)} segment(s), "
            f"expected {len(BARCODE_SEGMENTS)}"
        )
    if any(not segment for segment in segments):
        raise DnaTraceError(f"barcode key {key!r} has an empty segment")
    return Barcode(*segments)


def _buffer_integrity(arr: np.ndarray) -> dict[str, Any]:
    """Compute the F0-T2a §3.7 integrity block for one buffer.

    The buffer is canonicalised to C-contiguous little-endian float16 before
    hashing, so the ``sha256`` is reproducible across machines and matches the
    bytes written to the ``.f16`` shard.
    """
    canonical = np.ascontiguousarray(arr, dtype="<f2")
    n_nonfinite = int(canonical.size - int(np.isfinite(canonical).sum()))
    return {
        "shape": list(arr.shape),
        "dtype": "float16",
        "sha256": hashlib.sha256(canonical.tobytes()).hexdigest(),
        "n_nonfinite": n_nonfinite,
    }


def _recipe_hash(recipe: Recipe) -> str:
    """Deterministic ``sha256`` of a recipe — the lineage anchor (F0-T2a §4.2)."""
    payload = json.dumps(dataclasses.asdict(recipe), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_dna_json(
    *,
    barcode: Barcode,
    recipe: Recipe,
    audio: np.ndarray,
    target: np.ndarray,
    last_onset_s: float = 0.0,
    tail_s: float = 0.5,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the ``dna.json`` "Libretto Sanitario" for one Gold sample.

    The document permits full reverse-engineering of the sample (F0-T2a §4.2):
    lineage, render/augmentation parameters, and the ``sha256`` + ``n_nonfinite``
    of both buffers (F0-T2a §3.7). Records the tail-standardisation parameters
    that anchor the engine-uniform sample duration (F0-T2a §3.8).

    Args:
        barcode: The sample's six-segment barcode.
        recipe: The validated recipe that produced the sample.
        audio: The ``audio`` buffer, shape ``[n_mic, n_sample]``.
        target: The ``target`` matrix, shape ``[n_frame, 25]``.
        last_onset_s: Time of the last mapped drum onset in the MIDI source.
        tail_s: Standardised tail length (F0-T2a §3.8) — uniform across engines.
        generated_at: ISO-8601 timestamp; defaults to the current UTC time.

    Returns:
        The ``dna.json`` document as a plain, JSON-serialisable dict.

    Raises:
        DnaTraceError: If the barcode is malformed (via :func:`encode_barcode`),
            or ``last_onset_s`` / ``tail_s`` is negative.
    """
    if last_onset_s < 0.0:
        raise DnaTraceError(f"last_onset_s must be >= 0, got {last_onset_s}")
    if tail_s < 0.0:
        raise DnaTraceError(f"tail_s must be >= 0, got {tail_s}")
    key = encode_barcode(barcode)
    return {
        "dna_version": DNA_VERSION,
        "barcode": key,
        "key": key,
        "recipe_id": recipe.recipe_id,
        "recipe_sha256": _recipe_hash(recipe),
        "split": recipe.split.value,
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "lineage": {
            "midi_source": {
                "dataset": recipe.midi_source.dataset,
                "file": recipe.midi_source.file,
            },
            "midi_jitter": {
                "variant_idx": recipe.midi_jitter.variant_idx,
                "time_jitter_ms": list(recipe.midi_jitter.time_jitter_ms),
                "flam_probability": recipe.midi_jitter.flam_probability,
                "velocity_jitter": recipe.midi_jitter.velocity_jitter.value,
                "component_drop_probability": recipe.midi_jitter.component_drop_probability,
                "seed": recipe.midi_jitter.seed,
            },
            "render": {
                "engine": recipe.render.engine.value,
                "kit": recipe.render.kit,
                "mic_config": recipe.render.mic_config.value,
                "sample_rate": recipe.render.sample_rate,
            },
            "augmentation": {
                "level": recipe.augmentation.level,
                "reverb_ir": recipe.augmentation.reverb_ir,
                "mutilation": recipe.augmentation.mutilation,
                "saboteur": recipe.augmentation.saboteur,
            },
        },
        "audio": {
            **_buffer_integrity(audio),
            "last_onset_s": last_onset_s,
            "tail_s": tail_s,
        },
        "target": {
            **_buffer_integrity(target),
            "layout": "flat-28",
            "frame_rate_hz": recipe.target_frame_rate_hz,
        },
    }


def validate_dna_json(dna: dict[str, Any], *, audio: np.ndarray, target: np.ndarray) -> None:
    """Verify a ``dna.json`` against its buffers (Gate L2 / DoD F0-T2d).

    Recomputes the buffer hashes, checks ``0`` non-finite values, and checks
    that the recorded shapes match (F0-T2a §3.7).

    Args:
        dna: The ``dna.json`` document to verify.
        audio: The ``audio`` buffer the document is supposed to describe.
        target: The ``target`` matrix the document is supposed to describe.

    Raises:
        DnaTraceError: On any mismatch — missing block, non-finite values,
            shape mismatch, or an altered buffer (``sha256`` mismatch).
    """
    for block, arr in (("audio", audio), ("target", target)):
        recorded = dna.get(block)
        if not isinstance(recorded, dict):
            raise DnaTraceError(f"dna.json is missing the '{block}' integrity block")
        fresh = _buffer_integrity(arr)
        if recorded.get("n_nonfinite") != 0:
            raise DnaTraceError(
                f"dna.json '{block}': records {recorded.get('n_nonfinite')} "
                "non-finite value(s)"
            )
        if fresh["n_nonfinite"] != 0:
            raise DnaTraceError(f"dna.json '{block}': buffer contains NaN/Inf")
        if list(recorded.get("shape", [])) != fresh["shape"]:
            raise DnaTraceError(
                f"dna.json '{block}': recorded shape {recorded.get('shape')} "
                f"!= buffer shape {fresh['shape']}"
            )
        if recorded.get("sha256") != fresh["sha256"]:
            raise DnaTraceError(
                f"dna.json '{block}': sha256 mismatch — the buffer was altered"
            )
