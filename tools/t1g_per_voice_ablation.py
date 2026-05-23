#!/usr/bin/env python3
"""T1-G per-voice ablation — isolate which audio_augment voice disrupts most.

Three augmented datasets are built from the mix Gold baseline, each
enabling exactly one voice of the pipeline:

* ``noise_only``        — pre_normalize + noise floor only
* ``gain_only``         — pre_normalize + gain perturbation only
* ``mic_balance_only``  — pre_normalize + per-channel mic balance only

Each dataset is then used to retrain the T1-C winner (C=32 B=4, 20 epoch)
and the holdout F-measure is compared against the baseline + the full
augmentation. The voice whose isolation produces the smallest F-measure
drop is the *least disruptive*; the voice with the largest drop is the
*disruptor* to soften first in F0-T16-post v2.

Output: ``docs/gates/R&D_Tier1_reports/T1-G/`` with per-voice JSON
summary + Pareto plot of (voice mask, mean_F).

Usage:
    PYTHONPATH=src .venv/bin/python tools/t1g_per_voice_ablation.py \
        --baseline-pool data/gold/mix_2026-05-24 \
        --epochs 20 --batch-size 4 --channels 32
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_VOICE_CONFIGS: tuple[tuple[str, dict[str, bool]], ...] = (
    ("noise_only",
     {"enable_noise": True, "enable_gain": False, "enable_mic_balance": False}),
    ("gain_only",
     {"enable_noise": False, "enable_gain": True, "enable_mic_balance": False}),
    ("mic_balance_only",
     {"enable_noise": False, "enable_gain": False, "enable_mic_balance": True}),
)


def _apply_voice(
    baseline_pool: Path,
    voice_name: str,
    toggles: dict[str, bool],
    master_seed: int,
) -> Path:
    """Build the per-voice augmented Gold dataset via a thin Python one-shot.

    We call the audio_augment pipeline directly here (rather than
    ``tools/t1e_apply_audio_aug.py``) so we can pass the per-voice
    toggles. Output: ``baseline_pool.parent / "<base>_aug_<voice>"``.
    """
    out_dir = baseline_pool.parent / f"{baseline_pool.name}_aug_{voice_name}"
    if out_dir.exists():
        print(f"[T1-G] {voice_name}: pool already exists at {out_dir} — reusing")
        return out_dir

    sys.path.insert(0, str(_REPO_ROOT / "src"))
    import hashlib
    import json as _json
    import shutil

    import numpy as np

    from data_engineering.audio_augment import (  # noqa: E402
        apply_audio_augmentation,
    )
    out_dir.mkdir(parents=True)
    dna_paths = sorted(baseline_pool.glob("*.dna.json"))
    n_ok = 0
    n_fail = 0
    for dna_path in dna_paths:
        key = dna_path.name.removesuffix(".dna.json")
        audio_in = baseline_pool / f"{key}.audio.f16"
        target_in = baseline_pool / f"{key}.target.f16"
        if not (audio_in.exists() and target_in.exists()):
            continue
        buf = np.frombuffer(audio_in.read_bytes(), dtype=np.float16)
        audio = buf.reshape(8, -1).astype(np.float16, copy=True)
        try:
            augmented = apply_audio_augmentation(
                audio,
                sample_key=key,
                variant_idx=1,
                master_seed=master_seed,
                noise_db_fs=-50.0,
                gain_range_db=(-3.0, 3.0),
                mic_balance_range_db=(-2.0, 2.0),
                pre_normalize_peak=0.5,
                **toggles,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {key}: {exc}")
            n_fail += 1
            continue
        audio_out_path = out_dir / f"{key}.audio.f16"
        audio_out_path.write_bytes(
            augmented.astype(np.float16, copy=False).tobytes()
        )
        shutil.copy2(target_in, out_dir / f"{key}.target.f16")
        new_sha = hashlib.sha256(audio_out_path.read_bytes()).hexdigest()
        n_nonfinite = int((~np.isfinite(augmented.astype(np.float32))).sum())
        dna = _json.loads(dna_path.read_text())
        dna.setdefault("audio", {})["sha256"] = new_sha
        dna["audio"]["n_nonfinite"] = n_nonfinite
        dna.setdefault("lineage", {})["audio_augment_voice"] = voice_name
        (out_dir / f"{key}.dna.json").write_text(
            _json.dumps(dna, indent=2, sort_keys=True)
        )
        n_ok += 1
    print(f"[T1-G] {voice_name}: {n_ok} OK, {n_fail} failed → {out_dir}")
    return out_dir


def _train_one(
    pool: Path,
    run_id: str,
    epochs: int,
    batch_size: int,
    channels: int,
    crop_samples: int,
) -> Path:
    report_to = _REPO_ROOT / "artifacts" / f"{run_id}_report.json"
    save_to = _REPO_ROOT / "artifacts" / f"{run_id}.pt"
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "tools" / "t1b_train_mix.py"),
        "--pool", str(pool),
        "--epochs", str(epochs),
        "--batch-size", str(batch_size),
        "--channels", str(channels),
        "--crop-samples", str(crop_samples),
        "--seed", "0",
        "--run-id", run_id,
        "--save-to", str(save_to),
        "--report-to", str(report_to),
    ]
    env = {"PYTHONPATH": str(_REPO_ROOT / "src"), **os.environ}
    print(f"[T1-G] training {run_id} on {pool}", flush=True)
    subprocess.run(cmd, check=True, env=env)
    return report_to


def _aggregate(reports: dict[str, Path]) -> dict[str, dict[str, float]]:
    """Compute mean ± stdev of each per-voice run's holdout metrics."""
    out: dict[str, dict[str, float]] = {}
    for name, p in reports.items():
        run = json.loads(p.read_text())
        v = list(run["holdout_verdicts"].values())
        f_scores = [x["onset_f"] for x in v]
        shuf = [x["shuffled_f"] for x in v]
        timings = [x["timing_mae_ms"] for x in v
                   if x["timing_mae_ms"] == x["timing_mae_ms"]]
        hh = [x["hihat_mae"] for x in v]
        out[name] = {
            "n_holdout": float(len(v)),
            "mean_onset_f": float(statistics.mean(f_scores)) if f_scores else float("nan"),
            "mean_shuffled_f": float(statistics.mean(shuf)) if shuf else float("nan"),
            "mean_timing_mae_ms": float(statistics.mean(timings)) if timings else float("nan"),
            "mean_hihat_mae": float(statistics.mean(hh)) if hh else float("nan"),
        }
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--baseline-pool", type=Path,
                   default=Path("data/gold/mix_2026-05-24"))
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--channels", type=int, default=32)
    p.add_argument("--crop-samples", type=int, default=40960)
    p.add_argument("--master-seed", type=int, default=20260524)
    p.add_argument("--out", type=Path,
                   default=Path("docs/gates/R&D_Tier1_reports/T1-G"))
    args = p.parse_args()

    if not args.baseline_pool.exists():
        print(f"FATAL: baseline pool {args.baseline_pool} not found",
              file=sys.stderr)
        return 1

    # 1. Apply each voice in isolation, building 3 augmented datasets.
    voice_pools: dict[str, Path] = {}
    for name, toggles in _VOICE_CONFIGS:
        voice_pools[name] = _apply_voice(
            args.baseline_pool, name, toggles, args.master_seed,
        )

    # 2. Train T1-B on each voice's pool.
    reports: dict[str, Path] = {}
    for name, pool in voice_pools.items():
        run_id = f"t1g-{name}"
        reports[name] = _train_one(
            pool, run_id, args.epochs, args.batch_size,
            args.channels, args.crop_samples,
        )

    # 3. Aggregate + dump.
    summary = _aggregate(reports)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "per_voice_results.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True)
    )
    print("\n== per-voice ablation ==")
    print(f"{'voice':<20s} {'onset_F':>10s} {'shuf_F':>10s} {'mae_ms':>10s} {'hh_mae':>10s}")
    for name, m in summary.items():
        print(f"{name:<20s} {m['mean_onset_f']:>10.4f} "
              f"{m['mean_shuffled_f']:>10.4f} "
              f"{m['mean_timing_mae_ms']:>10.2f} "
              f"{m['mean_hihat_mae']:>10.4f}")
    print(f"\nwrote {args.out / 'per_voice_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
