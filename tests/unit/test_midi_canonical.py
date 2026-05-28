"""Layer-1 oracles for the F0-T18 MIDI Standard Translation Layer.

Anchors (``docs/specs/midi_source_standards.yaml`` + ``midi_canonical.py``):
- SSoT loads + validates; fail-loud on malformed articulations/standards.
- The cardinal principle: a note neither mapped nor explicitly ignored raises
  (never a silent drop).
- The headline remaps are correct: Roland TD-11 22 -> 42, 26 -> 46, 58 -> 43.
- Canonicalization preserves onset count + timing, and is deterministic.
- Every canonical render note maps to a bus in the GM bus mapping table
  (coherence between the two SSoTs).

Spec: ``docs/methodology/F0-T18_MIDI_STANDARD_TRANSLATION_SPEC.md`` §6.
"""
from __future__ import annotations

import collections
from pathlib import Path

import mido  # type: ignore[import-untyped]
import pytest

from data_engineering.gold.midi_canonical import (
    CanonicalizationError,
    canonicalize_midi,
    load_source_standards,
)
from data_engineering.gold.target_builder import load_bus_mapping

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STANDARDS = _REPO_ROOT / "docs" / "specs" / "midi_source_standards.yaml"
_BUS_MAP = _REPO_ROOT / "docs" / "specs" / "midi_mapping_table.yaml"


# ----------------------------------------------------------------------------
# SSoT loading + validation
# ----------------------------------------------------------------------------


def test_ssot_loads() -> None:
    std = load_source_standards(_STANDARDS)
    assert std.schema_version
    assert "roland_td11" in std.known_standards()
    assert "gm_standard" in std.known_standards()
    assert len(std.articulations) >= 12


def test_ssot_headline_remaps() -> None:
    std = load_source_standards(_STANDARDS)
    # The Pipeline Audit 2026-05-28 headline: hi-hat edge + hi floor tom.
    assert std.render_note("roland_td11", 22) == 42  # closed edge -> closed bow
    assert std.render_note("roland_td11", 26) == 46  # open edge -> open bow
    assert std.render_note("roland_td11", 58) == 43  # hi floor tom -> floor
    # Identity for already-canonical notes.
    assert std.render_note("roland_td11", 36) == 36
    assert std.render_note("roland_td11", 38) == 38


def test_ssot_articulation_hihat_opening() -> None:
    std = load_source_standards(_STANDARDS)
    closed = std.articulation_for("roland_td11", 22)
    opened = std.articulation_for("roland_td11", 26)
    assert closed is not None and closed.hihat_opening == 0.0
    assert opened is not None and opened.hihat_opening == 1.0


def test_unknown_standard_raises() -> None:
    std = load_source_standards(_STANDARDS)
    with pytest.raises(CanonicalizationError, match="unknown source standard"):
        std.render_note("td17_nonexistent", 36)


def test_unmapped_note_raises_not_silent() -> None:
    """The cardinal principle: a note in neither mapping nor ignored fails loud."""
    std = load_source_standards(_STANDARDS)
    with pytest.raises(CanonicalizationError, match="not mapped|silently"):
        std.render_note("roland_td11", 99)  # not a drum note in any standard


# ----------------------------------------------------------------------------
# Coherence between the two SSoTs (source standards <-> bus mapping table)
# ----------------------------------------------------------------------------


def test_every_render_note_maps_to_a_bus() -> None:
    """Every canonical render note an articulation emits must be mapped to a bus
    by midi_mapping_table.yaml — otherwise target_builder would drop it."""
    std = load_source_standards(_STANDARDS)
    bm = load_bus_mapping(_BUS_MAP)
    for name, art in std.articulations.items():
        assert art.render_gm in bm.gm_to_bus, (
            f"articulation {name} render_gm {art.render_gm} not in bus mapping table"
        )


def test_articulation_bus_matches_bus_mapping_table() -> None:
    """The bus declared in the articulations SSoT must equal the bus the GM bus
    mapping table assigns to the same render note (no divergence)."""
    std = load_source_standards(_STANDARDS)
    bm = load_bus_mapping(_BUS_MAP)
    for name, art in std.articulations.items():
        table_bus0 = bm.gm_to_bus[art.render_gm]  # 0-based
        assert art.bus - 1 == table_bus0, (
            f"{name}: SSoT bus {art.bus} != table bus {table_bus0 + 1} "
            f"for render note {art.render_gm}"
        )


# ----------------------------------------------------------------------------
# canonicalize_midi behaviour
# ----------------------------------------------------------------------------


def _write_midi(path: Path, notes: list[tuple[int, int]]) -> None:
    """Write a tiny drum MIDI: ``notes`` is a list of (note, delta_ticks)."""
    mf = mido.MidiFile()
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    for note, dt in notes:
        tr.append(mido.Message("note_on", note=note, velocity=100, time=dt, channel=9))
        tr.append(mido.Message("note_off", note=note, velocity=0, time=50, channel=9))
    mf.save(str(path))


def _onset_hist(path: Path) -> collections.Counter[int]:
    c: collections.Counter[int] = collections.Counter()
    for msg in mido.MidiFile(str(path)):
        if msg.type == "note_on" and msg.velocity > 0:
            c[msg.note] += 1
    return c


def test_canonicalize_edge_to_bow(tmp_path: Path) -> None:
    src = tmp_path / "src.mid"
    out = tmp_path / "canon.mid"
    # 3 closed-edge (22), 2 open-edge (26), 1 hi-floor (58), 4 kick (36)
    _write_midi(src, [(22, 0), (22, 10), (22, 10), (26, 10), (26, 10),
                      (58, 10), (36, 5), (36, 5), (36, 5), (36, 5)])
    hist = canonicalize_midi(src, standard="roland_td11", out_path=out)
    after = _onset_hist(out)
    assert after[42] == 3   # closed edge -> closed bow
    assert after[46] == 2   # open edge -> open bow
    assert after[43] == 1   # hi floor -> floor
    assert after[36] == 4   # kick identity
    assert hist["_ignored"] == 0
    assert hist["_total"] == 10


def test_canonicalize_preserves_onset_count(tmp_path: Path) -> None:
    src = tmp_path / "src.mid"
    out = tmp_path / "canon.mid"
    _write_midi(src, [(22, 0), (42, 10), (26, 10), (36, 10), (38, 10)])
    canonicalize_midi(src, standard="roland_td11", out_path=out)
    before = sum(_onset_hist(src).values())
    after = sum(_onset_hist(out).values())
    assert before == after == 5


def test_canonicalize_deterministic(tmp_path: Path) -> None:
    src = tmp_path / "src.mid"
    out_a = tmp_path / "a.mid"
    out_b = tmp_path / "b.mid"
    _write_midi(src, [(22, 0), (26, 10), (36, 10), (58, 10)])
    canonicalize_midi(src, standard="roland_td11", out_path=out_a)
    canonicalize_midi(src, standard="roland_td11", out_path=out_b)
    assert out_a.read_bytes() == out_b.read_bytes()


def test_canonicalize_unknown_note_fails_loud(tmp_path: Path) -> None:
    src = tmp_path / "src.mid"
    out = tmp_path / "canon.mid"
    _write_midi(src, [(36, 0), (99, 10)])  # 99 not a drum note anywhere
    with pytest.raises(CanonicalizationError, match="not mapped|silently"):
        canonicalize_midi(src, standard="roland_td11", out_path=out)


def test_canonicalize_preserves_timing(tmp_path: Path) -> None:
    """The canonical MIDI is time-identical to the source (onset seconds equal)."""
    src = tmp_path / "src.mid"
    out = tmp_path / "canon.mid"
    _write_midi(src, [(22, 0), (22, 120), (26, 120)])

    def onset_times(p: Path) -> list[float]:
        t = 0.0
        out_t: list[float] = []
        for msg in mido.MidiFile(str(p)):
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                out_t.append(round(t, 6))
        return out_t

    canonicalize_midi(src, standard="roland_td11", out_path=out)
    assert onset_times(src) == onset_times(out)
