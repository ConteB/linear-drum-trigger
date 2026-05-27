#!/usr/bin/env python3
"""Listening test ShittyKit — qualitative discrimination of OOD vs pathology.

CEO directive 2026-05-25 (sessione mixed-5kit FAIL): il mini-L3 cross-kit
ha saturazione confermata a ~0.10 val F. La domanda residua: ShittyKit è
*strutturalmente OOD* (la distribuzione timbrica è troppo lontana — fisiologico
del setup mini-L3) o è *pathologically defective* (il kit ha un problema
specifico che la rete coglie in modo anomalo)?

**2026-05-25 (post-listening-test) — extended for loss design competition:**
the test now accepts ``--checkpoint`` + ``--run-id`` to compare multiple
training runs under the same evaluation protocol. Each run produces its own
output subdir under ``docs/gates/F0-T4c_MINI_L3/listening_test_<run_id>/``.

Diagnosi:
  - Per-bus F sul val ShittyKit (aggregate + per-sample distribution)
  - Confronto con 5 DRSKit train sample (in-distribution baseline)
  - Confusion matrix per-bus su ShittyKit (false positive ratio)
  - Waveform/spettrogramma di 2 sample selezionati

Output:
  docs/gates/F0-T4c_MINI_L3/listening_test_<run_id>/
    ├── per_bus_summary.json
    ├── per_bus_comparison.png
    └── waveform_comparison.png
"""
from __future__ import annotations

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

from neural.channel_agnostic import (  # noqa: E402
    ChannelAgnosticConfig,
    ChannelAgnosticFrontend,
)
from neural.data import DEFAULT_LOOKAHEAD_FRAMES, load_pool  # noqa: E402
from neural.model import ComposedTCN, TCNConfig, TCNModel  # noqa: E402
from neural.preprocessing import PreprocessingFrontend  # noqa: E402
from neural.reporter import evaluate_sample_for_report  # noqa: E402


BUS_NAMES = [
    "kick", "snare", "hihat", "tom_hi_mid", "floor",
    "ride", "crash_a", "crash_b_misc",
]
GATE_ROOT = _REPO_ROOT / "docs" / "gates" / "F0-T4c_MINI_L3"


def load_model_from_checkpoint(
    ckpt_path: Path,
    *,
    warmup_pool: Path | None = None,
    warmup_n_samples: int = 30,
) -> ComposedTCN:
    """Load a TCN checkpoint with optional P1+P2 + F0-T4e channel-agnostic frontend.

    **2026-05-26 audit bugfix**: ChannelNorm has EMA-tracked running stats
    (mean/var) that are CRITICAL for correct inference but were not being
    serialized by older training runs. Two recovery paths:

    1. If the checkpoint includes ``preprocess_state`` (saved by the
       2026-05-26+ trainer), load it directly — the running stats are exact.
    2. Otherwise (legacy checkpoints: B-planA, H, c128, combo-final, ...)
       run a *warm-up pass* over ``warmup_n_samples`` from ``warmup_pool``
       in TRAIN mode to repopulate the EMA, then switch to eval mode.
       This reconstructs the running stats post-hoc (deterministic seed,
       sample-order stable for reproducibility).

    **F0-T4e (Decision Lock CEO 2026-05-26)**: checkpoints saved after this
    spec may include ``channel_agnostic_state``. If present, the
    :class:`ChannelAgnosticFrontend` is composed *before* the preprocessing
    frontend, mirroring the training-time pipeline. The ``input_agnostic``
    flag in the checkpoint is the authoritative signal; the warmup pass
    runs through the full composed stack so the ChannelNorm EMA reflects
    the actual aggregated tensor the model was trained on.
    """
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    tcn = TCNModel(TCNConfig(channels=ckpt["config"]["channels"], in_channels=9))
    tcn.load_state_dict(ckpt["model_state"])
    pre = PreprocessingFrontend(n_mic=8, onset_envelope=True)

    # F0-T4e channel-agnostic frontend (optional, opt-in via training flag).
    channel_agnostic: ChannelAgnosticFrontend | None = None
    if ckpt.get("input_agnostic"):
        per_ch = int(ckpt.get("input_agnostic_channels") or 4)
        channel_agnostic = ChannelAgnosticFrontend(
            ChannelAgnosticConfig(per_channel_channels=per_ch),
        )
        if "channel_agnostic_state" in ckpt:
            channel_agnostic.load_state_dict(ckpt["channel_agnostic_state"])
            print(f"[listening] F0-T4e channel-agnostic frontend ON  "
                  f"C_per_ch={per_ch}  loaded from checkpoint")
        else:
            print("[listening] ⚠️ WARNING: input_agnostic=True but no "
                  "channel_agnostic_state in checkpoint — using random init "
                  "(this is a checkpoint format bug, not a runtime issue).")

    if "preprocess_state" in ckpt:
        pre.load_state_dict(ckpt["preprocess_state"])
        print(f"[listening] loaded preprocess_state from checkpoint "
              f"(running_var range "
              f"[{pre.channel_norm.running_var.min().item():.4f}, "
              f"{pre.channel_norm.running_var.max().item():.4f}])")
    elif warmup_pool is not None:
        print(f"[listening] checkpoint has no preprocess_state — "
              f"running warm-up pass on {warmup_n_samples} train samples "
              f"to reconstruct ChannelNorm EMA…")
        from neural.data import discover_gold_keys, load_gold_sample  # noqa: PLC0415
        triples = sorted(discover_gold_keys(warmup_pool), key=lambda x: x[1])
        # Pick spread-out indices to span all kits/MIDI of the train pool.
        step = max(1, len(triples) // warmup_n_samples)
        picks = triples[::step][:warmup_n_samples]
        pre.train()  # enable EMA update
        if channel_agnostic is not None:
            channel_agnostic.eval()  # the frontend has no running stats
        with torch.no_grad():
            for d, k in picks:
                s = load_gold_sample(d, k)
                # Use the first crop_samples worth of audio (4.46s default).
                audio = torch.from_numpy(s.audio[:, :196608]).float().unsqueeze(0)
                if channel_agnostic is not None:
                    audio = channel_agnostic(audio)
                pre(audio)  # updates running_mean/running_var
        pre.eval()
        rv = pre.channel_norm.running_var
        print(f"[listening] warm-up done — running_var range "
              f"[{rv.min().item():.4f}, {rv.max().item():.4f}]  "
              f"(was [1.0, 1.0] before)")
    else:
        print("[listening] ⚠️ WARNING: legacy checkpoint without "
              "preprocess_state and no warmup_pool — ChannelNorm will be "
              "identity passthrough (BUG: incorrect input scaling).")

    eval_model = ComposedTCN(
        tcn, channel_agnostic=channel_agnostic, preprocessing=pre,
    ).eval()
    return eval_model


def evaluate_with_fixed_threshold(
    model: Any, audio_np: Any, target_np: Any,
    *, n_sample: int, lookahead_frames: int, threshold: float = 0.1,
    skip_edge_frames: int = 0,
) -> dict[str, Any]:
    """Evaluate one sample with a *fixed* peak-pick threshold (no tuning).

    `evaluate_sample_for_report` always tunes the threshold per sample
    (which inflates the F-mean — useful for L3 de-risking but not
    representative of production). This variant uses a fixed threshold,
    the production setting.

    **2026-05-25 (post-piano-roll diagnostic):** ``skip_edge_frames``
    crops the first N frames from BOTH prediction and target before
    peak-picking. This isolates the network's true behaviour from the
    receptive-field-warmup edge effect (which contains ~77 % of total FP
    on the ShittyKit val pool — see `LOSS_COMPETITION` §addendum).
    """
    import torch  # noqa: PLC0415
    from neural.metrics import match_onsets, peak_pick  # noqa: PLC0415

    L = max(0, int(lookahead_frames))
    audio = torch.from_numpy(audio_np[None, :, :n_sample]).float()
    with torch.no_grad():
        pred = model(audio).squeeze(0).cpu().numpy()
    # Lookahead shift on target.
    if L > 0:
        target = target_np[L:]
        pred = pred[:target.shape[0]]
    else:
        target = target_np[:pred.shape[0]]
    # Edge crop — drop the first ``skip_edge_frames`` from both pred and target.
    if skip_edge_frames > 0:
        pred = pred[skip_edge_frames:]
        target = target[skip_edge_frames:]
    # flat-25: onset cols are 0,3,6,9,12,15,18,21
    onset_pred = pred[:, 0:24:3]
    onset_target = target[:, 0:24:3]

    n_true_per_bus, n_pred_per_bus, n_matched_per_bus = [], [], []
    f_per_bus = []
    confusion = []
    for b in range(8):
        peaks_pred = peak_pick(onset_pred[:, b], threshold=threshold)
        peaks_true = peak_pick(onset_target[:, b], threshold=0.5)
        n_m, _ = match_onsets(peaks_pred, peaks_true)
        n_t, n_p = len(peaks_true), len(peaks_pred)
        n_true_per_bus.append(n_t); n_pred_per_bus.append(n_p)
        n_matched_per_bus.append(n_m)
        precision = n_m / n_p if n_p > 0 else None
        recall = n_m / n_t if n_t > 0 else None
        f = (2 * precision * recall / (precision + recall)
             if precision and recall and precision + recall > 0 else None)
        f_per_bus.append(f if f is not None else float("nan"))
        confusion.append({
            "TP": n_m,
            "FP": n_p - n_m,
            "FN": n_t - n_m,
            "TN": 0,
        })

    f_finite = [f for f in f_per_bus if not np.isnan(f)]
    f_mean = float(np.mean(f_finite)) if f_finite else float("nan")

    return {
        "f_mean": f_mean,
        "f_per_bus": f_per_bus,
        "n_true_per_bus": n_true_per_bus,
        "n_pred_per_bus": n_pred_per_bus,
        "n_matched_per_bus": n_matched_per_bus,
        "confusion": confusion,
        "threshold": threshold,
    }


def aggregate_per_bus(evals: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum TP/FP/FN per bus across samples + compute aggregate F."""
    n_bus = 8
    tp = [0] * n_bus
    fp = [0] * n_bus
    fn = [0] * n_bus
    f_per_sample: list[list[float | None]] = [[] for _ in range(n_bus)]
    n_samples_with_bus = [0] * n_bus
    for ev in evals:
        for b in range(n_bus):
            cm = ev["confusion"][b]
            tp[b] += cm.get("TP", 0)
            fp[b] += cm.get("FP", 0)
            fn[b] += cm.get("FN", 0)
            f_b = ev["f_per_bus"][b]
            if f_b is not None and not (isinstance(f_b, float)
                                          and np.isnan(f_b)):
                f_per_sample[b].append(float(f_b))
                n_samples_with_bus[b] += 1
    summary = {}
    for b in range(n_bus):
        bus = BUS_NAMES[b]
        precision = tp[b] / (tp[b] + fp[b]) if tp[b] + fp[b] > 0 else None
        recall = tp[b] / (tp[b] + fn[b]) if tp[b] + fn[b] > 0 else None
        f_agg = (2 * precision * recall / (precision + recall)
                 if precision and recall and precision + recall > 0 else None)
        summary[bus] = {
            "tp": tp[b], "fp": fp[b], "fn": fn[b],
            "precision": precision, "recall": recall,
            "f_aggregate": f_agg,
            "f_mean_sample": float(np.mean(f_per_sample[b]))
                              if f_per_sample[b] else None,
            "f_max_sample": float(np.max(f_per_sample[b]))
                              if f_per_sample[b] else None,
            "n_samples_with_bus": n_samples_with_bus[b],
            "fp_to_fn_ratio": (fp[b] / fn[b]) if fn[b] > 0 else None,
        }
    return summary


def plot_per_bus_comparison(
    shittykit_summary: dict[str, Any],
    drskit_summary: dict[str, Any],
    out_path: Path,
) -> None:
    """Bar chart: F per-bus ShittyKit val vs DRSKit train."""
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    x = np.arange(len(BUS_NAMES))
    width = 0.35

    # Top: F-mean per sample (mean of per-sample F-scores)
    shitty_f = [shittykit_summary[b]["f_mean_sample"] or 0.0 for b in BUS_NAMES]
    drs_f = [drskit_summary[b]["f_mean_sample"] or 0.0 for b in BUS_NAMES]
    axes[0].bar(x - width/2, shitty_f, width, label="ShittyKit val (vergine)",
                color="#cc4444", edgecolor="black")
    axes[0].bar(x + width/2, drs_f, width, label="DRSKit train (in-dist)",
                color="#44aa44", edgecolor="black")
    axes[0].set_ylabel("F-measure (mean per sample)")
    axes[0].set_title("Per-bus F-measure: ShittyKit (val, cross-kit) vs "
                      "DRSKit (train, in-distribution)\n"
                      "Checkpoint: mini-l3-crosskit-p1p2-c64-mixed5kit "
                      "(C=64, 5 kit train, val F_mean = 0.099)")
    axes[0].legend(loc="upper right")
    axes[0].grid(axis="y", alpha=0.3)
    axes[0].set_ylim(0, 1.0)

    # Bottom: FP/FN ratio (collapse indicator)
    fp_fn = [shittykit_summary[b]["fp_to_fn_ratio"] for b in BUS_NAMES]
    fp_fn_plot = [v if v is not None else 0.0 for v in fp_fn]
    bars = axes[1].bar(x, fp_fn_plot, color="#cc4444", edgecolor="black")
    axes[1].axhline(1.0, color="black", linestyle="--", alpha=0.5,
                    label="balanced FP=FN")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(BUS_NAMES, rotation=20)
    axes[1].set_ylabel("FP / FN ratio (ShittyKit val)")
    axes[1].set_title("False-Positive / False-Negative ratio per bus — "
                      "high values = 'predict-everywhere' collapse")
    axes[1].legend()
    axes[1].grid(axis="y", alpha=0.3)
    for bar, val in zip(bars, fp_fn, strict=True):
        if val is not None and val > 0:
            axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                         f"{val:.1f}", ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close()


def plot_waveform_comparison(
    shitty_sample: Any, drs_sample: Any, out_path: Path,
) -> None:
    """Spectrogram comparison of 1 ShittyKit val + 1 DRSKit train sample."""
    fig, axes = plt.subplots(2, 4, figsize=(16, 7))

    for col, (label, sample) in enumerate([
        ("ShittyKit val (vergine)", shitty_sample),
        ("DRSKit train (in-dist)", drs_sample),
    ]):
        audio = sample.audio[:, :44100 * 3]  # first 3s
        # Pick representative channels: snare (1), hihat (2)
        for row, ch_idx, ch_name in [(0, 1, "snare"), (1, 2, "hihat")]:
            ax_wav = axes[row, col * 2]
            ax_spec = axes[row, col * 2 + 1]

            t = np.arange(audio.shape[1]) / 44100
            ax_wav.plot(t, audio[ch_idx], color="black", linewidth=0.5)
            ax_wav.set_xlim(0, 3)
            peak = float(np.abs(audio[ch_idx]).max()) if audio.shape[1] > 0 else 0.0
            ax_wav.set_title(f"{label}\n{ch_name} waveform (peak={peak:.3f})",
                             fontsize=9)
            ax_wav.set_xlabel("time (s)")
            ax_wav.set_ylim(-0.5, 0.5)
            ax_wav.grid(alpha=0.3)

            # Spectrogram
            from scipy.signal import spectrogram  # noqa: PLC0415
            f, t_s, Sxx = spectrogram(audio[ch_idx], fs=44100, nperseg=1024,
                                       noverlap=512)
            log_sxx = 10 * np.log10(Sxx + 1e-12)
            ax_spec.pcolormesh(t_s, f, log_sxx, shading="auto", cmap="magma",
                               vmin=-60, vmax=0)
            ax_spec.set_ylim(0, 12000)
            ax_spec.set_title(f"{ch_name} spectrogram", fontsize=9)
            ax_spec.set_xlabel("time (s)")
            ax_spec.set_ylabel("Hz")

    plt.tight_layout()
    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close()


def main() -> int:
    import argparse  # noqa: PLC0415
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint", type=Path,
        default=_REPO_ROOT / "artifacts" / "mini_l3_tcn_p1p2_c64_mixed5kit.pt",
    )
    parser.add_argument("--run-id", default="shittykit_2026-05-25",
                         help="Sub-directory name for the output.")
    parser.add_argument("--fixed-threshold", type=float, default=0.1,
                         help="Threshold for the production-style evaluation.")
    parser.add_argument("--warmup-pool", type=Path,
                        default=_REPO_ROOT / "data" / "gold" / "mini_l3_train",
                        help="Train pool used to warm up ChannelNorm running "
                             "stats for legacy checkpoints (without "
                             "preprocess_state). Set empty string to disable.")
    parser.add_argument("--warmup-n-samples", type=int, default=60,
                        help="Number of train samples used in the warm-up pass "
                             "(2026-05-26 audit bugfix).")
    parser.add_argument("--skip-edge-frames", type=int, default=0,
                        help="Skip the first N output frames in the fixed-"
                             "threshold evaluation (Bug #3 from 2026-05-26 "
                             "audit; recommended 1024 = TCN RF size).")
    args = parser.parse_args()

    ckpt_path = args.checkpoint
    if not ckpt_path.exists():
        print(f"ERROR: missing checkpoint {ckpt_path}", flush=True)
        return 1

    out_dir = GATE_ROOT / f"listening_test_{args.run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    global OUT_DIR  # noqa: PLW0603 — back-compat for any closure capture
    OUT_DIR = out_dir

    print(f"[listening] loading checkpoint {ckpt_path.name}…", flush=True)
    warmup_pool: Path | None = args.warmup_pool if str(args.warmup_pool) else None
    model = load_model_from_checkpoint(
        ckpt_path, warmup_pool=warmup_pool,
        warmup_n_samples=args.warmup_n_samples,
    )

    print(f"[listening] loading ShittyKit val…", flush=True)
    val_samples = load_pool(_REPO_ROOT / "data" / "gold" / "mini_l3_val")
    print(f"[listening]   {len(val_samples)} val samples", flush=True)

    print(f"[listening] loading DRSKit train sample…", flush=True)
    # GoldSample.key doesn't carry the kit; load directly from the kit
    # sub-directory (load_pool is recursive but the kit info is the
    # parent path, not the key).
    drs_samples = load_pool(_REPO_ROOT / "data" / "gold" / "mini_l3_train" / "DRSKit")
    print(f"[listening]   {len(drs_samples)} DRSKit train samples — pick 30",
          flush=True)
    drs_samples = drs_samples[:30]  # subset for speed

    crop_samples = 196608
    lookahead = DEFAULT_LOOKAHEAD_FRAMES

    print(f"[listening] evaluating ShittyKit ({len(val_samples)} samples) — "
          f"tuned threshold…", flush=True)
    shitty_evals_tuned = [
        evaluate_sample_for_report(model, s.audio, s.target,
                                    n_sample=crop_samples,
                                    lookahead_frames=lookahead)
        for s in val_samples
    ]
    print(f"[listening] evaluating ShittyKit ({len(val_samples)} samples) — "
          f"fixed threshold {args.fixed_threshold}…", flush=True)
    shitty_evals_fixed = [
        evaluate_with_fixed_threshold(model, s.audio, s.target,
                                       n_sample=crop_samples,
                                       lookahead_frames=lookahead,
                                       threshold=args.fixed_threshold,
                                       skip_edge_frames=args.skip_edge_frames)
        for s in val_samples
    ]
    print(f"[listening] evaluating DRSKit train ({len(drs_samples)} samples) — "
          f"tuned threshold…", flush=True)
    drs_evals_tuned = [
        evaluate_sample_for_report(model, s.audio, s.target,
                                    n_sample=crop_samples,
                                    lookahead_frames=lookahead)
        for s in drs_samples
    ]
    print(f"[listening] evaluating DRSKit train ({len(drs_samples)} samples) — "
          f"fixed threshold {args.fixed_threshold}…", flush=True)
    drs_evals_fixed = [
        evaluate_with_fixed_threshold(model, s.audio, s.target,
                                       n_sample=crop_samples,
                                       lookahead_frames=lookahead,
                                       threshold=args.fixed_threshold,
                                       skip_edge_frames=args.skip_edge_frames)
        for s in drs_samples
    ]

    # Aggregate both protocols.
    shitty_summary_tuned = aggregate_per_bus(shitty_evals_tuned)
    shitty_summary_fixed = aggregate_per_bus(shitty_evals_fixed)
    drs_summary_tuned = aggregate_per_bus(drs_evals_tuned)
    drs_summary_fixed = aggregate_per_bus(drs_evals_fixed)

    f_overall_shitty_tuned = float(np.mean([
        e["f_mean"] for e in shitty_evals_tuned if not np.isnan(e["f_mean"])
    ]))
    f_overall_shitty_fixed = float(np.mean([
        e["f_mean"] for e in shitty_evals_fixed if not np.isnan(e["f_mean"])
    ]))
    f_overall_drs_tuned = float(np.mean([
        e["f_mean"] for e in drs_evals_tuned if not np.isnan(e["f_mean"])
    ]))
    f_overall_drs_fixed = float(np.mean([
        e["f_mean"] for e in drs_evals_fixed if not np.isnan(e["f_mean"])
    ]))

    ckpt_abs = ckpt_path.resolve()
    try:
        ckpt_rel = str(ckpt_abs.relative_to(_REPO_ROOT))
    except ValueError:
        ckpt_rel = str(ckpt_abs)
    summary = {
        "checkpoint": ckpt_rel,
        "run_id": args.run_id,
        "fixed_threshold": args.fixed_threshold,
        "n_shittykit_val_samples": len(val_samples),
        "n_drskit_train_samples_eval": len(drs_samples),
        "f_overall_shittykit_tuned": f_overall_shitty_tuned,
        "f_overall_shittykit_fixed": f_overall_shitty_fixed,
        "f_overall_drskit_train_tuned": f_overall_drs_tuned,
        "f_overall_drskit_train_fixed": f_overall_drs_fixed,
        "per_bus_shittykit_val_tuned": shitty_summary_tuned,
        "per_bus_shittykit_val_fixed": shitty_summary_fixed,
        "per_bus_drskit_train_tuned": drs_summary_tuned,
        "per_bus_drskit_train_fixed": drs_summary_fixed,
    }
    # For backward-compat with plot functions (single set of summaries).
    shitty_summary = shitty_summary_fixed
    drs_summary = drs_summary_fixed
    shitty_evals = shitty_evals_fixed

    (OUT_DIR / "per_bus_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True)
    )
    print(f"[listening] wrote {OUT_DIR}/per_bus_summary.json", flush=True)

    plot_per_bus_comparison(shitty_summary, drs_summary,
                             OUT_DIR / "per_bus_comparison.png")
    print(f"[listening] wrote per_bus_comparison.png", flush=True)

    # Pick the worst & best ShittyKit sample for waveform comparison
    shitty_evals_sorted = sorted(
        zip(val_samples, shitty_evals, strict=True),
        key=lambda x: x[1]["f_mean"] if not np.isnan(x[1]["f_mean"]) else -1,
    )
    worst_shitty = shitty_evals_sorted[0][0]
    drs_pick = drs_samples[0]
    plot_waveform_comparison(worst_shitty, drs_pick,
                              OUT_DIR / "waveform_comparison.png")
    print(f"[listening] wrote waveform_comparison.png", flush=True)

    # Console summary
    print("\n" + "=" * 88)
    print(f"LISTENING TEST SUMMARY  [run_id = {args.run_id}]")
    print("=" * 88)
    print(f"ShittyKit val F (tuned per-sample):    {f_overall_shitty_tuned:.4f}")
    print(f"ShittyKit val F (fixed thr {args.fixed_threshold}):       "
          f"{f_overall_shitty_fixed:.4f}")
    print(f"DRSKit train F (tuned per-sample):     {f_overall_drs_tuned:.4f}")
    print(f"DRSKit train F (fixed thr {args.fixed_threshold}):        "
          f"{f_overall_drs_fixed:.4f}")
    print(f"Ratio DRS_tuned/Shitty_tuned: "
          f"{f_overall_drs_tuned / max(f_overall_shitty_tuned, 1e-6):.2f}×")
    print(f"Ratio DRS_fixed/Shitty_fixed: "
          f"{f_overall_drs_fixed / max(f_overall_shitty_fixed, 1e-6):.2f}×")
    print()
    print("Per-bus (FIXED threshold — production-style):")
    print(f"{'Bus':<14} | {'ShittyKit F':>11} | {'DRSKit F':>9} | "
          f"{'FP/FN (Shitty)':>14}")
    print("-" * 88)
    for b in BUS_NAMES:
        s = shitty_summary_fixed[b]
        d = drs_summary_fixed[b]
        f_s = s["f_mean_sample"]
        f_d = d["f_mean_sample"]
        ratio = s["fp_to_fn_ratio"]
        f_s_str = f"{f_s:.3f}" if f_s is not None else "—"
        f_d_str = f"{f_d:.3f}" if f_d is not None else "—"
        ratio_str = f"{ratio:.2f}" if ratio is not None else "—"
        print(f"{b:<14} | {f_s_str:>11} | {f_d_str:>9} | {ratio_str:>14}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
