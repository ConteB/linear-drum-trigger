#!/usr/bin/env python3
"""Render-throughput calibration — local micro-benchmark of the Gold pipeline.

Times every recipe in ``recipes/mini_batch/`` end-to-end (recipe -> render ->
audio.f16 + target.f16 + dna.json) and produces a structured report:

    * per-recipe wall-clock seconds, audio duration, mic count, audio bytes
    * per-engine aggregate throughput (samples/h, audio-seconds/h, MB/h)
    * a render-factor (wall / audio) — how many real seconds per second of audio
    * a projection to a target dataset size (default 1.5 TB) — the F2-T1 spend

The script is read-only of design intent and additive of measurement only: it
re-uses ``data_engineering.gold.orchestrate.build_gold_sample`` so the timings
are of the *real* pipeline, not of a mock. Sfizz runs anywhere the vendored
binary is present; DrumGizmo recipes need the Linux CLI (run via OrbStack).

Usage:
    python tools/calibrate_render.py --engine sfizz
    orb -m ubuntu run -- bash -lc \\
        "cd /path/to/repo && ~/ntg-venv/bin/python tools/calibrate_render.py \\
         --engine drumgizmo"

The CSV report lands under ``audition/calibration/<engine>.csv`` and a summary
is printed to stdout — both are part of the F0-T3 / pre-F2-T1 evidence trail.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from dataclasses import dataclass
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
_DEFAULT_OUT = _REPO_ROOT / "data" / "gold" / "calibration"
_DEFAULT_REPORT_DIR = _REPO_ROOT / "audition" / "calibration"
#: Default target Gold dataset size (DOSSIER §9.2 — ~1.5 TB on HDD).
_DEFAULT_TARGET_TB = 1.5


@dataclass
class _Row:
    recipe_id: str
    engine: str
    kit: str
    n_mic: int
    n_sample: int
    audio_duration_s: float
    wall_clock_s: float
    audio_bytes: int
    target_bytes: int


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="render-throughput calibration")
    p.add_argument(
        "--engine",
        choices=[e.value for e in Engine],
        default=None,
        help="restrict the run to a single render engine",
    )
    p.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    p.add_argument("--recipes", type=Path, default=_RECIPE_DIR)
    p.add_argument("--report-dir", type=Path, default=_DEFAULT_REPORT_DIR)
    p.add_argument(
        "--target-tb",
        type=float,
        default=_DEFAULT_TARGET_TB,
        help=f"target Gold dataset size in TB (default {_DEFAULT_TARGET_TB})",
    )
    return p.parse_args()


def _format_seconds(secs: float) -> str:
    """Render a wall-clock duration in h/m/s, depending on magnitude."""
    if secs < 60:
        return f"{secs:.2f} s"
    if secs < 3600:
        return f"{secs/60:.2f} min"
    if secs < 86400:
        return f"{secs/3600:.2f} h"
    return f"{secs/86400:.2f} d"


def _project(rows: list[_Row], target_bytes: int) -> dict[str, float]:
    """Project mini-batch throughput to a target dataset size."""
    if not rows:
        return {}
    total_wall = sum(r.wall_clock_s for r in rows)
    total_audio_bytes = sum(r.audio_bytes for r in rows)
    total_audio_s = sum(r.audio_duration_s for r in rows)

    if total_wall == 0 or total_audio_bytes == 0:
        return {}

    bytes_per_sec_wall = total_audio_bytes / total_wall
    seconds_per_sample = total_wall / len(rows)
    bytes_per_sample = total_audio_bytes / len(rows)
    samples_for_target = target_bytes / bytes_per_sample
    wall_for_target_s = samples_for_target * seconds_per_sample
    render_factor = total_wall / total_audio_s if total_audio_s else 0.0

    return {
        "bytes_per_sec_wall": bytes_per_sec_wall,
        "render_factor_wall_per_audio_s": render_factor,
        "bytes_per_sample": bytes_per_sample,
        "seconds_per_sample_wall": seconds_per_sample,
        "samples_for_target": samples_for_target,
        "wall_for_target_s_single_thread": wall_for_target_s,
    }


def _print_summary(rows: list[_Row], target_tb: float) -> None:
    """Stdout summary — terse per-row + per-engine projection."""
    if not rows:
        print("no rows — nothing to summarise")
        return

    print("=" * 78)
    print(f"{'recipe':22s} {'engine':10s} {'n_mic':>5} {'audio_s':>8} "
          f"{'wall_s':>8} {'wall/audio':>10} {'MB':>7}")
    print("-" * 78)
    for r in rows:
        ratio = r.wall_clock_s / r.audio_duration_s if r.audio_duration_s else float("nan")
        mb = r.audio_bytes / (1024 * 1024)
        print(f"{r.recipe_id:22s} {r.engine:10s} {r.n_mic:5d} "
              f"{r.audio_duration_s:8.2f} {r.wall_clock_s:8.2f} {ratio:10.2f} {mb:7.2f}")
    print("-" * 78)

    target_bytes = int(target_tb * (1024 ** 4))
    proj = _project(rows, target_bytes)
    total_audio_mb = sum(r.audio_bytes for r in rows) / (1024 * 1024)
    total_wall = sum(r.wall_clock_s for r in rows)
    print(f"  rows: {len(rows)}  total_audio: {total_audio_mb:.2f} MB  "
          f"total_wall: {_format_seconds(total_wall)}")

    if not proj:
        return

    print(f"  bytes/sample:      {proj['bytes_per_sample']/1024/1024:.2f} MB")
    print(f"  wall/sample:       {_format_seconds(proj['seconds_per_sample_wall'])}")
    print(f"  render factor:     {proj['render_factor_wall_per_audio_s']:.2f}x "
          f"(wall seconds per second of audio)")
    print(f"  throughput:        "
          f"{proj['bytes_per_sec_wall']/1024/1024:.2f} MB/s of audio bytes")
    print()
    print(f"  projection to {target_tb:.1f} TB Gold (single-thread):")
    print(f"    samples needed:  {proj['samples_for_target']:,.0f}")
    wall = proj["wall_for_target_s_single_thread"]
    print(f"    wall (1 thread): {_format_seconds(wall)}")
    for cores in (8, 16, 32, 64):
        print(f"    @ {cores:3d} cores ideal: {_format_seconds(wall/cores)}")
    print("=" * 78)


def main() -> int:
    args = _parse_args()

    recipe_paths = sorted(args.recipes.glob("*.yaml"))
    if not recipe_paths:
        print(f"FATAL: no recipes in {args.recipes}", file=sys.stderr)
        return 1

    bus_mapping = load_bus_mapping(DEFAULT_BUS_MAPPING_PATH)

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    label = args.engine or "all"
    print(f"calibrate_render — engine={label}  recipes={len(recipe_paths)}")
    print(f"  out:    {args.out}")
    print(f"  report: {args.report_dir}")

    rows: list[_Row] = []
    for recipe_path in recipe_paths:
        recipe = load_recipe(recipe_path)
        if args.engine and recipe.render.engine.value != args.engine:
            continue

        t0 = time.perf_counter()
        result = build_gold_sample(recipe, out_dir=args.out, bus_mapping=bus_mapping)
        wall = time.perf_counter() - t0

        audio_path = args.out / f"{result.key}.audio.f16"
        target_path = args.out / f"{result.key}.target.f16"
        audio_bytes = audio_path.stat().st_size
        target_bytes = target_path.stat().st_size
        audio_duration_s = result.n_sample / 44100.0

        rows.append(_Row(
            recipe_id=result.recipe_id,
            engine=result.engine.value,
            kit=recipe.render.kit,
            n_mic=result.n_mic,
            n_sample=result.n_sample,
            audio_duration_s=audio_duration_s,
            wall_clock_s=wall,
            audio_bytes=audio_bytes,
            target_bytes=target_bytes,
        ))
        print(f"  [{len(rows):2d}] {result.recipe_id:22s} {result.engine.value:10s} "
              f"wall={wall:6.2f}s  audio={audio_duration_s:5.2f}s  "
              f"factor={wall/audio_duration_s if audio_duration_s else 0:5.2f}x")

    csv_path = args.report_dir / f"{label}.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "recipe_id", "engine", "kit", "n_mic", "n_sample",
            "audio_duration_s", "wall_clock_s", "audio_bytes", "target_bytes",
        ])
        for r in rows:
            w.writerow([
                r.recipe_id, r.engine, r.kit, r.n_mic, r.n_sample,
                f"{r.audio_duration_s:.6f}", f"{r.wall_clock_s:.6f}",
                r.audio_bytes, r.target_bytes,
            ])

    _print_summary(rows, args.target_tb)
    print(f"  CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
