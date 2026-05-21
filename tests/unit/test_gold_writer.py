"""§6.2 — Gold-tensor writer oracle.

Critical module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3).
Contract: F0-T2a §3. Written test-first — awaiting F0-T2d.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from data_engineering.gold.gold_writer import (
    HIHAT_OPENING_COL,
    R_TARGET_HZ,
    GoldWriterError,
    bus_columns,
    n_frames,
    write_gold_sample,
)
from harness import awaiting

pytestmark = pytest.mark.critical


@awaiting("F0-T2d")
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


@awaiting("F0-T2d")
@pytest.mark.parametrize(
    "bus, cols",
    [
        pytest.param(0, (0, 1, 2), id="bus-0"),
        pytest.param(1, (3, 4, 5), id="bus-1"),
        pytest.param(7, (21, 22, 23), id="bus-7"),
    ],
)
def test_bus_columns_follow_flat25_layout(bus, cols) -> None:
    # F0-T2a §3.3 — bus b -> columns (3b, 3b+1, 3b+2).
    assert bus_columns(bus) == cols


@awaiting("F0-T2d")
def test_bus_columns_never_collide_with_hihat_head() -> None:
    # The 24 onset/vel/microtiming columns must not overlap the Hi-Hat head.
    for bus in range(8):
        assert max(bus_columns(bus)) < HIHAT_OPENING_COL


@awaiting("F0-T2d")
def test_writes_the_sample_triple(gold_dir, make_audio, make_target, sample_dna) -> None:
    key = "GMD042-V1T1-DGZ-R2-C1H0-SLK102"
    write_gold_sample(
        gold_dir, key, audio=make_audio(), target=make_target(), dna=sample_dna
    )
    # F0-T2a §3.1 — the audio/target/dna triple, keyed by the barcode.
    assert (gold_dir / f"{key}.audio.f16").exists()
    assert (gold_dir / f"{key}.target.f16").exists()
    assert (gold_dir / f"{key}.dna.json").exists()


@awaiting("F0-T2d")
def test_rejects_non_finite_audio(gold_dir, make_audio, make_target, sample_dna) -> None:
    # ENGINEERING_STANDARDS §6 / F0-T2a §3.7 — fail loud, never write NaN/Inf.
    bad = make_audio()
    bad[0, 0] = np.inf
    with pytest.raises(GoldWriterError):
        write_gold_sample(gold_dir, "K", audio=bad, target=make_target(), dna=sample_dna)


@awaiting("F0-T2d")
def test_rejects_silent_zero_audio(gold_dir, make_audio, make_target, sample_dna) -> None:
    # ENGINEERING_STANDARDS §6 — an identically-zero render is a structural defect.
    silent = make_audio(fill=0.0)
    with pytest.raises(GoldWriterError):
        write_gold_sample(gold_dir, "K", audio=silent, target=make_target(), dna=sample_dna)


@awaiting("F0-T2d")
def test_rejects_wrong_target_width(gold_dir, make_audio, sample_dna) -> None:
    # F0-T2a §3.3 — the target matrix is flat-25; 24 columns is a violation.
    bad_target = np.zeros((128, 24), dtype=np.float16)
    with pytest.raises(GoldWriterError):
        write_gold_sample(
            gold_dir, "K", audio=make_audio(), target=bad_target, dna=sample_dna
        )
