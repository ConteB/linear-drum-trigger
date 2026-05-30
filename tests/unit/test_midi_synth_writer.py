"""Layer-1 oracles for ``midi_synth._writer``.

Pure helper — the focus is fail-loud on malformed events + round-trip
event preservation (write ⇒ read back ⇒ identical absolute-tick events).
"""
from __future__ import annotations

from pathlib import Path

import mido  # type: ignore[import-untyped]
import pytest

from data_engineering.midi_synth._writer import (
    BUS_TO_GM_NOTES,
    DEFAULT_NOTE_LEN_TICKS,
    NOTE_MAX,
    TICKS_PER_BEAT,
    VELOCITY_MAX,
    VELOCITY_MIN,
    GrooveSpec,
    MidiSynthError,
    loop_groove_to_min_duration,
    write_events_to_midi,
)


def _read_back_events(path: Path) -> list[tuple[int, int, int]]:
    midi = mido.MidiFile(str(path))
    out: list[tuple[int, int, int]] = []
    abs_tick = 0
    for msg in midi.tracks[0]:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            out.append((abs_tick, msg.note, msg.velocity))
    return out


def test_writes_minimal_groove(tmp_path: Path) -> None:
    spec = GrooveSpec(name="smoke", bpm=120, events=[(0, 36, 100), (240, 38, 90)])
    out = write_events_to_midi(spec, tmp_path / "smoke.mid")
    assert out.exists()
    assert _read_back_events(out) == [(0, 36, 100), (240, 38, 90)]


def test_round_trip_preserves_absolute_ticks(tmp_path: Path) -> None:
    events = [(0, 36, 100), (60, 38, 80), (60, 42, 70), (480, 36, 95)]
    spec = GrooveSpec(name="round-trip", bpm=140, events=events)
    out = write_events_to_midi(spec, tmp_path / "rt.mid")
    read_back = _read_back_events(out)
    # Order at the same tick may flip on read — compare as multiset.
    assert sorted(read_back) == sorted(events)


def test_unsorted_input_is_normalised(tmp_path: Path) -> None:
    """Inputs out of chronological order are sorted defensively."""
    events = [(480, 36, 100), (0, 38, 90), (240, 42, 70)]
    spec = GrooveSpec(name="unsorted", bpm=120, events=events)
    out = write_events_to_midi(spec, tmp_path / "u.mid")
    assert _read_back_events(out) == [(0, 38, 90), (240, 42, 70), (480, 36, 100)]


def test_tempo_is_written(tmp_path: Path) -> None:
    spec = GrooveSpec(name="tempo", bpm=145, events=[(0, 36, 100)])
    out = write_events_to_midi(spec, tmp_path / "t.mid")
    midi = mido.MidiFile(str(out))
    tempos = [m for m in midi.tracks[0] if m.type == "set_tempo"]
    assert tempos and tempos[0].tempo == mido.bpm2tempo(145)


def test_ticks_per_beat_is_written(tmp_path: Path) -> None:
    spec = GrooveSpec(name="tpb", bpm=120, events=[(0, 36, 100)])
    out = write_events_to_midi(spec, tmp_path / "tpb.mid")
    assert mido.MidiFile(str(out)).ticks_per_beat == TICKS_PER_BEAT


def test_rejects_negative_tick(tmp_path: Path) -> None:
    spec = GrooveSpec(name="neg", bpm=120, events=[(-1, 36, 100)])
    with pytest.raises(MidiSynthError, match="negative abs_tick"):
        write_events_to_midi(spec, tmp_path / "neg.mid")


def test_rejects_out_of_range_note(tmp_path: Path) -> None:
    spec = GrooveSpec(name="hi", bpm=120, events=[(0, NOTE_MAX + 1, 100)])
    with pytest.raises(MidiSynthError, match="out of MIDI range"):
        write_events_to_midi(spec, tmp_path / "hi.mid")


def test_rejects_zero_velocity(tmp_path: Path) -> None:
    spec = GrooveSpec(name="v0", bpm=120, events=[(0, 36, VELOCITY_MIN - 1)])
    with pytest.raises(MidiSynthError, match="velocity"):
        write_events_to_midi(spec, tmp_path / "v0.mid")


def test_rejects_too_loud(tmp_path: Path) -> None:
    spec = GrooveSpec(name="vmax", bpm=120, events=[(0, 36, VELOCITY_MAX + 1)])
    with pytest.raises(MidiSynthError, match="velocity"):
        write_events_to_midi(spec, tmp_path / "vmax.mid")


def test_rejects_nonpositive_bpm(tmp_path: Path) -> None:
    spec = GrooveSpec(name="bpm0", bpm=0, events=[(0, 36, 100)])
    with pytest.raises(MidiSynthError, match="bpm must be positive"):
        write_events_to_midi(spec, tmp_path / "bpm0.mid")


def test_rejects_nonpositive_note_len(tmp_path: Path) -> None:
    spec = GrooveSpec(name="len0", bpm=120, events=[(0, 36, 100)])
    with pytest.raises(MidiSynthError, match="note_len_ticks must be positive"):
        write_events_to_midi(spec, tmp_path / "n0.mid", note_len_ticks=0)


def test_creates_parent_dirs(tmp_path: Path) -> None:
    spec = GrooveSpec(name="deep", bpm=120, events=[(0, 36, 100)])
    nested = tmp_path / "a" / "b" / "c" / "deep.mid"
    write_events_to_midi(spec, nested)
    assert nested.exists()


def test_bus_to_gm_notes_covers_all_9_channels() -> None:
    assert set(BUS_TO_GM_NOTES.keys()) == set(range(1, 10))  # F0-T19 flat-28
    for bus_id, notes in BUS_TO_GM_NOTES.items():
        assert len(notes) > 0, f"bus {bus_id} has empty note list"
        for note in notes:
            assert 0 <= note <= 127, f"bus {bus_id} has out-of-range note {note}"


def test_default_note_len_is_positive() -> None:
    """Sanity check on the module constant."""
    assert DEFAULT_NOTE_LEN_TICKS > 0


def _groove_dur_s(spec: GrooveSpec) -> float:
    max_tick = max(t for t, _, _ in spec.events) + DEFAULT_NOTE_LEN_TICKS
    return max_tick / (TICKS_PER_BEAT * spec.bpm / 60.0)


def test_loop_groove_reaches_min_duration() -> None:
    """F0-T19: short synthetic grooves loop-extend to >= the mini-L3 crop.

    A 2-bar groove at high BPM is < 5 s; the loop must tile it (bar-aligned)
    until it spans >= min_duration_s, deterministically, with no overlap.
    """
    events = [(i * TICKS_PER_BEAT, 36 if i % 2 else 38, 100) for i in range(8)]
    for bpm in (80, 120, 160, 200):
        g = GrooveSpec(name="t", bpm=bpm, events=events)
        ext = loop_groove_to_min_duration(g, min_duration_s=6.0)
        assert _groove_dur_s(ext) >= 6.0, f"bpm={bpm} only {_groove_dur_s(ext)}s"
        # deterministic
        assert ext.events == loop_groove_to_min_duration(g, min_duration_s=6.0).events
        # tiled count is an exact multiple of the original
        assert len(ext.events) % len(events) == 0


def test_loop_groove_leaves_long_groove_unchanged() -> None:
    g = GrooveSpec(name="t", bpm=80, events=[(0, 36, 100), (40 * TICKS_PER_BEAT, 38, 100)])
    assert loop_groove_to_min_duration(g, min_duration_s=6.0).events == g.events


def test_loop_groove_empty_is_noop() -> None:
    g = GrooveSpec(name="t", bpm=120, events=[])
    assert loop_groove_to_min_duration(g, min_duration_s=6.0).events == []
