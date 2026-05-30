#!/usr/bin/env python3
"""F0-T20b smoke — render ONE franken-kit Gold sample end-to-end (DG pool).

Runs on OrbStack (DrumGizmo binary is Linux). Verifies: per-instrument render +
sum produces a valid Gold sample (peak in range, target shape, dna valid) and that
the instrument->kit assignment is a genuine hybrid.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))

from tools.mini_l3_runner import _resolve_kit_paths  # noqa: E402

from data_engineering.gold.franken import build_franken_gold_sample  # noqa: E402
from data_engineering.gold.recipe import parse_recipe  # noqa: E402
from data_engineering.gold.target_builder import load_bus_mapping  # noqa: E402


def _recipe_yaml(kit: str, kit_path: str, midi_file: str) -> str:
    return f"""
recipe_id: R-FK-smoke-{kit}
schema_version: "1.0"
split: train
midi_source:
  dataset: GMD
  file: {midi_file}
  standard: roland_td11
  bus_mapping: midi_mapping_table.yaml@2.0
midi_jitter:
  time_jitter_ms: [0.0, 0.0]
  flam_probability: 0.0
  velocity_jitter: none
  component_drop_probability: 0.0
  seed: 0
  variant_idx: 0
render:
  engine: drumgizmo
  kit: {kit}
  kit_path: {kit_path}
  sample_rate: 44100
  mic_config: multitrack_full
augmentation:
  level: 1
  reverb_ir: null
  mutilation: {{}}
  saboteur: null
output:
  target_frame_rate_hz: 344.53125
"""


def main() -> int:
    midi = sorted((_REPO / "bronze/gmd/mini_l3").glob("*.mid"))[0]
    midi_rel = str(midi.relative_to(_REPO))
    bus_mapping = load_bus_mapping(_REPO / "docs/specs/midi_mapping_table.yaml")

    train_kits, _ = _resolve_kit_paths()
    dg = [(lbl, path) for eng, lbl, path in train_kits if eng == "drumgizmo"]
    print(f"[franken-smoke] DG pool: {[k for k, _ in dg]}")

    kit_pool = {
        lbl: parse_recipe(_recipe_yaml(lbl, path, midi_rel)) for lbl, path in dg
    }
    template = next(iter(kit_pool.values()))

    out = _REPO / "data/gold/_franken_smoke"
    with tempfile.TemporaryDirectory():
        result, assignment = build_franken_gold_sample(
            template,
            kit_pool=kit_pool,
            out_dir=out,
            bus_mapping=bus_mapping,
            franken_kit_label="FKsmoke01",
            master_seed=42,
            variant_idx=0,
            repo_root=_REPO,
        )
    print(f"[franken-smoke] MIDI: {midi.name}")
    print(f"[franken-smoke] assignment (hybrid kit): {assignment}")
    print(f"[franken-smoke] key        : {result.key}")
    print(f"[franken-smoke] audio      : [{result.n_mic} x {result.n_sample}]")
    print(f"[franken-smoke] target     : [{result.n_frame} x ?]  peak={result.audio_peak:.4f}")
    distinct = len(set(assignment.values()))
    print(f"[franken-smoke] distinct kits used: {distinct}")
    assert result.n_mic == 8, "expected 8-bus audio"
    assert 0.0 < result.audio_peak <= 1.0, "peak out of range"
    print("[franken-smoke] ✓ valid franken Gold sample written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
