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
from data_engineering.gold.target_builder import (  # noqa: E402
    last_onset_seconds,
    load_bus_mapping,
)
from data_engineering.midi_augment.jitter import apply_midi_jitter  # noqa: E402

MASTER_SEED = 20260601
MIN_FREE_GB = 6.0
# Crop = 196608 (4.46 s); the dataset needs (crop_frames + lookahead)·128 audio
# samples. Grooves whose tail-standardized render is shorter are dropped at
# render time (else they fail-loud at training). 196608 + 35·128 = 201088.
MIN_SAMPLE_LEN = 135552 + 35 * 128  # 3.07s crop threshold
# CAP groove length: GMD v1 has full-performance grooves (minutes) that render to
# 80+ MB each and OOM OrbStack. The training crop is only 3.07 s, so cap source
# MIDIs at MAX_MIDI_S → bounded sample size (~4 MB) and bounded render RAM.
MAX_MIDI_S = 6.0
TRAIN_DIR = _REPO / "data/gold/scaling_train"
VAL_DIR = _REPO / "data/gold/scaling_val"


def _free_gb() -> float:
    return shutil.disk_usage(str(_REPO)).free / (1 << 30)


def _trim_midi_seconds(midi: mido.MidiFile, max_s: float) -> mido.MidiFile:
    """Trim a MIDI to its first ``max_s`` seconds (tempo-aware), closing any
    notes still open at the cut. Bounds render size + RAM for long grooves."""
    merged = mido.merge_tracks(midi.tracks)
    out = mido.MidiFile(ticks_per_beat=midi.ticks_per_beat)
    track = mido.MidiTrack()
    tempo = 500000  # default 120 BPM until a set_tempo says otherwise
    abs_s = 0.0
    open_notes: set[tuple[int, int]] = set()
    for msg in merged:
        dt_s = mido.tick2second(msg.time, midi.ticks_per_beat, tempo)
        if abs_s + dt_s > max_s:
            break
        abs_s += dt_s
        if msg.type == "set_tempo":
            tempo = msg.tempo
        track.append(msg.copy())
        if msg.type == "note_on" and msg.velocity > 0:
            open_notes.add((msg.channel, msg.note))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            open_notes.discard((msg.channel, msg.note))
    for ch, note in open_notes:
        track.append(mido.Message("note_off", note=note, channel=ch, velocity=0, time=0))
    track.append(mido.MetaMessage("end_of_track", time=0))
    out.tracks.append(track)
    return out


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
  target_frame_rate_hz: 86.1328125
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
                # Render each qualifying groove through ALL kits × variants — more
                # audio examples per groove (timbral + jitter volume) so the scaling
                # axis reaches a real range despite the ~25% long-groove qualify rate.
                trimmed = _trim_midi_seconds(mido.MidiFile(str(midi)), MAX_MIDI_S)
                # Pre-check length ONCE (no render): skip short grooves before
                # wasting 4 kits × N variants of rendering on them.
                probe = tmp / f"{tag}_{i}_probe.mid"
                trimmed.save(str(probe))
                try:
                    last_onset = last_onset_seconds(probe, bus_mapping=bus_mapping)
                except Exception:  # noqa: BLE001 — no mapped notes etc.
                    short += 1
                    continue
                if (last_onset + 0.5) * 44100 < MIN_SAMPLE_LEN:
                    short += 1
                    continue
                for kit, kpath in (dg if tag == "TR" else dg[:1]):
                    for v in range(variants):
                        if done >= target:
                            break
                        try:
                            jit = apply_midi_jitter(
                                trimmed, variant_idx=v,
                                master_seed=MASTER_SEED, source_midi_id=midi_rel)
                            jpath = tmp / f"{tag}_{i}_{kit}_v{v}.mid"
                            jit.save(str(jpath))
                            rid = f"R-{tag}-{stem}-{kit}-V{v}"
                            rec = parse_recipe(
                                _recipe_yaml(kit, kpath, midi_rel, rid, v))
                            res = build_gold_sample(
                                rec, out_dir=out_root / kit, bus_mapping=bus_mapping,
                                repo_root=_REPO, midi_path_override=jpath)
                            if res.n_sample < MIN_SAMPLE_LEN:
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
                                    print(f"  ✗ {tag} {stem} {kit} v{v}: "
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
