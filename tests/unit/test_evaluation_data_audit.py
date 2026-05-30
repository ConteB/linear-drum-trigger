"""Layer-1 oracles for :mod:`evaluation.data_audit` (F0-T17 §3.1)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

# Re-use the synthetic fixture factory from the common test (kept private —
# pytest collects test_evaluation_common, so the import path is stable).
from tests.unit.test_evaluation_common import _make_dna

from evaluation.data_audit import (
    N_CHANNELS,
    ONSET_PROB_FLOOR,
    TARGET_COLS,
    _build_duration_histogram,
    _count_onsets,
    _hh_articulation_counts,
    _mic_config_histogram,
    run,
)

pytestmark = pytest.mark.evaluation


# --- _count_onsets ------------------------------------------------------------


def _make_target(n_frame: int = 32) -> np.ndarray:
    return np.zeros((n_frame, TARGET_COLS), dtype=np.float32)


def test_count_onsets_zero_target_returns_zeros() -> None:
    counts, vels = _count_onsets(_make_target())
    assert counts.tolist() == [0] * N_CHANNELS
    assert all(v.size == 0 for v in vels)


def test_count_onsets_strict_local_maximum() -> None:
    """An isolated peak above the floor counts as one onset, regardless of width."""
    t = _make_target(32)
    # bus 0: a 3-frame Gaussian-like skirt 0.4 / 0.9 / 0.4 — one onset at idx 5
    t[4, 0] = 0.4
    t[5, 0] = 0.9
    t[5, 1] = 0.75  # velocity
    t[6, 0] = 0.4
    # bus 2: two clearly separated peaks
    t[10, 6] = 0.8
    t[10, 7] = 0.5
    t[20, 6] = 0.95
    t[20, 7] = 1.0

    counts, vels = _count_onsets(t)
    assert counts[0] == 1
    assert counts[2] == 2
    assert pytest.approx(vels[0].tolist()) == [0.75]
    assert pytest.approx(sorted(vels[2].tolist())) == [0.5, 1.0]


def test_count_onsets_floor_filters_subthreshold_peaks() -> None:
    t = _make_target(8)
    # bus 1: local-max but below floor → not an onset.
    t[3, 3] = ONSET_PROB_FLOOR - 0.01
    counts, _ = _count_onsets(t)
    assert counts.sum() == 0


def test_count_onsets_plateau_is_not_strict_max() -> None:
    """Two equal adjacent frames do NOT count as an onset (strict inequality)."""
    t = _make_target(8)
    t[3, 0] = 0.9
    t[4, 0] = 0.9  # plateau — neither frame is a strict local max
    counts, _ = _count_onsets(t)
    assert counts[0] == 0


# --- _hh_articulation_counts --------------------------------------------------


def test_hh_articulation_counts_segments_not_frames() -> None:
    """A long held 'open' segment counts as ONE open event, not N."""
    t = _make_target(20)
    # closed for frames 0..4, then open for 5..14, then pedal for 15..19
    t[5:15, 27] = 0.9   # open
    t[15:, 27] = 0.4    # pedal
    counts = _hh_articulation_counts(t)
    assert counts == {"closed": 1, "pedal": 1, "open": 1}


def test_hh_articulation_counts_all_zero() -> None:
    counts = _hh_articulation_counts(_make_target(8))
    assert counts == {"closed": 1, "pedal": 0, "open": 0}


# --- _build_duration_histogram ------------------------------------------------


def test_duration_histogram_uses_n_sample_div_sr(tmp_path: Path) -> None:
    """Duration = n_sample / sample_rate."""
    _make_dna(tmp_path, key="A", n_sample=44100, sample_rate=44100)  # 1.0 s
    _make_dna(tmp_path, key="B", n_sample=88200, sample_rate=44100)  # 2.0 s
    _make_dna(tmp_path, key="C", n_sample=132300, sample_rate=44100)  # 3.0 s
    from evaluation.common import scan_gold_dir

    metas = scan_gold_dir(tmp_path)
    hist = _build_duration_histogram(metas, n_bin=10)
    assert hist["min_s"] == pytest.approx(1.0)
    assert hist["max_s"] == pytest.approx(3.0)
    assert hist["mean_s"] == pytest.approx(2.0)
    assert sum(hist["counts"]) == 3


# --- _mic_config_histogram ----------------------------------------------------


def test_mic_config_histogram_counts_each_value(tmp_path: Path) -> None:
    _make_dna(tmp_path, key="A", mic_config="multitrack_full")
    _make_dna(tmp_path, key="B", mic_config="multitrack_full")
    _make_dna(tmp_path, key="C", mic_config="glyn_johns")
    from evaluation.common import scan_gold_dir

    metas = scan_gold_dir(tmp_path)
    h = _mic_config_histogram(metas)
    assert h == {"glyn_johns": 1, "multitrack_full": 2}


# --- run() end-to-end ---------------------------------------------------------


def _write_target_with_onsets(
    target_path: Path, *, n_frame: int, onsets_per_bus: list[int]
) -> None:
    """Write a target.f16 with exactly ``onsets_per_bus[b]`` strict-local-max onsets per bus."""
    t = np.zeros((n_frame, TARGET_COLS), dtype=np.float32)
    for b, n in enumerate(onsets_per_bus):
        # Evenly spaced strict-local-max peaks at frame stride 4 (avoid clashes
        # with adjacent peaks in other buses; each peak is one frame wide
        # because zero-zero-peak-zero-zero is strict-local-max by definition).
        for k in range(n):
            frame = 4 + k * 4
            assert frame < n_frame, "onset count exceeds frame budget for bus"
            t[frame, 3 * b] = 0.9
            t[frame, 3 * b + 1] = 0.7  # velocity
    target_path.write_bytes(t.astype(np.float16).tobytes())


def _make_sample_with_onsets(gold_dir: Path, key: str, onsets_per_bus: list[int],
                              n_frame: int = 64) -> None:
    gold_dir.mkdir(parents=True, exist_ok=True)
    _make_dna(gold_dir, key=key, n_frame=n_frame)
    _write_target_with_onsets(gold_dir / f"{key}.target.f16",
                              n_frame=n_frame, onsets_per_bus=onsets_per_bus)


def test_run_class_imbalance_pct_matches_onset_counts(tmp_path: Path) -> None:
    # Sample A: bus 0 → 10 onsets, every other bus → 1 (so no empty-bus failure).
    gold = tmp_path / "gold"
    _make_sample_with_onsets(gold, "A", [10, 1, 1, 1, 1, 1, 1, 1, 1])
    result = run(
        gold_dir=gold,
        thresholds=Path("src/evaluation/thresholds.yaml"),
        out_dir=tmp_path / "out",
    )
    assert result.passed is True
    # 10/(10+8) = 55.56 % for bus 0 (9 channels).
    assert result.metrics["class_imbalance_pct"][0] == pytest.approx(10 / 18 * 100.0)
    for b in range(1, N_CHANNELS):
        assert result.metrics["class_imbalance_pct"][b] == pytest.approx(1 / 18 * 100.0)


def test_run_empty_bus_surfaces_as_warning_not_failure(tmp_path: Path) -> None:
    """Empty buses are *informative* (F0-T17 §7) — surfaced in warnings, not failures."""
    gold = tmp_path / "gold"
    gold.mkdir()
    _make_sample_with_onsets(gold, "A", [10, 5, 0, 0, 0, 0, 0, 0, 0])
    result = run(
        gold_dir=gold,
        thresholds=Path("src/evaluation/thresholds.yaml"),
        out_dir=tmp_path / "out",
    )
    assert result.passed is True  # informative — never blocks
    assert result.failures == []
    assert result.metrics["empty_buses"] == [2, 3, 4, 5, 6, 7, 8]
    assert any("empty bus" in w for w in result.metrics["warnings"])


def test_run_all_buses_populated_passes(tmp_path: Path) -> None:
    gold = tmp_path / "gold"
    gold.mkdir()
    _make_sample_with_onsets(gold, "A", [4, 4, 4, 4, 4, 4, 4, 4, 4], n_frame=64)
    result = run(
        gold_dir=gold,
        thresholds=Path("src/evaluation/thresholds.yaml"),
        out_dir=tmp_path / "out",
    )
    assert result.passed is True
    assert result.metrics["empty_buses"] == []
    assert result.metrics["minority_buses"] == []  # 4/36 = 11.1 % each


def test_run_minority_buses_surfaced_but_not_blocking(tmp_path: Path) -> None:
    gold = tmp_path / "gold"
    gold.mkdir()
    # Bus 0 with 100 onsets, buses 1..7 with 2 each → 2/(100+14) ≈ 1.7 % < 5 %.
    _make_sample_with_onsets(gold, "A", [100, 2, 2, 2, 2, 2, 2, 2], n_frame=512)
    result = run(
        gold_dir=gold,
        thresholds=Path("src/evaluation/thresholds.yaml"),
        out_dir=tmp_path / "out",
    )
    assert result.passed is True  # minority is informative, not blocking
    assert result.metrics["minority_buses"] == [1, 2, 3, 4, 5, 6, 7]
    assert any("minority bus" in w for w in result.metrics["warnings"])


def test_run_writes_json_and_png(tmp_path: Path) -> None:
    gold = tmp_path / "gold"
    gold.mkdir()
    _make_sample_with_onsets(gold, "A", [4, 4, 4, 4, 4, 4, 4, 4], n_frame=64)
    out = tmp_path / "out"
    result = run(
        gold_dir=gold,
        thresholds=Path("src/evaluation/thresholds.yaml"),
        out_dir=out,
    )
    assert result.report_json.exists()
    assert result.report_png.exists()
    assert result.report_json.suffix == ".json"
    assert result.report_png.suffix == ".png"
    doc = json.loads(result.report_json.read_text())
    assert doc["module_name"] == "data_audit"
    assert doc["n_sample"] == 1


def test_run_is_deterministic(tmp_path: Path) -> None:
    """Same input → byte-identical JSON (ENGINEERING_STANDARDS §1)."""
    gold = tmp_path / "gold"
    gold.mkdir()
    _make_sample_with_onsets(gold, "A", [4, 4, 4, 4, 4, 4, 4, 4], n_frame=64)
    r1 = run(gold_dir=gold, thresholds=Path("src/evaluation/thresholds.yaml"),
             out_dir=tmp_path / "out1")
    r2 = run(gold_dir=gold, thresholds=Path("src/evaluation/thresholds.yaml"),
             out_dir=tmp_path / "out2")
    assert r1.report_json.read_bytes() == r2.report_json.read_bytes()


def test_run_corrupt_target_fails_loud(tmp_path: Path) -> None:
    """Target file with wrong size → DataAuditError."""
    from evaluation.data_audit import DataAuditError

    gold = tmp_path / "gold"
    gold.mkdir()
    _make_dna(gold, key="A", n_frame=64)
    # Truncate the target file to break the n_frame * 25 invariant.
    (gold / "A.target.f16").write_bytes(b"\x00" * 10)
    with pytest.raises(DataAuditError, match="expected"):
        run(gold_dir=gold, thresholds=Path("src/evaluation/thresholds.yaml"),
            out_dir=tmp_path / "out")


def test_run_cli_exit_code(tmp_path: Path) -> None:
    """CLI returns 0 on pass, 1 on fail (set -e contract)."""
    from evaluation.data_audit import main

    gold = tmp_path / "gold"
    gold.mkdir()
    _make_sample_with_onsets(gold, "A", [4, 4, 4, 4, 4, 4, 4, 4], n_frame=64)
    rc = main([
        "--gold-dir", str(gold),
        "--thresholds", "src/evaluation/thresholds.yaml",
        "--out", str(tmp_path / "out"),
    ])
    assert rc == 0

    # Empty buses → still exit 0 (informative module). The 1 exit path
    # belongs to a raised exception (corrupt target), tested elsewhere.
    gold2 = tmp_path / "gold2"
    gold2.mkdir()
    _make_sample_with_onsets(gold2, "B", [4, 0, 0, 0, 0, 0, 0, 0], n_frame=64)
    rc = main([
        "--gold-dir", str(gold2),
        "--thresholds", "src/evaluation/thresholds.yaml",
        "--out", str(tmp_path / "out2"),
    ])
    assert rc == 0
