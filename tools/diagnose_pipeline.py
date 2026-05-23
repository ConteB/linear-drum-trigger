#!/usr/bin/env python3
"""Opzione A · Step 2 — Input pipeline diagnostic (numerical audit).

Loads N random samples from a Gold pool and reports per-channel audio
statistics + per-bus target sparsity, *exactly* as the training loop sees them
(via :func:`GoldDataset` → ``_apply_canonical_slots``).

Looks for the three failure modes the memory hypothesis enumerates:

1. **Input scale broken** — audio not centred, var ≪ 0.01 (silent slots
   diluting the signal), or peak saturating ≈ 1.0 (cooked Gold).
2. **Slot map degenerate** — most of the 8 canonical slots are zero-filled
   (i.e. the dataset is dominated by mic_config = mono / solo_stereo and the
   network is learning on 1-2 slots only).
3. **Target sparsity extreme** — onset density per bus < 0.5 % or > 30 %,
   either of which collapses the gradient (no positives / class noise).

Usage::

    PYTHONPATH=src .venv/bin/python tools/diagnose_pipeline.py \\
        --pool data/gold/mix_2026-05-24 --n-samples 50

Writes a JSON report to ``artifacts/pipeline_diagnostic.json`` and prints a
short table to stdout.

Spec: ``[[next-session-option-a-diagnostic]]`` §2.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from neural.data import (  # noqa: E402
    CANONICAL_SLOTS,
    ENCODER_STRIDE,
    HIHAT_OPENING_COL,
    discover_gold_keys,
    load_gold_sample,
)

# Default audit crop = 65 536 samples = 512 frames = ~1.5 s. Matches the
# t1b_train_mix.py default.
_DEFAULT_CROP_SAMPLES = 65536


def _percentile_safe(arr: np.ndarray, q: float) -> float:
    if arr.size == 0:
        return float("nan")
    return float(np.percentile(arr, q))


def _audio_stats(audio: np.ndarray) -> dict[str, list[float]]:
    """Per-channel mean / std / min / max / peak / pct-zero of an [8, N] buffer."""
    n_chan, _ = audio.shape
    means: list[float] = []
    stds: list[float] = []
    mins: list[float] = []
    maxes: list[float] = []
    peaks: list[float] = []
    pct_zero: list[float] = []
    for c in range(n_chan):
        ch = audio[c]
        # Cast to float64 to avoid fp16 / fp32 underflow on var()
        ch64 = ch.astype(np.float64, copy=False)
        means.append(float(ch64.mean()))
        stds.append(float(ch64.std()))
        mins.append(float(ch64.min()))
        maxes.append(float(ch64.max()))
        peaks.append(float(np.abs(ch64).max()))
        # "Zero" means literally 0.0 — these are the canonical-slot zero-fills.
        pct_zero.append(float(np.mean(ch == 0.0) * 100.0))
    return {
        "mean": means,
        "std": stds,
        "min": mins,
        "max": maxes,
        "peak": peaks,
        "pct_zero": pct_zero,
    }


def _target_stats(target: np.ndarray) -> dict[str, list[float] | float]:
    """Per-bus onset density and HiHat opening summary from a [T, 25] target."""
    onset = target[:, 0:24:3]  # [T, 8]
    velocity = target[:, 1:24:3]  # [T, 8]
    microtiming = target[:, 2:24:3]  # [T, 8]
    hihat = target[:, HIHAT_OPENING_COL]  # [T]

    T = onset.shape[0]  # noqa: N806
    onset_density_per_bus: list[float] = []
    onset_peak_per_bus: list[float] = []
    velocity_mean_active_per_bus: list[float] = []
    for b in range(onset.shape[1]):
        # "On" frames: target Gaussian-smeared > 0.5 (matches the training
        # mask threshold of loss.LossConfig.onset_mask_threshold).
        on_mask = onset[:, b] > 0.5
        onset_density_per_bus.append(float(on_mask.mean() * 100.0))
        onset_peak_per_bus.append(float(onset[:, b].max()))
        if on_mask.any():
            velocity_mean_active_per_bus.append(
                float(velocity[on_mask, b].mean())
            )
        else:
            velocity_mean_active_per_bus.append(float("nan"))
    return {
        "onset_density_pct": onset_density_per_bus,
        "onset_peak_per_bus": onset_peak_per_bus,
        "velocity_mean_active": velocity_mean_active_per_bus,
        "hihat_min": float(hihat.min()),
        "hihat_max": float(hihat.max()),
        "hihat_mean": float(hihat.mean()),
        "hihat_std": float(hihat.std()),
        "microtiming_min": float(microtiming.min()),
        "microtiming_max": float(microtiming.max()),
        "n_frames": T,
    }


def _check_nonfinite(audio: np.ndarray, target: np.ndarray) -> tuple[int, int]:
    return (
        int(np.sum(~np.isfinite(audio))),
        int(np.sum(~np.isfinite(target))),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Input pipeline diagnostic (Opzione A · Step 2)"
    )
    parser.add_argument(
        "--pool",
        type=Path,
        default=_REPO_ROOT / "data" / "gold" / "mix_2026-05-24",
        help="Gold pool root",
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=50,
        help="How many random samples to audit (default: 50)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--crop-samples",
        type=int,
        default=_DEFAULT_CROP_SAMPLES,
        help="Crop length used to mimic the training-time view (default: 65536)",
    )
    parser.add_argument(
        "--report-to",
        type=Path,
        default=_REPO_ROOT / "artifacts" / "pipeline_diagnostic.json",
    )
    args = parser.parse_args()

    if not args.pool.is_dir():
        print(f"FATAL: pool {args.pool} not found", file=sys.stderr)
        return 1
    if args.crop_samples % ENCODER_STRIDE != 0:
        print(
            f"FATAL: --crop-samples {args.crop_samples} not a multiple of "
            f"ENCODER_STRIDE={ENCODER_STRIDE}",
            file=sys.stderr,
        )
        return 1

    rng = random.Random(args.seed)
    triples = discover_gold_keys(args.pool)
    if len(triples) == 0:
        print(f"FATAL: no Gold triples under {args.pool}", file=sys.stderr)
        return 1
    chosen = rng.sample(triples, min(args.n_samples, len(triples)))
    print(f"[diagnose] pool       = {args.pool}")
    print(f"[diagnose] available  = {len(triples)} samples")
    print(f"[diagnose] auditing   = {len(chosen)} samples (seed={args.seed})")
    print(f"[diagnose] crop_samples = {args.crop_samples}")

    crop_frames = args.crop_samples // ENCODER_STRIDE

    mic_configs: Counter[str] = Counter()
    engines: Counter[str] = Counter()

    # Aggregate buffers: per-channel arrays of means/stds/peaks across the
    # whole audit, plus a global non-finite counter.
    per_chan_means: list[list[float]] = [[] for _ in range(CANONICAL_SLOTS)]
    per_chan_stds: list[list[float]] = [[] for _ in range(CANONICAL_SLOTS)]
    per_chan_peaks: list[list[float]] = [[] for _ in range(CANONICAL_SLOTS)]
    per_chan_pct_zero: list[list[float]] = [[] for _ in range(CANONICAL_SLOTS)]
    per_bus_onset_density: list[list[float]] = [[] for _ in range(8)]
    per_bus_onset_peak: list[list[float]] = [[] for _ in range(8)]
    per_bus_velocity_active: list[list[float]] = [[] for _ in range(8)]
    hihat_mean_list: list[float] = []
    hihat_std_list: list[float] = []
    hihat_min_list: list[float] = []
    hihat_max_list: list[float] = []
    microtiming_max_list: list[float] = []
    nonfinite_audio = 0
    nonfinite_target = 0
    n_samples_audited = 0

    for triple_dir, key in chosen:
        try:
            s = load_gold_sample(triple_dir, key)
        except Exception as e:  # noqa: BLE001
            print(f"[diagnose] WARN skipping {key}: {e}", file=sys.stderr)
            continue
        n_samples_audited += 1
        mic_configs[s.mic_config] += 1
        engines[s.engine] += 1

        # Mimic the training crop: random window of crop_samples, frame-aligned.
        n_sample = s.audio.shape[1]
        max_start_frame = (n_sample - args.crop_samples) // ENCODER_STRIDE
        if max_start_frame < 0:
            print(
                f"[diagnose] WARN sample {key} too short "
                f"({n_sample} < {args.crop_samples})", file=sys.stderr,
            )
            continue
        start_frame = rng.randint(0, max_start_frame)
        start_sample = start_frame * ENCODER_STRIDE
        a = s.audio[:, start_sample : start_sample + args.crop_samples]
        t = s.target[start_frame : start_frame + crop_frames]

        nf_a, nf_t = _check_nonfinite(a, t)
        nonfinite_audio += nf_a
        nonfinite_target += nf_t

        a_stats = _audio_stats(a)
        t_stats = _target_stats(t)
        for c in range(CANONICAL_SLOTS):
            per_chan_means[c].append(a_stats["mean"][c])
            per_chan_stds[c].append(a_stats["std"][c])
            per_chan_peaks[c].append(a_stats["peak"][c])
            per_chan_pct_zero[c].append(a_stats["pct_zero"][c])
        density = t_stats["onset_density_pct"]
        peak = t_stats["onset_peak_per_bus"]
        velactive = t_stats["velocity_mean_active"]
        assert isinstance(density, list)
        assert isinstance(peak, list)
        assert isinstance(velactive, list)
        for b in range(8):
            per_bus_onset_density[b].append(density[b])
            per_bus_onset_peak[b].append(peak[b])
            per_bus_velocity_active[b].append(velactive[b])
        hihat_mean_list.append(float(t_stats["hihat_mean"]))  # type: ignore[arg-type]
        hihat_std_list.append(float(t_stats["hihat_std"]))  # type: ignore[arg-type]
        hihat_min_list.append(float(t_stats["hihat_min"]))  # type: ignore[arg-type]
        hihat_max_list.append(float(t_stats["hihat_max"]))  # type: ignore[arg-type]
        microtiming_max_list.append(float(abs(t_stats["microtiming_max"])))  # type: ignore[arg-type]

    if n_samples_audited == 0:
        print("FATAL: no samples successfully audited", file=sys.stderr)
        return 1

    def _summarise(per_unit: list[list[float]]) -> list[dict[str, float]]:
        out: list[dict[str, float]] = []
        for vals in per_unit:
            arr = np.array(
                [v for v in vals if v == v],  # noqa: PLR0124 — keep finite (drop NaN)
                dtype=np.float64,
            )
            out.append(
                {
                    "p05": _percentile_safe(arr, 5),
                    "median": _percentile_safe(arr, 50),
                    "p95": _percentile_safe(arr, 95),
                    "mean": float(arr.mean()) if arr.size else float("nan"),
                }
            )
        return out

    audio_stats_summary = {
        "mean_per_slot": _summarise(per_chan_means),
        "std_per_slot": _summarise(per_chan_stds),
        "peak_per_slot": _summarise(per_chan_peaks),
        "pct_zero_per_slot": _summarise(per_chan_pct_zero),
    }
    target_stats_summary = {
        "onset_density_pct_per_bus": _summarise(per_bus_onset_density),
        "onset_peak_per_bus": _summarise(per_bus_onset_peak),
        "velocity_mean_active_per_bus": _summarise(per_bus_velocity_active),
        "hihat_mean_distribution": {
            "p05": _percentile_safe(np.array(hihat_mean_list), 5),
            "median": _percentile_safe(np.array(hihat_mean_list), 50),
            "p95": _percentile_safe(np.array(hihat_mean_list), 95),
        },
        "hihat_std_distribution": {
            "p05": _percentile_safe(np.array(hihat_std_list), 5),
            "median": _percentile_safe(np.array(hihat_std_list), 50),
            "p95": _percentile_safe(np.array(hihat_std_list), 95),
        },
        "hihat_min_max_range": {
            "min_of_min": float(np.min(hihat_min_list)),
            "max_of_max": float(np.max(hihat_max_list)),
        },
        "microtiming_abs_max_median": float(np.median(microtiming_max_list)),
    }

    report = {
        "n_samples_audited": n_samples_audited,
        "crop_samples": args.crop_samples,
        "crop_frames": crop_frames,
        "mic_configs": dict(mic_configs),
        "engines": dict(engines),
        "nonfinite_audio_total": nonfinite_audio,
        "nonfinite_target_total": nonfinite_target,
        "audio_stats": audio_stats_summary,
        "target_stats": target_stats_summary,
    }

    args.report_to.parent.mkdir(parents=True, exist_ok=True)
    args.report_to.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(f"[diagnose] wrote {args.report_to}")

    # ---- Pretty-print the critical numbers to stdout ----
    print()
    print("=" * 78)
    print("  AUDIO STATS (per canonical slot, across audited samples)")
    print("=" * 78)
    print(f"  mic_configs: {dict(mic_configs)}")
    print(f"  engines:     {dict(engines)}")
    print(f"  nonfinite audio = {nonfinite_audio}, nonfinite target = "
          f"{nonfinite_target}")
    print()
    slot_names = ["KCK", "SNR", "HH ", "TOM", "FLR", "OHL", "OHR", "ROO"]
    print(f"  {'slot':<6}{'std (p50)':>12}{'peak (p50)':>14}"
          f"{'%zero (p50)':>14}")
    for c in range(CANONICAL_SLOTS):
        std = audio_stats_summary["std_per_slot"][c]["median"]
        peak = audio_stats_summary["peak_per_slot"][c]["median"]
        pctz = audio_stats_summary["pct_zero_per_slot"][c]["median"]
        print(f"  {slot_names[c]:<6}{std:>12.4f}{peak:>14.4f}{pctz:>14.2f}")
    print()
    print("=" * 78)
    print("  TARGET STATS (per bus, across audited samples)")
    print("=" * 78)
    print(f"  {'bus':<6}{'density % (p50)':>18}{'peak (p50)':>14}"
          f"{'vel|active (p50)':>20}")
    for b in range(8):
        d = target_stats_summary["onset_density_pct_per_bus"][b]["median"]
        p = target_stats_summary["onset_peak_per_bus"][b]["median"]
        v = target_stats_summary["velocity_mean_active_per_bus"][b]["median"]
        v_str = "n/a" if v != v else f"{v:.3f}"  # noqa: PLR0124
        print(f"  {slot_names[b]:<6}{d:>18.3f}{p:>14.3f}{v_str:>20}")
    print()
    hh = target_stats_summary["hihat_mean_distribution"]
    hhstd = target_stats_summary["hihat_std_distribution"]
    print(f"  hihat mean p05/p50/p95 = "
          f"{hh['p05']:.3f}/{hh['median']:.3f}/{hh['p95']:.3f}")
    print(f"  hihat std  p05/p50/p95 = "
          f"{hhstd['p05']:.3f}/{hhstd['median']:.3f}/{hhstd['p95']:.3f}")

    # ---- Heuristic flags ----
    print()
    print("=" * 78)
    print("  HEURISTIC FLAGS")
    print("=" * 78)
    flags: list[str] = []
    # Slot zero-fill: any slot with > 80 % zero-fill across the median sample is
    # not providing signal. mic_config distribution explains this.
    for c in range(CANONICAL_SLOTS):
        pctz_p50 = audio_stats_summary["pct_zero_per_slot"][c]["median"]
        if pctz_p50 > 80.0:
            flags.append(
                f"slot {slot_names[c]} is ≥80 % zero-filled (p50 {pctz_p50:.1f}%)"
                " — does the input ever populate it?"
            )
    # Audio scale: any slot with std median < 1e-4 is essentially silent
    for c in range(CANONICAL_SLOTS):
        std_p50 = audio_stats_summary["std_per_slot"][c]["median"]
        if 0 < std_p50 < 1e-4:
            flags.append(
                f"slot {slot_names[c]} std (p50) = {std_p50:.6f} — sub-noise-floor"
            )
    # Onset density: < 0.5 % is extreme sparsity; > 30 % is mush
    for b in range(8):
        d = target_stats_summary["onset_density_pct_per_bus"][b]["median"]
        if d < 0.5:
            flags.append(
                f"bus {slot_names[b]} onset density p50 = {d:.2f}% — extreme "
                "sparsity (gradient starved)"
            )
        elif d > 30.0:
            flags.append(
                f"bus {slot_names[b]} onset density p50 = {d:.2f}% — too dense "
                "(class noise)"
            )
    # Peak target: should be near 1.0 for Gaussian-smeared onset
    for b in range(8):
        peak = target_stats_summary["onset_peak_per_bus"][b]["median"]
        if peak > 0 and peak < 0.95:
            flags.append(
                f"bus {slot_names[b]} onset peak p50 = {peak:.3f} — target not "
                "saturating to 1.0 (loss threshold 0.5 may misalign)"
            )
    # Hihat: should span [0, 1]
    if target_stats_summary["hihat_min_max_range"]["max_of_max"] < 0.5:
        flags.append("hihat target never exceeds 0.5 — opening axis collapsed")
    if not flags:
        flags.append("no heuristic flags — pipeline looks numerically clean")
    for f in flags:
        print(f"  ⚠ {f}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
