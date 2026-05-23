#!/usr/bin/env python3
"""T1-B baseline training — TCN on the mixed-dataset 70/15/15.

Adapts the F0-T4b training loop (`src/neural/train.py`) to the 585-sample
mix Gold dataset produced by the 2026-05-24 R&D session. The F0-T4a default
topology (C=32, B=4, look-ahead ~100 ms) is preserved; only the dataset and
the train/holdout split change.

Holdout: 50 sample chosen deterministically (seed=42) — ~8.5 % of the pool.
The remainder (535 sample) feeds the training loader.

Output (default ``--run-id t1b-mix-baseline``):

* ``artifacts/<run_id>.pt`` — final checkpoint
* ``artifacts/<run_id>_report.json`` — JSON summary
* ``reports/<YYYY-MM-DD>-<run_id>/report.html`` — Tier-1 HTML report

Usage:
    PYTHONPATH=src .venv/bin/python tools/t1b_train_mix.py \
        --epochs 50 --batch-size 8 --seed 0
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from neural.data import discover_gold_keys  # noqa: E402
from neural.loss import LossConfig  # noqa: E402
from neural.train import train  # noqa: E402

#: Default mix Gold directory produced by mix_dataset + render_mix_chunked.
_DEFAULT_POOL = _REPO_ROOT / "data" / "gold" / "mix_2026-05-24"
#: Default number of holdout samples (≈ 8.5 % of 585).
_DEFAULT_HOLDOUT_N = 50
#: Seed for the deterministic holdout selection — *separate* from the
#: training seed so the same holdout is reused across seed sweeps (T1-D).
_HOLDOUT_SEED = 42


def _pick_holdout(pool_root: Path, n: int, seed: int) -> tuple[str, ...]:
    """Sample ``n`` keys from ``pool_root`` deterministically."""
    triples = discover_gold_keys(pool_root)
    keys = sorted(k for _, k in triples)
    if len(keys) <= n:
        raise SystemExit(
            f"holdout n={n} >= pool size {len(keys)} — choose a smaller n"
        )
    rng = random.Random(seed)
    return tuple(sorted(rng.sample(keys, n)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pool", type=Path, default=_DEFAULT_POOL)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--crop-samples", type=int, default=65536)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=0,
                        help="model + loader seed (HOLDOUT seed is fixed at 42)")
    parser.add_argument("--channels", type=int, default=32,
                        help="TCN channel width C (F0-T4a default = 32)")
    parser.add_argument("--holdout-n", type=int, default=_DEFAULT_HOLDOUT_N)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--run-id", default="t1b-mix-baseline")
    parser.add_argument("--run-title",
                        default="T1-B baseline — TCN on mix 70/15/15 dataset")
    parser.add_argument("--save-to", type=Path,
                        default=Path("artifacts/t1b-mix-baseline.pt"))
    parser.add_argument("--report-to", type=Path,
                        default=Path("artifacts/t1b-mix-baseline_report.json"))
    parser.add_argument("--html-report-dir", type=Path,
                        default=Path("reports"))
    parser.add_argument("--no-html-report", action="store_true")
    parser.add_argument(
        "--lookahead-frames", type=int, default=0,
        help="Audio look-ahead in frames (frame = 128 samples ≈ 2.9 ms). "
             "F0-T4a §3 prescribes ~100 ms = 35 frames; default 0 keeps the "
             "current strict-causal behaviour.",
    )
    parser.add_argument(
        "--include-keys-file", type=Path, default=None,
        help="Path to a JSON file containing the list of sample keys to include "
             "(everything else is dropped from the pool). Used for the Opzione A "
             "diagnostic experiments (e.g. drop the 30 chaos grooves).",
    )
    # ---- Loss-config overrides (Opzione A · Step 1 diagnostic experiments) ----
    parser.add_argument(
        "--pos-weight", type=float, default=None,
        help="LossConfig.pos_weight override (default = LossConfig() = 50.0)",
    )
    parser.add_argument(
        "--w-onset", type=float, default=None,
        help="LossConfig.w_onset override (default = 1.0)",
    )
    parser.add_argument(
        "--w-velocity", type=float, default=None,
        help="LossConfig.w_velocity override (default = 0.5)",
    )
    parser.add_argument(
        "--w-microtiming", type=float, default=None,
        help="LossConfig.w_microtiming override (default = 0.5)",
    )
    parser.add_argument(
        "--w-hihat", type=float, default=None,
        help="LossConfig.w_hihat override (default = 1.0)",
    )
    args = parser.parse_args()
    # Build LossConfig with any provided overrides; None == keep default.
    _default_lc = LossConfig()
    loss_config = LossConfig(
        w_onset=args.w_onset if args.w_onset is not None else _default_lc.w_onset,
        w_velocity=args.w_velocity if args.w_velocity is not None else _default_lc.w_velocity,
        w_microtiming=(
            args.w_microtiming
            if args.w_microtiming is not None
            else _default_lc.w_microtiming
        ),
        w_hihat=args.w_hihat if args.w_hihat is not None else _default_lc.w_hihat,
        focal_gamma=_default_lc.focal_gamma,
        fp_to_fn_ratio=_default_lc.fp_to_fn_ratio,
        pos_weight=args.pos_weight if args.pos_weight is not None else _default_lc.pos_weight,
        onset_mask_threshold=_default_lc.onset_mask_threshold,
    )

    if not args.pool.exists():
        print(f"FATAL: pool dir {args.pool} does not exist", file=sys.stderr)
        return 1

    include_keys: tuple[str, ...] | None = None
    if args.include_keys_file is not None:
        import json as _json  # noqa: PLC0415
        keys_list = _json.loads(args.include_keys_file.read_text())
        if not isinstance(keys_list, list) or not all(isinstance(k, str) for k in keys_list):
            raise SystemExit(
                f"FATAL: --include-keys-file {args.include_keys_file} "
                "must be a JSON list of strings"
            )
        include_keys = tuple(sorted(set(keys_list)))
        print(f"[T1-B] include_keys = {len(include_keys)} keys "
              f"(from {args.include_keys_file})")

    holdout_keys = _pick_holdout(args.pool, args.holdout_n, _HOLDOUT_SEED)
    # Make sure holdout_keys is a subset of include_keys, else the deterministic
    # holdout picker may select keys that the filter will drop. Re-pick from
    # the filtered set.
    if include_keys is not None:
        rng = random.Random(_HOLDOUT_SEED)
        holdout_keys = tuple(sorted(rng.sample(list(include_keys), args.holdout_n)))
    print(f"[T1-B] pool       = {args.pool}")
    print(f"[T1-B] holdout    = {len(holdout_keys)} keys (seed={_HOLDOUT_SEED})")
    print(f"[T1-B] epochs     = {args.epochs}, batch_size = {args.batch_size}")
    print(f"[T1-B] crop       = {args.crop_samples} samples")
    print(f"[T1-B] seed       = {args.seed}")
    print(f"[T1-B] save_to    = {args.save_to}")
    print(f"[T1-B] run_id     = {args.run_id}")

    result = train(
        pool_root=args.pool,
        holdout_keys=holdout_keys,
        crop_samples=args.crop_samples,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        seed=args.seed,
        force_cpu=args.cpu,
        save_to=args.save_to,
        report_dir=None if args.no_html_report else args.html_report_dir,
        run_id=args.run_id,
        run_title=args.run_title,
        tcn_channels=args.channels,
        loss_config=loss_config,
        include_keys=include_keys,
        lookahead_frames=args.lookahead_frames,
    )
    print(
        f"[T1-B] loss_cfg  = pos_w={loss_config.pos_weight} "
        f"w_on={loss_config.w_onset} w_vel={loss_config.w_velocity} "
        f"w_mt={loss_config.w_microtiming} w_hh={loss_config.w_hihat}"
    )

    # Save the JSON summary side-by-side (the train() loop already wrote the
    # checkpoint + HTML report; here we add a flat dict the sweep tools can
    # consume programmatically).
    import json
    summary = {
        "config": result.config,
        "n_parameters": result.n_parameters,
        "train_keys_count": len(result.train_keys),
        "holdout_keys_count": len(result.holdout_keys),
        "wall_time_s": result.wall_time_s,
        "final_train_loss": result.final_train_loss,
        # Full per-epoch history (Opzione A · Step 1 — per-head loss tracking).
        # Each entry: {epoch, train_loss, loss_onset, loss_velocity,
        # loss_microtiming, loss_hihat}.
        "history": result.history,
        "holdout_verdicts": {
            k: {
                "passes": bool(v.passes),
                "onset_f": float(v.f_measure_mean),
                "shuffled_f": float(v.f_shuffled),
                "timing_mae_ms": float(v.timing_mae_ms),
                "hihat_mae": float(v.hihat_mae),
            }
            for k, v in result.holdout_verdicts.items()
        },
    }
    args.report_to.parent.mkdir(parents=True, exist_ok=True)
    args.report_to.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(f"[T1-B] wrote {args.report_to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
