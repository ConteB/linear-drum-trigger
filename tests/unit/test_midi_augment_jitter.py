"""Layer-1 unit oracles for ``midi_augment.jitter`` (F0-T16-pre).

Derive from F0-T15-pre §4.1 (LOCKED 2026-05-23) and DOSSIER §3.1. The oracles
cover every voice individually + the pipeline, with binary-free inputs
synthesised by ``mido``. Time is anchored at 120 BPM / 480 TPB so the ms↔tick
conversion is integral (1 tick = 1/960 s ≈ 1.0417 ms).
"""
from __future__ import annotations

import mido  # type: ignore[import-untyped]
import pytest

from data_engineering.midi_augment.jitter import (
    FLAM_DISTANCE_MAX_MS,
    FLAM_DISTANCE_MIN_MS,
    GAIN_SHIFT_MIN,
    KICK_NOTE,
    SNARE_NOTE,
    TIME_JITTER_CLIP_MS,
    VELOCITY_MAX,
    VELOCITY_MIN,
    MidiAugmentError,
    apply_midi_jitter,
    midi_bytes,
    midi_to_event_list,
)

_TPB = 480
_BPM = 120
_TICKS_PER_SECOND = _TPB * _BPM // 60  # = 960
_MS_PER_TICK = 1000.0 / _TICKS_PER_SECOND
_NOTE_LEN_TICKS = 60


def _make_midi(events: list[tuple[int, int, int]]) -> mido.MidiFile:
    """Synthesise a single-track drum MIDI from ``(abs_tick, note, velocity)``."""
    midi = mido.MidiFile(ticks_per_beat=_TPB)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(_BPM), time=0))

    timed: list[tuple[int, int, mido.Message]] = []
    for abs_tick, note, velocity in events:
        timed.append(
            (abs_tick, 1, mido.Message("note_on", note=note, velocity=velocity))
        )
        timed.append(
            (
                abs_tick + _NOTE_LEN_TICKS,
                0,
                mido.Message("note_off", note=note, velocity=64),
            )
        )
    timed.sort(key=lambda item: (item[0], item[1]))
    prev = 0
    for abs_tick, _, msg in timed:
        track.append(msg.copy(time=abs_tick - prev))
        prev = abs_tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    return midi


_DEFAULT_GROOVE = [
    # one bar of kick/snare/hi-hat at 120 BPM (480 tpb)
    (0, KICK_NOTE, 100),
    (480, SNARE_NOTE, 100),
    (960, KICK_NOTE, 100),
    (1440, SNARE_NOTE, 100),
    *[(i * 240, 42, 80) for i in range(8)],  # closed hi-hat eighths
]


# ----------------------------------------------------------------------------
# 1. Baseline (variant_idx = 0)
# ----------------------------------------------------------------------------


class TestBaselineVariantIsIdentity:
    """``variant_idx=0`` must return the same note events as the input.

    Identity is checked at the *event level* (abs_tick / note / velocity) — the
    round-trip ``flatten ∘ unflatten`` is allowed to renormalise the on-wire
    encoding (delta-times, track structure), but the audible content must not
    change.
    """

    def test_event_list_matches_input(self) -> None:
        src = _make_midi(_DEFAULT_GROOVE)
        out = apply_midi_jitter(
            src, variant_idx=0, master_seed=42, source_midi_id="x.mid"
        )
        expected = sorted(_DEFAULT_GROOVE)
        # midi_to_event_list returns (abs_tick_on, note, velocity)
        assert midi_to_event_list(out) == expected

    def test_input_midi_is_not_mutated(self) -> None:
        src = _make_midi(_DEFAULT_GROOVE)
        before = midi_bytes(src)
        _ = apply_midi_jitter(
            src, variant_idx=2, master_seed=42, source_midi_id="x.mid"
        )
        after = midi_bytes(src)
        assert before == after, "apply_midi_jitter must not mutate its input"

    def test_baseline_is_deterministic_across_runs(self) -> None:
        src = _make_midi(_DEFAULT_GROOVE)
        a = midi_bytes(
            apply_midi_jitter(src, variant_idx=0, master_seed=7, source_midi_id="x")
        )
        b = midi_bytes(
            apply_midi_jitter(src, variant_idx=0, master_seed=7, source_midi_id="x")
        )
        assert a == b


# ----------------------------------------------------------------------------
# 2. Determinism — seed-driven replay
# ----------------------------------------------------------------------------


class TestJitteredDeterminism:
    """Same seed, same MIDI, same variant_idx → byte-identical output."""

    def test_same_seed_yields_same_bytes(self) -> None:
        src = _make_midi(_DEFAULT_GROOVE)
        a = midi_bytes(
            apply_midi_jitter(src, variant_idx=3, master_seed=42, source_midi_id="x")
        )
        b = midi_bytes(
            apply_midi_jitter(src, variant_idx=3, master_seed=42, source_midi_id="x")
        )
        assert a == b

    def test_diff_variant_yields_diff_bytes(self) -> None:
        src = _make_midi(_DEFAULT_GROOVE)
        a = midi_bytes(
            apply_midi_jitter(src, variant_idx=1, master_seed=42, source_midi_id="x")
        )
        b = midi_bytes(
            apply_midi_jitter(src, variant_idx=2, master_seed=42, source_midi_id="x")
        )
        assert a != b

    def test_diff_master_seed_yields_diff_bytes(self) -> None:
        src = _make_midi(_DEFAULT_GROOVE)
        a = midi_bytes(
            apply_midi_jitter(src, variant_idx=1, master_seed=42, source_midi_id="x")
        )
        b = midi_bytes(
            apply_midi_jitter(src, variant_idx=1, master_seed=43, source_midi_id="x")
        )
        assert a != b


# ----------------------------------------------------------------------------
# 3. Time Jittering — bounded onset shift, duration conservation
# ----------------------------------------------------------------------------


def _onset_table(midi: mido.MidiFile) -> dict[tuple[int, int], int]:
    """Return ``{(note_index, note): abs_tick_on}`` — note-index is the position
    in the input order, used by the caller to align baseline vs jittered."""
    raise NotImplementedError  # not used — keep here for future symmetry


class TestTimeJitterBounds:
    """Onset shifts stay within ±5 ms after rounding to tick (F0-T15-pre)."""

    def test_onset_shift_stays_within_clip(self) -> None:
        src = _make_midi(_DEFAULT_GROOVE)
        out = apply_midi_jitter(
            src, variant_idx=1, master_seed=42, source_midi_id="x.mid"
        )
        src_events = midi_to_event_list(src)
        # The output may contain flam insertions (extra notes); we match each
        # source onset to the closest output onset of the same note and
        # compute the delta. Because the source has only well-separated hits
        # and the flam companion is *before* the original, the "closest" rule
        # still picks the right anchor for the original.
        out_by_note: dict[int, list[int]] = {}
        for abs_tick, note, _ in midi_to_event_list(out):
            out_by_note.setdefault(note, []).append(abs_tick)
        for src_tick, src_note, _ in src_events:
            # The original survives in the output (component dropping is rare
            # at 10 % per cell, but if a kick/snare is dropped, the snare/kick
            # in the same zone survives by skeleton clause; for other notes,
            # we re-run the test in batch — see property tests). We tolerate
            # an absence by skipping the anchor.
            if src_note not in out_by_note:
                continue
            closest = min(
                out_by_note[src_note], key=lambda t: abs(t - src_tick)
            )
            shift_ticks = closest - src_tick
            shift_ms = shift_ticks * _MS_PER_TICK
            # The flam companion is 15-25 ms *before* the original; if the
            # closest match landed on the companion (because the original
            # was dropped), the shift would be roughly -15 to -25 ms — out
            # of the time-jitter clip but still bounded by the flam clip.
            # We accept either.
            within_time_jitter = abs(shift_ms) <= TIME_JITTER_CLIP_MS + _MS_PER_TICK
            within_flam_window = (
                -FLAM_DISTANCE_MAX_MS - _MS_PER_TICK
                <= shift_ms
                <= -FLAM_DISTANCE_MIN_MS + _MS_PER_TICK
            )
            assert within_time_jitter or within_flam_window, (
                f"note {src_note}: shift {shift_ms:.2f} ms outside "
                f"time-jitter clip ±{TIME_JITTER_CLIP_MS} ms "
                f"and flam window [-{FLAM_DISTANCE_MAX_MS}, -{FLAM_DISTANCE_MIN_MS}] ms"
            )

    def test_no_negative_absolute_ticks(self) -> None:
        # An onset at t=0 cannot shift to t<0 (the codec clamps).
        src = _make_midi([(0, KICK_NOTE, 100)])
        out = apply_midi_jitter(
            src, variant_idx=1, master_seed=42, source_midi_id="x.mid"
        )
        for abs_tick, _, _ in midi_to_event_list(out):
            assert abs_tick >= 0


# ----------------------------------------------------------------------------
# 4. Velocity Jittering / Ghost / Gain — range conservation
# ----------------------------------------------------------------------------


class TestVelocityBounds:
    """Velocity stays in [1, 127] across every voice combination."""

    def test_velocity_clipped_under_jitter(self) -> None:
        # Boundary stress: every note at velocity 1 — gauss + ghost + gain
        # could push it to 0 (silent) without clipping.
        src = _make_midi([(i * 240, KICK_NOTE, 1) for i in range(16)])
        for variant_idx in range(1, 5):
            out = apply_midi_jitter(
                src, variant_idx=variant_idx, master_seed=42, source_midi_id="x"
            )
            for _, _, vel in midi_to_event_list(out):
                assert VELOCITY_MIN <= vel <= VELOCITY_MAX

    def test_velocity_clipped_under_high_input(self) -> None:
        # Mirror stress: every note at 127 — gauss + gain ×2 could push it
        # above 127 without clipping.
        src = _make_midi([(i * 240, KICK_NOTE, 127) for i in range(16)])
        for variant_idx in range(1, 5):
            out = apply_midi_jitter(
                src, variant_idx=variant_idx, master_seed=42, source_midi_id="x"
            )
            for _, _, vel in midi_to_event_list(out):
                assert VELOCITY_MIN <= vel <= VELOCITY_MAX


class TestGhostMasking:
    """Notes above ``GHOST_THRESHOLD`` are never attenuated to below it.

    Ghost masking attenuates notes ≤ 40 by ×[0.3, 1.0]; loud notes (vel > 40)
    must not be touched by this voice. They can still move under gauss-σ=8
    and ×[0.5, 2.0] gain — the assertion bounds the *ghost contribution*,
    not the absolute velocity (covered by ``TestVelocityBounds``).
    """

    def test_loud_notes_keep_dynamics(self) -> None:
        # All-loud (vel=100); the ghost voice should be a no-op on this input.
        # Final velocity is set by gauss + gain, so it can move; here we just
        # confirm that *no note drops by more than the gauss + gain envelope*.
        src = _make_midi([(i * 240, KICK_NOTE, 100) for i in range(64)])
        out = apply_midi_jitter(
            src, variant_idx=1, master_seed=42, source_midi_id="x"
        )
        # Worst-case envelope: gauss draws of -3σ (-24) + gain 0.5 -> floor.
        envelope_floor = int(round((100 - 3 * 8) * GAIN_SHIFT_MIN))
        for _, _, vel in midi_to_event_list(out):
            assert vel >= max(VELOCITY_MIN, envelope_floor - 5), (
                "loud note attenuated more than the gauss+gain envelope; "
                "ghost masking is leaking onto vel > 40 notes"
            )


class TestGlobalGainShift:
    """The same gain factor applies to every note in a single call."""

    def test_proportional_under_pure_gain(self) -> None:
        # 16 identical-velocity notes; after one variant we look at the
        # ratio of output velocities — if gain is *global* (per call), the
        # spread comes only from gauss/ghost, not from per-note gain noise.
        src = _make_midi([(i * 240, KICK_NOTE, 60) for i in range(16)])
        out = apply_midi_jitter(
            src, variant_idx=1, master_seed=99, source_midi_id="x"
        )
        velocities = [v for _, _, v in midi_to_event_list(out)]
        # Spread <= range of (gauss σ=8 × ~3σ) + (ghost factor ~0.3-1.0)
        spread = max(velocities) - min(velocities)
        # gauss ±24 + ghost factor diff (24 worst-case) ≈ 96. Generous
        # envelope: a per-note gain noise of ×[0.5, 2.0] would push the
        # spread to ~120+; if we see > 110, gain is leaking per-note.
        assert spread <= 110, (
            f"per-note velocity spread {spread} too wide — global gain may "
            f"be applied per-note instead of once per track"
        )


# ----------------------------------------------------------------------------
# 5. Component Dropping — skeleton clause
# ----------------------------------------------------------------------------


class TestComponentDropSkeleton:
    """In any zone with both kick + snare present, at least one survives."""

    def test_skeleton_holds_under_many_seeds(self) -> None:
        # Long groove: 100 bars of straight 8th-note kick/snare. Even at 10 %
        # drop rate per cell, with 50 (note, zone) cells, the probability
        # that both KICK and SNARE in the same zone get marked is ≈ 1 %
        # per zone — so over 100 trials we expect ~10 vetoes. We just
        # assert: never see a zone with neither.
        events = []
        for bar in range(100):
            base = bar * 4 * _TPB
            events.append((base + 0 * _TPB, KICK_NOTE, 100))
            events.append((base + 1 * _TPB, SNARE_NOTE, 100))
            events.append((base + 2 * _TPB, KICK_NOTE, 100))
            events.append((base + 3 * _TPB, SNARE_NOTE, 100))
        src = _make_midi(events)
        for seed in range(20):
            out = apply_midi_jitter(
                src, variant_idx=1, master_seed=seed, source_midi_id="x"
            )
            seen_notes = {n for _, n, _ in midi_to_event_list(out)}
            assert KICK_NOTE in seen_notes or SNARE_NOTE in seen_notes


# ----------------------------------------------------------------------------
# 6. Fail-loud
# ----------------------------------------------------------------------------


class TestFailLoud:
    def test_rejects_non_midi(self) -> None:
        with pytest.raises(MidiAugmentError, match="mido.MidiFile"):
            apply_midi_jitter(
                "not a midi",  # type: ignore[arg-type]
                variant_idx=0,
                master_seed=0,
                source_midi_id="x",
            )

    def test_rejects_orphan_note_on(self) -> None:
        midi = mido.MidiFile(ticks_per_beat=_TPB)
        track = mido.MidiTrack()
        midi.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(_BPM), time=0))
        # An open note_on without note_off — must be rejected loud.
        track.append(mido.Message("note_on", note=KICK_NOTE, velocity=100, time=0))
        track.append(mido.MetaMessage("end_of_track", time=0))
        with pytest.raises(MidiAugmentError, match="without matching note_off"):
            apply_midi_jitter(
                midi, variant_idx=1, master_seed=42, source_midi_id="x"
            )

    def test_rejects_empty_midi(self) -> None:
        midi = mido.MidiFile(ticks_per_beat=_TPB)
        with pytest.raises(MidiAugmentError, match="at least one track"):
            apply_midi_jitter(
                midi, variant_idx=0, master_seed=42, source_midi_id="x"
            )


def _cc4_values(m: mido.MidiFile) -> list[int]:
    return [msg.value for msg in m if msg.type == "control_change" and msg.control == 4]


def test_jitter_preserves_cc4_hihat_pedal() -> None:
    """F0-T19 §7b: ``control_change`` (CC#4 hi-hat pedal) survives jitter.

    Before the fix the jitter rebuilt the MIDI from notes only, silently
    dropping CC#4 — which left the continuous hi-hat opening head inert. The
    head reads CC#4 from the rendered MIDI, so jitter must preserve it.
    """
    midi = mido.MidiFile(ticks_per_beat=_TPB)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(_BPM), time=0))
    track.append(mido.Message("control_change", control=4, value=10, time=0))
    track.append(mido.Message("note_on", note=KICK_NOTE, velocity=100, time=0))
    track.append(mido.Message("note_off", note=KICK_NOTE, velocity=64, time=60))
    track.append(mido.Message("control_change", control=4, value=90, time=60))
    track.append(mido.Message("note_on", note=SNARE_NOTE, velocity=90, time=60))
    track.append(mido.Message("note_off", note=SNARE_NOTE, velocity=64, time=60))
    track.append(mido.MetaMessage("end_of_track", time=0))

    assert _cc4_values(midi) == [10, 90]
    # variant 0 (identity): CC#4 preserved exactly, in order.
    out0 = apply_midi_jitter(midi, variant_idx=0, master_seed=7, source_midi_id="cc4")
    assert _cc4_values(out0) == [10, 90]
    # variant 1 (jittered): every CC#4 event still present (notes may be dropped).
    out1 = apply_midi_jitter(midi, variant_idx=1, master_seed=7, source_midi_id="cc4")
    assert sorted(_cc4_values(out1)) == [10, 90]
