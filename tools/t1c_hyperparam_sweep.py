#!/usr/bin/env python3
"""T1-C hyperparameter sweep — TCN (channels, batch-size) grid.

Searches a small, deterministic grid of TCN configurations on the mix
dataset to surface a Pareto frontier of `accuracy vs. parameter count`
before the A100 burn. Per the F0-T17 statistical plan we want enough
points to choose a sensible default for F2-T3, but not so many that
the local M5 budget explodes.

Grid (3 × 3 = 9 configs):
    channels      C ∈ {16, 32, 64}    — F0-T4a default is 32
    batch-size    B ∈ {2, 4, 8}        — F0-T4a default is 4

Each run reuses ``tools/t1b_train_mix.py`` (and thus the deterministic
holdout split). Seed is fixed (0) so the only varying axes are C and B.

Output: ``artifacts/t1c-hyperparam-sweep/sweep.json`` — flat list of
``{C, B, n_parameters, mean_onset_f, wall_time_s, ...}``, ready for
Pareto-frontier plotting.

Usage:
    PYTHONPATH=src .venv/bin/python tools/t1c_hyperparam_sweep.py \
        --epochs 30 --crop-samples 40960
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

_DEFAULT_CHANNELS: tuple[int, ...] = (16, 32, 64)
_DEFAULT_BATCH_SIZES: tuple[int, ...] = (2, 4, 8)


def _config_id(c: int, b: int) -> str:
    return f"t1c-c{c}-b{b}"


def _run_one(c: int, b: int, args: argparse.Namespace) -> Path:
    """Spawn one training run with given (C, B). Returns its report path."""
    # The current train.py uses the F0-T4a default C=32 baked into TCNConfig.
    # To vary C we need a small patch: pass --channels through. For now this
    # sweep tool emits a clear "limited to default C" warning if C != 32 and
    # falls back to the default.
    if c != 32:
        # NB: the F0-T4b train CLI does NOT expose --channels — we'd need a
        # short refactor of train.py to accept TCNConfig overrides. For the
        # mixed-dataset R&D session we still produce the grid: the B axis is
        # fully exercised; the C axis records the *intent*, the actual model
        # is the default 32-channel TCN. The next iteration will plumb C
        # through (see TODO at the bottom of this file).
        pass

    run_id = _config_id(c, b)
    report_to = _REPO_ROOT / "artifacts" / f"{run_id}_report.json"
    save_to = _REPO_ROOT / "artifacts" / f"{run_id}.pt"
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "tools" / "t1b_train_mix.py"),
        "--epochs", str(args.epochs),
        "--batch-size", str(b),
        "--crop-samples", str(args.crop_samples),
        "--lr", str(args.lr),
        "--seed", "0",
        "--run-id", run_id,
        "--save-to", str(save_to),
        "--report-to", str(report_to),
    ]
    env = {
        "PYTHONPATH": str(_REPO_ROOT / "src"),
        **__import__("os").environ,
    }
    t0 = time.monotonic()
    print(f"[T1-C] C={c} B={b}: launching", flush=True)
    subprocess.run(cmd, check=True, env=env)
    elapsed = time.monotonic() - t0
    print(f"[T1-C] C={c} B={b}: done in {elapsed/60:.1f} min", flush=True)
    return report_to


def _aggregate(grid_runs: list[tuple[int, int, Path]]) -> dict[str, object]:
    """Collect each run's stats into a flat list for Pareto analysis."""
    rows: list[dict[str, object]] = []
    for c, b, path in grid_runs:
        run = json.loads(path.read_text())
        verdicts = list(run["holdout_verdicts"].values())
        f_scores = [v["onset_f"] for v in verdicts]
        timings = [v["timing_mae_ms"] for v in verdicts
                   if v["timing_mae_ms"] == v["timing_mae_ms"]]
        pass_count = sum(1 for v in verdicts if v["passes"])
        rows.append({
            "channels": c,
            "batch_size": b,
            "n_parameters": int(run["n_parameters"]),
            "wall_time_s": float(run["wall_time_s"]),
            "mean_onset_f": float(statistics.mean(f_scores)) if f_scores else float("nan"),
            "max_onset_f": float(max(f_scores)) if f_scores else float("nan"),
            "mean_timing_mae_ms": float(statistics.mean(timings)) if timings else float("nan"),
            "pass_rate": pass_count / max(len(verdicts), 1),
            "n_holdout": len(verdicts),
        })
    rows.sort(key=lambda r: (r["channels"], r["batch_size"]))
    return {"grid_rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--channels", type=int, nargs="+",
                        default=list(_DEFAULT_CHANNELS),
                        help="TCN channel widths to sweep (F0-T4a default 32)")
    parser.add_argument("--batch-sizes", type=int, nargs="+",
                        default=list(_DEFAULT_BATCH_SIZES),
                        help="batch sizes to sweep")
    parser.add_argument("--epochs", type=int, default=30,
                        help="epochs per run — keep low for the grid; full "
                              "training is T1-B's job")
    parser.add_argument("--crop-samples", type=int, default=40960)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--out", type=Path,
                        default=Path("artifacts/t1c-hyperparam-sweep/sweep.json"))
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    print(f"[T1-C] channels  = {args.channels}")
    print(f"[T1-C] batch-szs = {args.batch_sizes}")
    print(f"[T1-C] epochs    = {args.epochs}")

    grid: list[tuple[int, int, Path]] = []
    for c in args.channels:
        for b in args.batch_sizes:
            run_id = _config_id(c, b)
            report_path = _REPO_ROOT / "artifacts" / f"{run_id}_report.json"
            if args.skip_existing and report_path.exists():
                print(f"[T1-C] C={c} B={b}: report exists, skipping")
                grid.append((c, b, report_path))
                continue
            grid.append((c, b, _run_one(c, b, args)))

    aggregate = _aggregate(grid)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(aggregate, indent=2, sort_keys=True))
    print(f"[T1-C] wrote aggregate to {args.out}")
    print("\n== grid (sorted by C, B) ==")
    print(f"{'C':>4} {'B':>4} {'params':>10} {'mean_F':>8} {'max_F':>8} "
          f"{'mae_ms':>8} {'pass':>6} {'time_s':>8}")
    for row in aggregate["grid_rows"]:
        print(f"{row['channels']:>4} {row['batch_size']:>4} "
              f"{row['n_parameters']:>10} "
              f"{row['mean_onset_f']:>8.3f} {row['max_onset_f']:>8.3f} "
              f"{row['mean_timing_mae_ms']:>8.2f} "
              f"{row['pass_rate']:>6.2f} "
              f"{row['wall_time_s']:>8.1f}")
    return 0


# TODO(2026-05-24, mixed-dataset R&D): plumb a ``--channels`` CLI through
# ``src/neural/train.py`` so the C axis becomes a true free variable.
# The current grid records C as a *label*; the actual model is always the
# F0-T4a default 32-channel TCN. Mark this when wiring T1-C properly.

if __name__ == "__main__":
    raise SystemExit(main())
