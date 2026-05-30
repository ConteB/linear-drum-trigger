"""Layer-1 oracles for :mod:`evaluation.evaluation_suite` (F0-T17 §3.4)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from evaluation.evaluation_suite import (
    MODULE_NAME,
    N_CHANNELS,
    EvaluationSuiteError,
    _bootstrap_ci,
    _confusion_matrix,
    _f_measure,
    _mcnemar,
    run,
)

pytestmark = pytest.mark.evaluation


THRESHOLDS = Path("src/evaluation/thresholds.yaml")


# --- _f_measure ---------------------------------------------------------------


def test_f_measure_perfect_match() -> None:
    ref = np.array([0.1, 0.5, 1.0])
    pred = np.array([0.1, 0.5, 1.0])
    assert _f_measure(pred, ref, tol_s=0.025) == 1.0


def test_f_measure_both_empty_is_one() -> None:
    assert _f_measure(np.array([]), np.array([]), tol_s=0.025) == 1.0


def test_f_measure_pred_empty_ref_nonempty_is_zero() -> None:
    assert _f_measure(np.array([]), np.array([0.1]), tol_s=0.025) == 0.0


def test_f_measure_outside_tolerance_is_zero() -> None:
    """Predictions ±50 ms from ref → outside ±25 ms tolerance → F=0."""
    ref = np.array([0.5])
    pred = np.array([0.55])  # 50 ms off
    assert _f_measure(pred, ref, tol_s=0.025) == 0.0


def test_f_measure_partial_match() -> None:
    ref = np.array([0.1, 0.5, 1.0])
    pred = np.array([0.1, 0.5])  # 2 hits, 1 miss → F = 2P*R/(P+R) = 2*1*0.66/(1+0.66) = 0.8
    f = _f_measure(pred, ref, tol_s=0.025)
    assert f == pytest.approx(0.8, abs=0.01)


# --- _bootstrap_ci ------------------------------------------------------------


def test_bootstrap_ci_single_value_collapses_to_point() -> None:
    ci = _bootstrap_ci([0.9], n_resamples=100, seed=0)
    assert ci == {"lo": 0.9, "mean": 0.9, "hi": 0.9}


def test_bootstrap_ci_empty_collapses_to_zero() -> None:
    ci = _bootstrap_ci([], n_resamples=100, seed=0)
    assert ci == {"lo": 0.0, "mean": 0.0, "hi": 0.0}


def test_bootstrap_ci_around_constant_is_tight() -> None:
    """All values identical → bootstrap CI collapses to that value."""
    ci = _bootstrap_ci([0.85] * 20, n_resamples=200, seed=0)
    assert ci["mean"] == pytest.approx(0.85)
    assert ci["hi"] - ci["lo"] < 0.001


def test_bootstrap_ci_seed_is_deterministic() -> None:
    rng_vals = list(np.random.default_rng(0).uniform(0.7, 0.9, size=30))
    c1 = _bootstrap_ci(rng_vals, n_resamples=500, seed=42)
    c2 = _bootstrap_ci(rng_vals, n_resamples=500, seed=42)
    assert c1 == c2


# --- _confusion_matrix --------------------------------------------------------


def test_confusion_matrix_diagonal_when_perfect() -> None:
    doc = {
        "samples": [
            {
                "key": "K1",
                "predictions": {str(b): [{"time_s": float(b) * 0.1, "prob": 0.9}]
                                  for b in range(N_CHANNELS)},
                "references": {str(b): [{"time_s": float(b) * 0.1, "velocity": 0.8}]
                                 for b in range(N_CHANNELS)},
            }
        ]
    }
    M = _confusion_matrix(doc, tol_s=0.025)
    for b in range(N_CHANNELS):
        assert M[b][b] == 1
        for other in range(N_CHANNELS):
            if other != b:
                assert M[b][other] == 0


def test_confusion_matrix_off_diagonal_when_bus_confused() -> None:
    """Pred at time T on bus 0, ref at time T on bus 1 → M[0][1] += 1."""
    doc = {
        "samples": [
            {
                "key": "K1",
                "predictions": {"0": [{"time_s": 0.1, "prob": 0.9}]},
                "references": {"1": [{"time_s": 0.1, "velocity": 0.8}]},
            }
        ]
    }
    M = _confusion_matrix(doc, tol_s=0.025)
    assert M[0][1] == 1
    assert M[0][0] == 0


# --- _mcnemar -----------------------------------------------------------------


def _doc_with_hits(*, hits: list[int], times: list[float] | None = None) -> dict:
    """Build a 1-sample doc where bus 0 has reference at every ``times`` and
    a prediction iff ``hits[i] == 1`` at the corresponding time."""
    if times is None:
        times = [0.1 * i for i in range(len(hits))]
    return {
        "samples": [{
            "key": "K1",
            "references": {"0": [{"time_s": t, "velocity": 0.8} for t in times]},
            "predictions": {"0": [{"time_s": t, "prob": 0.9}
                                    for t, h in zip(times, hits, strict=True) if h]},
        }],
    }


def test_mcnemar_identical_predictions_undefined() -> None:
    doc = _doc_with_hits(hits=[1, 1, 0])
    res = _mcnemar(doc, doc, tol_s=0.025)
    assert res.get("skipped_reason") == "no discordant pairs — undefined"


def test_mcnemar_systematic_b_better_than_a_yields_low_p() -> None:
    """A misses many that B hits → strong discordance → low p."""
    times = [0.1 * i for i in range(40)]
    # A: 50 % hits — first 20 events; B: 100 % hits.
    a = _doc_with_hits(hits=[1] * 20 + [0] * 20, times=times)
    b = _doc_with_hits(hits=[1] * 40, times=times)
    res = _mcnemar(a, b, tol_s=0.025)
    assert res["p_value"] is not None
    assert res["p_value"] < 0.001
    assert res["table"]["a0_b1"] == 20
    assert res["table"]["a1_b0"] == 0


def test_mcnemar_no_overlapping_keys_skips() -> None:
    a = {"samples": [{"key": "A", "predictions": {}, "references": {}}]}
    b = {"samples": [{"key": "B", "predictions": {}, "references": {}}]}
    res = _mcnemar(a, b, tol_s=0.025)
    assert res["skipped_reason"] == "no overlapping sample keys"


# --- run() end-to-end ---------------------------------------------------------


def _write_predictions(
    path: Path,
    *,
    n_sample: int,
    f_target: float,
    n_event_per_sample: int = 20,
    tempo_bpm: float = 120.0,
    kit: str = "DRSKit",
) -> None:
    """Write a predictions JSON where each bus's F-measure ≈ ``f_target``."""
    samples = []
    rng = np.random.default_rng(0)
    for i in range(n_sample):
        ref = {str(b): [{"time_s": float(0.1 * j + 0.001 * b), "velocity": 0.7}
                          for j in range(n_event_per_sample)] for b in range(N_CHANNELS)}
        # To hit F=f_target with perfect P=R, set hits = round(n*f_target).
        # F = 2PR/(P+R); P=R=f → F=f. So pick (hits, misses) such that
        # P=R=f_target: predict only at hit positions (no false positives).
        n_hit = int(round(n_event_per_sample * f_target))
        idx = sorted(rng.choice(n_event_per_sample, size=n_hit, replace=False))
        pred = {str(b): [{"time_s": float(0.1 * j + 0.001 * b), "prob": 0.9}
                           for j in idx] for b in range(N_CHANNELS)}
        samples.append({
            "key": f"K{i:03d}",
            "kit": kit,
            "tempo_bpm": tempo_bpm,
            "duration_s": 5.0,
            "predictions": pred,
            "references": ref,
        })
    path.write_text(json.dumps({"model_id": "test-v1", "samples": samples}, indent=2),
                    encoding="utf-8")


def test_run_passes_when_f_above_thresholds(tmp_path: Path) -> None:
    pred = tmp_path / "preds.json"
    _write_predictions(pred, n_sample=20, f_target=0.95)
    result = run(predictions=pred, thresholds=THRESHOLDS, out_dir=tmp_path / "out")
    assert result.passed is True, result.failures


def test_run_fails_when_per_bus_f_below_threshold(tmp_path: Path) -> None:
    pred = tmp_path / "preds.json"
    _write_predictions(pred, n_sample=20, f_target=0.50)  # < 0.80 LOCKED floor
    result = run(predictions=pred, thresholds=THRESHOLDS, out_dir=tmp_path / "out")
    assert result.passed is False
    assert any("F=" in f for f in result.failures)


def test_run_writes_json_and_png(tmp_path: Path) -> None:
    pred = tmp_path / "preds.json"
    _write_predictions(pred, n_sample=12, f_target=0.92)
    result = run(predictions=pred, thresholds=THRESHOLDS, out_dir=tmp_path / "out")
    assert result.report_json.exists()
    assert result.report_png.exists()
    doc = json.loads(result.report_json.read_text())
    assert doc["module_name"] == MODULE_NAME
    assert "per_bus_f_ci" in doc
    assert "f_macro" in doc
    assert "confusion_matrix" in doc
    assert "sliced" in doc


def test_run_deterministic_for_same_seed(tmp_path: Path) -> None:
    pred = tmp_path / "preds.json"
    _write_predictions(pred, n_sample=15, f_target=0.93)
    r1 = run(predictions=pred, thresholds=THRESHOLDS, out_dir=tmp_path / "out1", seed=42)
    r2 = run(predictions=pred, thresholds=THRESHOLDS, out_dir=tmp_path / "out2", seed=42)
    assert r1.report_json.read_bytes() == r2.report_json.read_bytes()


def test_run_predictions_b_triggers_mcnemar(tmp_path: Path) -> None:
    pa = tmp_path / "a.json"
    pb = tmp_path / "b.json"
    _write_predictions(pa, n_sample=15, f_target=0.90)
    _write_predictions(pb, n_sample=15, f_target=0.95)
    result = run(predictions=pa, thresholds=THRESHOLDS, out_dir=tmp_path / "out",
                  predictions_b=pb)
    assert "mcnemar_a_vs_b" in result.metrics


def test_run_missing_predictions_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(EvaluationSuiteError, match="cannot read"):
        run(predictions=tmp_path / "nope.json", thresholds=THRESHOLDS,
            out_dir=tmp_path / "out")


def test_run_empty_samples_fails_loud(tmp_path: Path) -> None:
    p = tmp_path / "preds.json"
    p.write_text(json.dumps({"samples": []}), encoding="utf-8")
    with pytest.raises(EvaluationSuiteError, match="non-empty"):
        run(predictions=p, thresholds=THRESHOLDS, out_dir=tmp_path / "out")


def test_run_cli_exit_code(tmp_path: Path) -> None:
    from evaluation.evaluation_suite import main

    pred = tmp_path / "preds.json"
    _write_predictions(pred, n_sample=10, f_target=0.95)
    rc = main([
        "--predictions", str(pred),
        "--thresholds", str(THRESHOLDS),
        "--out", str(tmp_path / "out"),
    ])
    assert rc == 0

    fail_pred = tmp_path / "fail.json"
    _write_predictions(fail_pred, n_sample=10, f_target=0.40)
    rc = main([
        "--predictions", str(fail_pred),
        "--thresholds", str(THRESHOLDS),
        "--out", str(tmp_path / "out2"),
    ])
    assert rc == 1
