"""§6.2 — Gold-tensor writer oracle.

Critical module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3).
Contract: F0-T2a §3. Written test-first (F0-T9b); implemented by F0-T2d.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from data_engineering.gold.gold_writer import (
    HIHAT_OPENING_COL,
    N_CHANNELS,
    R_TARGET_HZ,
    TARGET_COLS,
    GoldWriterError,
    bus_columns,
    n_frames,
    write_gold_sample,
)

pytestmark = pytest.mark.critical


@pytest.mark.parametrize(
    "duration_s, expected",
    [
        pytest.param(0.0, 0, id="zero-duration"),
        pytest.param(1.0, math.ceil(R_TARGET_HZ), id="one-second"),
        pytest.param(10.0, math.ceil(10.0 * R_TARGET_HZ), id="ten-seconds"),
    ],
)
def test_n_frames_is_ceil_of_duration_times_rate(duration_s, expected) -> None:
    # F0-T2a §3.4 — n_frame = ceil(duration_s * R_target).
    assert n_frames(duration_s) == expected


@pytest.mark.parametrize(
    "bus, cols",
    [
        pytest.param(0, (0, 1, 2), id="bus-0"),
        pytest.param(1, (3, 4, 5), id="bus-1"),
        pytest.param(7, (21, 22, 23), id="bus-7"),
        pytest.param(8, (24, 25, 26), id="bus-8"),
    ],
)
def test_bus_columns_follow_flat28_layout(bus, cols) -> None:
    # F0-T19 §7b — channel b -> columns (3b, 3b+1, 3b+2).
    assert bus_columns(bus) == cols


def test_bus_columns_never_collide_with_hihat_head() -> None:
    # The 27 onset/vel/microtiming columns must not overlap the Hi-Hat head.
    for bus in range(N_CHANNELS):
        assert max(bus_columns(bus)) < HIHAT_OPENING_COL


def test_writes_the_sample_triple(gold_dir, make_audio, make_target, sample_dna) -> None:
    key = "GMD042-V1T1-DGZ-R2-C1H0-SLK102"
    write_gold_sample(
        gold_dir, key, audio=make_audio(), target=make_target(), dna=sample_dna
    )
    # F0-T2a §3.1 — the audio/target/dna triple, keyed by the barcode.
    assert (gold_dir / f"{key}.audio.f16").exists()
    assert (gold_dir / f"{key}.target.f16").exists()
    assert (gold_dir / f"{key}.dna.json").exists()


def test_rejects_non_finite_audio(gold_dir, make_audio, make_target, sample_dna) -> None:
    # ENGINEERING_STANDARDS §6 / F0-T2a §3.7 — fail loud, never write NaN/Inf.
    bad = make_audio()
    bad[0, 0] = np.inf
    with pytest.raises(GoldWriterError, match="NaN/Inf"):
        write_gold_sample(gold_dir, "K", audio=bad, target=make_target(), dna=sample_dna)


def test_rejects_silent_zero_audio(gold_dir, make_audio, make_target, sample_dna) -> None:
    # ENGINEERING_STANDARDS §6 — an identically-zero render is a structural defect.
    silent = make_audio(fill=0.0)
    with pytest.raises(GoldWriterError, match="silent-zero"):
        write_gold_sample(gold_dir, "K", audio=silent, target=make_target(), dna=sample_dna)


def test_rejects_wrong_target_width(gold_dir, make_audio, sample_dna) -> None:
    # F0-T19 §7b — the target matrix is flat-28; 24 columns is a violation.
    bad_target = np.zeros((128, 24), dtype=np.float16)
    with pytest.raises(GoldWriterError, match="flat-28"):
        write_gold_sample(
            gold_dir, "K", audio=make_audio(), target=bad_target, dna=sample_dna
        )


# --------------------------------------------------------------------------
# F0-T2d coverage — failure modes & on-disk byte contract
# --------------------------------------------------------------------------


def test_n_frames_rejects_negative_duration() -> None:
    with pytest.raises(GoldWriterError, match="must be >= 0"):
        n_frames(-0.001)


def test_n_frames_honours_custom_rate() -> None:
    # The rate is a parameter; ceil applies whatever rate is passed.
    assert n_frames(2.0, r_target_hz=100.0) == 200
    assert n_frames(2.0, r_target_hz=100.5) == 201


@pytest.mark.parametrize("bad_bus", [-1, N_CHANNELS, 99])
def test_bus_columns_rejects_out_of_range(bad_bus) -> None:
    # channel 9 would land on (27, 28, 29) — past the Hi-Hat head.
    with pytest.raises(GoldWriterError, match="channel index"):
        bus_columns(bad_bus)


def test_rejects_non_finite_target(gold_dir, make_audio, make_target, sample_dna) -> None:
    bad = make_target()
    bad[0, 0] = np.nan
    with pytest.raises(GoldWriterError, match="NaN/Inf"):
        write_gold_sample(gold_dir, "K", audio=make_audio(), target=bad, dna=sample_dna)


def test_rejects_non_float16_audio(gold_dir, make_audio, make_target, sample_dna) -> None:
    # F0-T2a §3.2 — the buffer is float16; float32 silently doubles every byte.
    bad = make_audio().astype(np.float32)
    with pytest.raises(GoldWriterError, match="float16"):
        write_gold_sample(gold_dir, "K", audio=bad, target=make_target(), dna=sample_dna)


def test_rejects_non_float16_target(gold_dir, make_audio, make_target, sample_dna) -> None:
    bad = make_target().astype(np.float32)
    with pytest.raises(GoldWriterError, match="float16"):
        write_gold_sample(gold_dir, "K", audio=make_audio(), target=bad, dna=sample_dna)


def test_rejects_one_dimensional_audio(gold_dir, make_target, sample_dna) -> None:
    flat = np.ones(4096, dtype=np.float16)
    with pytest.raises(GoldWriterError, match="2-D"):
        write_gold_sample(gold_dir, "K", audio=flat, target=make_target(), dna=sample_dna)


@pytest.mark.parametrize("n_mic", [0, 9])
def test_rejects_audio_channel_count_out_of_range(
    gold_dir, make_target, sample_dna, n_mic
) -> None:
    # F0-T2a §3.2 — n_mic in [1, 8].
    bad = np.ones((n_mic, 256), dtype=np.float16)
    with pytest.raises(GoldWriterError, match="n_mic"):
        write_gold_sample(gold_dir, "K", audio=bad, target=make_target(), dna=sample_dna)


def test_rejects_zero_sample_audio(gold_dir, make_target, sample_dna) -> None:
    empty = np.ones((4, 0), dtype=np.float16)
    with pytest.raises(GoldWriterError, match="zero samples"):
        write_gold_sample(gold_dir, "K", audio=empty, target=make_target(), dna=sample_dna)


def test_rejects_three_dimensional_target(gold_dir, make_audio, sample_dna) -> None:
    cube = np.ones((8, 8, TARGET_COLS), dtype=np.float16)
    with pytest.raises(GoldWriterError, match="2-D"):
        write_gold_sample(gold_dir, "K", audio=make_audio(), target=cube, dna=sample_dna)


def test_returns_the_output_directory(gold_dir, make_audio, make_target, sample_dna) -> None:
    out = write_gold_sample(
        gold_dir, "K", audio=make_audio(), target=make_target(), dna=sample_dna
    )
    assert out == gold_dir


def test_buffers_round_trip_as_raw_le_float16(
    gold_dir, make_audio, make_target, sample_dna
) -> None:
    # The .f16 file is raw little-endian float16 — bit-exact, no header (§3.2).
    audio, target = make_audio(n_mic=3, n_sample=512), make_target(n_frame=64)
    write_gold_sample(gold_dir, "K", audio=audio, target=target, dna=sample_dna)
    raw_audio = (gold_dir / "K.audio.f16").read_bytes()
    assert len(raw_audio) == audio.size * 2  # float16 == 2 bytes/sample
    restored = np.frombuffer(raw_audio, dtype="<f2").reshape(audio.shape)
    assert np.array_equal(restored, audio)
    raw_target = (gold_dir / "K.target.f16").read_bytes()
    assert len(raw_target) == target.size * 2


def test_dna_json_is_written_verbatim(gold_dir, make_audio, make_target, sample_dna) -> None:
    write_gold_sample(gold_dir, "K", audio=make_audio(), target=make_target(), dna=sample_dna)
    written = json.loads((gold_dir / "K.dna.json").read_text(encoding="utf-8"))
    assert written == sample_dna


@pytest.mark.parametrize("n_mic", [1, 8])
def test_accepts_channel_count_at_both_bounds(
    gold_dir, make_audio, make_target, sample_dna, n_mic
) -> None:
    # F0-T2a §3.2 — n_mic in [1, 8] is a *closed* interval; 1 and 8 are valid.
    audio = make_audio(n_mic=n_mic, n_sample=256)
    out = write_gold_sample(gold_dir, "K", audio=audio, target=make_target(), dna=sample_dna)
    raw = (out / "K.audio.f16").read_bytes()
    assert len(raw) == audio.size * 2


def test_creates_missing_parent_directories(
    tmp_path, make_audio, make_target, sample_dna
) -> None:
    # The triple must land even when out_dir does not exist yet.
    nested = tmp_path / "gold" / "train" / "shard-000"
    write_gold_sample(nested, "K", audio=make_audio(), target=make_target(), dna=sample_dna)
    assert (nested / "K.audio.f16").is_file()
    assert (nested / "K.dna.json").is_file()
