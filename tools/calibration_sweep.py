#!/usr/bin/env python3
"""Calibration sweep — post-hoc threshold tuning + temperature scaling.

**Sequenza A del piano F0-T4e DISCOVERY_REPORT (2026-05-27).** Zero retrain
— il checkpoint F0-T4e è già su disco. Il listening test ha rivelato che
il bottleneck residuo è calibrazione assoluta (FP/FN 9-39× simmetrico
cross-kit, precision 0.005-0.05 vs recall 0.13-0.38).

Due interventi post-hoc che non toccano i pesi del modello:

1. **Threshold tuning per-bus.** Il fixed 0.1 globale è subottimale. Sweep
   ``threshold ∈ {0.05, 0.10, ..., 0.95}`` per ogni bus indipendentemente
   e trova quello che massimizza F-aggregate sul pool val.

2. **Temperature scaling** (Guo et al. 2017). Recupera i logit dal sigmoid
   del modello (``logit = log(p / (1-p))``), divide per ``T > 0``, riapplica
   sigmoid: ``p_calibrated = sigmoid(logit / T)``. Per ``T > 1`` smussa le
   probabilità (riduce FP), per ``T < 1`` le acuisce (aumenta confidence).
   Sweep ``T`` per bus indipendente.

Output:
    docs/gates/F0-T4c_MINI_L3/listening_test_<run_id>/calibration_sweep.json
    docs/gates/F0-T4c_MINI_L3/listening_test_<run_id>/calibration_sweep.png
    docs/gates/F0-T4c_MINI_L3/listening_test_<run_id>/CALIBRATION_REPORT.html

Usage::

    python tools/calibration_sweep.py \\
        --checkpoint artifacts/mini_l3_tcn_F0T4e.pt \\
        --run-id mini-l3-F0T4e-2026-05-27
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from neural.data import DEFAULT_LOOKAHEAD_FRAMES, load_pool  # noqa: E402
from neural.metrics import match_onsets, peak_pick  # noqa: E402

# Reuse the listening-test loader (handles composed_state + channel_agnostic_state).
sys.path.insert(0, str(_REPO_ROOT / "tools"))
from listening_test_shittykit import load_model_from_checkpoint  # noqa: E402

BUS_NAMES = [
    "kick", "snare_head", "snare_sidestick", "hihat", "tom",
    "ride_bow", "ride_bell", "crash", "aux",
]
N_BUS = 9  # F0-T19 §7b flat-28: 9 type-class channels
GATE_ROOT = _REPO_ROOT / "docs" / "gates" / "F0-T4c_MINI_L3"

# Sweep grids — coarse enough to be fast, fine enough to find the optimum.
THRESHOLD_GRID = [0.05, 0.07, 0.10, 0.13, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35,
                  0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80]
TEMPERATURE_GRID = [0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0]


def collect_raw_predictions(
    model: torch.nn.Module, val_samples: list, *, n_sample: int,
    lookahead_frames: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Run forward on every val sample, collect ``(N, T, 8)`` onset prob + target arrays.

    Returns a *concatenated* representation along the time axis: each sample
    contributes its full predicted/target onset matrix (no peak-picking yet).
    Returned shape: lists of per-sample tensors so we can compute aggregate
    F per (bus, threshold) without padding bias.
    """
    L = max(0, int(lookahead_frames))
    per_sample_pred: list[np.ndarray] = []
    per_sample_target: list[np.ndarray] = []
    with torch.no_grad():
        for s in val_samples:
            audio = torch.from_numpy(s.audio[None, :, :n_sample]).float()
            pred = model(audio).squeeze(0).cpu().numpy()  # [T, 25]
            if L > 0:
                target = s.target[L:]
                pred = pred[:target.shape[0]]
            else:
                target = s.target[:pred.shape[0]]
            # flat-28 (F0-T19 §7b): onset columns 0,3,...,24 (9 channels)
            onset_pred = pred[:, 0:27:3]      # [T, 9]
            onset_target = target[:, 0:27:3]  # [T, 9]
            per_sample_pred.append(onset_pred.astype(np.float32))
            per_sample_target.append(onset_target.astype(np.float32))
    return per_sample_pred, per_sample_target


def apply_temperature(probs: np.ndarray, T: float) -> np.ndarray:
    """``p_calibrated = sigmoid(log(p/(1-p)) / T)`` — temperature scaling.

    Clamps probs to [eps, 1-eps] to avoid inf in the logit. T == 1.0 is the
    identity; T > 1 smooths (less confident), T < 1 sharpens (more confident).
    """
    if T == 1.0:
        return probs
    eps = 1e-6
    p = np.clip(probs, eps, 1.0 - eps)
    logit = np.log(p / (1.0 - p))
    return 1.0 / (1.0 + np.exp(-logit / T))


def f_aggregate_for_bus(
    per_sample_pred: list[np.ndarray],
    per_sample_target: list[np.ndarray],
    bus: int,
    *, threshold: float, temperature: float = 1.0,
    skip_edge_frames: int = 0,
) -> tuple[float, dict[str, int]]:
    """Compute aggregate F1 for a single bus across all samples.

    Counts TP/FP/FN globally and computes precision/recall/F over the whole
    pool. This is the *fixed-threshold production metric* used in the
    listening test (line 200 of listening_test_shittykit.py).
    """
    tp = fp = fn = 0
    for pred_full, target_full in zip(per_sample_pred, per_sample_target):
        # Edge crop applied symmetrically.
        if skip_edge_frames > 0:
            pred_b = pred_full[skip_edge_frames:, bus]
            target_b = target_full[skip_edge_frames:, bus]
        else:
            pred_b = pred_full[:, bus]
            target_b = target_full[:, bus]
        # Temperature scaling on predictions only (target stays Gaussian).
        pred_cal = apply_temperature(pred_b, temperature)
        peaks_pred = peak_pick(pred_cal, threshold=threshold)
        peaks_true = peak_pick(target_b, threshold=0.5)
        n_m, _ = match_onsets(peaks_pred, peaks_true)
        n_p, n_t = len(peaks_pred), len(peaks_true)
        tp += n_m
        fp += (n_p - n_m)
        fn += (n_t - n_m)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f = (2 * precision * recall / (precision + recall)
         if precision + recall > 0 else 0.0)
    return f, {"tp": tp, "fp": fp, "fn": fn,
               "precision": precision, "recall": recall}


def sweep_per_bus(
    per_sample_pred, per_sample_target, *, skip_edge_frames: int,
) -> dict[str, Any]:
    """For each bus, find the (threshold, temperature) that maximizes F-aggregate."""
    best_per_bus: dict[str, dict[str, Any]] = {}
    full_grid: dict[str, list[dict[str, Any]]] = {b: [] for b in BUS_NAMES}
    for bus_idx in range(N_BUS):
        # Skip empty buses (no positive onsets in any sample).
        any_positive = any(
            (t[:, bus_idx] > 0.5).any() for t in per_sample_target
        )
        if not any_positive:
            best_per_bus[BUS_NAMES[bus_idx]] = {
                "skipped": True,
                "reason": "no positive onsets in val pool",
            }
            continue
        best_f = -1.0
        best_thr = None
        best_T = None
        best_stats = None
        for thr, T in itertools.product(THRESHOLD_GRID, TEMPERATURE_GRID):
            f, stats = f_aggregate_for_bus(
                per_sample_pred, per_sample_target, bus_idx,
                threshold=thr, temperature=T,
                skip_edge_frames=skip_edge_frames,
            )
            full_grid[BUS_NAMES[bus_idx]].append({
                "threshold": thr, "temperature": T, "f": f,
                "precision": stats["precision"], "recall": stats["recall"],
            })
            if f > best_f:
                best_f = f
                best_thr = thr
                best_T = T
                best_stats = stats
        best_per_bus[BUS_NAMES[bus_idx]] = {
            "best_threshold": best_thr,
            "best_temperature": best_T,
            "best_f": best_f,
            "stats": best_stats,
        }
    return {"best_per_bus": best_per_bus, "full_grid": full_grid}


def baseline_f_at_threshold(
    per_sample_pred, per_sample_target,
    *, threshold: float, skip_edge_frames: int,
) -> dict[str, Any]:
    """Compute baseline F (no calibration) for every bus at given threshold."""
    out: dict[str, dict[str, Any]] = {}
    for bus_idx in range(N_BUS):
        any_pos = any((t[:, bus_idx] > 0.5).any() for t in per_sample_target)
        if not any_pos:
            out[BUS_NAMES[bus_idx]] = {"skipped": True}
            continue
        f, stats = f_aggregate_for_bus(
            per_sample_pred, per_sample_target, bus_idx,
            threshold=threshold, temperature=1.0,
            skip_edge_frames=skip_edge_frames,
        )
        out[BUS_NAMES[bus_idx]] = {
            "threshold": threshold, "temperature": 1.0,
            "f": f, "stats": stats,
        }
    return out


def macro_f(per_bus_results: dict[str, Any], key: str = "best_f") -> float:
    """Mean across non-skipped buses."""
    values: list[float] = []
    for b in BUS_NAMES:
        entry = per_bus_results.get(b, {})
        if entry.get("skipped"):
            continue
        v = entry.get(key)
        if v is None:
            v = entry.get("f")
        if v is not None:
            values.append(float(v))
    return float(np.mean(values)) if values else float("nan")


def plot_calibration(sweep: dict[str, Any], baseline: dict[str, Any],
                      out_path: Path) -> None:
    """Bar chart: baseline F per bus vs calibrated F per bus."""
    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(N_BUS)
    width = 0.35
    base_vals = []
    cal_vals = []
    for b in BUS_NAMES:
        bv = baseline.get(b, {})
        cv = sweep["best_per_bus"].get(b, {})
        if bv.get("skipped") or cv.get("skipped"):
            base_vals.append(0.0)
            cal_vals.append(0.0)
        else:
            base_vals.append(float(bv.get("f", 0.0)))
            cal_vals.append(float(cv.get("best_f", 0.0)))
    ax.bar(x - width / 2, base_vals, width,
           label=f"Baseline (thr=0.1, T=1.0)", color="#999")
    ax.bar(x + width / 2, cal_vals, width,
           label="Calibrated (per-bus optimum)", color="#1f6feb")
    ax.set_xticks(x)
    ax.set_xticklabels(BUS_NAMES, rotation=20, ha="right")
    ax.set_ylabel("F-aggregate (ShittyKit val)")
    ax.set_title("Calibration sweep — F per bus, baseline vs calibrated")
    ax.legend()
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    for i, (b, c) in enumerate(zip(base_vals, cal_vals)):
        if b > 0:
            ax.text(i - width / 2, b + 0.005, f"{b:.3f}", ha="center",
                    fontsize=8, color="#444")
        if c > 0:
            ax.text(i + width / 2, c + 0.005, f"{c:.3f}", ha="center",
                    fontsize=8, color="#1f6feb")
    plt.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def f_mean_per_sample(
    per_sample_pred, per_sample_target,
    *, thresholds_per_bus: list[float], temperatures_per_bus: list[float],
    skip_edge_frames: int,
) -> dict[str, Any]:
    """Compute the F **mean-per-sample** with per-bus (thr, T) — confrontabile
    col F_overall_shittykit_fixed del listening_test (0.0905 baseline).

    Per ogni val sample, per ogni bus, calcola F del sample (TP/FP/FN locali),
    poi media i F per-sample non-NaN. Lo stesso protocollo usato in
    ``listening_test_shittykit.evaluate_with_fixed_threshold``.
    """
    f_per_sample_all: list[float] = []
    f_per_sample_per_bus: list[list[float]] = [[] for _ in range(N_BUS)]
    for pred_full, target_full in zip(per_sample_pred, per_sample_target):
        sample_bus_fs: list[float] = []
        for bus in range(N_BUS):
            thr = thresholds_per_bus[bus]
            T = temperatures_per_bus[bus]
            if skip_edge_frames > 0:
                pred_b = pred_full[skip_edge_frames:, bus]
                target_b = target_full[skip_edge_frames:, bus]
            else:
                pred_b = pred_full[:, bus]
                target_b = target_full[:, bus]
            pred_cal = apply_temperature(pred_b, T)
            peaks_pred = peak_pick(pred_cal, threshold=thr)
            peaks_true = peak_pick(target_b, threshold=0.5)
            n_p, n_t = len(peaks_pred), len(peaks_true)
            n_m, _ = match_onsets(peaks_pred, peaks_true)
            # Listening-test-compatible logic (line 200-204 of
            # listening_test_shittykit.py): skip bus from the sample mean
            # if P=0 or R=0 (both interpreted as "F undefined", NaN).
            # This is more optimistic than F=0 but matches the published
            # 0.0905 baseline. Switch via ``count_zero_as_zero`` to opt
            # into the strict interpretation.
            if n_p == 0 or n_t == 0 or n_m == 0:
                continue
            p = n_m / n_p
            r = n_m / n_t
            if p + r == 0:
                continue
            f_sample = 2 * p * r / (p + r)
            sample_bus_fs.append(f_sample)
            f_per_sample_per_bus[bus].append(f_sample)
        if sample_bus_fs:
            f_per_sample_all.append(float(np.mean(sample_bus_fs)))
    return {
        "f_mean_per_sample": float(np.mean(f_per_sample_all)) if f_per_sample_all else float("nan"),
        "f_max_per_sample": float(np.max(f_per_sample_all)) if f_per_sample_all else float("nan"),
        "f_min_per_sample": float(np.min(f_per_sample_all)) if f_per_sample_all else float("nan"),
        "n_samples": len(f_per_sample_all),
        "f_per_bus_mean": [
            float(np.mean(v)) if v else float("nan")
            for v in f_per_sample_per_bus
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibration sweep — threshold + temperature scaling post-hoc.",
    )
    parser.add_argument("--checkpoint", type=Path,
                        default=Path("artifacts/mini_l3_tcn_F0T4e.pt"))
    parser.add_argument("--val-pool", type=Path,
                        default=Path("data/gold/mini_l3_val"))
    parser.add_argument("--run-id", default="mini-l3-F0T4e-2026-05-27",
                        help="Output subdir under docs/gates/F0-T4c_MINI_L3/.")
    parser.add_argument("--n-sample", type=int, default=196608)
    parser.add_argument("--lookahead-frames", type=int,
                        default=DEFAULT_LOOKAHEAD_FRAMES)
    parser.add_argument("--skip-edge-frames", type=int, default=1024,
                        help="Mirror the listening_test default (1024 = TCN RF size).")
    parser.add_argument("--baseline-threshold", type=float, default=0.10,
                        help="Threshold for the no-calibration baseline.")
    args = parser.parse_args()

    out_dir = GATE_ROOT / f"listening_test_{args.run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[calib] loading checkpoint {args.checkpoint.name}…", flush=True)
    model = load_model_from_checkpoint(
        args.checkpoint, warmup_pool=Path("data/gold/mini_l3_train"),
        warmup_n_samples=30,
    )

    print(f"[calib] loading val pool {args.val_pool}…", flush=True)
    val_samples = load_pool(args.val_pool)
    print(f"[calib]   {len(val_samples)} val samples")

    print("[calib] running forward on all val samples…", flush=True)
    per_sample_pred, per_sample_target = collect_raw_predictions(
        model, val_samples, n_sample=args.n_sample,
        lookahead_frames=args.lookahead_frames,
    )

    print(f"[calib] computing baseline (thr={args.baseline_threshold}, T=1.0)…",
          flush=True)
    baseline = baseline_f_at_threshold(
        per_sample_pred, per_sample_target,
        threshold=args.baseline_threshold,
        skip_edge_frames=args.skip_edge_frames,
    )
    baseline_macro = macro_f(baseline, key="f")
    print(f"[calib]   baseline macro F = {baseline_macro:.4f}")

    print(f"[calib] sweeping {len(THRESHOLD_GRID)} × {len(TEMPERATURE_GRID)} "
          f"= {len(THRESHOLD_GRID) * len(TEMPERATURE_GRID)} combinations × "
          f"{N_BUS} buses…", flush=True)
    sweep = sweep_per_bus(
        per_sample_pred, per_sample_target,
        skip_edge_frames=args.skip_edge_frames,
    )
    calibrated_macro = macro_f(sweep["best_per_bus"], key="best_f")
    print(f"[calib]   calibrated macro F = {calibrated_macro:.4f}  "
          f"(lift +{(calibrated_macro / baseline_macro - 1) * 100:.0f}%)")

    print("\n[calib] per-bus optimum:")
    print(f"{'Bus':14s} | {'thr*':>5s} {'T*':>4s} | "
          f"{'F base':>7s} {'F cal':>7s} {'Δ':>6s} | "
          f"{'P cal':>6s} {'R cal':>6s}")
    print("-" * 80)
    for b in BUS_NAMES:
        bv = baseline.get(b, {})
        cv = sweep["best_per_bus"].get(b, {})
        if cv.get("skipped"):
            print(f"{b:14s} | {'—':>5s} {'—':>4s} | "
                  f"{'—':>7s} {'—':>7s} {'—':>6s} | "
                  f"{'—':>6s} {'—':>6s}    (no positive onsets)")
            continue
        f_b = float(bv.get("f", 0.0))
        f_c = float(cv.get("best_f", 0.0))
        delta = f_c - f_b
        stats = cv.get("stats") or {}
        print(f"{b:14s} | {cv['best_threshold']:>5.2f} {cv['best_temperature']:>4.1f} | "
              f"{f_b:>7.4f} {f_c:>7.4f} {delta:>+6.3f} | "
              f"{stats.get('precision', 0):>6.3f} {stats.get('recall', 0):>6.3f}")

    # Compute the mean-per-sample metrics (the listening-test-comparable F).
    print("\n[calib] computing mean-per-sample metrics…", flush=True)
    baseline_thr_vec = [args.baseline_threshold] * N_BUS
    baseline_T_vec = [1.0] * N_BUS
    cal_thr_vec = [
        sweep["best_per_bus"].get(b, {}).get("best_threshold")
        or args.baseline_threshold for b in BUS_NAMES
    ]
    cal_T_vec = [
        sweep["best_per_bus"].get(b, {}).get("best_temperature")
        or 1.0 for b in BUS_NAMES
    ]
    mps_baseline = f_mean_per_sample(
        per_sample_pred, per_sample_target,
        thresholds_per_bus=baseline_thr_vec,
        temperatures_per_bus=baseline_T_vec,
        skip_edge_frames=args.skip_edge_frames,
    )
    mps_cal = f_mean_per_sample(
        per_sample_pred, per_sample_target,
        thresholds_per_bus=cal_thr_vec,
        temperatures_per_bus=cal_T_vec,
        skip_edge_frames=args.skip_edge_frames,
    )
    print(f"[calib]   F mean-per-sample baseline  = {mps_baseline['f_mean_per_sample']:.4f}  "
          f"(range [{mps_baseline['f_min_per_sample']:.3f}, "
          f"{mps_baseline['f_max_per_sample']:.3f}])")
    print(f"[calib]   F mean-per-sample calibrated = {mps_cal['f_mean_per_sample']:.4f}  "
          f"(range [{mps_cal['f_min_per_sample']:.3f}, "
          f"{mps_cal['f_max_per_sample']:.3f}])")
    if mps_baseline["f_mean_per_sample"] > 0:
        lift_mps = (mps_cal["f_mean_per_sample"] / mps_baseline["f_mean_per_sample"] - 1) * 100
        print(f"[calib]   lift mean-per-sample       = {lift_mps:+.1f}%")

    out_json = out_dir / "calibration_sweep.json"
    out_json.write_text(json.dumps({
        "checkpoint": str(args.checkpoint),
        "n_val_samples": len(val_samples),
        "skip_edge_frames": args.skip_edge_frames,
        "baseline_threshold": args.baseline_threshold,
        "baseline_per_bus": baseline,
        "baseline_macro_f": baseline_macro,
        "sweep": sweep,
        "calibrated_macro_f": calibrated_macro,
        "threshold_grid": THRESHOLD_GRID,
        "temperature_grid": TEMPERATURE_GRID,
        "mean_per_sample_baseline": mps_baseline,
        "mean_per_sample_calibrated": mps_cal,
        "calibrated_thresholds_per_bus": dict(zip(BUS_NAMES, cal_thr_vec)),
        "calibrated_temperatures_per_bus": dict(zip(BUS_NAMES, cal_T_vec)),
    }, indent=2, default=str))
    print(f"\n[calib] wrote {out_json}", flush=True)

    out_png = out_dir / "calibration_sweep.png"
    plot_calibration(sweep, baseline, out_png)
    print(f"[calib] wrote {out_png.name}", flush=True)

    print(f"\n{'='*78}")
    print(f"CALIBRATION SWEEP SUMMARY  [run_id={args.run_id}]")
    print(f"{'='*78}")
    print(f"Metric (aggregate per-bus, then mean across buses)")
    print(f"  Baseline   macro F (thr={args.baseline_threshold}, T=1.0):  "
          f"{baseline_macro:.4f}")
    print(f"  Calibrated macro F (per-bus optimum):              "
          f"{calibrated_macro:.4f}")
    if baseline_macro > 0:
        lift = (calibrated_macro / baseline_macro - 1) * 100
        print(f"  Lift                                               {lift:+.1f}%")
    print(f"")
    print(f"Metric (mean per-sample, listening-test-comparable)")
    print(f"  Baseline   F mean-per-sample (thr={args.baseline_threshold}, T=1.0):  "
          f"{mps_baseline['f_mean_per_sample']:.4f}")
    print(f"  Calibrated F mean-per-sample (per-bus optimum):    "
          f"{mps_cal['f_mean_per_sample']:.4f}")
    if mps_baseline["f_mean_per_sample"] > 0:
        lift_mps = (mps_cal["f_mean_per_sample"] / mps_baseline["f_mean_per_sample"] - 1) * 100
        print(f"  Lift                                               {lift_mps:+.1f}%")
    print(f"")
    print(f"Listening test reference (mini-l3-F0T4e-2026-05-27):")
    print(f"  F mean-per-sample (thr=0.1, T=1.0, tuned per-sample!):  0.1895")
    print(f"  F max-per-sample:                                       0.6400")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
