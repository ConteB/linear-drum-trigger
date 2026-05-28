#!/usr/bin/env python3
"""F0-T19 hi-hat choke in a REAL groove — does each open get choked by the next hit?

CEO listening note: open hi-hat seems to ring on while closed hits continue. The
isolated single-open test choked cleanly, but a real pattern interleaves many
hits. This extracts ONLY the hi-hat notes from the jazz groove, renders them
hi-hat-only (no other drums to confuse the ear), and:
  * writes jazz_hihat_only_{asis,tobe}.wav (overhead stereo) to listen;
  * prints the hi-hat event timeline + a per-event check: just before the NEXT
    hi-hat hit, is the previous one still ringing, and does it drop after?

Run on OrbStack:  ~/ntg-venv/bin/python tools/poc_hihat_choke_groove.py
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

from data_engineering.gold.midi_canonical import canonicalize_midi  # noqa: E402

KIT = _REPO / "vendor/drumgizmo/DRSKit/DRSKit_full.xml"
VENDOR_MIDIMAP = _REPO / "vendor/drumgizmo/DRSKit/Midimap_full.xml"
OUT = _REPO / "docs/gates/F0-T19_AB_COMPARISON"
JAZZ = "bronze/gmd/v1/groove/drummer10/session1/7_jazz-swing_215_beat_4-4.mid"
SR = 44100
HIHAT_NOTES = {42: "closed", 44: "pedal", 46: "open"}
TOBE = {42: "Hihat_closed", 44: "Hihat_foot", 46: "Hihat_open"}


def write_midimap(path: Path, mapping: dict[int, str]) -> None:
    rows = "\n".join(f'  <map note="{n}" instr="{i}"/>' for n, i in sorted(mapping.items()))
    path.write_text(f"<midimap>\n{rows}\n</midimap>\n")


def hihat_only(src_canon: Path, out: Path) -> list[tuple[float, int]]:
    """Keep only hi-hat note_on/off; return [(time_s, note)] event list."""
    mf = mido.MidiFile(str(src_canon))
    tpb = mf.ticks_per_beat
    keep = mido.MidiFile(ticks_per_beat=tpb); tr = mido.MidiTrack(); keep.tracks.append(tr)
    events: list[tuple[float, int]] = []
    abs_t = 0; last = 0
    tempo = 500000
    for msg in mido.merge_tracks(mf.tracks):
        abs_t += msg.time
        if msg.type == "set_tempo":
            tempo = msg.tempo
        if msg.type in ("note_on", "note_off") and msg.note in HIHAT_NOTES:
            nm = msg.copy(time=abs_t - last); tr.append(nm); last = abs_t
            if msg.type == "note_on" and msg.velocity > 0:
                events.append((mido.tick2second(abs_t, tpb, tempo), msg.note))
    keep.save(str(out))
    return events


def render(midi: Path, midimap: Path, prefix: Path, endpos: int) -> None:
    cmd = ["drumgizmo", "-s", "-i", "midifile",
           "-I", f"file={midi},midimap={midimap}",
           "-o", "wavfile", "-O", f"file={prefix},srate={SR}",
           "-e", str(endpos), str(KIT)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)


def chan(prefix: Path, name: str) -> np.ndarray | None:
    hits = sorted(prefix.parent.glob(f"{prefix.name}{name}-*.wav"))
    if not hits:
        return None
    d, _ = sf.read(str(hits[0]))
    return d.mean(axis=1) if d.ndim > 1 else d


def write_oh(prefix: Path, out_wav: Path) -> None:
    left, right = chan(prefix, "OHL"), chan(prefix, "OHR")
    assert left is not None and right is not None
    n = min(len(left), len(right))
    st = np.stack([left[:n], right[:n]], axis=1)
    pk = float(np.abs(st).max())
    sf.write(str(out_wav), (st / pk * 0.9 if pk else st).astype(np.float32), SR, subtype="PCM_16")


def rms(x: np.ndarray, t0: float, t1: float) -> float:
    a, b = int(t0 * SR), int(t1 * SR)
    seg = x[max(0, a):min(len(x), b)]
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hh_choke_") as tmp:
        tmpd = Path(tmp)
        canon = tmpd / "jazz_canon.mid"
        canonicalize_midi(_REPO / JAZZ, standard="roland_td11", out_path=canon)
        hh = tmpd / "jazz_hihat_only.mid"
        events = hihat_only(canon, hh)
        endpos = round((mido.MidiFile(str(hh)).length + 3.5) * SR)

        tobe_mm = tmpd / "tobe.xml"; write_midimap(tobe_mm, TOBE)
        # AS-IS uses the vendor midimap (whatever it maps 42/44/46 to)
        for variant, mm in (("asis", VENDOR_MIDIMAP), ("tobe", tobe_mm)):
            pref = tmpd / f"hh_{variant}_ch"; render(hh, mm, pref, endpos)
            write_oh(pref, OUT / f"jazz_hihat_only_{variant}.wav")

        # choke check on the TO-BE Hihat mic
        pref = tmpd / "hh_tobe_ch"; render(hh, tobe_mm, pref, endpos)
        hihat = chan(pref, "Hihat"); assert hihat is not None
        print(f"jazz hi-hat events: {len(events)}  (closed={sum(1 for _,n in events if n==42)} "
              f"open={sum(1 for _,n in events if n==46)} pedal={sum(1 for _,n in events if n==44)})")
        print("\nPer OPEN hit: ring just before next hit, and 80 ms AFTER next hit "
              "(should collapse if the next hit chokes it):")
        bad = 0
        for i, (t, n) in enumerate(events[:-1]):
            if n != 46:
                continue
            t_next = events[i + 1][0]
            pre = rms(hihat, t_next - 0.030, t_next - 0.005)   # open still ringing
            post = rms(hihat, t_next + 0.090, t_next + 0.140)  # after next hit lands
            ratio = post / pre if pre > 1e-6 else 0.0
            verdict = "choked ✓" if ratio < 0.6 else "STILL RINGING ✗"
            if ratio >= 0.6:
                bad += 1
            print(f"  open @ {t:5.2f}s  next @ {t_next:5.2f}s (Δ{t_next-t:.2f}s)  "
                  f"pre={pre:.4f} post={post:.4f} ratio={ratio:.2f}  {verdict}")
        print(f"\n{'ALL opens choked by the next hit ✓' if bad==0 else f'{bad} open(s) NOT choked ✗'}")
    print(f"\nWAVs: {OUT.relative_to(_REPO)}/jazz_hihat_only_{{asis,tobe}}.wav")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
