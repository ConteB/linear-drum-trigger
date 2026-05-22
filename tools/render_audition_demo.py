#!/usr/bin/env python3
"""Audition demo — multi-genre / multi-tempo render showcase (DrumGizmo, stereo).

A listening showcase for the F0 render pipeline: a handful of drum grooves
across genres and tempos, each rendered through the full DRSKit multi-mic kit
(:class:`DrumGizmoRenderer`, F0-T2c) and mixed down to a polished **stereo**
WAV — close mics panned across the field, the overhead pair as the stereo bed,
a touch of room. The renders carry DrumGizmo's real inter-mic bleed.

This is aural-proof material only — it touches no Gold tensor and no recipe.
Output lands in ``audition/demo/`` (git-ignored, regenerable).

DrumGizmo is a Linux toolchain — run inside the OrbStack VM:
    orb run -m ubuntu bash -lc '~/ntg-venv/bin/python tools/render_audition_demo.py'
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import mido  # type: ignore[import-untyped]
import numpy as np
import soundfile as sf  # type: ignore[import-untyped]

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.gold.render import (  # noqa: E402
    DRSKIT_MULTITRACK8,
    DrumGizmoRenderer,
)

_KIT_XML = _REPO_ROOT / "vendor" / "drumgizmo" / "DRSKit" / "DRSKit_full.xml"
_MIDIMAP_XML = _REPO_ROOT / "vendor" / "drumgizmo" / "DRSKit" / "Midimap_full.xml"
_OUT_DIR = _REPO_ROOT / "audition" / "demo"
_TPB = 480  # MIDI ticks per beat

# GM drum notes covered by both the bus map and DRSKit's Midimap_full.xml.
K, S, STICK = 36, 38, 37
HHC, HHP, HHO = 42, 44, 46  # hi-hat: closed / pedal / open
TOM, FLOOR_HI, FLOOR_LO = 47, 43, 41
RIDE, CRASH, CRASH2 = 51, 49, 57


def _hh(step: float, note: int, vel: int, count: int) -> list[tuple[float, int, int]]:
    """``count`` evenly-spaced hi-hat/ride hits, ``step`` beats apart."""
    return [(i * step, note, vel) for i in range(count)]


@dataclass
class Groove:
    """One demo groove: a genre, a tempo and a one-bar pattern."""

    name: str
    bpm: int
    bars: int
    bar: list[tuple[float, int, int]]  # (beat, note, velocity), beat in [0, 4)
    fill: list[tuple[float, int, int]] = field(default_factory=list)


# --------------------------------------------------------------------------
# The showcase — eight genres from 66 to 184 BPM.
# --------------------------------------------------------------------------
GROOVES: list[Groove] = [
    Groove(
        "rock", 120, 4,
        bar=[(0, K, 102), (2, K, 98), (2.5, K, 82), (1, S, 108), (3, S, 108)]
        + [(i * 0.5, HHC, 88 if i % 2 == 0 else 66) for i in range(8)],
        fill=[(2, S, 92), (2.5, TOM, 100), (3, FLOOR_HI, 104), (3.5, FLOOR_LO, 112)],
    ),
    Groove(
        "funk", 96, 4,
        bar=[(0, K, 106), (0.75, K, 84), (1.5, K, 78), (2.5, K, 100), (3.25, K, 82)]
        + [(1, S, 112), (3, S, 112)]
        + [(0.5, S, 32), (1.75, S, 40), (2.25, S, 36), (3.5, S, 44)]
        + [(i * 0.25, HHC, 82 if i % 4 == 0 else (42 if i % 2 else 60)) for i in range(16)],
        fill=[(2, S, 58), (2.5, TOM, 96), (2.75, TOM, 88),
              (3, FLOOR_HI, 100), (3.5, FLOOR_LO, 110)],
    ),
    Groove(
        "jazz-swing", 148, 4,
        bar=[(0, RIDE, 90), (1, RIDE, 76), (1.667, RIDE, 70), (2, RIDE, 86),
             (3, RIDE, 76), (3.667, RIDE, 70)]
        + [(1, HHP, 64), (3, HHP, 64)]
        + [(0, K, 38), (1, K, 34), (2, K, 38), (3, K, 34)]
        + [(2.333, S, 52), (3.667, S, 46)],
        fill=[(2, S, 66), (2.667, TOM, 72), (3, S, 60),
              (3.333, FLOOR_HI, 78), (3.667, RIDE, 82)],
    ),
    Groove(
        "metal", 184, 2,
        bar=[(i * 0.25, K, 98 if i % 4 == 0 else 86) for i in range(16)]
        + [(1, S, 116), (3, S, 116)]
        + _hh(0.5, RIDE, 80, 8),
        fill=[(3, TOM, 110), (3.25, TOM, 104), (3.5, FLOOR_HI, 110), (3.75, FLOOR_LO, 118)],
    ),
    Groove(
        "hip-hop", 86, 4,
        bar=[(0, K, 110), (0.75, K, 70), (2.5, K, 106), (1, S, 114), (3, S, 114)]
        + [(i * 0.5 + (0.05 if i % 2 else 0.0), HHC, 78 if i % 2 == 0 else 54)
           for i in range(8)],
    ),
    Groove(
        "bossa-latin", 134, 4,
        bar=[(0, STICK, 96), (0.75, STICK, 88), (1.5, STICK, 92),
             (2.5, STICK, 94), (3, STICK, 88)]
        + [(0, K, 86), (1.5, K, 76), (2, K, 84), (3.5, K, 74)]
        + _hh(0.5, RIDE, 62, 8),
    ),
    Groove(
        "shuffle-blues", 114, 4,
        bar=[(b + off, HHC, vel)
             for b in range(4)
             for off, vel in ((0.0, 84), (0.667, 58))]
        + [(0, K, 100), (2, K, 96), (1, S, 106), (3, S, 106)],
        fill=[(2.667, TOM, 90), (3, FLOOR_HI, 98),
              (3.333, FLOOR_HI, 92), (3.667, FLOOR_LO, 110)],
    ),
    Groove(
        "ballad-halftime", 66, 4,
        bar=[(0, K, 94), (2.5, K, 70), (2, S, 98)]
        + [(i * 0.5, HHC, 58 if i % 2 == 0 else 42) for i in range(8)]
        + [(1.5, HHO, 64), (3.5, HHO, 70)],
        fill=[(3, S, 58), (3.5, FLOOR_HI, 86)],
    ),
]

# Per-channel mix of the DRSKIT_MULTITRACK8 layout
# (kick, snare, hihat, tom, floor, oh_L, oh_R, room): (gain, pan in [-1, 1]).
_MIX: tuple[tuple[float, float], ...] = (
    (0.92, 0.00),   # kick   — centred, forward
    (0.86, -0.05),  # snare  — a hair left of centre
    (0.52, -0.38),  # hihat  — drummer's perspective, left
    (0.70, -0.25),  # tom    — left
    (0.70, 0.32),   # floor  — right
    (0.52, -0.62),  # oh_L   — stereo bed, left
    (0.52, 0.62),   # oh_R   — stereo bed, right
    (0.34, 0.00),   # room   — centred glue
)


def _build_midi(groove: Groove, path: Path) -> None:
    """Synthesise a groove MIDI: ``bar`` repeated, a crash in, a fill to close."""
    events: list[tuple[float, int, int]] = [(0.0, CRASH, 112)]
    for bar_idx in range(groove.bars):
        base = bar_idx * 4.0
        last = bar_idx == groove.bars - 1
        pattern = (
            [e for e in groove.bar if e[0] < 2.0] + groove.fill
            if last and groove.fill
            else groove.bar
        )
        events += [(base + beat, note, vel) for beat, note, vel in pattern]

    midi = mido.MidiFile(ticks_per_beat=_TPB)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(groove.bpm), time=0))

    timed: list[tuple[int, int, mido.Message]] = []
    for beat, note, vel in events:
        tick = round(beat * _TPB)
        timed.append((tick, 1, mido.Message("note_on", note=note, velocity=vel)))
        timed.append((tick + 30, 0, mido.Message("note_off", note=note, velocity=0)))
    timed.sort(key=lambda item: (item[0], item[1]))

    prev = 0
    for tick, _, message in timed:
        track.append(message.copy(time=tick - prev))
        prev = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(str(path))


def _stereo_mix(multimic_wav: Path) -> tuple[np.ndarray, int]:
    """Mix the 8-mic render down to a panned, normalised stereo pair."""
    audio, sr = sf.read(str(multimic_wav), dtype="float32", always_2d=True)
    if audio.shape[1] != len(_MIX):
        raise ValueError(f"expected {len(_MIX)} channels, got {audio.shape[1]}")

    stereo = np.zeros((audio.shape[0], 2), dtype=np.float64)
    for ch, (gain, pan) in enumerate(_MIX):
        # Constant-power pan — keeps the perceived level steady across the field.
        theta = (pan + 1.0) * 0.25 * np.pi
        stereo[:, 0] += audio[:, ch] * gain * np.cos(theta)
        stereo[:, 1] += audio[:, ch] * gain * np.sin(theta)

    peak = float(np.abs(stereo).max())
    if peak > 0.0:
        stereo *= 0.84 / peak  # leave ~1.5 dB of headroom
    return stereo.astype(np.float32), sr


def main() -> int:
    """Render every demo groove to a stereo WAV in ``audition/demo/``."""
    if not _KIT_XML.is_file():
        print(f"FATAL: DRSKit not found at {_KIT_XML}", file=sys.stderr)
        return 1

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    renderer = DrumGizmoRenderer()

    print("=" * 72)
    print("Audition demo — multi-genre render showcase (DrumGizmo, stereo)")
    print(f"  output: {_OUT_DIR}")
    print("=" * 72)

    with tempfile.TemporaryDirectory(prefix="audition_demo_") as tmp:
        tmp_dir = Path(tmp)
        for index, groove in enumerate(GROOVES, start=1):
            midi_path = tmp_dir / f"{groove.name}.mid"
            multimic_wav = tmp_dir / f"{groove.name}_8mic.wav"
            _build_midi(groove, midi_path)

            midi_len = mido.MidiFile(str(midi_path)).length
            renderer.render(
                kit_path=_KIT_XML,
                midimap_path=_MIDIMAP_XML,
                midi_path=midi_path,
                wav_path=multimic_wav,
                duration_s=midi_len + 5.0,  # tail for cymbal / ambience decay
                channel_map=DRSKIT_MULTITRACK8,
            )
            stereo, sr = _stereo_mix(multimic_wav)
            out_wav = _OUT_DIR / f"{index:02d}_{groove.name}_{groove.bpm}bpm.wav"
            sf.write(str(out_wav), stereo, sr, subtype="FLOAT")

            seconds = stereo.shape[0] / sr
            print(f"  [{index:2d}] {groove.name:16s} {groove.bpm:3d} bpm  "
                  f"{seconds:5.1f}s  ->  {out_wav.name}")

    print("=" * 72)
    print(f"OK — {len(GROOVES)} stereo demos rendered to {_OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
