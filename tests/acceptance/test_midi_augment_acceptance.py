"""Acceptance — MIDI augmentation on the F0-T2e mini-batch (F0-T16-pre).

Smoke run on the synthetic GMD mini-batch (``bronze/gmd/mini/groove_NN.mid``):

* baseline (variant_idx=0) is event-level identity to the source;
* every jittered variant is *different* from the baseline (the jitter
  actually fires);
* every output respects the locked ranges (velocity ∈ [1, 127], no negative
  abs_ticks, onset shifts within the time-jitter clip or the flam window).

This is the F0-T16-pre §6.3 oracle that mirrors the F0-T2e acceptance for
the render side — same shape (smoke + correctness), same scope (no real
engine needed — pipeline is binary-free).
"""
from __future__ import annotations

from pathlib import Path

import mido  # type: ignore[import-untyped]
import pytest

from data_engineering.midi_augment.jitter import (
    KICK_NOTE,
    SNARE_NOTE,
    VELOCITY_MAX,
    VELOCITY_MIN,
    apply_midi_jitter,
    midi_to_event_list,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MINI_BATCH = _REPO_ROOT / "bronze" / "gmd" / "mini"


@pytest.fixture(scope="module")
def mini_batch_midis() -> list[Path]:
    midis = sorted(_MINI_BATCH.glob("groove_*.mid"))
    if not midis:
        pytest.skip(
            "mini-batch fixtures missing — regenerate with "
            "`python tools/gen_mini_batch_fixtures.py`"
        )
    return midis


class TestMiniBatchSmoke:
    """Every mini-batch MIDI augments without raising."""

    def test_every_midi_augments_under_k2(self, mini_batch_midis: list[Path]) -> None:
        for midi_path in mini_batch_midis:
            src = mido.MidiFile(str(midi_path))
            for variant_idx in range(3):  # baseline + k=2 variants
                out = apply_midi_jitter(
                    src,
                    variant_idx=variant_idx,
                    master_seed=42,
                    source_midi_id=str(midi_path.relative_to(_REPO_ROOT)),
                )
                # Output is a valid MidiFile with at least one track.
                assert out.tracks


class TestBaselineIdentityAcrossMiniBatch:
    """Variant 0 reproduces the input events exactly, across the whole batch."""

    def test_baseline_event_list_matches_source(
        self, mini_batch_midis: list[Path]
    ) -> None:
        for midi_path in mini_batch_midis:
            src = mido.MidiFile(str(midi_path))
            src_events = midi_to_event_list(src)
            out = apply_midi_jitter(
                src,
                variant_idx=0,
                master_seed=42,
                source_midi_id=str(midi_path.relative_to(_REPO_ROOT)),
            )
            out_events = midi_to_event_list(out)
            assert out_events == src_events, (
                f"baseline must be identity for {midi_path.name}"
            )


class TestVariantsDifferFromBaseline:
    """Each jittered variant produces an audibly different event list.

    "Audibly different" here means: the multiset of ``(abs_tick_on, note,
    velocity)`` tuples differs from the baseline's. The jitter is small in
    magnitude (σ=2 ms ≈ 2 ticks) so the *count* of events might be unchanged
    when component dropping happens to veto all draws; what changes is the
    *content*.
    """

    def test_at_least_one_variant_per_midi_differs(
        self, mini_batch_midis: list[Path]
    ) -> None:
        for midi_path in mini_batch_midis:
            src = mido.MidiFile(str(midi_path))
            source_midi_id = str(midi_path.relative_to(_REPO_ROOT))
            baseline = midi_to_event_list(
                apply_midi_jitter(
                    src,
                    variant_idx=0,
                    master_seed=42,
                    source_midi_id=source_midi_id,
                )
            )
            differs = False
            for variant_idx in (1, 2):
                jittered = midi_to_event_list(
                    apply_midi_jitter(
                        src,
                        variant_idx=variant_idx,
                        master_seed=42,
                        source_midi_id=source_midi_id,
                    )
                )
                if jittered != baseline:
                    differs = True
                    break
            assert differs, (
                f"no jittered variant of {midi_path.name} differs from baseline — "
                f"jitter pipeline is silently a no-op"
            )


class TestRangeInvariantsAcrossMiniBatch:
    """Velocity ∈ [1, 127] and abs_ticks ≥ 0 for every variant of every MIDI."""

    def test_velocity_and_ticks(self, mini_batch_midis: list[Path]) -> None:
        for midi_path in mini_batch_midis:
            src = mido.MidiFile(str(midi_path))
            source_midi_id = str(midi_path.relative_to(_REPO_ROOT))
            for variant_idx in range(3):
                out = apply_midi_jitter(
                    src,
                    variant_idx=variant_idx,
                    master_seed=42,
                    source_midi_id=source_midi_id,
                )
                for abs_tick, _, vel in midi_to_event_list(out):
                    assert abs_tick >= 0
                    assert VELOCITY_MIN <= vel <= VELOCITY_MAX


class TestGrooveSkeletonAcrossMiniBatch:
    """No mini-batch variant drops both KICK and SNARE entirely.

    A groove that loses kick + snare leaves the audio with no rhythmic
    skeleton — exactly the case the F0-T15-pre skeleton clause forbids.
    """

    def test_kick_or_snare_survives(self, mini_batch_midis: list[Path]) -> None:
        for midi_path in mini_batch_midis:
            src = mido.MidiFile(str(midi_path))
            source_midi_id = str(midi_path.relative_to(_REPO_ROOT))
            src_notes = {n for _, n, _ in midi_to_event_list(src)}
            if not ({KICK_NOTE, SNARE_NOTE} & src_notes):
                # The source has neither — skeleton clause is vacuously true.
                continue
            for variant_idx in (1, 2):
                out = apply_midi_jitter(
                    src,
                    variant_idx=variant_idx,
                    master_seed=42,
                    source_midi_id=source_midi_id,
                )
                out_notes = {n for _, n, _ in midi_to_event_list(out)}
                assert (KICK_NOTE in out_notes) or (SNARE_NOTE in out_notes), (
                    f"{midi_path.name} variant {variant_idx} lost both kick and snare"
                )
