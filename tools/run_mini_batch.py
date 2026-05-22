#!/usr/bin/env python3
"""F0-T2e — run the Gold pipeline mini-batch end-to-end.

Orchestrates every recipe under ``recipes/mini_batch/`` through the full
pipeline (recipe -> render -> audio.f16 + target.f16 -> dna.json) and prints a
stdout log of the N Gold samples generated — the DoD of F0-T2e and the §6.3
"smoke end-to-end + count" acceptance check (TESTING_DOCTRINE §6.3).

Fail-loud: the first recipe that fails aborts the run with a non-zero exit; a
clean run is the proof that the pipeline holds end-to-end.

Run:
    python tools/run_mini_batch.py                # every recipe
    python tools/run_mini_batch.py --engine sfizz # only the Sfizz subset
    python tools/run_mini_batch.py --out <dir>    # custom Gold output dir

DrumGizmo recipes need the ``drumgizmo`` CLI, provisioned on Linux (OrbStack /
Azure); the Sfizz subset runs anywhere the vendored binary is present.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.gold.orchestrate import (  # noqa: E402
    DEFAULT_BUS_MAPPING_PATH,
    build_gold_sample,
)
from data_engineering.gold.recipe import Engine, load_recipe  # noqa: E402
from data_engineering.gold.target_builder import load_bus_mapping  # noqa: E402

_RECIPE_DIR = _REPO_ROOT / "recipes" / "mini_batch"
_DEFAULT_OUT = _REPO_ROOT / "data" / "gold" / "mini_batch"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="F0-T2e mini-batch runner")
    parser.add_argument(
        "--engine",
        choices=[e.value for e in Engine],
        default=None,
        help="restrict the run to a single render engine",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_OUT,
        help=f"Gold output directory (default: {_DEFAULT_OUT})",
    )
    parser.add_argument(
        "--recipes",
        type=Path,
        default=_RECIPE_DIR,
        help=f"recipe directory (default: {_RECIPE_DIR})",
    )
    return parser.parse_args()


def main() -> int:
    """Run the mini-batch; return a process exit code."""
    args = _parse_args()

    recipe_paths = sorted(args.recipes.glob("*.yaml"))
    if not recipe_paths:
        print(f"FATAL: no recipes found in {args.recipes}", file=sys.stderr)
        print("       run tools/gen_mini_batch_fixtures.py first", file=sys.stderr)
        return 1

    bus_mapping = load_bus_mapping(DEFAULT_BUS_MAPPING_PATH)

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)

    print("=" * 72)
    print("F0-T2e — Gold pipeline mini-batch")
    print(f"  recipes: {args.recipes}")
    print(f"  output:  {args.out}")
    if args.engine:
        print(f"  engine filter: {args.engine}")
    print("=" * 72)

    seen_keys: dict[str, str] = {}
    generated = 0
    skipped = 0

    for recipe_path in recipe_paths:
        recipe = load_recipe(recipe_path)
        if args.engine and recipe.render.engine.value != args.engine:
            skipped += 1
            continue

        try:
            result = build_gold_sample(recipe, out_dir=args.out, bus_mapping=bus_mapping)
        except Exception as exc:  # noqa: BLE001 — fail loud, report which recipe
            print(f"  [{recipe.recipe_id}] FAILED: {type(exc).__name__}: {exc}")
            print("=" * 72)
            print(f"ABORTED after {generated} sample(s) — pipeline error above.")
            return 1

        if result.key in seen_keys:
            print(
                f"  [{recipe.recipe_id}] FAILED: barcode key {result.key!r} "
                f"collides with recipe {seen_keys[result.key]!r}"
            )
            return 1
        seen_keys[result.key] = recipe.recipe_id
        generated += 1

        print(
            f"  [{generated:2d}] {result.recipe_id:18s} {result.engine.value:9s} "
            f"key={result.key}"
        )
        print(
            f"       audio [{result.n_mic}x{result.n_sample}] peak={result.audio_peak:.4f}  "
            f"target [{result.n_frame}x25]"
        )

    print("=" * 72)
    print(f"OK — {generated} Gold sample(s) generated, 0 errors.")
    if skipped:
        print(f"     ({skipped} recipe(s) skipped by --engine {args.engine})")
    print(f"     written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
