#!/usr/bin/env python3
"""Local R&D Gold dataset — 200 grooves × 3 jitter variants × DrumGizmo+DRSKit.

Generated on Mac M5 (via OrbStack for DrumGizmo) **without any audio
augmentation** — used as a playground while we wait on the Azure A100 quota
ticket. Two downstream consumers:

1. **F0-T16-post R&D** — develop the audio-augmentation pipeline on real
   multi-mic Gold samples instead of synthetic fixtures.
2. **F0-T4b training R&D** — sweep TCN hyperparameters / debug the training
   loop before committing the A100 burn.

Pipeline reuses every locked F0 module:

* synthetic MIDI generator (6 style families, deterministic per index);
* :func:`evaluation.midi_augment.recipe_matrix.build_recipe_matrix_entries`
  for the ``M × (k+1) × E`` matrix with deterministic shuffle;
* :func:`evaluation.midi_augment.jitter.apply_midi_jitter` for the LOCKED
  F0-T15-pre voices on every variant ≥ 1;
* :func:`data_engineering.gold.orchestrate.build_gold_sample` for the
  render → audio.f16 + target.f16 + dna.json triple.

Output: ``data/gold/local_rnd/`` flat (one triple per recipe-matrix entry).

Run:
    python tools/generate_local_rnd_dataset.py             # full 200 × 3 = 600 sample
    python tools/generate_local_rnd_dataset.py --n 50      # smoke (50 × 3 = 150)
    python tools/generate_local_rnd_dataset.py --k 0       # baseline only (200 × 1)
    python tools/generate_local_rnd_dataset.py --skip-midi # reuse generated MIDIs

The DrumGizmo binary is provisioned on Linux (OrbStack ``ubuntu`` machine);
run this script *inside* OrbStack for the render stage. The MIDI synthesis +
jitter + writer side runs on macOS too — split steps with ``--midi-only``
and ``--render-only`` if you want to prepare on macOS and render on Linux.
"""
from __future__ import annotations

import argparse
import gc
import shutil
import sys
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path

import mido

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.gold.dna_trace import encode_barcode  # noqa: E402
from data_engineering.gold.orchestrate import (  # noqa: E402
    DEFAULT_BUS_MAPPING_PATH,
    GoldSampleResult,
    build_gold_sample,
    derive_barcode,
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
from data_engineering.midi_augment.jitter import apply_midi_jitter  # noqa: E402
from data_engineering.midi_augment.recipe_matrix import (  # noqa: E402
    RecipeMatrixEntry,
    build_recipe_matrix_entries,
)

# --- defaults ---------------------------------------------------------------

#: Default grooves count (CEO directive 2026-05-23).
_DEFAULT_N_GROOVES = 200
#: Jitter variants per MIDI — 2 jittered + 1 baseline = 3 total
#: (F0-T15-pre §5 LOCKED).
_DEFAULT_K_VARIANTS = 2
#: Run-level seed; identifies the dataset uniquely (replay-invariant).
_DEFAULT_MASTER_SEED = 20260523
#: Where the synthesised MIDIs live.
_DEFAULT_MIDI_DIR = _REPO_ROOT / "bronze" / "gmd" / "local_rnd"
#: Where the Gold output triples live.
_DEFAULT_GOLD_DIR = _REPO_ROOT / "data" / "gold" / "local_rnd"
#: Vendored DrumGizmo kit (single kit — DRSKit only for R&D speed).
_DRUMGIZMO_KIT = "vendor/drumgizmo/DRSKit/DRSKit_full.xml"

#: MIDI ticks per beat (matches F0-T2e).
_TICKS_PER_BEAT = 480

# GM drum notes (every one is in midi_mapping_table forward_gm_to_bus AND
# DRSKit Midimap_full.xml — voiced on the kit AND mapped to a bus).
_KICK, _SNARE = 36, 38
_HH_CLOSED, _HH_OPEN, _HH_PEDAL = 42, 46, 44
_LOW_TOM, _MID_TOM, _HIGH_TOM = 41, 45, 47
_FLOOR_TOM = 43
_RIDE, _RIDE_BELL = 51, 53
_CRASH, _SPLASH, _CHINA = 49, 55, 52


# ----------------------------------------------------------------------------
# Style families — six deterministic generators (chosen by groove_index % 6).
# ----------------------------------------------------------------------------

def _style_straight_rock(bars: int) -> list[tuple[int, int, int]]:
    """Kick on 1+3, snare on 2+4, eighths hi-hat. The diet of every drummer."""
    eighth = _TICKS_PER_BEAT // 2
    out: list[tuple[int, int, int]] = []
    for bar in range(bars):
        bt = bar * 4 * _TICKS_PER_BEAT
        out.append((bt + 0 * _TICKS_PER_BEAT, _KICK, 104))
        out.append((bt + 2 * _TICKS_PER_BEAT, _KICK, 96))
        out.append((bt + 1 * _TICKS_PER_BEAT, _SNARE, 100))
        out.append((bt + 3 * _TICKS_PER_BEAT, _SNARE, 100))
        for step in range(8):
            note = _HH_OPEN if step == 7 and bar == bars - 1 else _HH_CLOSED
            out.append((bt + step * eighth, note, 70 + (step % 3) * 8))
        if bar == 0:
            out.append((bt, _CRASH, 110))
    return out


def _style_funk_syncopated(bars: int) -> list[tuple[int, int, int]]:
    """Syncopated kick, ghost-note snare, sixteenth hi-hat with accents."""
    sixteenth = _TICKS_PER_BEAT // 4
    out: list[tuple[int, int, int]] = []
    for bar in range(bars):
        bt = bar * 4 * _TICKS_PER_BEAT
        # Syncopated kick: 1, 1-and, 3, 4-e.
        out.append((bt, _KICK, 100))
        out.append((bt + 1 * _TICKS_PER_BEAT + sixteenth * 2, _KICK, 88))
        out.append((bt + 2 * _TICKS_PER_BEAT, _KICK, 92))
        out.append((bt + 3 * _TICKS_PER_BEAT + sixteenth, _KICK, 80))
        # Snare on 2, 4 + ghost notes
        out.append((bt + 1 * _TICKS_PER_BEAT, _SNARE, 110))
        out.append((bt + 3 * _TICKS_PER_BEAT, _SNARE, 110))
        out.append((bt + 1 * _TICKS_PER_BEAT + sixteenth * 3, _SNARE, 32))  # ghost
        out.append((bt + 3 * _TICKS_PER_BEAT + sixteenth * 3, _SNARE, 30))  # ghost
        # Sixteenth hi-hat with accents on downbeats
        for step in range(16):
            vel = 88 if step % 4 == 0 else 60
            note = _HH_OPEN if step == 15 and bar == bars - 1 else _HH_CLOSED
            out.append((bt + step * sixteenth, note, vel))
    return out


def _style_jazz_brush(bars: int) -> list[tuple[int, int, int]]:
    """Ride pattern, soft kick, brush-friendly accents."""
    eighth = _TICKS_PER_BEAT // 2
    triplet = _TICKS_PER_BEAT // 3
    out: list[tuple[int, int, int]] = []
    for bar in range(bars):
        bt = bar * 4 * _TICKS_PER_BEAT
        # Soft kick on 1 + 3.
        out.append((bt + 0, _KICK, 70))
        out.append((bt + 2 * _TICKS_PER_BEAT, _KICK, 68))
        # Jazz ride: 1, 2-and, 3, 4-and (the "spang-a-lang").
        for beat in (0, 2):
            out.append((bt + beat * _TICKS_PER_BEAT, _RIDE, 80))
            out.append((bt + beat * _TICKS_PER_BEAT + eighth, _RIDE, 60))
            out.append((bt + beat * _TICKS_PER_BEAT + 2 * triplet, _RIDE, 70))
        for beat in (1, 3):
            out.append((bt + beat * _TICKS_PER_BEAT, _RIDE, 78))
            out.append((bt + beat * _TICKS_PER_BEAT + eighth, _RIDE, 58))
        # Snare brush on 2 and 4 (soft).
        out.append((bt + 1 * _TICKS_PER_BEAT, _SNARE, 50))
        out.append((bt + 3 * _TICKS_PER_BEAT, _SNARE, 50))
        # Hi-hat pedal on every beat (foot ostinato).
        for beat in range(4):
            out.append((bt + beat * _TICKS_PER_BEAT, _HH_PEDAL, 45))
    return out


def _style_halftime_hiphop(bars: int) -> list[tuple[int, int, int]]:
    """Kick 1, snare 3, dense hi-hat — modern half-time."""
    sixteenth = _TICKS_PER_BEAT // 4
    out: list[tuple[int, int, int]] = []
    for bar in range(bars):
        bt = bar * 4 * _TICKS_PER_BEAT
        out.append((bt, _KICK, 115))
        out.append((bt + 2 * _TICKS_PER_BEAT, _SNARE, 112))
        # Double kick on beat 3-and (typical hip-hop ghost kick)
        out.append((bt + 2 * _TICKS_PER_BEAT + sixteenth * 2, _KICK, 75))
        # Dense hi-hat — sixteenths with rolls
        for step in range(16):
            # Occasional roll: triplet 16ths on beats 4 of bar 2
            vel = 85 if step % 4 == 0 else 55
            out.append((bt + step * sixteenth, _HH_CLOSED, vel))
    return out


def _style_latin(bars: int) -> list[tuple[int, int, int]]:
    """Cuban-clave-inspired pattern with ride bell."""
    sixteenth = _TICKS_PER_BEAT // 4
    out: list[tuple[int, int, int]] = []
    for bar in range(bars):
        bt = bar * 4 * _TICKS_PER_BEAT
        # 3-2 son clave (in sixteenths): 1 . . . 1 . . 1 . . 1 . . 1 . .
        clave = [0, 4, 6, 10, 12, 14]
        for step in clave[:3]:
            out.append((bt + step * sixteenth, _RIDE_BELL, 90))
        for step in clave[3:]:
            out.append((bt + step * sixteenth, _SNARE, 92))
        # Kick on 1 and 3-and.
        out.append((bt, _KICK, 100))
        out.append((bt + 2 * _TICKS_PER_BEAT + sixteenth * 2, _KICK, 92))
        # Eighth-note hi-hat under everything.
        for step in range(8):
            out.append((bt + step * (_TICKS_PER_BEAT // 2), _HH_CLOSED, 60))
    return out


def _style_double_bass_metal(bars: int) -> list[tuple[int, int, int]]:
    """Double-pedal kick on every eighth, snare on 2+4, crash + china color."""
    eighth = _TICKS_PER_BEAT // 2
    sixteenth = _TICKS_PER_BEAT // 4
    out: list[tuple[int, int, int]] = []
    for bar in range(bars):
        bt = bar * 4 * _TICKS_PER_BEAT
        # Double-pedal kicks on every eighth.
        for step in range(8):
            out.append((bt + step * eighth, _KICK, 90 + (step % 2) * 10))
        # Snare on 2 + 4.
        out.append((bt + 1 * _TICKS_PER_BEAT, _SNARE, 115))
        out.append((bt + 3 * _TICKS_PER_BEAT, _SNARE, 115))
        # Crash on 1 of first bar; china at fills.
        if bar == 0:
            out.append((bt, _CRASH, 118))
        elif bar == bars - 1:
            # Tom fill on last beat
            for j, note in enumerate((_HIGH_TOM, _MID_TOM, _LOW_TOM, _FLOOR_TOM)):
                out.append((bt + 3 * _TICKS_PER_BEAT + j * sixteenth, note, 100))
        # Hi-hat splash accents on offbeats
        for step in range(4):
            out.append((bt + step * _TICKS_PER_BEAT + eighth, _HH_CLOSED, 65))
    return out


_STYLES = (
    ("rock", _style_straight_rock, (90, 130)),
    ("funk", _style_funk_syncopated, (95, 115)),
    ("jazz", _style_jazz_brush, (110, 160)),
    ("hiphop", _style_halftime_hiphop, (80, 100)),
    ("latin", _style_latin, (95, 135)),
    ("metal", _style_double_bass_metal, (120, 160)),
)


def _groove_for_index(index: int) -> tuple[str, int, list[tuple[int, int, int]]]:
    """Deterministic groove from ``index``: (style_name, bpm, event list)."""
    style_idx = index % len(_STYLES)
    style_name, generator, (bpm_lo, bpm_hi) = _STYLES[style_idx]
    # Spread BPM uniformly across the style range as ``index`` grows.
    bpm_steps = max(1, bpm_hi - bpm_lo)
    bpm = bpm_lo + ((index // len(_STYLES)) % bpm_steps)
    # 2 or 3 bars — alternating per family for variety.
    bars = 2 + ((index // len(_STYLES)) % 2)
    events = generator(bars)
    return style_name, bpm, events


_NOTE_TICKS = 60


def _write_midi(index: int, path: Path) -> tuple[str, int]:
    """Synthesise one groove MIDI; return ``(style_name, bpm)`` for the log."""
    style_name, bpm, events = _groove_for_index(index)
    midi = mido.MidiFile(ticks_per_beat=_TICKS_PER_BEAT)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

    timed: list[tuple[int, int, mido.Message]] = []
    for abs_tick, note, velocity in events:
        timed.append(
            (abs_tick, 1, mido.Message("note_on", note=note, velocity=velocity))
        )
        timed.append(
            (abs_tick + _NOTE_TICKS, 0, mido.Message("note_off", note=note, velocity=64))
        )
    timed.sort(key=lambda item: (item[0], item[1]))

    prev = 0
    for abs_tick, _, message in timed:
        track.append(message.copy(time=abs_tick - prev))
        prev = abs_tick
    track.append(mido.MetaMessage("end_of_track", time=0))

    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(str(path))
    return style_name, bpm


# ----------------------------------------------------------------------------
# Recipe synthesis (in-memory, no YAML)
# ----------------------------------------------------------------------------


def _recipe_from_entry(
    entry: RecipeMatrixEntry, midi_relpath: str
) -> Recipe:
    """Build a :class:`Recipe` directly — no YAML round-trip."""
    return Recipe(
        recipe_id=f"R-LOCAL-{entry.source_midi_id}-V{entry.variant_idx}",
        schema_version="1.0",
        split=Split.TRAIN,
        midi_source=MidiSource(
            dataset="LOCAL_RND",
            file=midi_relpath,
            bus_mapping="midi_mapping_table.yaml@1.0",
        ),
        midi_jitter=MidiJitter(
            # The Recipe's MidiJitter block is informative for replay; the
            # jitter is already applied in-memory via apply_midi_jitter
            # before the orchestrator sees the MIDI. We record the variant
            # parameters in the dna.json via the recipe metadata.
            time_jitter_ms=(0.0, 0.0) if entry.variant_idx == 0 else (2.0, 15.0),
            flam_probability=0.0 if entry.variant_idx == 0 else 0.05,
            velocity_jitter=(
                VelocityJitter.NONE if entry.variant_idx == 0 else VelocityJitter.BOTH
            ),
            component_drop_probability=0.0 if entry.variant_idx == 0 else 0.10,
            seed=entry.jitter_seed,
            # Propagate the variant index so the barcode's `jittervar`
            # segment (`J{idx:02d}`) actually distinguishes variant 1 from
            # variant 2 — otherwise both jittered branches collide on
            # `J00` and the second one overwrites the first on disk.
            variant_idx=entry.variant_idx,
        ),
        render=RenderSpec(
            engine=Engine.DRUMGIZMO if entry.engine == "drumgizmo" else Engine.SFIZZ,
            kit=entry.kit,
            kit_path=_DRUMGIZMO_KIT,
            sample_rate=44100,
            mic_config=MicConfig.MULTITRACK_FULL,
        ),
        augmentation=AugmentationSpec(
            level=1,                  # raw (no audio aug — F0-T15-post out of scope)
            reverb_ir=None,
            mutilation={},
            saboteur=None,
        ),
        target_frame_rate_hz=344.53125,
    )


# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------


def _generate_midis(n: int, midi_dir: Path) -> list[Path]:
    """Write the N MIDIs; return their paths sorted by index."""
    paths: list[Path] = []
    midi_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        path = midi_dir / f"groove_{i:04d}.mid"
        style_name, bpm = _write_midi(i, path)
        paths.append(path)
    return paths


def _midi_relpath(midi_path: Path) -> str:
    """Repo-relative path used as the recipe ``midi_source.file``."""
    return str(midi_path.relative_to(_REPO_ROOT))


def _expected_dna_path(recipe: object, out_dir: Path) -> Path:
    """Predict the on-disk ``.dna.json`` path that ``build_gold_sample`` would
    write for ``recipe`` — used for idempotent ``--skip-existing`` resume."""
    barcode = derive_barcode(recipe)  # type: ignore[arg-type]
    key = encode_barcode(barcode)
    return out_dir / f"{key}.dna.json"


def _render_entries(
    entries: Iterable[RecipeMatrixEntry],
    midi_paths: dict[str, Path],
    out_dir: Path,
    *,
    bus_mapping: object,
    log_every: int = 20,
    skip_existing: bool = False,
    gc_every: int = 10,
) -> tuple[int, int, int, float]:
    """Render every recipe-matrix entry.

    Returns ``(generated, skipped, failed, elapsed_s)``.

    When ``skip_existing=True`` an entry whose target ``.dna.json`` already
    lives under ``out_dir`` is left untouched (idempotent resume across
    process restarts — necessary on OOM-prone hosts).

    ``gc.collect()`` is invoked every ``gc_every`` samples to keep RSS
    bounded — the multi-mic Gold tensor + DrumGizmo WAVs make Python's
    incremental GC fall behind on small-memory hosts.
    """
    generated = 0
    skipped = 0
    failed = 0
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="local_rnd_jitter_") as tmp_root:
        tmp_dir = Path(tmp_root)
        total = len(list(entries)) if isinstance(entries, list) else None
        # Re-materialise the list since we may have consumed the iterator above.
        entry_list = list(entries) if not isinstance(entries, list) else entries
        if total is None:
            total = len(entry_list)
        for i, entry in enumerate(entry_list):
            src_midi = midi_paths[entry.source_midi_id]
            recipe = _recipe_from_entry(entry, _midi_relpath(src_midi))

            if skip_existing and _expected_dna_path(recipe, out_dir).exists():
                skipped += 1
                continue

            # Apply MIDI jitter in-memory; orchestrate.py reads from disk so
            # we write a transient jittered MIDI per entry.
            source_midi = mido.MidiFile(str(src_midi))
            jittered = apply_midi_jitter(
                source_midi,
                variant_idx=entry.variant_idx,
                master_seed=_DEFAULT_MASTER_SEED,
                source_midi_id=entry.source_midi_id,
            )
            transient_midi = tmp_dir / f"{entry.source_midi_id}_v{entry.variant_idx}.mid"
            jittered.save(str(transient_midi))

            try:
                _: GoldSampleResult = build_gold_sample(
                    recipe,
                    out_dir=out_dir,
                    bus_mapping=bus_mapping,
                    midi_path_override=transient_midi,
                )
                generated += 1
            except Exception as exc:  # noqa: BLE001 — log + continue
                failed += 1
                print(
                    f"  ✗ [{i + 1}/{total}] {entry.source_midi_id} v{entry.variant_idx} "
                    f"{entry.engine}: {type(exc).__name__}: {exc}",
                    flush=True,
                )

            # Drop residual references from the loop body, then let the
            # garbage collector reclaim the multi-mic audio + WAV buffers.
            del source_midi, jittered
            try:
                transient_midi.unlink()
            except OSError:
                pass
            if (i + 1) % gc_every == 0:
                gc.collect()
                continue

            if (i + 1) % log_every == 0:
                elapsed = time.monotonic() - started
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (total - (i + 1)) / rate if rate > 0 else 0
                print(
                    f"  [{i + 1}/{total}] OK · {rate:.2f} sample/s · "
                    f"ETA {eta / 60:.1f} min",
                    flush=True,
                )
    return generated, skipped, failed, time.monotonic() - started


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local R&D Gold dataset generator (CEO directive 2026-05-23)"
    )
    parser.add_argument(
        "--n", type=int, default=_DEFAULT_N_GROOVES,
        help=f"number of source grooves (default {_DEFAULT_N_GROOVES})",
    )
    parser.add_argument(
        "--k", type=int, default=_DEFAULT_K_VARIANTS,
        help=f"jitter variants per groove — k augmented + 1 baseline "
              f"(default {_DEFAULT_K_VARIANTS})",
    )
    parser.add_argument(
        "--seed", type=int, default=_DEFAULT_MASTER_SEED,
        help=f"master seed for recipe matrix + jitter (default {_DEFAULT_MASTER_SEED})",
    )
    parser.add_argument(
        "--midi-dir", type=Path, default=_DEFAULT_MIDI_DIR,
        help=f"MIDI output directory (default {_DEFAULT_MIDI_DIR})",
    )
    parser.add_argument(
        "--out", type=Path, default=_DEFAULT_GOLD_DIR,
        help=f"Gold output directory (default {_DEFAULT_GOLD_DIR})",
    )
    parser.add_argument(
        "--midi-only", action="store_true",
        help="generate only the MIDIs, skip rendering (for cross-platform splitting)",
    )
    parser.add_argument(
        "--render-only", action="store_true",
        help="skip MIDI generation, render only (MIDIs must exist already)",
    )
    parser.add_argument(
        "--clean-out", action="store_true",
        help="wipe the Gold output dir before rendering",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="skip recipe entries whose .dna.json already lives in --out "
              "(idempotent resume — necessary on OOM-prone hosts where the "
              "process is restarted after a kill)",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=0,
        help="if > 0, render only the next N entries (after honouring "
              "--skip-existing) and exit. Lets a wrapper script chunk the "
              "workload across multiple process invocations.",
    )
    parser.add_argument(
        "--source-mix", type=Path, default=None,
        help="path to a midi_synth mix_dataset directory (containing "
              "manifest.json). If set, the built-in 6 synthetic styles are "
              "ignored and the MIDIs from the mix are consumed instead. "
              "--n is also ignored (the manifest dictates the count).",
    )
    return parser.parse_args()


def _load_mix_midi_paths(mix_dir: Path) -> dict[str, Path]:
    """Read ``manifest.json`` from a midi_synth mix_dataset directory and
    return ``{midi_id: midi_path}`` with stable, jitter-seed-friendly IDs.

    The MIDI id has the shape ``mix_{order:04d}_{source}`` where ``source`` is
    one of ``gmd|rare|chaos`` — this preserves the source provenance in the
    recipe matrix barcode without leaking the full GMD path.
    """
    import json

    manifest_path = mix_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"mix manifest not found: {manifest_path}")
    data = json.loads(manifest_path.read_text())
    out: dict[str, Path] = {}
    mix_root = mix_dir.resolve()
    for entry in data["entries"]:
        midi_id = f"mix_{entry['order_idx']:04d}_{entry['source']}"
        out[midi_id] = (mix_root / entry["rel_path"]).resolve()
    return out


def main() -> int:
    args = _parse_args()

    if args.midi_only and args.render_only:
        print("FATAL: --midi-only and --render-only are mutually exclusive",
              file=sys.stderr)
        return 2
    if args.source_mix and (args.midi_only or args.render_only):
        print("FATAL: --source-mix is incompatible with --midi-only/--render-only",
              file=sys.stderr)
        return 2

    using_mix = args.source_mix is not None
    print("=" * 72)
    print("Local R&D dataset generator — CEO directive 2026-05-23")
    if using_mix:
        print(f"  source mix:    {args.source_mix}")
    else:
        print(f"  n grooves:     {args.n}")
    print(f"  k variants:    {args.k}")
    print(f"  master_seed:   {args.seed}")
    if not using_mix:
        print(f"  MIDI dir:      {args.midi_dir}")
    print(f"  Gold output:   {args.out}")
    print("=" * 72)

    # --- MIDI generation / loading ---
    midi_id_to_path: dict[str, Path]
    if using_mix:
        midi_id_to_path = _load_mix_midi_paths(args.source_mix)
        n_sources = len(midi_id_to_path)
        print(f"[1/2] mix dataset: {n_sources} MIDIs from {args.source_mix}")
        # Audit: show the source distribution.
        source_counts: dict[str, int] = {}
        for midi_id in midi_id_to_path:
            source = midi_id.rsplit("_", 1)[-1]
            source_counts[source] = source_counts.get(source, 0) + 1
        print("       source mix: " + ", ".join(
            f"{k}={v}" for k, v in sorted(source_counts.items())))
    elif args.render_only:
        midi_paths = sorted(args.midi_dir.glob("groove_*.mid"))
        if not midi_paths:
            print(f"FATAL: --render-only but no MIDIs in {args.midi_dir}",
                  file=sys.stderr)
            return 1
        print(f"[1/2] reusing {len(midi_paths)} existing MIDIs in {args.midi_dir}")
        midi_id_to_path = {
            f"groove_{i:04d}": p for i, p in enumerate(sorted(midi_paths))
        }
    else:
        print(f"[1/2] synthesising {args.n} MIDIs in {args.midi_dir} ...")
        t0 = time.monotonic()
        midi_paths = _generate_midis(args.n, args.midi_dir)
        print(f"       wrote {len(midi_paths)} MIDIs in {time.monotonic() - t0:.1f}s")
        # Audit: show the style distribution.
        styles: dict[str, int] = {}
        for i in range(args.n):
            style_name, _bpm, _events = _groove_for_index(i)
            styles[style_name] = styles.get(style_name, 0) + 1
        print("       style mix: " + ", ".join(
            f"{k}={v}" for k, v in sorted(styles.items())))
        midi_id_to_path = {
            f"groove_{i:04d}": p for i, p in enumerate(sorted(midi_paths))
        }

    if args.midi_only:
        print("=" * 72)
        print("OK — MIDIs only (--midi-only). Run --render-only on Linux to finish.")
        return 0

    # --- Recipe matrix ---
    n_sources = len(midi_id_to_path)
    entries = build_recipe_matrix_entries(
        source_midi_ids=sorted(midi_id_to_path.keys()),
        engines_kits=[("drumgizmo", "DRSKit")],
        k_variants=args.k,
        master_seed=args.seed,
    )
    print(f"[2/2] recipe matrix: {len(entries)} entries "
          f"(M={n_sources} × (k+1)={args.k + 1} × E=1)")

    # --- Render ---
    if args.clean_out and args.out.exists():
        print(f"       wiping existing {args.out}")
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True, exist_ok=True)

    bus_mapping = load_bus_mapping(DEFAULT_BUS_MAPPING_PATH)

    # Apply --chunk-size after --skip-existing filtering — chunk only the
    # entries that would actually be rendered this invocation.
    if args.chunk_size > 0:
        if args.skip_existing:
            entries = [
                e for e in entries
                if not _expected_dna_path(
                    _recipe_from_entry(e, _midi_relpath(midi_id_to_path[e.source_midi_id])),
                    args.out,
                ).exists()
            ]
        entries = entries[: args.chunk_size]
        print(f"       chunk: rendering {len(entries)} entries this invocation")
    elif args.skip_existing:
        print(f"       --skip-existing: scanning {len(entries)} entries for prior output")

    print(f"       rendering {len(entries)} sample(s) with DrumGizmo / DRSKit ...")
    generated, skipped, failed, elapsed = _render_entries(
        entries, midi_id_to_path, args.out,
        bus_mapping=bus_mapping,
        skip_existing=args.skip_existing and args.chunk_size == 0,
    )

    print("=" * 72)
    print(f"DONE — {generated} generated, {skipped} skipped, {failed} failed, "
          f"elapsed {elapsed / 60:.1f} min")
    if generated and elapsed > 0:
        print(f"        rate ≈ {generated / elapsed:.2f} sample/s")
    print(f"        output: {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
