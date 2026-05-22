#!/usr/bin/env python3
"""F0-T2e — generate the mini-batch fixtures: synthetic MIDI + recipes.

The F0 mini-batch is a *pipeline smoke test*, not the production Gold render
(that is F2-T1, on Azure, from the real Groove MIDI Dataset). The real GMD
Bronze layer is not provisioned in F0, so this script synthesises a small set
of deterministic multi-bus drum grooves with ``mido`` — the same approach the
F0-T2b/c acceptance oracles already use for their probe MIDIs — and emits one
recipe per groove.

Outputs (committed, tiny — regenerable by re-running this script):

* ``bronze/gmd/mini/groove_NN.mid`` — synthetic grooves;
* ``recipes/mini_batch/R-MINI-NN-<engine>.yaml`` — one recipe each.

Half the recipes drive Sfizz (clean stem), half DrumGizmo (multi-mic bleed).

Run:  ``python tools/gen_mini_batch_fixtures.py``
"""
from __future__ import annotations

from pathlib import Path

import mido

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MIDI_DIR = _REPO_ROOT / "bronze" / "gmd" / "mini"
_RECIPE_DIR = _REPO_ROOT / "recipes" / "mini_batch"

#: Number of grooves / recipes in the mini-batch (F0-T2e — "~10-20 scenari").
N_GROOVES = 12
#: MIDI resolution; a quarter note is this many ticks.
_TICKS_PER_BEAT = 480

# GM drum notes used by the grooves — every one is in both midi_mapping_table
# forward_gm_to_bus AND DRSKit Midimap_full.xml, so it both maps to a bus and
# voices on the kit.
_KICK, _SNARE = 36, 38
_HH_CLOSED, _HH_OPEN = 42, 46
_TOM, _FLOOR, _RIDE, _CRASH = 47, 41, 51, 49

# Vendored render assets (vendor/README.md).
_SFIZZ_KIT = "vendor/sfz/frankensnare/Programs/03-10x6ash.sfz"
_DRUMGIZMO_KIT = "vendor/drumgizmo/DRSKit/DRSKit_full.xml"


def _groove_events(index: int) -> list[tuple[int, int, int]]:
    """Return ``(abs_tick, note, velocity)`` events for groove ``index``.

    Deterministic in ``index``: tempo, bar count and fill content all derive
    from it, so the mini-batch is fully reproducible.
    """
    bars = 2 + (index % 2)  # 2 or 3 bars
    eighth = _TICKS_PER_BEAT // 2
    events: list[tuple[int, int, int]] = []

    for bar in range(bars):
        bar_tick = bar * 4 * _TICKS_PER_BEAT
        # Backbone: kick on beats 1 & 3, snare on beats 2 & 4.
        events.append((bar_tick + 0 * _TICKS_PER_BEAT, _KICK, 104))
        events.append((bar_tick + 2 * _TICKS_PER_BEAT, _KICK, 96))
        events.append((bar_tick + 1 * _TICKS_PER_BEAT, _SNARE, 100))
        events.append((bar_tick + 3 * _TICKS_PER_BEAT, _SNARE, 100))
        # Hi-hat on every eighth; an open hat closes each bar.
        for step in range(8):
            note = _HH_OPEN if step == 7 else _HH_CLOSED
            events.append((bar_tick + step * eighth, note, 72 + (step % 3) * 8))
        # A crash opens groove; the last bar carries a small fill.
        if bar == 0:
            events.append((bar_tick, _CRASH, 110))
        if bar == bars - 1:
            for beat, note in ((1, _TOM), (2, _FLOOR), (3, _RIDE)):
                if (index + beat) % 2 == 0:
                    events.append((bar_tick + beat * _TICKS_PER_BEAT + eighth, note, 88))

    return sorted(events)


#: Note duration, in ticks — every drum hit is a short fixed-length note.
_NOTE_TICKS = 60


def _write_midi(index: int, path: Path) -> None:
    """Synthesise one groove MIDI at a groove-specific tempo."""
    midi = mido.MidiFile(ticks_per_beat=_TICKS_PER_BEAT)
    track = mido.MidiTrack()
    midi.tracks.append(track)

    bpm = 90 + index * 8
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

    # Build every note_on / note_off as an absolute-tick message, then sort:
    # emitting deltas from a sorted stream keeps them all non-negative even
    # when several hits land on the same tick.
    timed: list[tuple[int, int, mido.Message]] = []
    for abs_tick, note, velocity in _groove_events(index):
        # (tick, kind) — kind 0 = note_off sorts before kind 1 = note_on.
        timed.append(
            (abs_tick, 1, mido.Message("note_on", note=note, velocity=velocity))
        )
        timed.append(
            (abs_tick + _NOTE_TICKS, 0, mido.Message("note_off", note=note, velocity=64))
        )
    timed.sort(key=lambda item: (item[0], item[1]))

    prev_tick = 0
    for abs_tick, _, message in timed:
        track.append(message.copy(time=abs_tick - prev_tick))
        prev_tick = abs_tick
    track.append(mido.MetaMessage("end_of_track", time=0))

    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(str(path))


def _recipe_yaml(index: int, engine: str) -> str:
    """Render the recipe YAML document for groove ``index`` (F0-T2a §1.2)."""
    if engine == "sfizz":
        kit, kit_path, mic = "Frankensnare", _SFIZZ_KIT, "solo_stereo"
    else:
        kit, kit_path, mic = "DRSKit", _DRUMGIZMO_KIT, "multitrack_full"
    return (
        f"# F0-T2e mini-batch — synthetic smoke recipe (generated).\n"
        f"recipe_id: R-MINI-{index:02d}-{engine.upper()}\n"
        f'schema_version: "1.0"\n'
        f"split: train\n"
        f"midi_source:\n"
        f"  dataset: GMD\n"
        f"  file: bronze/gmd/mini/groove_{index:02d}.mid\n"
        f"  bus_mapping: midi_mapping_table.yaml@1.0\n"
        f"midi_jitter:\n"
        f"  time_jitter_ms: [0, 0]\n"
        f"  flam_probability: 0.0\n"
        f"  velocity_jitter: none\n"
        f"  component_drop_probability: 0.0\n"
        f"  seed: {1000 + index}\n"
        f"render:\n"
        f"  engine: {engine}\n"
        f"  kit: {kit}\n"
        f"  kit_path: {kit_path}\n"
        f"  sample_rate: 44100\n"
        f"  mic_config: {mic}\n"
        f"augmentation:\n"
        f"  level: 1\n"
        f"  reverb_ir: null\n"
        f"  mutilation: {{}}\n"
        f"  saboteur: null\n"
        f"output:\n"
        f"  target_frame_rate_hz: 344.53125\n"
    )


def main() -> None:
    """Generate every mini-batch MIDI and recipe."""
    _MIDI_DIR.mkdir(parents=True, exist_ok=True)
    _RECIPE_DIR.mkdir(parents=True, exist_ok=True)

    for index in range(N_GROOVES):
        engine = "drumgizmo" if index % 2 == 0 else "sfizz"
        midi_path = _MIDI_DIR / f"groove_{index:02d}.mid"
        recipe_path = _RECIPE_DIR / f"R-MINI-{index:02d}-{engine.upper()}.yaml"
        _write_midi(index, midi_path)
        recipe_path.write_text(_recipe_yaml(index, engine), encoding="utf-8")
        print(f"  groove_{index:02d}  {engine:9s}  {midi_path.name}  +  {recipe_path.name}")

    print(f"generated {N_GROOVES} grooves + recipes")
    print(f"  MIDI:    {_MIDI_DIR.relative_to(_REPO_ROOT)}/")
    print(f"  recipes: {_RECIPE_DIR.relative_to(_REPO_ROOT)}/")


if __name__ == "__main__":
    main()
