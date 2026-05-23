"""Model evaluation dossier (F0-T17 §3.4) — **Gate L4** on E-GMD Holdout.

Consumes a JSON prediction artifact emitted at the end of F2-T3 (TCN trained
model fed with E-GMD Holdout audio) and the matching ground-truth JSON, and
produces:

* per-bus F-measure (``mir_eval.onset.evaluate``, tolerance ±25 ms);
* bootstrap 95 % CI for each per-bus F (and the macro mean), via
  :func:`scipy.stats.bootstrap`;
* inter-bus confusion matrix (predicted bus vs. ground-truth bus at matched
  onsets);
* per-bus reliability/calibration curve over the probability head;
* sliced F-score — by velocity bin, by tempo bin, by kit identity, by
  density (sparse vs dense events);
* optional McNemar A/B test between two prediction artifacts (e.g. with vs
  without augmentation level 3).

Gates ``per_bus_f_min`` (every bus) and ``f_macro_min`` (mean over the 8
buses), with the additional rule that the bootstrap CI half-width must not
exceed ``bootstrap_ci_max_width`` — an unstable model fails L4 even if its
central F crosses the threshold.

Spec: ``docs/methodology/F0-T17_STATISTICAL_TEST_PLAN.md`` §3.4.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import mir_eval  # type: ignore[import-untyped]
import numpy as np
from scipy import stats  # type: ignore[import-untyped]
from sklearn.calibration import calibration_curve  # type: ignore[import-untyped]

from evaluation.common import (
    ReportResult,
    Thresholds,
    _configure_lab_precision_style,
    load_thresholds,
    save_lab_precision_figure,
    write_report_json,
)

#: Module identifier.
MODULE_NAME = "evaluation_suite"

#: Number of transcription buses (F0-T2a flat-25 layout).
N_BUSES = 8

#: Canonical bus names — only used for plot labels (not in the gate decision).
BUS_NAMES = [
    "kick", "snare_top", "snare_bot_or_rim", "hihat",
    "tom1", "tom2", "tom3_floor", "cymbals",
]


class EvaluationSuiteError(RuntimeError):
    """Raised when prediction / reference artifacts cannot be loaded."""


def _load_predictions(path: Path) -> dict[str, Any]:
    """Read the prediction JSON, fail loud on schema violation.

    Expected schema::

        {
          "model_id": "<string>",
          "samples": [
            {
              "key": "<sample key>",
              "kit": "<kit name>",
              "tempo_bpm": <float>,
              "velocity_summary": <float>,  # mean velocity (optional)
              "predictions": {
                "0": [{"time_s": <float>, "prob": <float>}, ...],
                ...
                "7": [...]
              },
              "references": {
                "0": [{"time_s": <float>, "velocity": <float>}, ...],
                ...
                "7": [...]
              }
            }, ...
          ]
        }
    """
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise EvaluationSuiteError(f"{path}: cannot read predictions JSON: {exc}") from exc
    if not isinstance(doc, dict) or "samples" not in doc:
        raise EvaluationSuiteError(f"{path}: predictions JSON must have a 'samples' list")
    if not isinstance(doc["samples"], list) or not doc["samples"]:
        raise EvaluationSuiteError(f"{path}: 'samples' must be a non-empty list")
    return doc


def _bus_arrays(
    sample: dict[str, Any], bus: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract ``(pred_times, pred_probs, ref_times)`` for one sample and bus."""
    pred_events = sample.get("predictions", {}).get(str(bus), [])
    ref_events = sample.get("references", {}).get(str(bus), [])
    pred_times = np.array(sorted(e["time_s"] for e in pred_events), dtype=np.float64)
    pred_probs = np.array(
        [e.get("prob", 1.0) for e in sorted(pred_events, key=lambda x: x["time_s"])],
        dtype=np.float64,
    )
    ref_times = np.array(sorted(e["time_s"] for e in ref_events), dtype=np.float64)
    return pred_times, pred_probs, ref_times


def _f_measure(pred_times: np.ndarray, ref_times: np.ndarray, *, tol_s: float) -> float:
    """``mir_eval.onset.evaluate`` reduced to the F-measure scalar."""
    if pred_times.size == 0 and ref_times.size == 0:
        return 1.0  # both empty — perfect by convention
    if pred_times.size == 0 or ref_times.size == 0:
        return 0.0
    f, _, _ = mir_eval.onset.f_measure(ref_times, pred_times, window=tol_s)
    return float(f)


def _per_bus_f_measures(doc: dict[str, Any], *, tol_s: float) -> dict[int, list[float]]:
    """For each bus, the list of per-sample F-measures (one per sample)."""
    per_bus: dict[int, list[float]] = {b: [] for b in range(N_BUSES)}
    for s in doc["samples"]:
        for b in range(N_BUSES):
            pt, _, rt = _bus_arrays(s, b)
            per_bus[b].append(_f_measure(pt, rt, tol_s=tol_s))
    return per_bus


def _bootstrap_ci(values: list[float], *, n_resamples: int, seed: int) -> dict[str, float]:
    """``scipy.stats.bootstrap`` 95 % CI of the mean. Returns ``{lo, mean, hi}``."""
    arr = np.asarray(values, dtype=np.float64)
    if arr.size < 2:
        v = float(arr[0]) if arr.size == 1 else 0.0
        return {"lo": v, "mean": v, "hi": v}
    rng = np.random.default_rng(seed)
    res = stats.bootstrap(
        (arr,), np.mean, n_resamples=n_resamples,
        confidence_level=0.95, method="basic", random_state=rng,
    )
    return {
        "lo": float(res.confidence_interval.low),
        "mean": float(arr.mean()),
        "hi": float(res.confidence_interval.high),
    }


def _confusion_matrix(doc: dict[str, Any], *, tol_s: float) -> list[list[int]]:
    """Inter-bus confusion: predicted bus vs ground-truth bus at matched onsets.

    For each sample we greedily match each predicted onset to its closest
    unmatched ground-truth onset across *all* buses within ``tol_s``. The
    cell ``M[pred_bus][gt_bus]`` is incremented; the diagonal is the
    correctly-attributed onsets.
    """
    M = np.zeros((N_BUSES, N_BUSES), dtype=np.int64)
    for s in doc["samples"]:
        # Flatten predictions and references with their bus label.
        preds: list[tuple[float, int]] = []
        refs: list[tuple[float, int]] = []
        for b in range(N_BUSES):
            pt, _, rt = _bus_arrays(s, b)
            preds.extend((float(t), b) for t in pt)
            refs.extend((float(t), b) for t in rt)
        preds.sort()
        refs.sort()
        ref_used = [False] * len(refs)
        # Greedy matching — for each prediction, find the nearest unused ref
        # within tolerance; if found, mark and increment.
        for p_time, p_bus in preds:
            best_j = -1
            best_d = tol_s
            for j, (r_time, _r_bus) in enumerate(refs):
                if ref_used[j]:
                    continue
                d = abs(p_time - r_time)
                if d <= best_d:
                    best_d = d
                    best_j = j
            if best_j >= 0:
                ref_used[best_j] = True
                M[p_bus, refs[best_j][1]] += 1
    return M.tolist()


def _calibration_per_bus(
    doc: dict[str, Any], *, tol_s: float, n_bins: int = 10
) -> list[dict[str, Any]]:
    """Per-bus reliability curve over the predicted probability head."""
    rows: list[dict[str, Any]] = []
    for b in range(N_BUSES):
        probs: list[float] = []
        hits: list[int] = []
        for s in doc["samples"]:
            pt, pp, rt = _bus_arrays(s, b)
            for tp, prob in zip(pt, pp, strict=True):
                hit = 0
                for tr in rt:
                    if abs(tp - tr) <= tol_s:
                        hit = 1
                        break
                probs.append(float(prob))
                hits.append(hit)
        if len(probs) < 10:
            rows.append({"bus": b, "n_pred": len(probs), "skipped_reason": "too few preds"})
            continue
        try:
            fop, mpv = calibration_curve(hits, probs, n_bins=n_bins, strategy="uniform")
        except ValueError as exc:
            rows.append({"bus": b, "n_pred": len(probs), "skipped_reason": str(exc)})
            continue
        rows.append({
            "bus": b,
            "n_pred": len(probs),
            "mean_predicted": [float(x) for x in mpv],
            "fraction_of_positives": [float(x) for x in fop],
        })
    return rows


def _sliced_metrics(
    doc: dict[str, Any], *, tol_s: float
) -> dict[str, Any]:
    """F-score sliced by tempo bin, kit, and density."""
    samples = doc["samples"]

    # Tempo bins: <100, 100-140, >=140.
    def _tempo_bin(s: dict[str, Any]) -> str:
        tempo = float(s.get("tempo_bpm", 0.0))
        if tempo < 100:
            return "slow"
        if tempo < 140:
            return "mid"
        return "fast"

    # Density: total ref events normalised by sample duration; sparse < 4 ev/s.
    def _density_bin(s: dict[str, Any]) -> str:
        n_ev = sum(
            len(s.get("references", {}).get(str(b), [])) for b in range(N_BUSES)
        )
        dur = float(s.get("duration_s", 1.0)) or 1.0
        return "sparse" if (n_ev / dur) < 4.0 else "dense"

    def _f_for_subset(subset: list[dict[str, Any]]) -> float:
        if not subset:
            return float("nan")
        f_vals = []
        for s in subset:
            for b in range(N_BUSES):
                pt, _, rt = _bus_arrays(s, b)
                f_vals.append(_f_measure(pt, rt, tol_s=tol_s))
        return float(np.mean(f_vals)) if f_vals else float("nan")

    tempo_slices: dict[str, dict[str, Any]] = {}
    for bin_name in ("slow", "mid", "fast"):
        subset = [s for s in samples if _tempo_bin(s) == bin_name]
        tempo_slices[bin_name] = {"n_sample": len(subset), "f_mean": _f_for_subset(subset)}

    density_slices: dict[str, dict[str, Any]] = {}
    for bin_name in ("sparse", "dense"):
        subset = [s for s in samples if _density_bin(s) == bin_name]
        density_slices[bin_name] = {"n_sample": len(subset), "f_mean": _f_for_subset(subset)}

    kits_seen = sorted({s.get("kit", "unknown") for s in samples})
    kit_slices: dict[str, dict[str, Any]] = {}
    for kit in kits_seen:
        subset = [s for s in samples if s.get("kit") == kit]
        kit_slices[kit] = {"n_sample": len(subset), "f_mean": _f_for_subset(subset)}

    return {
        "by_tempo": tempo_slices,
        "by_density": density_slices,
        "by_kit": kit_slices,
    }


def _mcnemar(
    doc_a: dict[str, Any], doc_b: dict[str, Any], *, tol_s: float
) -> dict[str, Any]:
    """McNemar's test on per-onset hit/miss between two prediction artifacts.

    Both artifacts MUST share the same sample keys (otherwise the test is
    ill-defined). Returns the standard 2×2 contingency table plus the
    McNemar χ² with continuity correction.
    """
    samples_a = {s["key"]: s for s in doc_a["samples"]}
    samples_b = {s["key"]: s for s in doc_b["samples"]}
    common = sorted(set(samples_a) & set(samples_b))
    if not common:
        return {"skipped_reason": "no overlapping sample keys"}

    # For each sample, build per-bus hit/miss vectors (one entry per ref event).
    a_hits: list[int] = []
    b_hits: list[int] = []
    for key in common:
        sa, sb = samples_a[key], samples_b[key]
        for bus in range(N_BUSES):
            _, _, rt = _bus_arrays(sa, bus)
            pa, _, _ = _bus_arrays(sa, bus)
            pb, _, _ = _bus_arrays(sb, bus)
            for tr in rt:
                a_hit = int(any(abs(p - tr) <= tol_s for p in pa))
                b_hit = int(any(abs(p - tr) <= tol_s for p in pb))
                a_hits.append(a_hit)
                b_hits.append(b_hit)
    a = np.asarray(a_hits)
    b = np.asarray(b_hits)
    n_a1_b0 = int(((a == 1) & (b == 0)).sum())
    n_a0_b1 = int(((a == 0) & (b == 1)).sum())
    n_a1_b1 = int(((a == 1) & (b == 1)).sum())
    n_a0_b0 = int(((a == 0) & (b == 0)).sum())
    # McNemar with continuity correction.
    if n_a1_b0 + n_a0_b1 == 0:
        return {
            "table": {"a1_b1": n_a1_b1, "a1_b0": n_a1_b0,
                       "a0_b1": n_a0_b1, "a0_b0": n_a0_b0},
            "statistic": None, "p_value": None,
            "skipped_reason": "no discordant pairs — undefined",
        }
    chi2 = (abs(n_a1_b0 - n_a0_b1) - 1) ** 2 / (n_a1_b0 + n_a0_b1)
    p = float(stats.chi2.sf(chi2, df=1))
    return {
        "table": {"a1_b1": n_a1_b1, "a1_b0": n_a1_b0,
                   "a0_b1": n_a0_b1, "a0_b0": n_a0_b0},
        "statistic": float(chi2),
        "p_value": p,
        "n_event": int(a.size),
    }


def _build_figure(metrics: dict[str, Any]) -> Any:
    _configure_lab_precision_style()
    import matplotlib.pyplot as plt  # noqa: PLC0415

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))

    # Panel 1 — per-bus F-mean + bootstrap CI
    ax = axes[0, 0]
    bus_ci = metrics["per_bus_f_ci"]
    means = [b["mean"] for b in bus_ci]
    err_lo = [b["mean"] - b["lo"] for b in bus_ci]
    err_hi = [b["hi"] - b["mean"] for b in bus_ci]
    ax.bar(range(N_BUSES), means, color="#1a1a1a",
            yerr=[err_lo, err_hi], capsize=3)
    ax.axhline(metrics["per_bus_f_min"], linestyle="--", linewidth=0.8, color="#a00000")
    ax.set_title("Per-bus F-measure (95 % CI)")
    ax.set_xticks(range(N_BUSES))
    ax.set_xticklabels(BUS_NAMES, rotation=30, ha="right")
    ax.set_ylim(0, 1.05)

    # Panel 2 — confusion matrix
    ax = axes[0, 1]
    M = np.array(metrics["confusion_matrix"], dtype=np.float64)
    M_norm = M / M.sum(axis=1, keepdims=True).clip(min=1)
    im = ax.imshow(M_norm, cmap="Greys", vmin=0, vmax=1)
    ax.set_title("Inter-bus confusion (row-normalised)")
    ax.set_xticks(range(N_BUSES))
    ax.set_xticklabels(BUS_NAMES, rotation=30, ha="right")
    ax.set_yticks(range(N_BUSES))
    ax.set_yticklabels(BUS_NAMES)
    ax.set_xlabel("Ground truth bus")
    ax.set_ylabel("Predicted bus")
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.04)

    # Panel 3 — sliced metrics
    ax = axes[1, 0]
    sliced = metrics["sliced"]
    cats: list[str] = []
    vals: list[float] = []
    for k, v in sliced["by_tempo"].items():
        cats.append(f"tempo:{k}")
        vals.append(float(v["f_mean"]) if not np.isnan(v["f_mean"]) else 0.0)
    for k, v in sliced["by_density"].items():
        cats.append(f"density:{k}")
        vals.append(float(v["f_mean"]) if not np.isnan(v["f_mean"]) else 0.0)
    ax.bar(cats, vals, color="#1a1a1a")
    ax.axhline(metrics["per_bus_f_min"], linestyle="--", linewidth=0.8, color="#a00000")
    ax.set_title("Sliced F (tempo + density)")
    ax.tick_params(axis="x", rotation=30)
    ax.set_ylim(0, 1.05)

    # Panel 4 — calibration on bus 0 (kick — usually highest-prob class).
    ax = axes[1, 1]
    cal_rows = [r for r in metrics["calibration"] if "mean_predicted" in r]
    if cal_rows:
        r = cal_rows[0]
        ax.plot([0, 1], [0, 1], linestyle="--", linewidth=0.8, color="#a00000")
        ax.plot(r["mean_predicted"], r["fraction_of_positives"], "o-", color="#1a1a1a")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("Mean predicted probability")
        ax.set_ylabel("Fraction of positives")
        ax.set_title(f"Calibration — bus {r['bus']}")

    fig.suptitle(
        f"F0-T17 evaluation_suite — F_macro={metrics['f_macro']['mean']:.3f} "
        f"(95 % CI [{metrics['f_macro']['lo']:.3f}, {metrics['f_macro']['hi']:.3f}])",
        y=1.02,
    )
    return fig


def run(
    *,
    predictions: Path | str,
    thresholds: Thresholds | Path | str,
    out_dir: Path | str,
    seed: int = 4242,
    predictions_b: Path | str | None = None,
) -> ReportResult:
    """Run the Gate L4 evaluation suite.

    Args:
        predictions: JSON artifact from F2-T3 inference on E-GMD.
        thresholds: Locked thresholds (object or path).
        out_dir: Where ``evaluation_suite.report.{json,png}`` are written.
        seed: Bootstrap RNG seed (determinism anchor).
        predictions_b: Optional second artifact — when set, McNemar A/B test
            is computed between ``predictions`` (A) and ``predictions_b`` (B).
    """
    thr = thresholds if isinstance(thresholds, Thresholds) else load_thresholds(thresholds)
    doc = _load_predictions(Path(predictions))
    tol_s = thr.onset_tolerance_ms / 1000.0

    per_bus = _per_bus_f_measures(doc, tol_s=tol_s)

    per_bus_ci: list[dict[str, Any]] = []
    for b in range(N_BUSES):
        ci = _bootstrap_ci(per_bus[b], n_resamples=thr.bootstrap_n_resamples, seed=seed + b)
        per_bus_ci.append({"bus": b, **ci, "n_sample": len(per_bus[b])})

    f_macro_vals = [float(np.mean(per_bus[b])) for b in range(N_BUSES) if per_bus[b]]
    f_macro_ci = _bootstrap_ci(f_macro_vals, n_resamples=thr.bootstrap_n_resamples, seed=seed)

    confusion = _confusion_matrix(doc, tol_s=tol_s)
    calibration = _calibration_per_bus(doc, tol_s=tol_s)
    sliced = _sliced_metrics(doc, tol_s=tol_s)

    mcnemar: dict[str, Any] | None = None
    if predictions_b is not None:
        doc_b = _load_predictions(Path(predictions_b))
        mcnemar = _mcnemar(doc, doc_b, tol_s=tol_s)

    failures: list[str] = []
    for row in per_bus_ci:
        if row["mean"] < thr.per_bus_f_min:
            failures.append(
                f"bus {row['bus']} F={row['mean']:.4f} < {thr.per_bus_f_min}"
            )
        ci_width = row["hi"] - row["lo"]
        if ci_width > thr.bootstrap_ci_max_width:
            failures.append(
                f"bus {row['bus']} bootstrap CI width {ci_width:.4f} > "
                f"{thr.bootstrap_ci_max_width} — unstable estimate"
            )
    if f_macro_ci["mean"] < thr.f_macro_min:
        failures.append(
            f"F_macro={f_macro_ci['mean']:.4f} < {thr.f_macro_min}"
        )

    metrics: dict[str, Any] = {
        "module_name": MODULE_NAME,
        "model_id": doc.get("model_id"),
        "n_sample": len(doc["samples"]),
        "onset_tolerance_ms": thr.onset_tolerance_ms,
        "per_bus_f_min": thr.per_bus_f_min,
        "f_macro_min": thr.f_macro_min,
        "bootstrap_n_resamples": thr.bootstrap_n_resamples,
        "bootstrap_ci_max_width": thr.bootstrap_ci_max_width,
        "per_bus_f_ci": per_bus_ci,
        "f_macro": {**f_macro_ci, "n_bus": len(f_macro_vals)},
        "confusion_matrix": confusion,
        "calibration": calibration,
        "sliced": sliced,
    }
    if mcnemar is not None:
        metrics["mcnemar_a_vs_b"] = mcnemar

    passed = not failures

    json_path = write_report_json(out_dir, MODULE_NAME, {**metrics, "passed": passed,
                                                          "failures": failures})
    fig = _build_figure(metrics)
    png_path = save_lab_precision_figure(out_dir, MODULE_NAME, fig)

    return ReportResult(
        module_name=MODULE_NAME,
        passed=passed,
        metrics=metrics,
        failures=failures,
        report_json=json_path,
        report_png=png_path,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="F0-T17 evaluation suite — Gate L4 dossier on E-GMD Holdout."
    )
    p.add_argument("--predictions", type=Path, required=True)
    p.add_argument("--predictions-b", type=Path, default=None,
                    help="Optional second artifact — enables McNemar A/B test.")
    p.add_argument("--thresholds", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=4242)
    args = p.parse_args(argv)
    result = run(
        predictions=args.predictions,
        thresholds=args.thresholds,
        out_dir=args.out,
        seed=args.seed,
        predictions_b=args.predictions_b,
    )
    print(
        f"[{MODULE_NAME}] {'PASS' if result.passed else 'FAIL'} — "
        f"F_macro={result.metrics['f_macro']['mean']:.4f} "
        f"json={result.report_json}"
    )
    if not result.passed:
        for f in result.failures:
            print(f"  - {f}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
