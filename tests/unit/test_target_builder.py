"""Layer-1 unit oracles for the MIDI -> flat-25 target builder (F0-T2e).

These derive from the LOCKED F0-T2a §3.3 data contract and run binary-free:
the MIDI inputs are synthesised in-process with ``mido``, so no render engine
is needed. They cover the target builder's contract — layout, frame count,
numeric ranges, Gaussian onset smear, velocity/microtiming, the Hi-Hat opening
head — and its fail-loud behaviour (ENGINEERING_STANDARDS §6).
"""
from __future__ import annotations

import math
from pathlib import Path

import mido  # type: ignore[import-untyped]
import numpy as np
import pytest

from data_engineering.gold.gold_writer import R_TARGET_HZ, TARGET_COLS, n_frames
from data_engineering.gold.target_builder import (
    HIHAT_OPENING_BY_NOTE,
    BusMapping,
    TargetBuilderError,
    build_target,
    last_onset_seconds,
    load_bus_mapping,
)

# The real, versioned mapping table — the locked F0-T2a §1.1 artefact.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAPPING_TABLE = _REPO_ROOT / "docs" / "specs" / "midi_mapping_table.yaml"

# At 120 BPM with 480 ticks/beat, one tick is 1/960 s — a tidy tick<->time map.
_TPB = 480
_BPM = 120
_TICKS_PER_SECOND = _TPB * _BPM // 60  # = 960 (integer — MIDI ticks are ints)

_KICK, _SNARE = 36, 38
_HH_CLOSED, _HH_PEDAL, _HH_OPEN = 42, 44, 46


def _make_midi(path: Path, events: list[tuple[int, int, int]]) -> Path:
    """Write a MIDI of ``(abs_tick, note, velocity)`` hits at 120 BPM."""
    midi = mido.MidiFile(ticks_per_beat=_TPB)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(_BPM), time=0))

    timed: list[tuple[int, int, mido.Message]] = []
    for abs_tick, note, velocity in events:
        timed.append((abs_tick, 1, mido.Message("note_on", note=note, velocity=velocity)))
        timed.append((abs_tick + 30, 0, mido.Message("note_off", note=note, velocity=0)))
    timed.sort(key=lambda item: (item[0], item[1]))

    prev = 0
    for abs_tick, _, message in timed:
        track.append(message.copy(time=abs_tick - prev))
        prev = abs_tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(str(path))
    return path


@pytest.fixture
def bus_mapping() -> BusMapping:
    """The real GM -> 8-bus mapping loaded from the versioned table."""
    return load_bus_mapping(_MAPPING_TABLE)


# --------------------------------------------------------------------------
# load_bus_mapping
# --------------------------------------------------------------------------
def test_mapping_table_loads_the_nine_channels(bus_mapping: BusMapping) -> None:
    """The locked table maps kick/snare/hi-hat onto channels 0/1/3 (0-based, F0-T19)."""
    assert bus_mapping.schema_version == "2.0"
    assert bus_mapping.gm_to_bus[_KICK] == 0
    assert bus_mapping.gm_to_bus[_SNARE] == 1
    assert bus_mapping.gm_to_bus[_HH_CLOSED] == 3  # hihat is channel 4 (1-based)
    # Every mapped channel index stays inside the 9-channel contract.
    assert all(0 <= bus <= 8 for bus in bus_mapping.gm_to_bus.values())


def test_mapping_table_missing_file_fails_loud() -> None:
    """A missing mapping table raises, never returns a partial mapping."""
    with pytest.raises(TargetBuilderError, match="cannot read"):
        load_bus_mapping(_REPO_ROOT / "docs" / "specs" / "does_not_exist.yaml")


def test_mapping_table_rejects_bus_id_out_of_range(tmp_path: Path) -> None:
    """A channel id outside [1, 9] is a contract violation — fail loud."""
    bad = tmp_path / "bad.yaml"
    bad.write_text('schema_version: "1.0"\nforward_gm_to_bus: {36: 10}\n', encoding="utf-8")
    with pytest.raises(TargetBuilderError, match="channel id 10"):
        load_bus_mapping(bad)


def test_mapping_table_rejects_missing_forward_block(tmp_path: Path) -> None:
    """Without ``forward_gm_to_bus`` there is nothing to map — fail loud."""
    bad = tmp_path / "bad.yaml"
    bad.write_text('schema_version: "1.0"\n', encoding="utf-8")
    with pytest.raises(TargetBuilderError, match="forward_gm_to_bus"):
        load_bus_mapping(bad)


# --------------------------------------------------------------------------
# build_target — layout & frame count
# --------------------------------------------------------------------------
def test_target_has_flat28_shape_and_dtype(tmp_path: Path, bus_mapping: BusMapping) -> None:
    """The matrix is ``[n_frame, 28]`` float16 (F0-T19 §7b)."""
    midi = _make_midi(tmp_path / "g.mid", [(0, _KICK, 100), (480, _SNARE, 90)])
    target = build_target(midi, duration_s=2.0, bus_mapping=bus_mapping)
    assert target.shape == (n_frames(2.0), TARGET_COLS)
    assert target.dtype == np.float16


def test_frame_count_follows_the_ratified_formula(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """``n_frame = ceil(duration_s * R_target)`` (F0-T2a §3.4)."""
    midi = _make_midi(tmp_path / "g.mid", [(0, _KICK, 100)])
    target = build_target(midi, duration_s=3.0, bus_mapping=bus_mapping)
    assert target.shape[0] == math.ceil(3.0 * R_TARGET_HZ)


# --------------------------------------------------------------------------
# build_target — onset, velocity, microtiming
# --------------------------------------------------------------------------
#: A MIDI tick that lands *exactly* on target frame 735 at the ratified
#: R_target (tick 2048 -> 2048 * 44100 / (480*120/60 * 128) = frame 735): an
#: onset on a frame centre makes the Gaussian peak reach a clean 1.0.
_ON_GRID_TICK = 2048
_ON_GRID_FRAME = 735


def test_onset_is_gaussian_smeared_not_a_spike(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """An onset is a soft Gaussian bump, not a lone digital 1 (DOSSIER §6.2)."""
    midi = _make_midi(tmp_path / "g.mid", [(_ON_GRID_TICK, _KICK, 100)])
    target = build_target(midi, duration_s=3.0, bus_mapping=bus_mapping)
    onset = target[:, 0].astype(np.float32)  # bus 0 onset column

    peak_frame = int(np.argmax(onset))
    assert peak_frame == _ON_GRID_FRAME
    # An onset exactly on a frame centre peaks at a clean 1.0.
    assert onset[peak_frame] == pytest.approx(1.0, abs=0.01)
    # The smear writes its neighbours — it is not a digital spike.
    assert onset[peak_frame - 1] > 0.1
    assert onset[peak_frame + 1] > 0.1
    assert onset[peak_frame - 1] < onset[peak_frame]  # symmetric decay
    assert onset[peak_frame + 1] < onset[peak_frame]


def test_velocity_is_normalised_from_midi_range(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """Velocity column holds ``midi_velocity / 127`` (F0-T2a §3.5)."""
    midi = _make_midi(tmp_path / "g.mid", [(0, _KICK, 127), (_TICKS_PER_SECOND, _SNARE, 64)])
    target = build_target(midi, duration_s=2.0, bus_mapping=bus_mapping)
    assert target[:, 1].astype(np.float32).max() == pytest.approx(1.0, abs=0.01)
    snare_vel = target[:, 4].astype(np.float32)
    assert snare_vel.max() == pytest.approx(64 / 127, abs=0.01)


def test_numeric_ranges_respect_the_contract(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """onset/velocity in [0,1], microtiming in [-1,1], hi-hat in [0,1] (§3.5)."""
    events = [
        (0, _KICK, 110), (240, _HH_CLOSED, 80), (480, _SNARE, 95),
        (720, _HH_OPEN, 100), (960, _KICK, 120),
    ]
    target = build_target(
        _make_midi(tmp_path / "g.mid", events), duration_s=2.0, bus_mapping=bus_mapping
    ).astype(np.float32)
    for bus in range(9):
        assert target[:, 3 * bus].min() >= 0.0 and target[:, 3 * bus].max() <= 1.0
        assert target[:, 3 * bus + 1].min() >= 0.0 and target[:, 3 * bus + 1].max() <= 1.0
        micro = target[:, 3 * bus + 2]
        assert micro.min() >= -1.0 and micro.max() <= 1.0
    assert target[:, 27].min() >= 0.0 and target[:, 27].max() <= 1.0


def test_microtiming_encodes_the_sub_frame_residual(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """An onset off the frame grid carries a non-zero microtiming residual."""
    # Half a frame period is sr/R/2 samples; pick a time deliberately between
    # two frames so the residual is clearly non-zero.
    off_grid_s = 0.5 + (0.5 / R_TARGET_HZ)
    tick = round(off_grid_s * _TICKS_PER_SECOND)
    midi = _make_midi(tmp_path / "g.mid", [(tick, _KICK, 100)])
    target = build_target(midi, duration_s=2.0, bus_mapping=bus_mapping).astype(np.float32)
    micro = target[:, 2]
    assert np.any(micro != 0.0), "off-grid onset must carry a microtiming residual"


# --------------------------------------------------------------------------
# build_target — Hi-Hat opening head
# --------------------------------------------------------------------------
def test_hihat_opening_head_tracks_articulation(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """Closed -> 0, open -> 1; the head is step-held between hits (§3.3)."""
    midi = _make_midi(
        tmp_path / "g.mid",
        [(_TICKS_PER_SECOND, _HH_CLOSED, 90), (2 * _TICKS_PER_SECOND, _HH_OPEN, 90)],
    )
    target = build_target(midi, duration_s=3.0, bus_mapping=bus_mapping).astype(np.float32)
    opening = target[:, 27]
    assert opening[0] == 0.0  # closed before any hit
    assert opening[-1] == pytest.approx(HIHAT_OPENING_BY_NOTE[_HH_OPEN])  # held open
    assert set(np.unique(opening)).issubset({0.0, 0.5, 1.0})


def _make_midi_with_cc4(
    path: Path, notes: list[tuple[int, int, int]], cc4: list[tuple[int, int]]
) -> Path:
    """MIDI of note hits + CC#4 (hi-hat pedal) events, both in absolute ticks."""
    midi = mido.MidiFile(ticks_per_beat=_TPB)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(_BPM), time=0))
    timed: list[tuple[int, int, mido.Message]] = []
    for abs_tick, note, vel in notes:
        timed.append((abs_tick, 1, mido.Message("note_on", note=note, velocity=vel)))
        timed.append((abs_tick + 30, 0, mido.Message("note_off", note=note, velocity=0)))
    for abs_tick, value in cc4:
        timed.append((abs_tick, 2, mido.Message("control_change", control=4, value=value)))
    timed.sort(key=lambda item: (item[0], item[1]))
    prev = 0
    for abs_tick, _, message in timed:
        track.append(message.copy(time=abs_tick - prev))
        prev = abs_tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(str(path))
    return path


def test_hihat_opening_head_uses_cc4_pedal_when_present(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """With CC#4 present, the opening head = clamp(1 - cc4/127) (F0-T19 §7b).

    Empirically (GMD probe 2026-05-29): high pedal pressure = closed = low
    openness, so CC#4 = 0 -> fully open (1.0), CC#4 = 127 -> fully closed (0.0).
    The continuous pedal supersedes the discrete-note articulations.
    """
    # CC4=0 (open) at t=0; CC4=127 (closed) at t=1 s. A hi-hat hit anchors mapped onsets.
    midi = _make_midi_with_cc4(
        tmp_path / "g.mid",
        notes=[(0, _HH_CLOSED, 90), (2 * _TICKS_PER_SECOND, _HH_CLOSED, 90)],
        cc4=[(0, 0), (_TICKS_PER_SECOND, 127)],
    )
    target = build_target(midi, duration_s=3.0, bus_mapping=bus_mapping).astype(np.float32)
    opening = target[:, 27]
    early = int(0.5 * R_TARGET_HZ)  # within the open (CC4=0) segment
    late = int(2.0 * R_TARGET_HZ)   # within the closed (CC4=127) segment
    assert opening[early] == pytest.approx(1.0, abs=1e-3)
    assert opening[late] == pytest.approx(0.0, abs=1e-3)


# --------------------------------------------------------------------------
# build_target — collapse, fail-loud, determinism
# --------------------------------------------------------------------------
def test_collapsed_bus_keeps_the_louder_event(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """Two snare hits on one frame collapse to the louder one (F0-T2a §5)."""
    # Notes 38 and 40 both map to the snare bus; place them on the same tick.
    midi = _make_midi(tmp_path / "g.mid", [(480, 38, 60), (480, 40, 120)])
    target = build_target(midi, duration_s=2.0, bus_mapping=bus_mapping).astype(np.float32)
    assert target[:, 4].max() == pytest.approx(120 / 127, abs=0.01)


def test_empty_midi_fails_loud_by_default(tmp_path: Path, bus_mapping: BusMapping) -> None:
    """A MIDI with no mapped drum notes would give an empty target — fail loud."""
    midi = _make_midi(tmp_path / "g.mid", [(0, 60, 100)])  # note 60 is not a GM drum note
    with pytest.raises(TargetBuilderError, match="no GM drum notes"):
        build_target(midi, duration_s=2.0, bus_mapping=bus_mapping)


def test_empty_midi_allowed_when_explicitly_requested(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """``allow_empty`` permits a deliberate silence scenario (an all-zero target)."""
    midi = _make_midi(tmp_path / "g.mid", [(0, 60, 100)])
    target = build_target(midi, duration_s=1.0, bus_mapping=bus_mapping, allow_empty=True)
    assert not np.any(target)


def test_non_positive_duration_fails_loud(tmp_path: Path, bus_mapping: BusMapping) -> None:
    """A non-positive duration cannot define a target — fail loud."""
    midi = _make_midi(tmp_path / "g.mid", [(0, _KICK, 100)])
    with pytest.raises(TargetBuilderError, match="duration_s"):
        build_target(midi, duration_s=0.0, bus_mapping=bus_mapping)


def test_missing_midi_fails_loud(tmp_path: Path, bus_mapping: BusMapping) -> None:
    """A missing MIDI file fails loud (ENGINEERING_STANDARDS §6)."""
    with pytest.raises(TargetBuilderError, match="not found"):
        build_target(tmp_path / "absent.mid", duration_s=1.0, bus_mapping=bus_mapping)


def test_unmapped_notes_are_ignored_not_fatal(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """Notes outside the 8-bus map are dropped; mapped ones still transcribe."""
    midi = _make_midi(tmp_path / "g.mid", [(0, _KICK, 100), (240, 60, 100)])
    target = build_target(midi, duration_s=2.0, bus_mapping=bus_mapping)
    assert np.any(target[:, 0])  # the kick survived


def test_build_target_is_deterministic(tmp_path: Path, bus_mapping: BusMapping) -> None:
    """Same MIDI in -> bit-identical target out (ENGINEERING_STANDARDS §1)."""
    midi = _make_midi(tmp_path / "g.mid", [(0, _KICK, 100), (480, _SNARE, 90)])
    first = build_target(midi, duration_s=2.0, bus_mapping=bus_mapping)
    second = build_target(midi, duration_s=2.0, bus_mapping=bus_mapping)
    assert np.array_equal(first, second)


# --------------------------------------------------------------------------
# last_onset_seconds — F0-T2a §3.8 (tail standardization anchor)
# --------------------------------------------------------------------------
def test_last_onset_seconds_returns_the_last_mapped_event(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """``last_onset_seconds`` is the time of the latest mapped onset, in seconds."""
    # Kick @ 0 ticks, Snare @ 960 ticks (= 1.0 s at 120 BPM / 480 TPB).
    midi = _make_midi(tmp_path / "g.mid", [(0, _KICK, 100), (960, _SNARE, 90)])
    assert last_onset_seconds(midi, bus_mapping=bus_mapping) == pytest.approx(1.0, abs=1e-6)


def test_last_onset_seconds_ignores_unmapped_notes(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """An unmapped note later in time is NOT the last onset — only mapped events count."""
    # Kick at 0 (mapped), pitch 60 at 1920 ticks (= 2.0 s, not in drum map).
    midi = _make_midi(tmp_path / "g.mid", [(0, _KICK, 100), (1920, 60, 100)])
    assert last_onset_seconds(midi, bus_mapping=bus_mapping) == pytest.approx(0.0, abs=1e-6)


def test_last_onset_seconds_empty_midi_fails_loud(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """A MIDI with no mapped drum onsets cannot anchor the tail — fail loud by default."""
    midi = _make_midi(tmp_path / "g.mid", [(0, 60, 100)])  # non-drum only
    with pytest.raises(TargetBuilderError, match="last_onset_s"):
        last_onset_seconds(midi, bus_mapping=bus_mapping)


def test_last_onset_seconds_empty_midi_allowed_explicitly(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """Deliberate silence scenarios get ``0.0`` when ``allow_empty=True``."""
    midi = _make_midi(tmp_path / "g.mid", [(0, 60, 100)])
    assert last_onset_seconds(midi, bus_mapping=bus_mapping, allow_empty=True) == 0.0


def test_last_onset_seconds_missing_midi_fails_loud(
    tmp_path: Path, bus_mapping: BusMapping
) -> None:
    """An unreadable MIDI fails loud — never silently returns a default."""
    with pytest.raises(TargetBuilderError, match="MIDI file not found"):
        last_onset_seconds(tmp_path / "absent.mid", bus_mapping=bus_mapping)
