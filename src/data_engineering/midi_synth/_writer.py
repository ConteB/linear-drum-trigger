"""Shared MIDI writer for ``midi_synth`` generators (rare_emphasis + chaos).

Pure helper around :mod:`mido` — no business logic, no randomness. Anchored at
``TICKS_PER_BEAT = 480`` (matches F0-T2e / generate_local_rnd_dataset.py).

The ``GrooveSpec`` tuple is the contract: ``(name, bpm, events)`` where
``events`` is the canonical ``list[tuple[abs_tick, note, velocity]]`` form
used everywhere else in the project.

Fail-loud (mirrors :mod:`midi_augment` style):

* ``MidiSynthError`` on negative ticks / out-of-range velocity / unknown notes.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import mido  # type: ignore[import-untyped]

#: Ticks per beat — must match :mod:`midi_augment.jitter` and ``F0-T2e``.
TICKS_PER_BEAT: int = 480

#: Default note-off offset (60 ticks ≈ 1/8th-note at 480 TPB).
DEFAULT_NOTE_LEN_TICKS: int = 60

#: MIDI velocity bounds (GM spec).
VELOCITY_MIN: int = 1
VELOCITY_MAX: int = 127

#: MIDI note bounds (GM drum kit valid range).
NOTE_MIN: int = 0
NOTE_MAX: int = 127


class MidiSynthError(ValueError):
    """Raised on malformed groove events or write parameters."""


class GrooveSpec(NamedTuple):
    """A single groove ready to be serialised as MIDI.

    Attributes
    ----------
    name
        Human label for the log (e.g. ``"rare-crash-led-0"``).
    bpm
        Tempo in beats per minute (positive integer).
    events
        Sorted list of ``(abs_tick, note, velocity)`` triples. The writer
        sorts them again defensively, but well-formed inputs should be
        already chronological.
    """

    name: str
    bpm: int
    events: list[tuple[int, int, int]]


def write_events_to_midi(
    spec: GrooveSpec,
    path: Path,
    *,
    ticks_per_beat: int = TICKS_PER_BEAT,
    note_len_ticks: int = DEFAULT_NOTE_LEN_TICKS,
) -> Path:
    """Serialise ``spec`` to ``path`` as a one-track GM-drum MIDI file.

    Each ``(abs_tick, note, velocity)`` triple is emitted as a
    ``note_on``/``note_off`` pair separated by ``note_len_ticks``.

    Raises
    ------
    MidiSynthError
        If ``spec.bpm`` is non-positive, any tick is negative, a note or
        velocity falls outside GM bounds, or ``note_len_ticks`` is non-positive.
    """
    if spec.bpm <= 0:
        raise MidiSynthError(f"bpm must be positive, got {spec.bpm}")
    if ticks_per_beat <= 0:
        raise MidiSynthError(f"ticks_per_beat must be positive, got {ticks_per_beat}")
    if note_len_ticks <= 0:
        raise MidiSynthError(f"note_len_ticks must be positive, got {note_len_ticks}")
    for idx, (abs_tick, note, velocity) in enumerate(spec.events):
        if abs_tick < 0:
            raise MidiSynthError(
                f"event {idx} has negative abs_tick={abs_tick} (groove={spec.name!r})"
            )
        if not NOTE_MIN <= note <= NOTE_MAX:
            raise MidiSynthError(
                f"event {idx} note={note} out of MIDI range [{NOTE_MIN}, {NOTE_MAX}]"
                f" (groove={spec.name!r})"
            )
        if not VELOCITY_MIN <= velocity <= VELOCITY_MAX:
            raise MidiSynthError(
                f"event {idx} velocity={velocity} out of range"
                f" [{VELOCITY_MIN}, {VELOCITY_MAX}] (groove={spec.name!r})"
            )

    midi = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(spec.bpm), time=0))

    # (abs_tick, priority, message) — note_on (1) before note_off (0) at same
    # tick to preserve a sane note duration even for zero-length notes.
    timed: list[tuple[int, int, mido.Message]] = []
    for abs_tick, note, velocity in spec.events:
        timed.append(
            (abs_tick, 1, mido.Message("note_on", note=note, velocity=velocity))
        )
        timed.append(
            (
                abs_tick + note_len_ticks,
                0,
                mido.Message("note_off", note=note, velocity=64),
            )
        )
    timed.sort(key=lambda item: (item[0], item[1]))

    prev = 0
    for abs_tick, _, message in timed:
        track.append(message.copy(time=abs_tick - prev))
        prev = abs_tick
    track.append(mido.MetaMessage("end_of_track", time=0))

    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(str(path))
    return path


# ----------------------------------------------------------------------------
# GM note constants (mirror tools/generate_local_rnd_dataset.py — every one is
# in midi_mapping_table.yaml forward_gm_to_bus AND in DRSKit Midimap_full.xml).
# ----------------------------------------------------------------------------

KICK: int = 36
SNARE: int = 38
SIDE_STICK: int = 37
HH_CLOSED: int = 42
HH_PEDAL: int = 44
HH_OPEN: int = 46
LOW_FLOOR_TOM: int = 41
HIGH_FLOOR_TOM: int = 43
LOW_TOM: int = 45
LOW_MID_TOM: int = 47
HI_MID_TOM: int = 48
HIGH_TOM: int = 50
RIDE: int = 51
RIDE_BELL: int = 53
CRASH_1: int = 49
CRASH_2: int = 57
CHINA: int = 52
SPLASH: int = 55

#: Bus → list of GM notes voiced on DRSKit. Used by the chaos generator.
#: Mirrors ``midi_mapping_table.yaml::forward_gm_to_bus`` restricted to the
#: notes actually rendered by DRSKit (kit-driven, not theoretical).
BUS_TO_GM_NOTES: dict[int, tuple[int, ...]] = {
    1: (KICK,),                       # kick
    2: (SNARE, SIDE_STICK),           # snare
    3: (HH_CLOSED, HH_PEDAL, HH_OPEN),  # hihat
    4: (HI_MID_TOM, HIGH_TOM, LOW_MID_TOM),  # tom_hi_mid
    5: (LOW_FLOOR_TOM, HIGH_FLOOR_TOM, LOW_TOM),  # floor_tom
    6: (RIDE, RIDE_BELL),             # ride
    7: (CRASH_1,),                    # crash_a
    8: (CRASH_2, CHINA, SPLASH),      # crash_b_misc
}
