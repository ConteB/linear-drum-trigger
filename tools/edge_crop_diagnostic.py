#!/usr/bin/env python3
"""Edge-crop diagnostic — CEO directive 2026-05-25 (post-piano-roll).

Quantifica l'impatto del receptive-field warmup edge effect sul checkpoint B.
Valuta lo stesso pool ShittyKit con 3 livelli di crop edge:

  full         : nessun crop (status quo della metrica corrente)
  crop_0.5s    : skip primi 172 frame (≈ 0.5 s, durata del cluster FP iniziale)
  crop_rf      : skip primi 1024 frame (≈ 2.97 s, intera zona RF warmup)

Output: console table + JSON sotto docs/gates/F0-T4c_MINI_L3/edge_crop_diagnostic/.

Razionale: la diagnostica inline ha mostrato che 77 % dei FP totali sul val
ShittyKit cade nei primi 1024 frame (zona dove la convoluzione causale vede
zero-pad). Il crop separa l'F "vera" della rete (zona stabile) dall'artefatto
edge-RF.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from neural.data import DEFAULT_LOOKAHEAD_FRAMES, load_pool  # noqa: E402
from neural.model import TCNConfig, TCNModel  # noqa: E402
from neural.preprocessing import PreprocessingFrontend  # noqa: E402

# Import the local helpers — they live in the same dir.
sys.path.insert(0, str(_REPO_ROOT / "tools"))
from listening_test_shittykit import (  # noqa: E402
    _Composed,
    aggregate_per_bus,
    evaluate_with_fixed_threshold,
)

BUS_NAMES = ["kick", "snare", "hihat", "tom_hi_mid", "floor",
             "ride", "crash_a", "crash_b_misc"]
FRAME_HZ = 44100 / 128
N_SAMPLES = 196608

CROP_LEVELS = [
    ("full",      0),
    ("crop_0.5s", int(0.5 * FRAME_HZ)),    # 172 frame
    ("crop_rf",   1024),                     # 2.97 s
]


def main() -> int:
    import argparse  # noqa: PLC0415
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint", type=Path,
        default=_REPO_ROOT / "artifacts" / "mini_l3_tcn_loss-B.pt",
    )
    parser.add_argument("--threshold", type=float, default=0.1)
    args = parser.parse_args()

    print(f"[edge-crop] loading checkpoint {args.checkpoint.name}…", flush=True)
    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    tcn = TCNModel(TCNConfig(channels=ckpt["config"]["channels"], in_channels=9))
    tcn.load_state_dict(ckpt["model_state"])
    pre = PreprocessingFrontend(n_mic=8, onset_envelope=True)
    model = _Composed(pre, tcn).eval()

    val = load_pool(_REPO_ROOT / "data" / "gold" / "mini_l3_val")
    drs = load_pool(_REPO_ROOT / "data" / "gold" / "mini_l3_train" / "DRSKit")[:30]
    print(f"[edge-crop] ShittyKit val: {len(val)} samples", flush=True)
    print(f"[edge-crop] DRSKit train: {len(drs)} samples", flush=True)

    results = {}
    for crop_label, skip_frames in CROP_LEVELS:
        print(f"\n[edge-crop] === {crop_label} (skip {skip_frames} frame) ===",
              flush=True)
        shitty_evals = [
            evaluate_with_fixed_threshold(
                model, s.audio, s.target,
                n_sample=N_SAMPLES,
                lookahead_frames=DEFAULT_LOOKAHEAD_FRAMES,
                threshold=args.threshold,
                skip_edge_frames=skip_frames,
            ) for s in val
        ]
        drs_evals = [
            evaluate_with_fixed_threshold(
                model, s.audio, s.target,
                n_sample=N_SAMPLES,
                lookahead_frames=DEFAULT_LOOKAHEAD_FRAMES,
                threshold=args.threshold,
                skip_edge_frames=skip_frames,
            ) for s in drs
        ]

        shitty_agg = aggregate_per_bus(shitty_evals)
        drs_agg = aggregate_per_bus(drs_evals)
        f_shitty = float(np.mean([e["f_mean"] for e in shitty_evals
                                   if not np.isnan(e["f_mean"])]))
        f_drs = float(np.mean([e["f_mean"] for e in drs_evals
                                if not np.isnan(e["f_mean"])]))
        # Totals
        total_tp = sum(c["TP"] for ev in shitty_evals
                       for c in ev["confusion"])
        total_fp = sum(c["FP"] for ev in shitty_evals
                       for c in ev["confusion"])
        total_fn = sum(c["FN"] for ev in shitty_evals
                       for c in ev["confusion"])
        prec = total_tp / max(total_tp + total_fp, 1)
        rec = total_tp / max(total_tp + total_fn, 1)
        f_micro = 2 * prec * rec / max(prec + rec, 1e-9)

        results[crop_label] = {
            "skip_frames": skip_frames,
            "skip_seconds": skip_frames / FRAME_HZ,
            "f_shitty_macro": f_shitty,
            "f_drs_macro": f_drs,
            "shitty_total_TP": total_tp,
            "shitty_total_FP": total_fp,
            "shitty_total_FN": total_fn,
            "shitty_precision": prec,
            "shitty_recall": rec,
            "shitty_f_micro": f_micro,
            "shitty_per_bus": shitty_agg,
            "drs_per_bus": drs_agg,
        }

        print(f"  ShittyKit: F_macro = {f_shitty:.4f}  F_micro = {f_micro:.4f}  "
              f"P = {prec:.4f}  R = {rec:.4f}")
        print(f"  ShittyKit:   TP = {total_tp}  FP = {total_fp}  FN = {total_fn}")
        print(f"  DRSKit:    F_macro = {f_drs:.4f}")

    # Save JSON
    out_dir = _REPO_ROOT / "docs" / "gates" / "F0-T4c_MINI_L3" / \
              "edge_crop_diagnostic_2026-05-25"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "checkpoint": str(args.checkpoint.relative_to(_REPO_ROOT)) if (
            _REPO_ROOT in args.checkpoint.parents or args.checkpoint.is_relative_to(_REPO_ROOT)
        ) else str(args.checkpoint),
        "threshold": args.threshold,
        "frame_hz": FRAME_HZ,
        "results_by_crop": results,
    }
    out_path = out_dir / "edge_crop_summary.json"
    out_path.write_text(json.dumps(summary, indent=2, default=float))
    print(f"\n[edge-crop] wrote {out_path}", flush=True)

    # Console summary table
    print("\n" + "=" * 96)
    print("SUMMARY — edge crop diagnostic (checkpoint B, threshold = 0.1)")
    print("=" * 96)
    print(f"{'Crop level':<14} | {'skip (s)':>8} | "
          f"{'F Shitty':>9} | {'F micro':>9} | {'P':>6} | {'R':>6} | "
          f"{'TP':>5} | {'FP':>6} | {'FN':>5} | {'F DRSKit':>9}")
    print("-" * 96)
    for crop_label, _ in CROP_LEVELS:
        r = results[crop_label]
        print(f"{crop_label:<14} | {r['skip_seconds']:>8.3f} | "
              f"{r['f_shitty_macro']:>9.4f} | {r['shitty_f_micro']:>9.4f} | "
              f"{r['shitty_precision']:>6.4f} | {r['shitty_recall']:>6.4f} | "
              f"{r['shitty_total_TP']:>5} | {r['shitty_total_FP']:>6} | "
              f"{r['shitty_total_FN']:>5} | {r['f_drs_macro']:>9.4f}")
    print()

    # Per-bus delta crop_rf vs full
    print("Per-bus ShittyKit F (fixed thr 0.1):")
    print(f"{'Bus':<14} | {'full F':>8} | {'crop_0.5s F':>11} | {'crop_rf F':>9} | "
          f"{'Δ (rf-full)':>11}")
    print("-" * 96)
    for b in BUS_NAMES:
        f_full = results["full"]["shitty_per_bus"][b]["f_mean_sample"]
        f_05 = results["crop_0.5s"]["shitty_per_bus"][b]["f_mean_sample"]
        f_rf = results["crop_rf"]["shitty_per_bus"][b]["f_mean_sample"]
        f_full_s = f"{f_full:.3f}" if f_full is not None else "—"
        f_05_s = f"{f_05:.3f}" if f_05 is not None else "—"
        f_rf_s = f"{f_rf:.3f}" if f_rf is not None else "—"
        delta = (f_rf - f_full) if (f_rf and f_full) else None
        delta_s = f"{delta:+.3f}" if delta is not None else "—"
        print(f"{b:<14} | {f_full_s:>8} | {f_05_s:>11} | {f_rf_s:>9} | "
              f"{delta_s:>11}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
