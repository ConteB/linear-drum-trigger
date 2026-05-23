"""Layer-1 oracles for ``midi_synth.rare_emphasis`` (Layer B).

The contract: 30 deterministic grooves, 5 families × 6 sub-grooves, with the
*rare* bus voicings (crash/china/ride/tom/splash) over-represented relative to
straight GMD. Determinism (byte-for-byte) is the bedrock — the jitter pipeline
runs *downstream* of this layer.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from data_engineering.midi_synth._writer import (
    CHINA,
    CRASH_1,
    CRASH_2,
    HI_MID_TOM,
    HIGH_FLOOR_TOM,
    HIGH_TOM,
    LOW_FLOOR_TOM,
    LOW_MID_TOM,
    LOW_TOM,
    RIDE,
    RIDE_BELL,
    SPLASH,
    GrooveSpec,
    write_events_to_midi,
)
from data_engineering.midi_synth.rare_emphasis import (
    N_GROOVES,
    generate_rare_emphasis_grooves,
)

_TOM_NOTES = {HI_MID_TOM, HIGH_TOM, LOW_MID_TOM, LOW_TOM, HIGH_FLOOR_TOM, LOW_FLOOR_TOM}
_CRASH_NOTES = {CRASH_1, CRASH_2}


# ----------------------------------------------------------------------------
# Cardinality + determinism
# ----------------------------------------------------------------------------


def test_default_count_is_30() -> None:
    grooves = generate_rare_emphasis_grooves()
    assert len(grooves) == N_GROOVES == 30


def test_deterministic_across_calls() -> None:
    a = generate_rare_emphasis_grooves()
    b = generate_rare_emphasis_grooves()
    assert a == b


def test_byte_deterministic_midi_serialisation(tmp_path: Path) -> None:
    grooves = generate_rare_emphasis_grooves()
    out_a = write_events_to_midi(grooves[0], tmp_path / "a.mid")
    out_b = write_events_to_midi(grooves[0], tmp_path / "b.mid")
    assert out_a.read_bytes() == out_b.read_bytes()


def test_n_parameter_respected() -> None:
    g5 = generate_rare_emphasis_grooves(n=5)
    g30 = generate_rare_emphasis_grooves(n=30)
    assert len(g5) == 5
    assert g5 == g30[:5]


def test_rejects_out_of_range_n() -> None:
    with pytest.raises(ValueError, match="outside"):
        generate_rare_emphasis_grooves(n=0)
    with pytest.raises(ValueError, match="outside"):
        generate_rare_emphasis_grooves(n=31)


# ----------------------------------------------------------------------------
# Family coverage
# ----------------------------------------------------------------------------


def test_five_families_each_six_grooves() -> None:
    grooves = generate_rare_emphasis_grooves()
    families = [g.name.split("-")[1] for g in grooves]
    counter = Counter(families)
    # Family names contain the second segment of name (after "rare-").
    expected = {"crash_led", "china_led", "ride_led", "tom_fill_heavy", "splash_bell"}
    assert set(counter.keys()) == expected
    assert all(v == 6 for v in counter.values()), f"per-family counts: {counter}"


def test_names_are_unique() -> None:
    grooves = generate_rare_emphasis_grooves()
    assert len({g.name for g in grooves}) == len(grooves)


def test_names_have_expected_prefix() -> None:
    for g in generate_rare_emphasis_grooves():
        assert g.name.startswith("rare-"), f"unexpected name: {g.name}"


def test_bpm_values_cover_three_tiers() -> None:
    grooves = generate_rare_emphasis_grooves()
    bpms = {g.bpm for g in grooves}
    assert bpms == {90, 115, 140}


def test_bar_lengths_cover_2_and_3() -> None:
    grooves = generate_rare_emphasis_grooves()
    # Bars are encoded in the name: "bars2" / "bars3".
    bars = {g.name.split("-")[-1] for g in grooves}
    assert bars == {"bars2", "bars3"}


# ----------------------------------------------------------------------------
# Rare-emphasis substance: each family foregrounds its target bus
# ----------------------------------------------------------------------------


def _events_by_family(family: str) -> list[tuple[int, int, int]]:
    """Collect events from all grooves of the given family."""
    out: list[tuple[int, int, int]] = []
    for g in generate_rare_emphasis_grooves():
        if g.name.startswith(f"rare-{family}-"):
            out.extend(g.events)
    return out


def test_crash_led_foregrounds_crash() -> None:
    events = _events_by_family("crash_led")
    crash_count = sum(1 for _, n, _ in events if n in _CRASH_NOTES)
    # Crash on every downbeat across 6 grooves (2-3 bars × 6 grooves ~ 15+).
    assert crash_count >= 12, f"too few crashes: {crash_count}"


def test_china_led_foregrounds_china() -> None:
    events = _events_by_family("china_led")
    china_count = sum(1 for _, n, _ in events if n == CHINA)
    # China on every upbeat → 4 per bar × 12+ bars ≈ 50+.
    assert china_count >= 40, f"too few china hits: {china_count}"


def test_ride_led_foregrounds_ride() -> None:
    events = _events_by_family("ride_led")
    ride_count = sum(1 for _, n, _ in events if n in {RIDE, RIDE_BELL})
    # Ride on every eighth → 8 per bar × 12+ bars ≈ 100+.
    assert ride_count >= 80, f"too few rides: {ride_count}"


def test_tom_fill_heavy_foregrounds_toms() -> None:
    events = _events_by_family("tom_fill_heavy")
    tom_count = sum(1 for _, n, _ in events if n in _TOM_NOTES)
    # 4 toms per bar × 12+ bars ≈ 50+.
    assert tom_count >= 40, f"too few tom hits: {tom_count}"


def test_splash_bell_foregrounds_splash_and_bell() -> None:
    events = _events_by_family("splash_bell")
    splash = sum(1 for _, n, _ in events if n == SPLASH)
    bell = sum(1 for _, n, _ in events if n == RIDE_BELL)
    # Splash on every +e (4 per bar) + bell on 2-and/4-and (2 per bar).
    assert splash >= 30, f"too few splashes: {splash}"
    assert bell >= 18, f"too few bells: {bell}"


# ----------------------------------------------------------------------------
# Event hygiene (events must round-trip the writer cleanly)
# ----------------------------------------------------------------------------


def test_all_grooves_are_writable(tmp_path: Path) -> None:
    for groove in generate_rare_emphasis_grooves():
        path = tmp_path / f"{groove.name}.mid"
        write_events_to_midi(groove, path)
        assert path.exists()


def test_all_events_have_nonnegative_ticks() -> None:
    for g in generate_rare_emphasis_grooves():
        for tick, _, _ in g.events:
            assert tick >= 0, f"negative tick in {g.name}: {tick}"


def test_all_events_within_midi_velocity_range() -> None:
    for g in generate_rare_emphasis_grooves():
        for _, _, vel in g.events:
            assert 1 <= vel <= 127, f"out-of-range velocity in {g.name}: {vel}"


def test_groove_spec_is_a_namedtuple() -> None:
    g = generate_rare_emphasis_grooves(n=1)[0]
    assert isinstance(g, GrooveSpec)
    assert g.name and g.bpm > 0 and len(g.events) > 0
