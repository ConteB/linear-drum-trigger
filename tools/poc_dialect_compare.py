#!/usr/bin/env python3
"""F0-T19 AS-IS vs TO-BE render comparison — PoC, DRSKit, DrumGizmo (OrbStack).

Renders the SAME canonical-GM groove two ways, varying ONLY the midimap:
  * AS-IS  — DRSKit's shipped (Plan-A-patched) ``Midimap_full.xml``.
  * TO-BE  — a midimap GENERATED from DRSKit's own instrument list, mapping each
             canonical GM note to the *correct* instrument (Arrow 2 of F0-T19).

Listening mix = OVERHEAD STEREO (OHL/OHR), the kit's coherent full-kit image —
NOT a mono sum of all 13 mics (which combs the room/overhead bleed into mush).

Also runs an isolated HI-HAT CHOKE diagnostic: open-alone vs open-then-closed,
measured on the Hihat mic, to verify the close chokes the open ring.

Run on OrbStack:  ~/ntg-venv/bin/python tools/poc_dialect_compare.py
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf  # type: ignore[import-untyped]

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
import mido  # type: ignore[import-untyped]  # noqa: E402

from data_engineering.gold.midi_canonical import canonicalize_midi  # noqa: E402

KIT = _REPO / "vendor/drumgizmo/DRSKit/DRSKit_full.xml"
VENDOR_MIDIMAP = _REPO / "vendor/drumgizmo/DRSKit/Midimap_full.xml"   # AS-IS (patched)
OUT = _REPO / "docs/gates/F0-T19_AB_COMPARISON"
SR = 44100

TOBE: dict[int, str] = {
    36: "Kdrum_with_contact", 37: "Snare_rim", 38: "Snare",
    42: "Hihat_closed", 44: "Hihat_foot", 46: "Hihat_open",
    47: "Tom2", 48: "Tom1", 43: "Tom3",
    51: "Ride_tip", 53: "Ride_shank_bell",
    49: "Crash_left_shank", 57: "Crash_right_shank",
    52: "Crash_right_tip", 55: "Crash_left_tip",
}
SUBSTITUTES = {37, 52, 55}
GROOVES = {
    "jazz": "bronze/gmd/v1/groove/drummer10/session1/7_jazz-swing_215_beat_4-4.mid",
    "rock": "bronze/gmd/v1/groove/drummer3/session1/14_rock_120_beat_4-4.mid",
    "funk": "bronze/gmd/v1/groove/drummer7/session2/77_funk_100_beat_4-4.mid",
}
_MAP_RE = re.compile(r'note="(\d+)"\s+instr="([^"]+)"')


def parse_midimap(path: Path) -> dict[int, str]:
    return {int(n): i for n, i in _MAP_RE.findall(path.read_text())}


def write_tobe_midimap(path: Path) -> None:
    rows = "\n".join(f'  <map note="{n}" instr="{TOBE[n]}"/>' for n in sorted(TOBE))
    path.write_text(f"<?xml version='1.0' encoding='UTF-8'?>\n<midimap>\n{rows}\n</midimap>\n")


def notes_used(midi: Path) -> list[int]:
    s = {m.note for m in mido.MidiFile(str(midi)) if m.type == "note_on" and m.velocity > 0}
    return sorted(s)


def build_midi(events: list[tuple[float, int]], out: Path) -> None:
    """events = [(time_s, note)]; one-shot note_on + a short note_off each."""
    mf = mido.MidiFile(); tr = mido.MidiTrack(); mf.tracks.append(tr)
    tpb = mf.ticks_per_beat
    msgs: list[tuple[int, mido.Message]] = []
    for t, n in events:
        on = round(t / 0.5 * tpb)
        msgs.append((on, mido.Message("note_on", note=n, velocity=100, channel=9)))
        msgs.append((on + tpb // 4, mido.Message("note_off", note=n, velocity=0, channel=9)))
    msgs.sort(key=lambda x: x[0])
    prev = 0
    for tick, m in msgs:
        m.time = tick - prev; prev = tick; tr.append(m)
    mf.save(str(out))


def render(midi: Path, midimap: Path, prefix: Path, endpos: int) -> None:
    cmd = ["drumgizmo", "-s", "-i", "midifile",
           "-I", f"file={midi},midimap={midimap}",
           "-o", "wavfile", "-O", f"file={prefix},srate={SR}",
           "-e", str(endpos), str(KIT)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=900)


def channel(prefix: Path, name: str) -> np.ndarray | None:
    hits = sorted(prefix.parent.glob(f"{prefix.name}{name}-*.wav"))
    if not hits:
        return None
    data, _ = sf.read(str(hits[0]))
    return data.mean(axis=1) if data.ndim > 1 else data


def overhead_stereo_wav(prefix: Path, out_wav: Path) -> tuple[float, float]:
    left, right = channel(prefix, "OHL"), channel(prefix, "OHR")
    assert left is not None and right is not None, "no OHL/OHR channels"
    n = min(len(left), len(right))
    st = np.stack([left[:n], right[:n]], axis=1).astype(np.float64)
    peak = float(np.abs(st).max()); rms = float(np.sqrt(np.mean(st ** 2)))
    st = st / peak * 0.9 if peak > 0 else st
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_wav), st.astype(np.float32), SR, subtype="PCM_16")
    return peak, rms


def choke_diagnostic(tmpd: Path, midimap: Path) -> None:
    """open-alone vs open+closed: does the closed hit choke the open ring?"""
    print("\n===== HI-HAT CHOKE DIAGNOSTIC (Hihat mic channel) =====")
    endpos = round(2.5 * SR)
    cases = {
        "open_alone": [(0.0, 46)],
        "open_then_closed": [(0.0, 46), (0.5, 42), (1.0, 42), (1.5, 42)],
    }
    energy: dict[str, np.ndarray] = {}
    for name, ev in cases.items():
        mid = tmpd / f"choke_{name}.mid"; build_midi(ev, mid)
        pref = tmpd / f"choke_{name}_ch"; render(mid, midimap, pref, endpos)
        hh = channel(pref, "Hihat")
        assert hh is not None, "no Hihat channel"
        energy[name] = np.abs(hh)
    # window strictly AFTER the first closed hit, between closed transients
    w0, w1 = int(0.62 * SR), int(0.95 * SR)
    e_open = float(np.sqrt(np.mean(energy["open_alone"][w0:w1] ** 2)))
    e_both = float(np.sqrt(np.mean(energy["open_then_closed"][w0:w1] ** 2)))
    ratio = e_both / e_open if e_open > 0 else float("nan")
    print(f"  Hihat-mic RMS in [0.62,0.95]s (after the close at 0.5s):")
    print(f"    open alone        = {e_open:.5f}   (open ring still sounding)")
    print(f"    open + closed     = {e_both:.5f}   (should DROP if the close chokes the open)")
    print(f"    ratio both/open   = {ratio:.2f}  →  "
          + ("CHOKE WORKS (open cut)" if ratio < 0.5 else
             "CHOKE NOT ENGAGING — open rings under the closed ✗"))


def main() -> int:
    asis_map = parse_midimap(VENDOR_MIDIMAP)
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="poc_dialect_") as tmp:
        tmpd = Path(tmp)
        tobe_midimap = tmpd / "DRSKit_generated_midimap.xml"
        write_tobe_midimap(tobe_midimap)
        (OUT / "DRSKit_generated_midimap.xml").write_text(tobe_midimap.read_text())

        for style, rel in GROOVES.items():
            src = _REPO / rel
            canon = tmpd / f"{style}_canon.mid"
            canonicalize_midi(src, standard="roland_td11", out_path=canon)
            used = notes_used(canon)
            endpos = round((mido.MidiFile(str(canon)).length + 2.0) * SR)
            print(f"\n===== {style.upper()}  ({rel.split('/')[-1]}) =====")
            for n in used:
                a = asis_map.get(n, "<UNMAPPED→SILENT>"); b = TOBE.get(n, "<unmapped>")
                flag = "" if a == b else "  DIFF"
                if n in SUBSTITUTES:
                    flag += " (subst)"
                print(f"  note {n:>3}  AS-IS {a:<24} TO-BE {b:<22}{flag}")
            for variant, mm in (("asis", VENDOR_MIDIMAP), ("tobe", tobe_midimap)):
                pref = tmpd / f"{style}_{variant}_ch"
                render(canon, mm, pref, endpos)
                peak, rms = overhead_stereo_wav(pref, OUT / f"{style}_{variant}.wav")
                print(f"  [{variant}] {style}_{variant}.wav  (OH stereo)  peak={peak:.3f} rms={rms:.4f}")

        choke_diagnostic(tmpd, tobe_midimap)
    print(f"\nWAVs (overhead stereo) in {OUT.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
