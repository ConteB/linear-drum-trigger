"""Layer-2 property oracles for ``midi_augment`` (F0-T16-pre).

Hypothesis covers what hand-rolled cases can miss:
- replay determinism over wide input spaces,
- bound conservation under any RNG draw,
- no-drop / no-duplicate of the recipe matrix.
"""
from __future__ import annotations

import mido  # type: ignore[import-untyped]
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from data_engineering.midi_augment.jitter import (
    VELOCITY_MAX,
    VELOCITY_MIN,
    apply_midi_jitter,
    midi_bytes,
    midi_to_event_list,
)
from data_engineering.midi_augment.recipe_matrix import (
    build_recipe_matrix_entries,
)
from data_engineering.midi_augment.seed import derive_jitter_seed

_TPB = 480

# A reasonable subset of drum GM notes (kick/snare/hi-hat/tom/cymbal family).
_DRUM_NOTES = st.sampled_from([36, 38, 42, 44, 46, 47, 41, 49, 51])


@st.composite
def _drum_grooves(draw) -> mido.MidiFile:  # type: ignore[no-untyped-def]
    n_notes = draw(st.integers(min_value=1, max_value=24))
    # Each note: absolute tick in [0, 4 bars), pitch from the drum set,
    # velocity in [1, 127].
    ticks = sorted(
        draw(
            st.lists(
                st.integers(min_value=0, max_value=4 * 4 * _TPB),
                min_size=n_notes,
                max_size=n_notes,
            )
        )
    )
    notes = [draw(_DRUM_NOTES) for _ in range(n_notes)]
    vels = [draw(st.integers(min_value=1, max_value=127)) for _ in range(n_notes)]
    midi = mido.MidiFile(ticks_per_beat=_TPB)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    timed: list[tuple[int, int, mido.Message]] = []
    note_len = 30
    for tick, note, vel in zip(ticks, notes, vels, strict=True):
        timed.append((tick, 1, mido.Message("note_on", note=note, velocity=vel)))
        timed.append(
            (tick + note_len, 0, mido.Message("note_off", note=note, velocity=64))
        )
    timed.sort(key=lambda x: (x[0], x[1]))
    prev = 0
    for tick, _, msg in timed:
        track.append(msg.copy(time=tick - prev))
        prev = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    return midi


# Hypothesis health-check exclusions: composite generation is slow-ish.
_HARNESS = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


class TestPropertyDeterminism:
    @_HARNESS
    @given(
        midi=_drum_grooves(),
        master_seed=st.integers(min_value=0, max_value=2**31 - 1),
        variant_idx=st.integers(min_value=0, max_value=4),
    )
    def test_replay_is_bit_identical(
        self, midi: mido.MidiFile, master_seed: int, variant_idx: int
    ) -> None:
        a = midi_bytes(
            apply_midi_jitter(
                midi,
                variant_idx=variant_idx,
                master_seed=master_seed,
                source_midi_id="prop",
            )
        )
        b = midi_bytes(
            apply_midi_jitter(
                midi,
                variant_idx=variant_idx,
                master_seed=master_seed,
                source_midi_id="prop",
            )
        )
        assert a == b


class TestPropertyVelocityBounds:
    @_HARNESS
    @given(
        midi=_drum_grooves(),
        master_seed=st.integers(min_value=0, max_value=2**31 - 1),
        variant_idx=st.integers(min_value=0, max_value=4),
    )
    def test_velocity_in_range(
        self, midi: mido.MidiFile, master_seed: int, variant_idx: int
    ) -> None:
        out = apply_midi_jitter(
            midi,
            variant_idx=variant_idx,
            master_seed=master_seed,
            source_midi_id="prop",
        )
        for _, _, vel in midi_to_event_list(out):
            assert VELOCITY_MIN <= vel <= VELOCITY_MAX


class TestPropertyNonNegativeTicks:
    @_HARNESS
    @given(
        midi=_drum_grooves(),
        master_seed=st.integers(min_value=0, max_value=2**31 - 1),
        variant_idx=st.integers(min_value=1, max_value=4),
    )
    def test_no_negative_absolute_ticks(
        self, midi: mido.MidiFile, master_seed: int, variant_idx: int
    ) -> None:
        out = apply_midi_jitter(
            midi,
            variant_idx=variant_idx,
            master_seed=master_seed,
            source_midi_id="prop",
        )
        for abs_tick, _, _ in midi_to_event_list(out):
            assert abs_tick >= 0


class TestPropertyRecipeMatrix:
    @_HARNESS
    @given(
        n_midi=st.integers(min_value=1, max_value=8),
        n_engine=st.integers(min_value=1, max_value=4),
        k=st.integers(min_value=0, max_value=3),
        master_seed=st.integers(min_value=0, max_value=2**31 - 1),
    )
    def test_cardinality_no_duplicate_no_drop(
        self, n_midi: int, n_engine: int, k: int, master_seed: int
    ) -> None:
        midis = [f"m_{i}.mid" for i in range(n_midi)]
        engines_kits = [(f"e_{i}", f"k_{i}") for i in range(n_engine)]
        entries = build_recipe_matrix_entries(
            source_midi_ids=midis,
            engines_kits=engines_kits,
            k_variants=k,
            master_seed=master_seed,
        )
        # Cardinality
        assert len(entries) == n_midi * (k + 1) * n_engine
        # No duplicate (midi, variant, engine, kit) — no drops either
        keys = {
            (e.source_midi_id, e.variant_idx, e.engine, e.kit) for e in entries
        }
        assert len(keys) == len(entries)
        # Every expected key is present
        expected = {
            (m, v, e, k_) for m in midis for v in range(k + 1) for (e, k_) in engines_kits
        }
        assert keys == expected

    @_HARNESS
    @given(
        n_midi=st.integers(min_value=1, max_value=6),
        n_engine=st.integers(min_value=1, max_value=3),
        k=st.integers(min_value=0, max_value=2),
        master_seed=st.integers(min_value=0, max_value=2**31 - 1),
    )
    def test_jitter_seed_matches_derivation(
        self, n_midi: int, n_engine: int, k: int, master_seed: int
    ) -> None:
        midis = [f"m_{i}.mid" for i in range(n_midi)]
        engines_kits = [(f"e_{i}", f"k_{i}") for i in range(n_engine)]
        entries = build_recipe_matrix_entries(
            source_midi_ids=midis,
            engines_kits=engines_kits,
            k_variants=k,
            master_seed=master_seed,
        )
        for entry in entries:
            assert entry.jitter_seed == derive_jitter_seed(
                master_seed, entry.source_midi_id, entry.variant_idx
            )
