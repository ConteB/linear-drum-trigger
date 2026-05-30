"""F0-T20b oracles — franken-kit split / assignment / routing (binary-free).

The render+sum acceptance lives in tools/franken_smoke.py (needs the DrumGizmo
binary on OrbStack); these Layer-1 oracles cover the pure logic.
"""
from __future__ import annotations

import mido
import pytest

from data_engineering.gold.franken import (
    INSTRUMENT_GROUPS,
    INSTRUMENT_NOTES,
    INSTRUMENT_ORDER,
    FrankenError,
    _note_family,
    derive_franken_assignment,
    split_midi_by_instrument,
)


def _midi_with_notes(notes: list[int], *, ticks: int = 480) -> mido.MidiFile:
    m = mido.MidiFile(ticks_per_beat=ticks)
    tr = mido.MidiTrack()
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    for i, n in enumerate(notes):
        tr.append(mido.Message("note_on", note=n, velocity=80, time=0 if i == 0 else ticks))
        tr.append(mido.Message("note_off", note=n, velocity=0, time=ticks // 2))
    tr.append(mido.MetaMessage("end_of_track", time=0))
    m.tracks.append(tr)
    return m


# --- families / routing -----------------------------------------------------

def test_instrument_groups_are_disjoint() -> None:
    seen: set[int] = set()
    for notes in INSTRUMENT_GROUPS.values():
        assert not (seen & notes), "instrument families overlap"
        seen |= notes


def test_instrument_order_covers_all_groups() -> None:
    assert set(INSTRUMENT_ORDER) == set(INSTRUMENT_GROUPS)


def test_note_family_routing() -> None:
    assert _note_family(36) == "kick"
    assert _note_family(38) == "snare"
    assert _note_family(42) == "hihat"
    assert _note_family(48) == "tom"
    assert _note_family(51) == "ride"
    assert _note_family(49) == "crash"
    assert _note_family(52) == "aux"


def test_note_family_unknown_is_fail_loud() -> None:
    with pytest.raises(FrankenError):
        _note_family(99)  # not a canonical articulation


# --- split ------------------------------------------------------------------

def test_split_routes_notes_to_families() -> None:
    m = _midi_with_notes([36, 38, 42, 48, 51])
    fams = split_midi_by_instrument(m)
    assert set(fams) == {"kick", "snare", "hihat", "tom", "ride"}
    for fam, fm in fams.items():
        notes = [msg.note for tr in fm.tracks for msg in tr
                 if msg.type == "note_on" and msg.velocity > 0]
        assert all(n in INSTRUMENT_GROUPS[fam] for n in notes)


def test_split_skips_empty_families() -> None:
    fams = split_midi_by_instrument(_midi_with_notes([36, 38]))
    assert set(fams) == {"kick", "snare"}  # no hihat/tom/etc.


def test_split_replicates_tempo_into_every_family() -> None:
    fams = split_midi_by_instrument(_midi_with_notes([36, 38, 42]))
    for fm in fams.values():
        tempos = [m for tr in fm.tracks for m in tr if m.type == "set_tempo"]
        assert len(tempos) == 1


def test_split_routes_control_change_to_hihat() -> None:
    m = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack()
    tr.append(mido.Message("control_change", control=4, value=90, time=0))
    tr.append(mido.Message("note_on", note=42, velocity=80, time=10))
    tr.append(mido.Message("note_off", note=42, velocity=0, time=240))
    m.tracks.append(tr)
    fams = split_midi_by_instrument(m)
    cc = [msg for tr in fams["hihat"].tracks for msg in tr if msg.type == "control_change"]
    assert len(cc) == 1 and cc[0].value == 90


def test_split_preserves_note_count() -> None:
    m = _midi_with_notes([36, 36, 38, 42, 42, 42])
    fams = split_midi_by_instrument(m)
    total = sum(
        1 for fm in fams.values() for tr in fm.tracks for msg in tr
        if msg.type == "note_on" and msg.velocity > 0
    )
    assert total == 6


# --- assignment -------------------------------------------------------------

def test_assignment_is_deterministic() -> None:
    kw = dict(instruments=["kick", "snare", "hihat"],
              kit_labels=("A", "B", "C"), master_seed=42,
              source_midi_id="x.mid", variant_idx=0)
    assert derive_franken_assignment(**kw) == derive_franken_assignment(**kw)


def test_assignment_changes_with_seed() -> None:
    base = dict(instruments=["kick", "snare", "hihat", "tom", "ride", "crash", "aux"],
                kit_labels=("A", "B", "C", "D"), source_midi_id="x.mid", variant_idx=0)
    a = derive_franken_assignment(master_seed=1, **base)
    b = derive_franken_assignment(master_seed=2, **base)
    assert a != b


def test_assignment_only_uses_pool_kits() -> None:
    pool = ("A", "B", "C")
    asg = derive_franken_assignment(
        instruments=list(INSTRUMENT_ORDER), kit_labels=pool,
        master_seed=7, source_midi_id="x.mid", variant_idx=0)
    assert set(asg.values()) <= set(pool)
    assert set(asg) == set(INSTRUMENT_ORDER)


def test_assignment_empty_pool_fail_loud() -> None:
    with pytest.raises(FrankenError):
        derive_franken_assignment(
            instruments=["kick"], kit_labels=(),
            master_seed=0, source_midi_id="x.mid", variant_idx=0)


def test_instrument_notes_union() -> None:
    assert INSTRUMENT_NOTES == frozenset().union(*INSTRUMENT_GROUPS.values())
