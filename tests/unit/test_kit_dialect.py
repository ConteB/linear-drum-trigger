"""F0-T19 oracles — canonical → kit dialect (Arrow ②), DrumGizmo + Sfizz.

Contract (docs/methodology/F0-T19_PER_KIT_MIDI_TRANSLATION_SPEC.md): the dialect
map translates our canonical GM render notes into each kit's own trigger
(DrumGizmo instrument name / Sfizz key). Fail-loud on unknown kit or unmapped
note — no silent drops (F0-T18 principle).
"""
from __future__ import annotations

import re

import mido  # type: ignore[import-untyped]
import pytest

from data_engineering.gold import kit_dialect

_DG_KITS = ("DRSKit", "MuldjordKit", "CrocellKit", "Aasimonster", "ShittyKit")
_SFZ_KITS = ("BigRustyDrums",)
# The 15 canonical render notes (midi_source_standards articulations).
_CANONICAL = {36, 37, 38, 42, 43, 44, 46, 47, 48, 49, 51, 52, 53, 55, 57}


def test_load_map_has_full_roster() -> None:
    kits = kit_dialect.load_dialect_map()
    for k in (*_DG_KITS, *_SFZ_KITS):
        assert k in kits, f"{k} missing from dialect map"


def test_has_kit() -> None:
    assert kit_dialect.has_kit("DRSKit")
    assert kit_dialect.has_kit("BigRustyDrums")
    assert not kit_dialect.has_kit("NoSuchKit")


@pytest.mark.parametrize("kit", _DG_KITS)
def test_dg_note_map_covers_all_canonical(kit: str) -> None:
    m = kit_dialect.drumgizmo_note_map(kit)
    assert set(m) == _CANONICAL, f"{kit} must map exactly the 15 canonical notes"
    assert all(isinstance(v, str) and v for v in m.values())


def test_dg_note_map_drskit_hihat_closed_is_main_instrument() -> None:
    # The whole point of F0-T19: 42 -> the proper Hihat_closed, not the shank.
    assert kit_dialect.drumgizmo_note_map("DRSKit")[42] == "Hihat_closed"


@pytest.mark.parametrize("kit", _SFZ_KITS)
def test_sfizz_key_map_covers_all_canonical(kit: str) -> None:
    m = kit_dialect.sfizz_key_map(kit)
    assert set(m) == _CANONICAL
    assert all(isinstance(v, int) for v in m.values())


def test_sfizz_remap_value_is_kit_key() -> None:
    # Big Rusty has no key-48 tom; canonical tom_high (48) remaps to 45.
    assert kit_dialect.sfizz_key_map("BigRustyDrums")[48] == 45


def test_substitute_entry_extracted() -> None:
    # DRSKit note 37 is a {instr, substitute} dict — must extract the instr.
    assert kit_dialect.drumgizmo_note_map("DRSKit")[37] == "Snare_rim"


def test_generate_drumgizmo_midimap(tmp_path) -> None:  # type: ignore[no-untyped-def]
    out = kit_dialect.generate_drumgizmo_midimap("DRSKit", tmp_path / "mm.xml")
    text = out.read_text()
    pairs = dict(
        (int(n), i) for n, i in re.findall(r'note="(\d+)"\s+instr="([^"]+)"', text)
    )
    assert pairs == kit_dialect.drumgizmo_note_map("DRSKit")


def test_remap_sfizz_midi_rewrites_and_preserves_timing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    src = tmp_path / "in.mid"
    mf = mido.MidiFile()
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.Message("note_on", note=48, velocity=100, channel=9, time=0))
    tr.append(mido.Message("note_off", note=48, velocity=0, channel=9, time=240))
    tr.append(mido.Message("note_on", note=36, velocity=100, channel=9, time=120))
    tr.append(mido.Message("note_off", note=36, velocity=0, channel=9, time=240))
    mf.save(str(src))
    out = kit_dialect.remap_sfizz_midi("BigRustyDrums", src, tmp_path / "out.mid")
    res = mido.MidiFile(str(out))
    notes = [(m.type, m.note, m.time) for m in res.tracks[0]
             if m.type in ("note_on", "note_off")]
    assert notes[0] == ("note_on", 45, 0)    # 48 -> 45 (tom remap), timing kept
    assert notes[1] == ("note_off", 45, 240)
    assert notes[2] == ("note_on", 36, 120)  # 36 -> 36 (identity)


def test_unknown_kit_fails_loud() -> None:
    with pytest.raises(kit_dialect.DialectError, match="not in dialect map"):
        kit_dialect.drumgizmo_note_map("NoSuchKit")


def test_engine_mismatch_fails_loud() -> None:
    with pytest.raises(kit_dialect.DialectError, match="not a drumgizmo kit"):
        kit_dialect.drumgizmo_note_map("BigRustyDrums")
    with pytest.raises(kit_dialect.DialectError, match="not a sfizz kit"):
        kit_dialect.sfizz_key_map("DRSKit")


def test_remap_unmapped_note_fails_loud(tmp_path) -> None:  # type: ignore[no-untyped-def]
    src = tmp_path / "bad.mid"
    mf = mido.MidiFile()
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.Message("note_on", note=99, velocity=100, channel=9, time=0))
    tr.append(mido.Message("note_off", note=99, velocity=0, channel=9, time=240))
    mf.save(str(src))
    with pytest.raises(kit_dialect.DialectError, match="no silent drop"):
        kit_dialect.remap_sfizz_midi("BigRustyDrums", src, tmp_path / "out.mid")
