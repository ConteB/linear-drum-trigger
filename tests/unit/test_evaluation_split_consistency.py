"""Layer-1 oracles for :mod:`evaluation.split_consistency` (F0-T17 §3.2)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from tests.unit.test_evaluation_common import _make_dna
from tests.unit.test_evaluation_data_audit import _write_target_with_onsets

from evaluation.common import GoldSampleMeta
from evaluation.data_audit import N_CHANNELS
from evaluation.split_consistency import (
    MODULE_NAME,
    _chi2_categorical,
    _ks_per_bus,
    _ks_scalar,
    _sha256_midi_source,
    run,
)

pytestmark = pytest.mark.evaluation


THRESHOLDS_PATH = Path("src/evaluation/thresholds.yaml")


# --- _ks_per_bus / _ks_scalar primitives --------------------------------------


def test_ks_identical_distributions_yields_high_p() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(0.5, 0.1, size=200).tolist()
    b = rng.normal(0.5, 0.1, size=200).tolist()
    res = _ks_scalar(a, b, label="x")
    assert res["p_value"] > 0.05  # not distinguishable


def test_ks_clearly_different_distributions_yields_low_p() -> None:
    rng = np.random.default_rng(1)
    a = rng.normal(0.0, 0.1, size=200).tolist()
    b = rng.normal(1.0, 0.1, size=200).tolist()
    res = _ks_scalar(a, b, label="x")
    assert res["p_value"] < 0.001


def test_ks_per_bus_skips_with_insufficient_samples() -> None:
    train_v: list[list[float]] = [[0.5]] * N_CHANNELS   # only 1 sample each
    val_v: list[list[float]] = [[0.5]] * N_CHANNELS
    rows = _ks_per_bus(train_v, val_v, label="velocity")
    assert len(rows) == N_CHANNELS
    assert all(r.get("skipped_reason") for r in rows)
    assert all(r["statistic"] is None for r in rows)


def test_ks_per_bus_returns_one_row_per_bus() -> None:
    rng = np.random.default_rng(2)
    pool_a = [rng.normal(0.5, 0.05, size=50).tolist() for _ in range(N_CHANNELS)]
    pool_b = [rng.normal(0.5, 0.05, size=50).tolist() for _ in range(N_CHANNELS)]
    rows = _ks_per_bus(pool_a, pool_b, label="velocity")
    assert [r["bus"] for r in rows] == list(range(N_CHANNELS))
    assert all(r["metric"] == "velocity" for r in rows)


# --- _chi2_categorical --------------------------------------------------------


def test_chi2_identical_categorical_yields_high_p() -> None:
    from collections import Counter

    a = Counter({"sfizz": 100, "drumgizmo": 100})
    b = Counter({"sfizz": 100, "drumgizmo": 100})
    res = _chi2_categorical(a, b, label="engine")
    assert res["p_value"] > 0.99


def test_chi2_imbalanced_categorical_yields_low_p() -> None:
    from collections import Counter

    a = Counter({"sfizz": 100, "drumgizmo": 1})
    b = Counter({"sfizz": 1, "drumgizmo": 100})
    res = _chi2_categorical(a, b, label="engine")
    assert res["p_value"] < 0.001


def test_chi2_zero_row_skips_with_reason() -> None:
    from collections import Counter

    # Train has 2 engines, val has none → categories union has 2, but val's row
    # sums to 0 → 'zero row' branch fires (the test above covers the 'single
    # category' branch by giving both sides the same single category).
    res = _chi2_categorical(
        Counter({"sfizz": 5, "drumgizmo": 5}), Counter(), label="engine"
    )
    assert res["skipped_reason"] == "one split has zero samples in this dimension"


def test_chi2_single_category_skips_with_reason() -> None:
    from collections import Counter

    a = Counter({"sfizz": 5})
    b = Counter({"sfizz": 5})
    res = _chi2_categorical(a, b, label="engine")
    assert res["skipped_reason"] == "fewer than 2 categories — chi-square undefined"


# --- _sha256_midi_source (leakage primitive) ---------------------------------


def test_midi_source_sha256_stable_across_calls() -> None:
    meta = _stub_meta("bronze/gmd/groove_42.mid")
    assert _sha256_midi_source(meta) == _sha256_midi_source(meta)


def test_midi_source_sha256_distinguishes_paths() -> None:
    a = _sha256_midi_source(_stub_meta("bronze/gmd/groove_01.mid"))
    b = _sha256_midi_source(_stub_meta("bronze/gmd/groove_02.mid"))
    assert a != b


def _stub_meta(midi_source: str) -> GoldSampleMeta:
    return GoldSampleMeta(
        key="K", dna_path=Path("/x"), audio_path=Path("/x"), target_path=Path("/x"),
        split="train", engine="sfizz", kit="DRSKit", mic_config="mono",
        sample_rate=44100, midi_source=midi_source,
        n_mic=1, n_sample=44100, n_frame=128,
        audio_sha256="", target_sha256="", recipe_sha256="",
        jitter_variant_idx=0, augmentation_level=1,
    )


# --- run() — fixture-driven scenarios ----------------------------------------


def _make_gold_with_splits(
    root: Path,
    *,
    train: list[tuple[str, dict]],
    val: list[tuple[str, dict]],
    onsets_per_bus: list[int] | None = None,
    n_frame: int = 64,
    flat: bool = True,
) -> Path:
    """Build a Gold dir with given train/val samples.

    If ``flat=True`` (default): one directory with samples carrying ``split``
    in their DNA. Otherwise builds ``root/train/`` and ``root/val/``.
    """
    if onsets_per_bus is None:
        onsets_per_bus = [3] * N_CHANNELS
    base_train = root if flat else root / "train"
    base_val = root if flat else root / "val"
    base_train.mkdir(parents=True, exist_ok=True)
    base_val.mkdir(parents=True, exist_ok=True)
    for key, overrides in train:
        _make_dna(base_train, key=key, split="train", n_frame=n_frame, **overrides)
        _write_target_with_onsets(
            base_train / f"{key}.target.f16",
            n_frame=n_frame,
            onsets_per_bus=onsets_per_bus,
        )
    for key, overrides in val:
        _make_dna(base_val, key=key, split="val", n_frame=n_frame, **overrides)
        _write_target_with_onsets(
            base_val / f"{key}.target.f16",
            n_frame=n_frame,
            onsets_per_bus=onsets_per_bus,
        )
    return root


def test_run_identical_distributions_passes(tmp_path: Path) -> None:
    """Train and val drawn from the same recipe distribution → PASS."""
    train = [(f"TRAIN-{i:03d}", {"midi_source": f"bronze/gmd/t{i}.mid"}) for i in range(30)]
    val = [(f"VAL-{i:03d}", {"midi_source": f"bronze/gmd/v{i}.mid"}) for i in range(30)]
    gold = _make_gold_with_splits(tmp_path / "gold", train=train, val=val)
    result = run(gold_dir=gold, thresholds=THRESHOLDS_PATH, out_dir=tmp_path / "out")
    assert result.passed is True, result.failures
    assert result.metrics["n_train"] == 30
    assert result.metrics["n_val"] == 30
    assert result.metrics["midi_leakage_count"] == 0


def test_run_midi_leakage_fails(tmp_path: Path) -> None:
    """Same bronze MIDI in both splits → leakage failure."""
    shared = "bronze/gmd/SHARED.mid"
    train = [(f"T{i}", {"midi_source": shared}) for i in range(5)]
    val = [(f"V{i}", {"midi_source": shared}) for i in range(5)]
    gold = _make_gold_with_splits(tmp_path / "gold", train=train, val=val)
    result = run(gold_dir=gold, thresholds=THRESHOLDS_PATH, out_dir=tmp_path / "out")
    assert result.passed is False
    assert any("MIDI leakage" in f for f in result.failures)
    assert result.metrics["midi_leakage_count"] == 1


def test_run_engine_imbalance_chi2_fails(tmp_path: Path) -> None:
    """Train all-sfizz vs val all-drumgizmo → χ² engine fails (p < 0.05)."""
    train = [(f"T{i:03d}", {"midi_source": f"t{i}.mid", "engine": "sfizz",
                             "kit": "Frankensnare"}) for i in range(30)]
    val = [(f"V{i:03d}", {"midi_source": f"v{i}.mid", "engine": "drumgizmo",
                          "kit": "DRSKit"}) for i in range(30)]
    gold = _make_gold_with_splits(tmp_path / "gold", train=train, val=val)
    result = run(gold_dir=gold, thresholds=THRESHOLDS_PATH, out_dir=tmp_path / "out")
    assert result.passed is False
    assert any("engine" in f for f in result.failures)


def test_run_handles_train_val_subdirs(tmp_path: Path) -> None:
    """If gold_dir has train/ and val/ subdirs, they are read separately."""
    train = [(f"T{i:03d}", {"midi_source": f"t{i}.mid"}) for i in range(10)]
    val = [(f"V{i:03d}", {"midi_source": f"v{i}.mid"}) for i in range(10)]
    gold = _make_gold_with_splits(tmp_path / "gold", train=train, val=val, flat=False)
    result = run(gold_dir=gold, thresholds=THRESHOLDS_PATH, out_dir=tmp_path / "out")
    assert result.metrics["n_train"] == 10
    assert result.metrics["n_val"] == 10


def test_run_empty_splits_fails_loud(tmp_path: Path) -> None:
    """A directory with no valid samples raises."""
    empty = tmp_path / "gold"
    empty.mkdir()
    # The scanner itself will raise GoldScanError → SplitConsistency surfaces it.
    from evaluation.common import GoldScanError
    with pytest.raises(GoldScanError):
        run(gold_dir=empty, thresholds=THRESHOLDS_PATH, out_dir=tmp_path / "out")


def test_run_only_one_split_passes_categorical_skips(tmp_path: Path) -> None:
    """If only train exists, chi-square / KS skip gracefully (no false fail)."""
    train = [(f"T{i:03d}", {"midi_source": f"t{i}.mid"}) for i in range(10)]
    gold = _make_gold_with_splits(tmp_path / "gold", train=train, val=[])
    result = run(gold_dir=gold, thresholds=THRESHOLDS_PATH, out_dir=tmp_path / "out")
    # With empty val pools everything skips → no failures, passes.
    assert result.passed is True, result.failures


def test_run_writes_json_and_png(tmp_path: Path) -> None:
    train = [(f"T{i}", {"midi_source": f"t{i}.mid"}) for i in range(5)]
    val = [(f"V{i}", {"midi_source": f"v{i}.mid"}) for i in range(5)]
    gold = _make_gold_with_splits(tmp_path / "gold", train=train, val=val)
    result = run(gold_dir=gold, thresholds=THRESHOLDS_PATH, out_dir=tmp_path / "out")
    assert result.report_json.exists()
    assert result.report_png.exists()
    doc = json.loads(result.report_json.read_text())
    assert doc["module_name"] == MODULE_NAME


def test_run_is_deterministic(tmp_path: Path) -> None:
    train = [(f"T{i}", {"midi_source": f"t{i}.mid"}) for i in range(10)]
    val = [(f"V{i}", {"midi_source": f"v{i}.mid"}) for i in range(10)]
    gold = _make_gold_with_splits(tmp_path / "gold", train=train, val=val)
    r1 = run(gold_dir=gold, thresholds=THRESHOLDS_PATH, out_dir=tmp_path / "out1")
    r2 = run(gold_dir=gold, thresholds=THRESHOLDS_PATH, out_dir=tmp_path / "out2")
    assert r1.report_json.read_bytes() == r2.report_json.read_bytes()


def test_run_cli_exit_code(tmp_path: Path) -> None:
    from evaluation.split_consistency import main

    train = [(f"T{i}", {"midi_source": f"t{i}.mid"}) for i in range(5)]
    val = [(f"V{i}", {"midi_source": f"v{i}.mid"}) for i in range(5)]
    gold = _make_gold_with_splits(tmp_path / "gold", train=train, val=val)
    rc = main([
        "--gold-dir", str(gold),
        "--thresholds", str(THRESHOLDS_PATH),
        "--out", str(tmp_path / "out"),
    ])
    assert rc == 0

    # Leakage scenario → exit 1
    shared = "bronze/gmd/SHARED.mid"
    train2 = [(f"T{i}", {"midi_source": shared}) for i in range(3)]
    val2 = [(f"V{i}", {"midi_source": shared}) for i in range(3)]
    gold2 = _make_gold_with_splits(tmp_path / "gold2", train=train2, val=val2)
    rc = main([
        "--gold-dir", str(gold2),
        "--thresholds", str(THRESHOLDS_PATH),
        "--out", str(tmp_path / "out2"),
    ])
    assert rc == 1
