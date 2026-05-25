#!/usr/bin/env python3
"""Listening test ShittyKit — qualitative discrimination of OOD vs pathology.

CEO directive 2026-05-25 (sessione mixed-5kit FAIL): il mini-L3 cross-kit
ha saturazione confermata a ~0.10 val F. La domanda residua: ShittyKit è
*strutturalmente OOD* (la distribuzione timbrica è troppo lontana — fisiologico
del setup mini-L3) o è *pathologically defective* (il kit ha un problema
specifico che la rete coglie in modo anomalo)?

Diagnosi:
  - Per-bus F sul val ShittyKit (aggregate + per-sample distribution)
  - Confronto con 5 DRSKit train sample (in-distribution baseline)
  - Confusion matrix per-bus su ShittyKit (false positive ratio)
  - Waveform/spettrogramma di 2 sample selezionati

Output:
  docs/gates/F0-T4c_MINI_L3/listening_test_shittykit_2026-05-25/
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

from neural.data import DEFAULT_LOOKAHEAD_FRAMES, load_pool  # noqa: E402
from neural.model import TCNConfig, TCNModel  # noqa: E402
from neural.preprocessing import PreprocessingFrontend  # noqa: E402
from neural.reporter import evaluate_sample_for_report  # noqa: E402


BUS_NAMES = [
    "kick", "snare", "hihat", "tom_hi_mid", "floor",
    "ride", "crash_a", "crash_b_misc",
]
OUT_DIR = _REPO_ROOT / "docs" / "gates" / "F0-T4c_MINI_L3" / \
          "listening_test_shittykit_2026-05-25"


class _Composed(torch.nn.Module):
    """Wrap preprocessing + TCN as one model for evaluate_sample_for_report."""

    def __init__(self, pre: torch.nn.Module, mdl: torch.nn.Module) -> None:
        super().__init__()
        self.pre = pre
        self.mdl = mdl
        self.config = mdl.config

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # noqa: D401
        return self.mdl(self.pre(x))


def load_model_from_checkpoint(ckpt_path: Path) -> _Composed:
    """Load the C=64 mixed-5kit checkpoint."""
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    tcn = TCNModel(TCNConfig(channels=ckpt["config"]["channels"], in_channels=9))
    tcn.load_state_dict(ckpt["model_state"])
    pre = PreprocessingFrontend(n_mic=8, onset_envelope=True)
    eval_model = _Composed(pre, tcn).eval()
    return eval_model


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
    ckpt_path = _REPO_ROOT / "artifacts" / "mini_l3_tcn_p1p2_c64_mixed5kit.pt"
    if not ckpt_path.exists():
        print(f"ERROR: missing checkpoint {ckpt_path}", flush=True)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[listening] loading checkpoint {ckpt_path.name}…", flush=True)
    model = load_model_from_checkpoint(ckpt_path)

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

    print(f"[listening] evaluating ShittyKit ({len(val_samples)} samples)…",
          flush=True)
    shitty_evals = [
        evaluate_sample_for_report(model, s.audio, s.target,
                                    n_sample=crop_samples,
                                    lookahead_frames=lookahead)
        for s in val_samples
    ]
    print(f"[listening] evaluating DRSKit train ({len(drs_samples)} samples)…",
          flush=True)
    drs_evals = [
        evaluate_sample_for_report(model, s.audio, s.target,
                                    n_sample=crop_samples,
                                    lookahead_frames=lookahead)
        for s in drs_samples
    ]

    shitty_summary = aggregate_per_bus(shitty_evals)
    drs_summary = aggregate_per_bus(drs_evals)

    f_overall_shitty = float(np.mean([
        e["f_mean"] for e in shitty_evals if not np.isnan(e["f_mean"])
    ]))
    f_overall_drs = float(np.mean([
        e["f_mean"] for e in drs_evals if not np.isnan(e["f_mean"])
    ]))

    summary = {
        "checkpoint": str(ckpt_path.relative_to(_REPO_ROOT)),
        "n_shittykit_val_samples": len(val_samples),
        "n_drskit_train_samples_eval": len(drs_samples),
        "f_overall_shittykit": f_overall_shitty,
        "f_overall_drskit_train": f_overall_drs,
        "f_ratio_train_to_val": f_overall_drs / max(f_overall_shitty, 1e-6),
        "per_bus_shittykit_val": shitty_summary,
        "per_bus_drskit_train": drs_summary,
    }

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
    print("\n" + "=" * 72)
    print("LISTENING TEST SUMMARY")
    print("=" * 72)
    print(f"ShittyKit val F_overall:       {f_overall_shitty:.4f} "
          f"(n={len(val_samples)})")
    print(f"DRSKit train F_overall:        {f_overall_drs:.4f} "
          f"(n={len(drs_samples)})")
    print(f"Ratio train/val:               {f_overall_drs / max(f_overall_shitty, 1e-6):.2f}×")
    print()
    print(f"{'Bus':<14} | {'ShittyKit val F':>15} | {'DRSKit train F':>15} | "
          f"{'FP/FN':>8}")
    print("-" * 72)
    for b in BUS_NAMES:
        s = shitty_summary[b]
        d = drs_summary[b]
        f_s = s["f_mean_sample"]
        f_d = d["f_mean_sample"]
        ratio = s["fp_to_fn_ratio"]
        f_s_str = f"{f_s:.3f}" if f_s is not None else "—"
        f_d_str = f"{f_d:.3f}" if f_d is not None else "—"
        ratio_str = f"{ratio:.2f}" if ratio is not None else "—"
        print(f"{b:<14} | {f_s_str:>15} | {f_d_str:>15} | {ratio_str:>8}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
