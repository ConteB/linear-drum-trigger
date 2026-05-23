"""Layer-3 acceptance — F0-T17 modules on the real F0-T2e mini-batch.

These tests do not require any external service: they read the locally
committed Gold mini-batch and verify each module *runs* end-to-end and
produces a contract-conforming JSON + PNG. The mini-batch is intentionally
synthetic (12 grooves, sparse drum patterns) so some bus distributions are
expected to be empty — the audit's *informative* gate is allowed to fail
here; the acceptance is on the *execution path*, not the gate verdict.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.evaluation, pytest.mark.acceptance]

REPO_ROOT = Path(__file__).resolve().parents[2]
MINI_BATCH = REPO_ROOT / "data" / "gold" / "mini_batch"
THRESHOLDS = REPO_ROOT / "src" / "evaluation" / "thresholds.yaml"

if not MINI_BATCH.is_dir() or not any(MINI_BATCH.glob("*.dna.json")):
    pytest.skip(
        "mini-batch absent — run tools/run_mini_batch.py first",
        allow_module_level=True,
    )


def test_data_audit_runs_on_mini_batch(tmp_path: Path) -> None:
    from evaluation.data_audit import MODULE_NAME, run

    result = run(gold_dir=MINI_BATCH, thresholds=THRESHOLDS, out_dir=tmp_path)
    assert result.report_json.exists()
    assert result.report_png.exists()
    doc = json.loads(result.report_json.read_text(encoding="utf-8"))
    assert doc["module_name"] == MODULE_NAME
    # The synthetic mini-batch has at least one onset.
    assert doc["n_onset_total"] >= 1
    # All metric blocks are populated.
    assert len(doc["class_imbalance_pct"]) == 8
    assert "engine_kit_contingency" in doc
    assert "hh_articulation" in doc


def test_split_consistency_runs_on_mini_batch(tmp_path: Path) -> None:
    """Mini-batch is train-only; KS / χ² should skip cleanly without erroring."""
    from evaluation.split_consistency import MODULE_NAME, run

    result = run(gold_dir=MINI_BATCH, thresholds=THRESHOLDS, out_dir=tmp_path)
    assert result.report_json.exists()
    assert result.report_png.exists()
    doc = json.loads(result.report_json.read_text(encoding="utf-8"))
    assert doc["module_name"] == MODULE_NAME
    assert doc["n_train"] >= 1
    # Mini-batch has no val split → midi_leakage_count must be 0.
    assert doc["midi_leakage_count"] == 0


def test_anti_leak_audit_runs_on_mini_batch(tmp_path: Path) -> None:
    """Mini-batch is single-engine; 3 tests must skip, tail-zero must pass."""
    from evaluation.anti_leak_audit import MODULE_NAME, run

    result = run(gold_dir=MINI_BATCH, thresholds=THRESHOLDS, out_dir=tmp_path)
    assert result.report_json.exists()
    assert result.report_png.exists()
    doc = json.loads(result.report_json.read_text(encoding="utf-8"))
    assert doc["module_name"] == MODULE_NAME
    # Single-engine mini-batch — three tests skip with documented reason.
    assert doc["duration_engine"]["skipped_reason"]
    assert doc["mi_audio_engine"]["skipped_reason"]
    assert doc["cross_engine_n_sample"]["skipped_reason"]
    # Tail-zero policy must hold — every engine median under threshold.
    for engine_summary in doc["tail_zero"]["per_engine"].values():
        assert engine_summary["median"] < 0.01
