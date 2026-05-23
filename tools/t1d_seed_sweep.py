#!/usr/bin/env python3
"""T1-D seed stability sweep — 5 runs with identical config, varying seed.

ENGINEERING_STANDARDS §5: a result is *stable* only when reproducible across
seeds. The baseline configuration (F0-T4a default, same as T1-B) is trained
with 5 distinct seeds; per-run holdout F-measure / shuffled-F / timing-MAE /
HH-MAE are aggregated and the standard deviation reported.

Each run reuses the deterministic holdout (seed=42, see ``tools/t1b_train_mix.py``)
so all 5 models are evaluated on the same 50 samples.

Output: ``artifacts/t1d-seed-sweep/seeds.json`` (aggregate JSON) +
``reports/<date>-t1d-seed-<seed>/report.html`` per run.

Usage:
    PYTHONPATH=src .venv/bin/python tools/t1d_seed_sweep.py \
        --epochs 50 --batch-size 8 \
        --seeds 42 137 1337 2024 9001
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: Default seed set — ENGINEERING_STANDARDS §5 calls for n≥5 to compute a CI.
_DEFAULT_SEEDS: tuple[int, ...] = (42, 137, 1337, 2024, 9001)


def _run_one(seed: int, args: argparse.Namespace) -> Path:
    """Spawn a single training run as a subprocess. Returns its report path."""
    run_id = f"t1d-seed-{seed}"
    report_to = _REPO_ROOT / "artifacts" / f"{run_id}_report.json"
    save_to = _REPO_ROOT / "artifacts" / f"{run_id}.pt"
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "tools" / "t1b_train_mix.py"),
        "--epochs", str(args.epochs),
        "--batch-size", str(args.batch_size),
        "--crop-samples", str(args.crop_samples),
        "--lr", str(args.lr),
        "--seed", str(seed),
        "--run-id", run_id,
        "--save-to", str(save_to),
        "--report-to", str(report_to),
    ]
    env = {
        "PYTHONPATH": str(_REPO_ROOT / "src"),
        **__import__("os").environ,
    }
    t0 = time.monotonic()
    print(f"[T1-D] seed {seed}: launching", flush=True)
    subprocess.run(cmd, check=True, env=env)
    elapsed = time.monotonic() - t0
    print(f"[T1-D] seed {seed}: done in {elapsed/60:.1f} min", flush=True)
    return report_to


def _aggregate(report_paths: list[Path]) -> dict[str, object]:
    """Read each per-seed report and compute mean / stdev across seeds."""
    runs: list[dict] = []
    for p in report_paths:
        runs.append(json.loads(p.read_text()))

    # Pull every holdout sample's metrics into a flat per-seed list.
    per_seed_f: dict[int, list[float]] = {}
    per_seed_shuf: dict[int, list[float]] = {}
    per_seed_timing: dict[int, list[float]] = {}
    per_seed_hh: dict[int, list[float]] = {}
    per_seed_pass_rate: dict[int, float] = {}
    per_seed_wall: dict[int, float] = {}
    for run in runs:
        seed = int(run["config"]["seed"])
        verdicts = list(run["holdout_verdicts"].values())
        per_seed_f[seed] = [v["onset_f"] for v in verdicts]
        per_seed_shuf[seed] = [v["shuffled_f"] for v in verdicts]
        per_seed_timing[seed] = [v["timing_mae_ms"] for v in verdicts
                                  if v["timing_mae_ms"] == v["timing_mae_ms"]]
        per_seed_hh[seed] = [v["hihat_mae"] for v in verdicts]
        per_seed_pass_rate[seed] = sum(1 for v in verdicts if v["passes"]) / len(verdicts)
        per_seed_wall[seed] = float(run["wall_time_s"])

    def _mean(xs: list[float]) -> float:
        return float(statistics.mean(xs)) if xs else float("nan")

    seed_summary = {
        seed: {
            "n_holdout": len(per_seed_f[seed]),
            "mean_onset_f": _mean(per_seed_f[seed]),
            "mean_shuffled_f": _mean(per_seed_shuf[seed]),
            "mean_timing_mae_ms": _mean(per_seed_timing[seed]),
            "mean_hihat_mae": _mean(per_seed_hh[seed]),
            "pass_rate": per_seed_pass_rate[seed],
            "wall_time_s": per_seed_wall[seed],
        }
        for seed in sorted(per_seed_f)
    }

    # Cross-seed aggregation: mean ± stdev of each per-run mean.
    means_f = [s["mean_onset_f"] for s in seed_summary.values()]
    means_shuf = [s["mean_shuffled_f"] for s in seed_summary.values()]
    means_t = [s["mean_timing_mae_ms"] for s in seed_summary.values()
               if s["mean_timing_mae_ms"] == s["mean_timing_mae_ms"]]
    means_hh = [s["mean_hihat_mae"] for s in seed_summary.values()]
    pass_rates = [s["pass_rate"] for s in seed_summary.values()]

    def _stat(xs: list[float]) -> dict[str, float]:
        if not xs:
            return {"mean": float("nan"), "stdev": float("nan"),
                    "min": float("nan"), "max": float("nan")}
        return {
            "mean": float(statistics.mean(xs)),
            "stdev": float(statistics.stdev(xs)) if len(xs) > 1 else 0.0,
            "min": float(min(xs)),
            "max": float(max(xs)),
        }

    return {
        "per_seed": seed_summary,
        "aggregate": {
            "onset_f": _stat(means_f),
            "shuffled_f": _stat(means_shuf),
            "timing_mae_ms": _stat(means_t),
            "hihat_mae": _stat(means_hh),
            "pass_rate": _stat(pass_rates),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+",
                        default=list(_DEFAULT_SEEDS))
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--crop-samples", type=int, default=40960)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--out", type=Path,
                        default=Path("artifacts/t1d-seed-sweep/seeds.json"))
    parser.add_argument("--skip-existing", action="store_true",
                        help="reuse per-seed reports already on disk")
    args = parser.parse_args()

    if len(args.seeds) < 2:
        print("FATAL: need at least 2 seeds for a stdev estimate", file=sys.stderr)
        return 1

    print(f"[T1-D] sweeping over {len(args.seeds)} seeds: {args.seeds}")
    reports: list[Path] = []
    for seed in args.seeds:
        run_id = f"t1d-seed-{seed}"
        report_path = _REPO_ROOT / "artifacts" / f"{run_id}_report.json"
        if args.skip_existing and report_path.exists():
            print(f"[T1-D] seed {seed}: report exists, skipping")
            reports.append(report_path)
            continue
        reports.append(_run_one(seed, args))

    aggregate = _aggregate(reports)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(aggregate, indent=2, sort_keys=True))
    print(f"[T1-D] wrote aggregate to {args.out}")
    # Pretty-print the aggregate.
    agg = aggregate["aggregate"]
    print("\n== aggregate (mean ± stdev across seeds) ==")
    for metric in ("onset_f", "shuffled_f", "timing_mae_ms", "hihat_mae", "pass_rate"):
        s = agg[metric]
        print(f"  {metric:15s}: {s['mean']:7.4f} ± {s['stdev']:.4f}  "
              f"(min={s['min']:.4f}, max={s['max']:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
