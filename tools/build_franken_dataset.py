#!/usr/bin/env python3
"""F0-T20b — build the franken-kit dataset for the local A/B (DG pool).

Train = 50% franken (hybrid kit from the 4 DG train kits) + 50% single-kit
(D3), across ``--variants`` jitter variants per MIDI (variant 0 = baseline).
Val = single-kit ShittyKit (held-out, the real cross-kit test). Runs on
OrbStack (DrumGizmo). Resume-safe (skip if the sample dir already exists).

Scaled to be comparable to the F0-T19 baseline (~577 train / 248 val, verdict
0.1455 production): 250 MIDI x 2 variants ~= 500 train, 250 val.

    orb run -m ubuntu bash -lc '~/ntg-venv/bin/python tools/build_franken_dataset.py \
        --n-train 250 --n-val 250 --variants 2'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import mido  # type: ignore[import-untyped]

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))

from tools.mini_l3_runner import _resolve_kit_paths  # noqa: E402

from data_engineering.gold.franken import build_franken_gold_sample  # noqa: E402
from data_engineering.gold.orchestrate import build_gold_sample  # noqa: E402
from data_engineering.gold.recipe import parse_recipe  # noqa: E402
from data_engineering.gold.target_builder import load_bus_mapping  # noqa: E402
from data_engineering.midi_augment.jitter import apply_midi_jitter  # noqa: E402

MASTER_SEED = 20260530
TRAIN_DIR = _REPO / "data/gold/franken_train"
VAL_DIR = _REPO / "data/gold/franken_val"


def _recipe_yaml(kit: str, kit_path: str, midi_file: str, rid: str, variant: int) -> str:
    return f"""
recipe_id: {rid}
schema_version: "1.0"
split: {"val" if "VAL" in rid else "train"}
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
  variant_idx: {variant}
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


def _coin_is_franken(midi_id: str) -> bool:
    h = hashlib.sha256(f"{MASTER_SEED}|coin|{midi_id}".encode()).digest()
    return (h[0] & 1) == 0  # ~50/50 deterministic, per-MIDI (all variants same type)


def _pick_single_kit(midi_id: str, kits: list[str]) -> str:
    h = hashlib.sha256(f"{MASTER_SEED}|single|{midi_id}".encode()).digest()
    return kits[int.from_bytes(h[:8], "big") % len(kits)]


def _jittered(midi_path: Path, midi_rel: str, variant: int, tmp: Path) -> Path:
    """Apply the LOCKED MIDI jitter for ``variant`` (0 = baseline) -> temp file."""
    jit = apply_midi_jitter(
        mido.MidiFile(str(midi_path)),
        variant_idx=variant,
        master_seed=MASTER_SEED,
        source_midi_id=midi_rel,
    )
    out = tmp / f"v{variant}.mid"
    jit.save(str(out))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-train", type=int, default=250)
    ap.add_argument("--n-val", type=int, default=250)
    ap.add_argument("--variants", type=int, default=2)
    args = ap.parse_args()

    midis = sorted((_REPO / "bronze/gmd/mini_l3").glob("*.mid"))
    bus_mapping = load_bus_mapping(_REPO / "docs/specs/midi_mapping_table.yaml")
    train_kits, val_kit = _resolve_kit_paths()
    dg = [(lbl, path) for eng, lbl, path in train_kits if eng == "drumgizmo"]
    dg_labels = [lbl for lbl, _ in dg]
    print(f"[franken-ds] DG train pool: {dg_labels} | val kit: {val_kit[0]} "
          f"| variants={args.variants}")

    n_fr = n_sg = fail = 0
    with tempfile.TemporaryDirectory(prefix="fkds_") as _tmp:
        tmp = Path(_tmp)
        # --- TRAIN: 50/50 franken / single, x variants ---
        for midi in midis[: args.n_train]:
            midi_rel = str(midi.relative_to(_REPO))
            mid = midi.stem
            is_fr = _coin_is_franken(mid)
            for v in range(args.variants):
                try:
                    jmidi = _jittered(midi, midi_rel, v, tmp)
                    if is_fr:
                        kit_pool = {
                            lbl: parse_recipe(
                                _recipe_yaml(lbl, p, midi_rel, f"R-FK-{mid}", v))
                            for lbl, p in dg
                        }
                        template = next(iter(kit_pool.values()))
                        res, asg = build_franken_gold_sample(
                            template, kit_pool=kit_pool, out_dir=TRAIN_DIR / "franken",
                            bus_mapping=bus_mapping, franken_kit_label="FK01",
                            master_seed=MASTER_SEED, variant_idx=v, repo_root=_REPO,
                            midi_path_override=jmidi,
                        )
                        (res.out_dir / "franken_provenance.json").write_text(
                            json.dumps(asg, sort_keys=True))
                        n_fr += 1
                    else:
                        kit = _pick_single_kit(mid, dg_labels)
                        kp = dict(dg)[kit]
                        rec = parse_recipe(
                            _recipe_yaml(kit, kp, midi_rel, f"R-SG-{mid}", v))
                        build_gold_sample(
                            rec, out_dir=TRAIN_DIR / "single",
                            bus_mapping=bus_mapping, repo_root=_REPO,
                            midi_path_override=jmidi)
                        n_sg += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"  ✗ train {mid} v{v}: {type(exc).__name__}: {exc}")
                    fail += 1
            tot = n_fr + n_sg
            if tot % 40 == 0 and tot > 0:
                print(f"  train: franken={n_fr} single={n_sg} fail={fail}")

        # --- VAL: single-kit ShittyKit (held-out), baseline variant only ---
        nv = vfail = 0
        for midi in midis[: args.n_val]:
            midi_rel = str(midi.relative_to(_REPO))
            mid = midi.stem
            try:
                jmidi = _jittered(midi, midi_rel, 0, tmp)
                rec = parse_recipe(
                    _recipe_yaml(val_kit[0], val_kit[1], midi_rel, f"R-VAL-{mid}", 0))
                build_gold_sample(
                    rec, out_dir=VAL_DIR / val_kit[0], bus_mapping=bus_mapping,
                    repo_root=_REPO, midi_path_override=jmidi)
                nv += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  ✗ val {mid}: {type(exc).__name__}: {exc}")
                vfail += 1
            if nv % 50 == 0 and nv > 0:
                print(f"  val: {nv}")

    print(f"[franken-ds] DONE train franken={n_fr} single={n_sg} fail={fail} | "
          f"val={nv} vfail={vfail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
