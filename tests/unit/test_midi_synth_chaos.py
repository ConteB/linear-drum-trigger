"""Layer-1 oracles for ``midi_synth.chaos_generator`` (Layer C).

The chaos generator must be:

1. **Deterministic** — same ``(master_seed, index)`` ⇒ byte-identical MIDI.
2. **Off-grid** — onsets cannot be all multiples of any small tick subdivision
   (otherwise we'd be reintroducing the grid-position shortcut).
3. **Multi-bus** — every chaos groove covers all 8 logical buses (Poisson rate
   > 0 means a non-zero firing probability over a multi-second window).
4. **Bounded** — velocity ∈ [40, 120], BPM ∈ [80, 200], duration ∈ [2, 6] s.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from data_engineering.midi_synth._writer import (
    BUS_TO_GM_NOTES,
    GrooveSpec,
    write_events_to_midi,
)
from data_engineering.midi_synth.chaos_generator import (
    BPM_MAX,
    BPM_MIN,
    DURATION_S_MAX,
    DURATION_S_MIN,
    LAMBDA_MAX,
    LAMBDA_MIN,
    N_GROOVES,
    VELOCITY_MAX,
    VELOCITY_MIN,
    generate_chaos_grooves,
)

# ----------------------------------------------------------------------------
# Cardinality + determinism
# ----------------------------------------------------------------------------


def test_default_count_is_30() -> None:
    grooves = generate_chaos_grooves()
    assert len(grooves) == N_GROOVES == 30


def test_deterministic_same_seed() -> None:
    a = generate_chaos_grooves(master_seed=42)
    b = generate_chaos_grooves(master_seed=42)
    assert a == b


def test_byte_deterministic_midi(tmp_path: Path) -> None:
    grooves = generate_chaos_grooves(master_seed=42)
    a = write_events_to_midi(grooves[3], tmp_path / "a.mid")
    b = write_events_to_midi(grooves[3], tmp_path / "b.mid")
    assert a.read_bytes() == b.read_bytes()


def test_different_seed_produces_different_grooves() -> None:
    a = generate_chaos_grooves(master_seed=42)
    b = generate_chaos_grooves(master_seed=43)
    # At the very least the first groove must differ.
    assert a[0] != b[0]


def test_different_indices_produce_different_grooves() -> None:
    grooves = generate_chaos_grooves(master_seed=42, n=5)
    distinct = {tuple(g.events) for g in grooves}
    assert len(distinct) == 5, "different indices must produce different events"


def test_n_parameter_respected() -> None:
    grooves = generate_chaos_grooves(n=7)
    full = generate_chaos_grooves(n=N_GROOVES)
    assert len(grooves) == 7
    # Same seed → first 7 entries identical between the two calls.
    assert grooves == full[:7]


def test_rejects_out_of_range_n() -> None:
    with pytest.raises(ValueError, match="outside"):
        generate_chaos_grooves(n=0)
    with pytest.raises(ValueError, match="outside"):
        generate_chaos_grooves(n=31)


# ----------------------------------------------------------------------------
# Doctrine: anti-shortcut (off-grid + multi-bus + uniform velocity)
# ----------------------------------------------------------------------------


def test_onsets_are_off_grid() -> None:
    """If onsets were all multiples of a small subdivision (e.g. 16th=120 ticks)
    the grid shortcut would still be exploitable. We require at least one
    onset to fall off the 16th-note grid in each groove (the Poisson + float
    rounding guarantees this with overwhelming probability)."""
    sixteenth_ticks = 480 // 4  # = 120
    for g in generate_chaos_grooves(master_seed=42):
        ticks = [t for t, _, _ in g.events if t > 0]
        if not ticks:
            continue  # rare empty bus case
        off_grid = sum(1 for t in ticks if t % sixteenth_ticks != 0)
        assert off_grid > 0, (
            f"groove {g.name} has every onset on the 16th-note grid — chaos broken"
        )


def test_covers_all_eight_buses_in_aggregate() -> None:
    """Across the 30 grooves, every bus must fire at least once (each bus has
    λ ≥ 2 hits/s × ≥ 2 s = ≥ 4 expected hits per groove → 120+ expected hits
    per bus across 30 grooves)."""
    all_notes: set[int] = set()
    for g in generate_chaos_grooves(master_seed=42):
        all_notes.update(note for _, note, _ in g.events)
    all_kit_notes = {n for notes in BUS_TO_GM_NOTES.values() for n in notes}
    # Each bus' note set must intersect all_notes.
    for bus_id, bus_notes in BUS_TO_GM_NOTES.items():
        assert all_notes & set(bus_notes), f"bus {bus_id} never fired across 30 grooves"
    # And no note outside the kit must appear (kit-driven note selection).
    assert all_notes <= all_kit_notes


def test_velocity_within_bounds() -> None:
    for g in generate_chaos_grooves(master_seed=42):
        for _, _, vel in g.events:
            assert VELOCITY_MIN <= vel <= VELOCITY_MAX, (
                f"velocity {vel} outside [{VELOCITY_MIN}, {VELOCITY_MAX}] in {g.name}"
            )


def test_velocity_is_roughly_uniform_in_aggregate() -> None:
    """Across 30 grooves we expect ~2000+ hits; the mean velocity should be
    near the midpoint of the uniform range (no natural skew like real music)."""
    all_vel: list[int] = []
    for g in generate_chaos_grooves(master_seed=42):
        all_vel.extend(v for _, _, v in g.events)
    assert len(all_vel) >= 500, f"too few hits in aggregate: {len(all_vel)}"
    mean = sum(all_vel) / len(all_vel)
    midpoint = (VELOCITY_MIN + VELOCITY_MAX) / 2
    # Generous bounds — sample size 500+ from Uniform[40,120] has std ~23,
    # so 3-sigma on the mean is ~3 around 80; ±5 covers it comfortably.
    assert abs(mean - midpoint) < 5, (
        f"velocity mean {mean:.1f} not near uniform midpoint {midpoint}"
    )


def test_bpm_within_bounds() -> None:
    for g in generate_chaos_grooves(master_seed=42):
        assert BPM_MIN <= g.bpm <= BPM_MAX, f"bpm {g.bpm} out of range in {g.name}"


def test_onsets_nonnegative() -> None:
    for g in generate_chaos_grooves(master_seed=42):
        for tick, _, _ in g.events:
            assert tick >= 0, f"negative tick {tick} in {g.name}"


def test_onsets_sorted_chronologically() -> None:
    """The chaos generator emits events in (tick, note, vel) order."""
    for g in generate_chaos_grooves(master_seed=42):
        if not g.events:
            continue
        ticks = [t for t, _, _ in g.events]
        assert ticks == sorted(ticks), f"events not sorted in {g.name}"


# ----------------------------------------------------------------------------
# Module constants sanity
# ----------------------------------------------------------------------------


def test_lambda_bounds_match_doctrine() -> None:
    # DOSSIER §3.4 LOCKED: λ ∈ [2, 15] hits/sec.
    assert LAMBDA_MIN == 2.0
    assert LAMBDA_MAX == 15.0


def test_duration_bounds_make_sense() -> None:
    assert 0 < DURATION_S_MIN < DURATION_S_MAX


def test_all_grooves_are_writable(tmp_path: Path) -> None:
    for g in generate_chaos_grooves(master_seed=42):
        path = tmp_path / f"{g.name.replace('.', '_')}.mid"
        write_events_to_midi(g, path)
        assert path.exists()


def test_groove_spec_type() -> None:
    g = generate_chaos_grooves(n=1, master_seed=42)[0]
    assert isinstance(g, GrooveSpec)
    assert g.name.startswith("chaos-")
