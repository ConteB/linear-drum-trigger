#!/usr/bin/env python3
"""F0-T20 scaling-curve — render N distinct GMD grooves (single-kit, rotating DG
kits) to test whether F rises with DATA QUANTITY. Runs on OrbStack (DrumGizmo).

Clean dataset (NO franken): each groove rendered through one rotating DG kit, the
canonical F0-T18/T19 pipeline (standard=roland_td11). Train and val grooves are
DISJOINT but use the SAME kits → val is held-out IN-distribution (isolates "more
data" from the ShittyKit cross-kit OOD wall). Resume-safe, disk-monitored
(hard-stop when free < MIN_FREE_GB).

    orb run -m ubuntu bash -lc '~/ntg-venv/bin/python tools/build_scaling_dataset.py \
        --n-train 2000 --n-val 200 --variants 2'
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import mido  # type: ignore[import-untyped]

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))

from tools.mini_l3_runner import _resolve_kit_paths  # noqa: E402

from data_engineering.gold.orchestrate import build_gold_sample  # noqa: E402
from data_engineering.gold.recipe import parse_recipe  # noqa: E402
from data_engineering.gold.target_builder import load_bus_mapping  # noqa: E402
from data_engineering.midi_augment.jitter import apply_midi_jitter  # noqa: E402

MASTER_SEED = 20260601
MIN_FREE_GB = 6.0
# Crop = 196608 (4.46 s); the dataset needs (crop_frames + lookahead)·128 audio
# samples. Grooves whose tail-standardized render is shorter are dropped at
# render time (else they fail-loud at training). 196608 + 35·128 = 201088.
MIN_SAMPLE_LEN = 135552 + 35 * 128  # 3.07s crop threshold
TRAIN_DIR = _REPO / "data/gold/scaling_train"
VAL_DIR = _REPO / "data/gold/scaling_val"


def _free_gb() -> float:
    return shutil.disk_usage(str(_REPO)).free / (1 << 30)


def _recipe_yaml(kit: str, kit_path: str, midi_file: str, rid: str, variant: int) -> str:
    split = "val" if "VAL" in rid else "train"
    return f"""
recipe_id: {rid}
schema_version: "1.0"
split: {split}
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--midi-dir", type=Path, default=_REPO / "bronze/gmd/v1")
    ap.add_argument("--n-train", type=int, default=2000)
    ap.add_argument("--n-val", type=int, default=200)
    ap.add_argument("--variants", type=int, default=2)
    args = ap.parse_args()

    midis = sorted(args.midi_dir.rglob("*.mid"))
    if not midis:
        sys.exit(f"no MIDIs under {args.midi_dir}")
    bus_mapping = load_bus_mapping(_REPO / "docs/specs/midi_mapping_table.yaml")
    train_kits, _ = _resolve_kit_paths()
    dg = [(lbl, p) for eng, lbl, p in train_kits if eng == "drumgizmo"]
    print(f"[scaling] {len(midis)} MIDIs | DG kits {[k for k, _ in dg]} | "
          f"variants={args.variants} | free={_free_gb():.1f}GB")

    # Disjoint groove split: first N_val grooves → val, rest → train.
    val_midis = midis[: args.n_val]
    train_midis = midis[args.n_val:]

    def render_set(midi_list: list[Path], out_root: Path, tag: str,
                   target: int, variants: int) -> tuple[int, int, int]:
        done = fail = short = 0
        with tempfile.TemporaryDirectory(prefix=f"scal_{tag}_") as _tmp:
            tmp = Path(_tmp)
            for i, midi in enumerate(midi_list):
                if done >= target:
                    break
                if _free_gb() < MIN_FREE_GB:
                    print(f"[scaling] ⚠ STOP {tag}: free {_free_gb():.1f}GB < "
                          f"{MIN_FREE_GB}GB (rendered {done})", flush=True)
                    break
                midi_rel = str(midi.relative_to(_REPO))
                stem = midi.stem
                kit, kpath = dg[i % len(dg)]  # rotate kits for timbral spread
                for v in range(variants):
                    if done >= target:
                        break
                    try:
                        jit = apply_midi_jitter(
                            mido.MidiFile(str(midi)), variant_idx=v,
                            master_seed=MASTER_SEED, source_midi_id=midi_rel)
                        jpath = tmp / f"{tag}_{i}_v{v}.mid"
                        jit.save(str(jpath))
                        rid = f"R-{tag}-{stem}-{kit}-V{v}"
                        rec = parse_recipe(
                            _recipe_yaml(kit, kpath, midi_rel, rid, v))
                        res = build_gold_sample(
                            rec, out_dir=out_root / kit, bus_mapping=bus_mapping,
                            repo_root=_REPO, midi_path_override=jpath)
                        if res.n_sample < MIN_SAMPLE_LEN:
                            # write_gold_sample writes the triple FLAT into the kit
                            # dir — delete only THIS sample's 3 files, never the dir.
                            for ext in (".audio.f16", ".target.f16", ".dna.json"):
                                (Path(res.out_dir) / f"{res.key}{ext}").unlink(
                                    missing_ok=True)
                            short += 1
                            continue
                        done += 1
                    except Exception as exc:  # noqa: BLE001
                        msg = str(exc)
                        if "too short" in msg or "min_audio" in msg or "< min" in msg:
                            short += 1
                        else:
                            fail += 1
                            if fail <= 5:
                                print(f"  ✗ {tag} {stem} v{v}: "
                                      f"{type(exc).__name__}: {msg[:80]}", flush=True)
                if done % 100 == 0 and done > 0:
                    print(f"  {tag}: {done} done, {short} short, {fail} fail, "
                          f"free={_free_gb():.1f}GB", flush=True)
        return done, short, fail

    nv, vs, vf = render_set(val_midis, VAL_DIR, "VAL", args.n_val, 1)
    print(f"[scaling] VAL done: {nv} (short {vs}, fail {vf})", flush=True)
    nt, ts, tf = render_set(train_midis, TRAIN_DIR, "TR", args.n_train, args.variants)
    print(f"[scaling] DONE train={nt} (short {ts}, fail {tf}) | val={nv} | "
          f"free={_free_gb():.1f}GB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
