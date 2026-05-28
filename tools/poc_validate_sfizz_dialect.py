#!/usr/bin/env python3
"""F0-T19 — validate the Sfizz dialect map (Arrow ②, MIDI remap) — macOS.

For the Sfizz kit in kit_dialect_map.yaml: remap each canonical note to the .sfz
key it declares, render that single note via sfizz_render, and verify it sounds
(0 phantom). A phantom = a key the .sfz has no region for (silent).

Run on macOS:  .venv/bin/python tools/poc_validate_sfizz_dialect.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
import mido  # type: ignore[import-untyped]  # noqa: E402

DIALECT = _REPO / "docs/specs/kit_dialect_map.yaml"
SFIZZ = _REPO / "vendor/sfizz/sfizz_render"
SR = 44100
SILENCE = 1e-4


def key_value(v: object) -> int:
    return int(v["key"]) if isinstance(v, dict) else int(v)


def single_note(key: int, out: Path) -> None:
    mf = mido.MidiFile(); tr = mido.MidiTrack(); mf.tracks.append(tr)
    tpb = mf.ticks_per_beat
    tr.append(mido.Message("note_on", note=key, velocity=100, channel=9, time=0))
    tr.append(mido.Message("note_off", note=key, velocity=0, channel=9, time=tpb * 2))
    mf.save(str(out))


def render(sfz: Path, midi: Path, wav: Path) -> None:
    subprocess.run([str(SFIZZ), "--sfz", str(sfz), "--midi", str(midi),
                    "--wav", str(wav), "--samplerate", str(SR)],
                   check=True, capture_output=True, timeout=120)


def main() -> int:
    spec = yaml.safe_load(DIALECT.read_text())
    total_phantom = 0
    for kit, cfg in spec["kits"].items():
        if cfg.get("engine") != "sfizz":
            continue
        sfz = _REPO / cfg["sfz"]
        m = {int(n): key_value(v) for n, v in cfg["map"].items()}
        print(f"=== {kit} ({len(m)} notes) — sfz={cfg['sfz']} ===")
        phantom = []
        with tempfile.TemporaryDirectory() as tmp:
            tmpd = Path(tmp)
            for canon, key in sorted(m.items()):
                midi = tmpd / f"n{canon}.mid"; single_note(key, midi)
                wav = tmpd / f"n{canon}.wav"; render(sfz, midi, wav)
                d, _ = sf.read(str(wav))
                pk = float(np.abs(d).max()) if d.size else 0.0
                tag = "" if pk >= SILENCE else "  ✗ PHANTOM"
                if pk < SILENCE:
                    phantom.append(canon)
                print(f"  canon {canon:>3} -> key {key:>3}  peak={pk:.4f}{tag}")
        if phantom:
            print(f"  ✗ PHANTOM notes: {phantom}"); total_phantom += len(phantom)
        else:
            print(f"  ✓ all {len(m)} canonical articulations SOUND (0 phantom)")
    print(f"\nOVERALL Sfizz: {total_phantom} phantom  "
          + ("✓ PASS" if total_phantom == 0 else "✗ FAIL"))
    return 0 if total_phantom == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
