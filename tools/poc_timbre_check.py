#!/usr/bin/env python3
"""F0-T19 timbre check — are DRSKit cymbal substitutes confusable with the hi-hat?

CEO listening note (jazz_tobe): a crash-like sound resembling the hi-hat. The
jazz groove's 3 splash hits (note 55) were mapped, as a substitute, to
``Crash_left_tip`` (DRSKit has no splash). This renders each relevant instrument
as an ISOLATED single hit, captures the overhead, and reports spectral centroid +
decay so we can see (and hear) how close the substitute sits to the hi-hat.

Run on OrbStack:  ~/ntg-venv/bin/python tools/poc_timbre_check.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf  # type: ignore[import-untyped]

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
import mido  # type: ignore[import-untyped]  # noqa: E402

KIT = _REPO / "vendor/drumgizmo/DRSKit/DRSKit_full.xml"
OUT = _REPO / "docs/gates/F0-T19_AB_COMPARISON/timbre"
SR = 44100
HIT_NOTE = 60

#: instrument → role (what it stands for in the groove)
INSTRS = {
    "Hihat_closed": "hihat closed (dominant in groove)",
    "Hihat_open": "hihat open",
    "Hihat_semi_open": "hihat semi-open (what AS-IS used for note 46)",
    "Crash_left_tip": "SPLASH SUBSTITUTE (note 55 → here) — the suspect",
    "Crash_left_shank": "real crash (note 49)",
    "Ride_tip": "ride bow (note 51, reference)",
}


def one_hit_midi(out: Path) -> None:
    mf = mido.MidiFile(); tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(mido.Message("note_on", note=HIT_NOTE, velocity=110, channel=9, time=0))
    tr.append(mido.Message("note_off", note=HIT_NOTE, velocity=0, channel=9, time=mf.ticks_per_beat))
    mf.save(str(out))


def render(midi: Path, midimap: Path, prefix: Path, endpos: int) -> None:
    cmd = ["drumgizmo", "-s", "-i", "midifile",
           "-I", f"file={midi},midimap={midimap}",
           "-o", "wavfile", "-O", f"file={prefix},srate={SR}",
           "-e", str(endpos), str(KIT)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)


def oh_mono(prefix: Path) -> np.ndarray:
    chans = []
    for name in ("OHL", "OHR"):
        hits = sorted(prefix.parent.glob(f"{prefix.name}{name}-*.wav"))
        if hits:
            d, _ = sf.read(str(hits[0]))
            chans.append(d.mean(axis=1) if d.ndim > 1 else d)
    n = min(len(c) for c in chans)
    return np.mean([c[:n] for c in chans], axis=0)


def spectral_centroid(x: np.ndarray) -> float:
    # centroid over the attack+body (first 0.4 s)
    seg = x[: int(0.4 * SR)] * np.hanning(min(len(x), int(0.4 * SR)))
    mag = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), 1 / SR)
    return float((freqs * mag).sum() / mag.sum()) if mag.sum() > 0 else 0.0


def decay_s(x: np.ndarray) -> float:
    env = np.abs(x)
    pk = env.max()
    if pk <= 0:
        return 0.0
    below = np.where(env >= pk * 0.01)[0]   # -40 dB
    return float(below[-1] / SR) if len(below) else 0.0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    endpos = round(3.0 * SR)
    with tempfile.TemporaryDirectory(prefix="timbre_") as tmp:
        tmpd = Path(tmp)
        midi = tmpd / "hit.mid"; one_hit_midi(midi)
        print(f"{'instrument':<20}{'centroid Hz':>12}{'decay s':>10}   role")
        rows = []
        for instr, role in INSTRS.items():
            mm = tmpd / f"{instr}.xml"
            mm.write_text(f"<midimap>\n  <map note=\"{HIT_NOTE}\" instr=\"{instr}\"/>\n</midimap>\n")
            pref = tmpd / f"{instr}_ch"; render(midi, mm, pref, endpos)
            x = oh_mono(pref)
            c, d = spectral_centroid(x), decay_s(x)
            pk = float(np.abs(x).max())
            wav = OUT / f"{instr}.wav"
            sf.write(str(wav), (x / pk * 0.9 if pk > 0 else x).astype(np.float32), SR, subtype="PCM_16")
            rows.append((instr, c, d))
            print(f"{instr:<20}{c:>12.0f}{d:>10.2f}   {role}")
        # closeness of the splash-substitute to the hi-hats
        cen = {i: c for i, c, _ in rows}
        print("\nCloseness to splash-substitute (Crash_left_tip) by spectral centroid:")
        sub = cen["Crash_left_tip"]
        for i in ("Hihat_open", "Hihat_closed", "Hihat_semi_open", "Crash_left_shank"):
            print(f"  |{i} - splash_subst| = {abs(cen[i]-sub):>6.0f} Hz")
    print(f"\nisolated WAVs in {OUT.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
