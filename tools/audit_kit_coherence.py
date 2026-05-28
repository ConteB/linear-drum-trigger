#!/usr/bin/env python3
"""Per-kit end-to-end coherence probe (F0-T18 follow-up, CEO 2026-05-28).

Where ``audit_midi_coherence.py`` checks coverage *statically* (is the note in
the midimap XML?), this tool checks it *empirically*: it synthesises a probe
MIDI carrying exactly one hit per canonical articulation, runs the FULL pipeline
(canonicalize -> render -> target) through one kit, and verifies — per
articulation — that the rendered audio actually carries energy where the target
says an onset is. It catches the failure modes static analysis cannot:

* **PHANTOM** — the target has an onset (the canonical MIDI carries the note)
  but the rendered audio is SILENT there (the kit's midimap references a missing
  sample, or the SFZ has no region for that note). The Plan-A bug class, per
  articulation, per kit.
* **DROPPED** — neither audio nor target (canonicalization put the note in the
  ignored registry; should not happen for the active standards).
* **OK** — audio energy present AND target onset present.

Engine-aware: DrumGizmo kits must run on Linux (OrbStack); Sfizz kits on macOS.
Use ``--engine-filter`` to pick the host, mirroring ``mini_l3_runner.py``.

    # macOS:
    python tools/audit_kit_coherence.py --engine-filter sfizz
    # OrbStack:
    python tools/audit_kit_coherence.py --engine-filter drumgizmo

Spec: ``docs/methodology/F0-T18_MIDI_STANDARD_TRANSLATION_SPEC.md``.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import mido  # type: ignore[import-untyped]
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.gold.gold_writer import R_TARGET_HZ  # noqa: E402
from data_engineering.gold.midi_canonical import (  # noqa: E402
    load_source_standards,
)
from data_engineering.gold.orchestrate import (  # noqa: E402
    DEFAULT_BUS_MAPPING_PATH,
    build_gold_sample,
)
from data_engineering.gold.recipe import (  # noqa: E402
    AugmentationSpec,
    Engine,
    MicConfig,
    MidiJitter,
    MidiSource,
    Recipe,
    RenderSpec,
    Split,
    VelocityJitter,
)
from data_engineering.gold.target_builder import load_bus_mapping  # noqa: E402

#: Kits to probe, mirroring mini_l3_runner. (engine, label, kit_path).
KITS: list[tuple[str, str, str]] = [
    ("drumgizmo", "DRSKit", "vendor/drumgizmo/DRSKit/DRSKit_full.xml"),
    ("drumgizmo", "MuldjordKit", "vendor/drumgizmo/MuldjordKit3/MuldjordKit3.xml"),
    ("drumgizmo", "CrocellKit", "vendor/drumgizmo/CrocellKit/CrocellKit_full.xml"),
    ("drumgizmo", "Aasimonster", "vendor/drumgizmo/Aasimonster/Aasimonster.xml"),
    ("drumgizmo", "ShittyKit", "vendor/drumgizmo/ShittyKit/ShittyKit.xml"),
    ("sfizz", "BigRustyDrums", "vendor/sfz/big-rusty-drums/Programs/01-full.sfz"),
]

PROBE_DT_S = 0.5       # spacing between probe hits
PROBE_VELOCITY = 100
SAMPLE_RATE = 44100
ENERGY_SILENCE = 1e-4  # peak below this in the hit window = silent


def build_probe_midi(standard: str, out_path: Path) -> list[tuple[int, int, float]]:
    """Write a probe MIDI: one hit per source note of ``standard``.

    Returns a list of ``(source_note, bus_1based, time_s)`` for analysis.
    """
    std = load_source_standards()
    note_map = std.standards[standard]
    out = mido.MidiFile()
    track = mido.MidiTrack()
    out.tracks.append(track)
    # mido delta times are in ticks; default tempo 500000 us/beat,
    # ticks_per_beat 480 -> 1 beat = 0.5 s. Use a tick count for PROBE_DT_S.
    ticks_per_beat = out.ticks_per_beat
    dt_ticks = int(round(PROBE_DT_S * 2 * ticks_per_beat))  # 0.5 s @ 120 bpm
    # An onset's spacing from the next is (note duration) + (next note_on delta).
    # Split dt_ticks across the two so consecutive onsets land EXACTLY PROBE_DT_S
    # apart — otherwise the note_off delta would push each onset later than the
    # layout records, drifting audio/target windows out of alignment.
    note_ticks = dt_ticks // 2          # how long the note is held
    gap_ticks = dt_ticks - note_ticks   # silence until the next note_on
    layout: list[tuple[int, int, float]] = []
    t = 0.0
    # deterministic order by source note
    first = True
    for src_note in sorted(note_map):
        art = std.articulations[note_map[src_note]]
        delta = 0 if first else gap_ticks
        first = False
        track.append(mido.Message("note_on", note=src_note,
                                  velocity=PROBE_VELOCITY, time=delta, channel=9))
        track.append(mido.Message("note_off", note=src_note,
                                  velocity=0, time=note_ticks, channel=9))
        t += PROBE_DT_S
        layout.append((src_note, art.bus, t - PROBE_DT_S))
    out.save(str(out_path))
    return layout


def probe_kit(engine: str, label: str, kit_rel: str, standard: str,
              repo_root: Path) -> dict[str, object]:
    """Render the probe through one kit and analyse per-articulation coherence."""
    bus_mapping = load_bus_mapping(DEFAULT_BUS_MAPPING_PATH)
    std = load_source_standards()
    with tempfile.TemporaryDirectory(prefix="kit_probe_") as tmp:
        tmpd = Path(tmp)
        probe_midi = tmpd / "probe.mid"
        layout = build_probe_midi(standard, probe_midi)
        # Place the probe MIDI under the repo so the recipe's relative path resolves.
        rel_midi = probe_midi  # absolute; use midi_path_override

        if engine == "drumgizmo":
            eng = Engine.DRUMGIZMO
            mic = MicConfig.MULTITRACK_FULL
        else:
            eng = Engine.SFIZZ
            mic = MicConfig.SOLO_STEREO

        recipe = Recipe(
            recipe_id=f"PROBE-{label}",
            schema_version="1.0",
            split=Split.TRAIN,  # irrelevant for a coherence probe; must be a valid enum
            midi_source=MidiSource(
                dataset="MINI_L3", file=str(rel_midi),
                bus_mapping="midi_mapping_table.yaml@1.0", standard=standard,
            ),
            midi_jitter=MidiJitter(
                time_jitter_ms=(0.0, 0.0), flam_probability=0.0,
                velocity_jitter=VelocityJitter.NONE,
                component_drop_probability=0.0, seed=0,
            ),
            render=RenderSpec(
                engine=eng, kit=label, kit_path=kit_rel, mic_config=mic,
                sample_rate=44100,
            ),
            augmentation=AugmentationSpec(
                level=0, reverb_ir=None, mutilation={}, saboteur=None,
            ),
            target_frame_rate_hz=R_TARGET_HZ,
        )
        result = build_gold_sample(
            recipe, out_dir=tmpd / "out", bus_mapping=bus_mapping,
            repo_root=repo_root, midi_path_override=probe_midi,
        )
        # Load the written audio + target back.
        audio = np.fromfile(result.out_dir / f"{result.key}.audio.f16",
                            dtype=np.float16).astype(np.float32)
        audio = audio.reshape(result.n_mic, result.n_sample)
        target = np.fromfile(result.out_dir / f"{result.key}.target.f16",
                            dtype=np.float16).astype(np.float32)
        target = target.reshape(result.n_frame, 25)

        rows = []
        n_ok = n_phantom = 0
        # collapse layout by bus (multiple source notes can hit the same bus)
        for src_note, bus_1, t_s in layout:
            art_name = std.standards[standard][src_note]
            s0 = int(t_s * SAMPLE_RATE)
            s1 = min(result.n_sample, s0 + int(0.25 * SAMPLE_RATE))
            peak = float(np.abs(audio[:, s0:s1]).max()) if s1 > s0 else 0.0
            # target onset on this bus within the window
            f0 = int(t_s * (result.n_frame / (result.n_sample / SAMPLE_RATE)))
            f1 = min(result.n_frame, f0 + 12)
            onset_col = (bus_1 - 1) * 3
            tgt = float(target[f0:f1, onset_col].max()) if f1 > f0 else 0.0
            audio_on = peak >= ENERGY_SILENCE
            tgt_on = tgt > 0.5
            if audio_on and tgt_on:
                verdict = "OK"
                n_ok += 1
            elif tgt_on and not audio_on:
                verdict = "PHANTOM"
                n_phantom += 1
            elif audio_on and not tgt_on:
                verdict = "AUDIO_NO_TARGET"
            else:
                verdict = "DROPPED"
            rows.append({
                "src_note": src_note, "articulation": art_name, "bus": bus_1,
                "audio_peak": round(peak, 4), "target": round(tgt, 3),
                "verdict": verdict,
            })
        return {
            "kit": label, "engine": engine, "n_mic": result.n_mic,
            "n_ok": n_ok, "n_phantom": n_phantom, "rows": rows,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-kit end-to-end coherence probe")
    ap.add_argument("--standard", default="roland_td11")
    ap.add_argument("--engine-filter", default="all",
                    choices=("all", "drumgizmo", "sfizz"))
    ap.add_argument("--out", type=Path,
                    default=Path("docs/gates/F0-T18_KIT_COHERENCE"))
    args = ap.parse_args()

    kits = [k for k in KITS if args.engine_filter in ("all", k[0])]
    args.out.mkdir(parents=True, exist_ok=True)
    all_results = []
    overall_phantom = 0
    for engine, label, kit_rel in kits:
        kit_path = _REPO_ROOT / kit_rel
        if not kit_path.exists():
            print(f"[{label}] kit path missing ({kit_rel}) — skipped")
            continue
        print(f"\n=== {label} ({engine}) ===")
        try:
            res = probe_kit(engine, label, kit_rel, args.standard, _REPO_ROOT)
        except Exception as exc:  # noqa: BLE001 — report per-kit, keep going
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            all_results.append({"kit": label, "engine": engine, "error": str(exc)})
            continue
        for r in res["rows"]:
            flag = "" if r["verdict"] == "OK" else f"  <-- {r['verdict']}"
            print(f"  note {r['src_note']:>3} {r['articulation']:<13} bus{r['bus']} "
                  f"peak={r['audio_peak']:.4f} tgt={r['target']:.2f} "
                  f"{r['verdict']}{flag}")
        print(f"  → {res['n_ok']} OK, {res['n_phantom']} PHANTOM (n_mic={res['n_mic']})")
        overall_phantom += res["n_phantom"]
        all_results.append(res)

    out_json = args.out / f"kit_coherence_{args.engine_filter}.json"
    out_json.write_text(json.dumps(all_results, indent=2))
    print(f"\nwrote {out_json}")
    print(f"OVERALL: {overall_phantom} phantom-target articulations across "
          f"{len([r for r in all_results if 'rows' in r])} kits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
