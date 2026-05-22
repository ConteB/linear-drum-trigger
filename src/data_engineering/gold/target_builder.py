"""MIDI -> flat-25 target matrix builder (F0-T2a §3.3, DOSSIER §6.2).

The render engines (F0-T2b/c) produce the ``audio`` buffer of a Gold sample;
this module produces its companion ``target`` matrix — the transcription
ground truth the model is trained against. It reads a drum MIDI file, maps
every General-MIDI drum note onto one of the 8 logical transcription buses via
the versioned ``midi_mapping_table.yaml`` (F0-T2a §1.1), and emits the locked
``flat-25`` layout (F0-T2a §3.3):

* per bus ``b in [0, 7]``: column ``3b`` onset (a Gaussian-smeared probability
  — DOSSIER §6.2, never a digital spike), ``3b+1`` velocity (normalised from
  the MIDI 0-127 range), ``3b+2`` microtiming (the sub-frame residual that
  keeps the event sample-accurate, F0-T2a §3.4);
* column 24: the continuous Hi-Hat opening head — a step-held signal driven by
  the discrete hi-hat articulations (closed/pedal/open), projected onto
  ``[0, 1]`` (F0-T2a §5).

Fail-loud (ENGINEERING_STANDARDS §6): every malformed input raises
:class:`TargetBuilderError` and no partial matrix is ever returned.

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §3.3.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mido  # type: ignore[import-untyped]
import numpy as np
import yaml

from data_engineering.gold.gold_writer import (
    HIHAT_OPENING_COL,
    N_BUSES,
    R_TARGET_HZ,
    TARGET_COLS,
    bus_columns,
    n_frames,
)

#: Onset Gaussian-smear standard deviation, in milliseconds (F0-T2a §3.5,
#: DOSSIER §6.2 — the ±3 ms symmetric smear; also recorded in ``dna.json``).
SMEAR_MS = 3.0
#: Half-width of the smear window, in standard deviations: beyond 4 sigma the
#: Gaussian is < 4e-4 and rounds to zero in float16 — no point writing it.
_SMEAR_WINDOW_SIGMA = 4.0
#: MIDI velocity is a 7-bit value; the contract stores it normalised (F0-T2a §3.5).
_MIDI_VELOCITY_MAX = 127.0

#: Hi-Hat opening value per GM articulation note (F0-T2a §5 / spec §5 survey):
#: the libraries expose discrete states; they are projected onto ``[0, 1]`` for
#: the continuous regression head (closed -> 0, pedal -> 0.5, open -> 1).
HIHAT_OPENING_BY_NOTE: dict[int, float] = {
    42: 0.0,  # Closed Hi-Hat
    44: 0.5,  # Pedal Hi-Hat
    46: 1.0,  # Open Hi-Hat
}


class TargetBuilderError(ValueError):
    """Raised when a MIDI file or mapping cannot yield a valid target matrix."""


@dataclass(frozen=True)
class BusMapping:
    """The GM-note -> 8-bus mapping, loaded from ``midi_mapping_table.yaml``.

    Attributes:
        gm_to_bus: GM drum note -> bus index in ``[0, 7]`` (the ``flat-25``
            0-based index, i.e. the table's 1-based ``id`` minus one).
        schema_version: Version string of the source table — checked against
            the ``midi_source.bus_mapping`` reference of a recipe.
    """

    gm_to_bus: dict[int, int]
    schema_version: str


def load_bus_mapping(path: str | Path) -> BusMapping:
    """Load and validate the GM -> 8-bus mapping table (F0-T2a §1.1).

    Args:
        path: Filesystem path to ``midi_mapping_table.yaml``.

    Returns:
        The validated :class:`BusMapping`.

    Raises:
        TargetBuilderError: If the file cannot be read, is not valid YAML, or
            its ``forward_gm_to_bus`` block violates the 8-bus contract.
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TargetBuilderError(f"cannot read mapping table {file_path}: {exc}") from exc
    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TargetBuilderError(f"mapping table is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise TargetBuilderError("mapping table: expected a top-level mapping")

    version = raw.get("schema_version")
    if not isinstance(version, str) or not version:
        raise TargetBuilderError("mapping table: missing 'schema_version'")

    forward = raw.get("forward_gm_to_bus")
    if not isinstance(forward, dict) or not forward:
        raise TargetBuilderError("mapping table: missing or empty 'forward_gm_to_bus'")

    gm_to_bus: dict[int, int] = {}
    for note, bus_id in forward.items():
        if not isinstance(note, int) or isinstance(note, bool):
            raise TargetBuilderError(f"mapping table: GM note {note!r} is not an integer")
        if not 0 <= note <= 127:
            raise TargetBuilderError(f"mapping table: GM note {note} out of MIDI range")
        if not isinstance(bus_id, int) or isinstance(bus_id, bool):
            raise TargetBuilderError(f"mapping table: bus id {bus_id!r} is not an integer")
        if not 1 <= bus_id <= N_BUSES:
            raise TargetBuilderError(
                f"mapping table: bus id {bus_id} for note {note} outside [1, {N_BUSES}]"
            )
        gm_to_bus[note] = bus_id - 1  # table is 1-based; flat-25 is 0-based

    return BusMapping(gm_to_bus=gm_to_bus, schema_version=version)


@dataclass(frozen=True)
class _Onset:
    """One extracted MIDI note-on, with its absolute time and velocity."""

    time_s: float
    note: int
    velocity: int


def _extract_onsets(midi_path: Path) -> list[_Onset]:
    """Read every note-on (velocity > 0) from ``midi_path``, timed in seconds."""
    if not midi_path.is_file():
        raise TargetBuilderError(f"MIDI file not found: {midi_path}")
    try:
        midi = mido.MidiFile(str(midi_path))
    except (OSError, ValueError, EOFError, KeyError, IndexError) as exc:
        raise TargetBuilderError(f"cannot parse MIDI file {midi_path}: {exc}") from exc

    onsets: list[_Onset] = []
    time_s = 0.0
    try:
        for msg in midi:  # iterating a MidiFile yields delta times in seconds
            time_s += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                onsets.append(_Onset(time_s=time_s, note=msg.note, velocity=msg.velocity))
    except (OSError, ValueError, EOFError, KeyError, IndexError) as exc:
        raise TargetBuilderError(f"cannot iterate MIDI file {midi_path}: {exc}") from exc
    return onsets


def build_target(
    midi_path: str | Path,
    *,
    duration_s: float,
    bus_mapping: BusMapping,
    r_target_hz: float = R_TARGET_HZ,
    smear_ms: float = SMEAR_MS,
    allow_empty: bool = False,
) -> np.ndarray:
    """Build the ``flat-25`` target matrix for one MIDI drum performance.

    Args:
        midi_path: Drum MIDI file to transcribe.
        duration_s: Length of the companion ``audio`` buffer, in seconds — the
            frame count is ``ceil(duration_s * r_target_hz)`` (F0-T2a §3.4), so
            ``target`` and ``audio`` describe the same time span.
        bus_mapping: GM-note -> 8-bus mapping (see :func:`load_bus_mapping`).
        r_target_hz: Target frame-rate; defaults to the F0-T4a ratified value.
        smear_ms: Onset Gaussian-smear standard deviation, in milliseconds.
        allow_empty: When ``False`` (default) a MIDI with no mapped drum events
            fails loud; set ``True`` only for deliberate silence scenarios.

    Returns:
        The ``[n_frame, 25]`` float16 target matrix (F0-T2a §3.3).

    Raises:
        TargetBuilderError: On an unreadable/malformed MIDI, a non-positive
            ``duration_s`` / ``smear_ms``, a zero frame count, or — unless
            ``allow_empty`` — a MIDI carrying no mapped drum events.
    """
    if duration_s <= 0.0:
        raise TargetBuilderError(f"duration_s must be positive, got {duration_s}")
    if smear_ms <= 0.0:
        raise TargetBuilderError(f"smear_ms must be positive, got {smear_ms}")
    if r_target_hz <= 0.0:
        raise TargetBuilderError(f"r_target_hz must be positive, got {r_target_hz}")

    n_frame = n_frames(duration_s, r_target_hz)
    if n_frame == 0:
        raise TargetBuilderError(
            f"duration_s {duration_s} yields a zero-frame target at {r_target_hz} Hz"
        )

    onsets = _extract_onsets(Path(midi_path))
    mapped = [o for o in onsets if o.note in bus_mapping.gm_to_bus]
    if not mapped and not allow_empty:
        raise TargetBuilderError(
            f"MIDI {midi_path} carries no GM drum notes in the bus mapping — "
            "the target would be identically empty (set allow_empty to override)"
        )

    # Build in float64 for headroom, then cast once to the float16 contract.
    target = np.zeros((n_frame, TARGET_COLS), dtype=np.float64)
    sigma_frames = smear_ms * 1.0e-3 * r_target_hz
    window = max(1, math.ceil(_SMEAR_WINDOW_SIGMA * sigma_frames))

    # Per (bus, frame) the loudest collapsed event — v1.0 keeps one onset per
    # bus per frame (F0-T2a §5; midi_mapping_table.yaml articulation_scope).
    best: dict[tuple[int, int], _Onset] = {}
    hihat_events: list[tuple[float, float]] = []  # (frame_float, opening)

    for onset in mapped:
        bus = bus_mapping.gm_to_bus[onset.note]
        frame_float = onset.time_s * r_target_hz
        onset_col, _, _ = bus_columns(bus)

        # Gaussian onset smear — a soft probability bump, never a spike.
        centre = int(round(frame_float))
        for frame in range(centre - window, centre + window + 1):
            if 0 <= frame < n_frame:
                z = (frame - frame_float) / sigma_frames
                target[frame, onset_col] = max(
                    target[frame, onset_col], math.exp(-0.5 * z * z)
                )

        # Velocity + microtiming land on the rounded frame; the louder of two
        # collapsed events on the same (bus, frame) wins.
        frame_idx = centre
        if 0 <= frame_idx < n_frame:
            key = (bus, frame_idx)
            incumbent = best.get(key)
            if incumbent is None or onset.velocity > incumbent.velocity:
                best[key] = onset

        if onset.note in HIHAT_OPENING_BY_NOTE:
            hihat_events.append((frame_float, HIHAT_OPENING_BY_NOTE[onset.note]))

    for (bus, frame_idx), onset in best.items():
        _, velocity_col, microtiming_col = bus_columns(bus)
        target[frame_idx, velocity_col] = onset.velocity / _MIDI_VELOCITY_MAX
        # Sub-frame residual in [-0.5, 0.5] frames -> [-1, 1] half-frame units.
        residual = onset.time_s * r_target_hz - frame_idx
        target[frame_idx, microtiming_col] = float(np.clip(2.0 * residual, -1.0, 1.0))

    # Hi-Hat opening head — step-held: each hi-hat hit sets the opening, which
    # holds until the next hi-hat hit (F0-T2a §3.3, continuous head).
    for frame_float, opening in sorted(hihat_events):
        frame_idx = int(round(frame_float))
        if frame_idx < n_frame:
            target[max(0, frame_idx) :, HIHAT_OPENING_COL] = opening

    if not bool(np.isfinite(target).all()):  # defensive — smear math is bounded
        raise TargetBuilderError("target contains NaN/Inf after construction")
    return target.astype(np.float16)
