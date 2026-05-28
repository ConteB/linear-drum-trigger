#!/usr/bin/env python3
"""F0-T19 — validate the per-kit dialect map (Arrow ②) for all DrumGizmo kits.

For each kit in docs/specs/kit_dialect_map.yaml (engine=drumgizmo):
  1. check every mapped instrument name actually exists in the kit XML (fail-loud);
  2. GENERATE a midimap (canonical note -> kit instrument);
  3. render an isolated one-hit-per-canonical-note probe through DrumGizmo;
  4. verify every canonical note produces audio (0 PHANTOM).

A PHANTOM here = a wrong instrument name (DrumGizmo finds nothing -> silence).
Substitutes still sound, so they count as OK (they're flagged separately).

Run on OrbStack:  ~/ntg-venv/bin/python tools/poc_validate_dialect_maps.py
"""
from __future__ import annotations

import re
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
SR = 44100
DT = 0.5
SILENCE = 1e-4
_INSTR_RE = re.compile(r'instrument name="([^"]+)"')


def instr_value(v: object) -> str:
    return v["instr"] if isinstance(v, dict) else str(v)


def kit_instruments(kit_xml: Path) -> set[str]:
    return set(_INSTR_RE.findall(kit_xml.read_text()))


def gen_midimap(note_to_instr: dict[int, str], out: Path) -> None:
    rows = "\n".join(f'  <map note="{n}" instr="{i}"/>' for n, i in sorted(note_to_instr.items()))
    out.write_text(f"<?xml version='1.0' encoding='UTF-8'?>\n<midimap>\n{rows}\n</midimap>\n")


def probe_midi(notes: list[int], out: Path) -> list[tuple[int, float]]:
    mf = mido.MidiFile(); tr = mido.MidiTrack(); mf.tracks.append(tr)
    tpb = mf.ticks_per_beat
    dt = int(round(DT * 2 * tpb)); note_ticks = dt // 2; gap = dt - note_ticks
    layout: list[tuple[int, float]] = []
    t = 0.0; first = True
    for n in notes:
        tr.append(mido.Message("note_on", note=n, velocity=100, channel=9,
                               time=0 if first else gap)); first = False
        tr.append(mido.Message("note_off", note=n, velocity=0, channel=9, time=note_ticks))
        layout.append((n, t)); t += DT
    mf.save(str(out))
    return layout


def single_note_midi(n: int, out: Path) -> None:
    mf = mido.MidiFile(); tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(mido.Message("note_on", note=n, velocity=100, channel=9, time=0))
    tr.append(mido.Message("note_off", note=n, velocity=0, channel=9, time=mf.ticks_per_beat // 4))
    mf.save(str(out))


def render(kit_xml: Path, midimap: Path, midi: Path, prefix: Path, endpos: int) -> None:
    subprocess.run(["drumgizmo", "-s", "-i", "midifile",
                    "-I", f"file={midi},midimap={midimap}",
                    "-o", "wavfile", "-O", f"file={prefix},srate={SR}",
                    "-e", str(endpos), str(kit_xml)],
                   check=True, capture_output=True, timeout=600)


def summed(prefix: Path) -> np.ndarray:
    mix: np.ndarray | None = None
    for w in sorted(prefix.parent.glob(prefix.name + "*.wav")):
        d, _ = sf.read(str(w))
        if d.ndim > 1:
            d = d.mean(axis=1)
        if mix is None:
            mix = np.zeros(len(d))
        n = min(len(mix), len(d)); mix[:n] += np.abs(d[:n])
    assert mix is not None
    return mix


def main() -> int:
    spec = yaml.safe_load(DIALECT.read_text())
    total_phantom = 0
    for kit, cfg in spec["kits"].items():
        if cfg.get("engine") != "drumgizmo":
            print(f"\n{kit}: engine={cfg.get('engine')} — skipped (handled by Sfizz path)")
            continue
        kit_xml = _REPO / cfg["kit_xml"]
        m = {int(n): instr_value(v) for n, v in cfg["map"].items()}
        avail = kit_instruments(kit_xml)
        missing = {n: i for n, i in m.items() if i not in avail}
        print(f"\n=== {kit} ({len(m)} notes) ===")
        if missing:
            print(f"  ✗ INSTRUMENT NAMES NOT IN KIT XML: {missing}")
            total_phantom += len(missing)
            continue
        print("  ✓ all instrument names exist in kit XML")
        with tempfile.TemporaryDirectory() as tmp:
            tmpd = Path(tmp)
            mm = tmpd / "gen_midimap.xml"; gen_midimap(m, mm)
            phantom = []
            for n in sorted(m):  # isolated single-note renders (no voice-steal cross-talk)
                single = tmpd / f"n{n}.mid"; single_note_midi(n, single)
                pref = tmpd / f"n{n}_ch"; render(kit_xml, mm, single, pref, round(2.0 * SR))
                pk = max((float(np.abs(sf.read(str(w))[0]).max())
                          for w in pref.parent.glob(pref.name + "*.wav")), default=0.0)
                if pk < SILENCE:
                    phantom.append(n)
            if phantom:
                print(f"  ✗ PHANTOM (silent) notes: {phantom}")
                total_phantom += len(phantom)
            else:
                print(f"  ✓ all {len(m)} canonical articulations SOUND in isolation (0 phantom)")
    print(f"\n{'='*50}\nOVERALL: {total_phantom} phantom/missing across all DG kits  "
          + ("✓ PASS" if total_phantom == 0 else "✗ FAIL"))
    return 0 if total_phantom == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
