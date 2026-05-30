#!/usr/bin/env python3
"""F2-T1 / T1-prep-A — generate the full recipe matrix for the Gold render.

Enumerates the cartesian product of:

* every source MIDI under ``--midi-source-dir`` (recursively);
* every ``(engine, kit)`` pair of the F0-T1b roster — split kit-wise:
  ``train`` = 8 kits, ``val`` = 2 kits ("vergini" — never seen at training);
* ``k_variants + 1`` jitter branches (variant 0 = baseline, 1..k = jittered)
  — Decision Lock CEO 2026-05-23, F0-T15-pre §5 / DOSSIER §3.1.

The shuffle is deterministic (Fisher-Yates anchored by ``--master-seed``); the
emitted ``manifest.json`` carries the seed so the ordering replays bit-per-bit
in the F0-T5 sharding stage.

Run modes
---------

``--smoke`` runs the builder on a tiny subset (1 MIDI, 2 kits, k=1) for a
sanity check on the local mini-batch. Always exercises the full code path
so a smoke-green builder ratifies the production-shape output.

Examples
--------

* Smoke on the mini-batch::

    python tools/build_recipe_matrix.py \\
        --midi-source-dir bronze/gmd/mini \\
        --output-dir recipes/f2-t1-smoke \\
        --master-seed 4242 \\
        --smoke

* Full F2-T1 matrix (on the VM, after the GMD Bronze layer is provisioned)::

    python tools/build_recipe_matrix.py \\
        --midi-source-dir bronze/gmd/full \\
        --output-dir recipes/f2-t1 \\
        --master-seed <run-seed> \\
        --k-variants 2
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.midi_augment import (  # noqa: E402  # type: ignore[import-not-found]
    RecipeMatrixEntry,
    build_recipe_matrix_entries,
)

# ---------------------------------------------------------------------------
# Roster F0-T1b (Decision Lock CEO 2026-05-20, amendment 2026-05-23) —
# 8 train kits + 2 val kits "vergini" (DOSSIER §10.2 Opzione B).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KitEntry:
    """Roster entry for a render kit."""

    engine: str  # "sfizz" | "drumgizmo"
    kit: str  # human-readable kit name (used in recipe + barcode salt)
    kit_path: str  # repo-relative path to the SFZ/DGZ kit entry file
    mic_config: str  # "solo_stereo" | "multitrack_full" | ...


_DGZ = "drumgizmo"
_SFZ = "sfizz"
_DGZ_MIC = "multitrack_full"
_SFZ_MIC = "solo_stereo"


_TRAIN_KITS: tuple[KitEntry, ...] = (
    KitEntry(_DGZ, "DRSKit",
             "vendor/drumgizmo/DRSKit/DRSKit_full.xml", _DGZ_MIC),
    KitEntry(_DGZ, "CrocellKit",
             "vendor/drumgizmo/CrocellKit/CrocellKit_full.xml", _DGZ_MIC),
    KitEntry(_DGZ, "MuldjordKit3",
             "vendor/drumgizmo/MuldjordKit3/MuldjordKit3_full.xml", _DGZ_MIC),
    KitEntry(_DGZ, "Aasimonster",
             "vendor/drumgizmo/Aasimonster/Aasimonster_full.xml", _DGZ_MIC),
    KitEntry(_SFZ, "Frankensnare",
             "vendor/sfz/frankensnare/Programs/03-10x6ash.sfz", _SFZ_MIC),
    KitEntry(_SFZ, "UnrulyDrums",
             "vendor/sfz/unruly-drums/Programs/03-kit-complete.sfz", _SFZ_MIC),
    KitEntry(_SFZ, "BigRustyDrums",
             "vendor/sfz/big-rusty-drums/Programs/01-full.sfz", _SFZ_MIC),
    # VSCO-2 CE — percussioni accessorie (DOSSIER §3.4 Stealth Mix Saboteurs);
    # less drum-kit variety, but widens the transient-diversity distribution.
    KitEntry(_SFZ, "VSCO2CE",
             "vendor/sfz/vsco-2-ce/Programs/percussion.sfz", _SFZ_MIC),
)


_VAL_KITS: tuple[KitEntry, ...] = (
    KitEntry(_DGZ, "ShittyKit",
             "vendor/drumgizmo/ShittyKit/ShittyKit_full.xml", _DGZ_MIC),
    KitEntry(_SFZ, "SwirlyDrums",
             "vendor/sfz/swirly-drums/Programs/01-full.sfz", _SFZ_MIC),
)

#: Smoke subset — used by ``--smoke``. One SFZ kit + one DGZ kit covers both
#: render engines without hitting the manifest-only kits (which require Blob
#: provisioning on the VM).
_SMOKE_TRAIN_KITS: tuple[KitEntry, ...] = (_TRAIN_KITS[0], _TRAIN_KITS[4])  # DRSKit + Frankensnare
_SMOKE_VAL_KITS: tuple[KitEntry, ...] = ()


# ---------------------------------------------------------------------------
# Jitter parameters (F0-T15-pre LOCKED) — projected into the recipe schema.
# ---------------------------------------------------------------------------


def _midi_jitter_block(*, variant_idx: int, seed: int) -> dict[str, object]:
    """Build the ``midi_jitter`` YAML block for a given variant.

    Variant 0 (baseline) carries zeros so the legacy parser still treats it as
    identity; the jittered branches carry the LOCKED parameter envelopes —
    the actual draws happen at render time via :mod:`data_engineering.midi_augment.jitter`,
    but the recipe records them for auditing.
    """
    if variant_idx == 0:
        return {
            "time_jitter_ms": [0.0, 0.0],
            "flam_probability": 0.0,
            "velocity_jitter": "none",
            "component_drop_probability": 0.0,
            "seed": seed,
            "variant_idx": 0,
        }
    return {
        "time_jitter_ms": [0.0, 5.0],  # symmetric clip ±5 ms (F0-T15-pre §4.1)
        "flam_probability": 0.05,
        "velocity_jitter": "both",  # gauss + ghost + gain
        "component_drop_probability": 0.10,
        "seed": seed,
        "variant_idx": variant_idx,
    }


# ---------------------------------------------------------------------------
# Recipe YAML emission
# ---------------------------------------------------------------------------


def _recipe_yaml(
    *,
    recipe_id: str,
    split: str,
    midi_source_file: str,
    kit_entry: KitEntry,
    variant_idx: int,
    seed: int,
) -> str:
    """Render the recipe YAML document (F0-T2a §1.2)."""
    midi_jitter = _midi_jitter_block(variant_idx=variant_idx, seed=seed)
    return (
        f"# F2-T1 recipe — generated by tools/build_recipe_matrix.py\n"
        f"recipe_id: {recipe_id}\n"
        f'schema_version: "1.0"\n'
        f"split: {split}\n"
        f"midi_source:\n"
        f"  dataset: GMD\n"
        f"  file: {midi_source_file}\n"
        # B1 (audit 2026-05-30): declare the source standard so orchestrate runs
        # F0-T18 canonicalization. WITHOUT this the canonicalization is skipped
        # (orchestrate gates on `standard is not None`) and the hi-hat edge GM
        # 22/26 silent drop (10% onsets / 34% hi-hat) recurs at 1.5 TB scale.
        # The Magenta GMD is Roland TD-11 (mirror of mini_l3_runner.py).
        f"  standard: roland_td11\n"
        # M5 (audit 2026-05-30): mapping table is now schema 2.0 (GM->9-channel).
        f"  bus_mapping: midi_mapping_table.yaml@2.0\n"
        f"midi_jitter:\n"
        f"  time_jitter_ms: {midi_jitter['time_jitter_ms']}\n"
        f"  flam_probability: {midi_jitter['flam_probability']}\n"
        f"  velocity_jitter: {midi_jitter['velocity_jitter']}\n"
        f"  component_drop_probability: {midi_jitter['component_drop_probability']}\n"
        f"  seed: {midi_jitter['seed']}\n"
        f"  variant_idx: {midi_jitter['variant_idx']}\n"
        f"render:\n"
        f"  engine: {kit_entry.engine}\n"
        f"  kit: {kit_entry.kit}\n"
        f"  kit_path: {kit_entry.kit_path}\n"
        f"  sample_rate: 44100\n"
        f"  mic_config: {kit_entry.mic_config}\n"
        f"augmentation:\n"
        f"  level: 1\n"
        f"  reverb_ir: null\n"
        f"  mutilation: {{}}\n"
        f"  saboteur: null\n"
        f"output:\n"
        f"  target_frame_rate_hz: 344.53125\n"
    )


def _recipe_id_for(entry: RecipeMatrixEntry) -> str:
    """Stable, human-grep-able recipe id derived from the matrix entry."""
    midi_stem = Path(entry.source_midi_id).stem
    return f"R-F2T1-{midi_stem}-{entry.kit}-J{entry.variant_idx:02d}"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _collect_midis(midi_source_dir: Path) -> list[Path]:
    """Walk ``midi_source_dir`` for ``*.mid`` files."""
    midis = sorted(midi_source_dir.rglob("*.mid"))
    if not midis:
        raise FileNotFoundError(
            f"no MIDI files under {midi_source_dir!s} — provision the Bronze layer first"
        )
    return midis


def _build_split(
    *,
    split: str,
    midis: list[Path],
    kits: tuple[KitEntry, ...],
    k_variants: int,
    master_seed: int,
    output_dir: Path,
) -> dict[str, object]:
    """Emit every recipe YAML for a single split, return manifest summary."""
    if not kits:
        return {
            "split": split,
            "n_entries": 0,
            "n_midi": len(midis),
            "n_kit": 0,
            "k_variants": k_variants,
            "files": [],
        }

    # The recipe-matrix builder takes (engine, kit) pairs as opaque tokens —
    # we feed it the *kit name* in the second slot so the resulting
    # ``jitter_seed`` (derived from master + midi_id + variant) is unaffected
    # by the kit_path. The kit_path is looked up downstream by ``kit name``.
    source_midi_ids = [str(m.relative_to(_REPO_ROOT)) for m in midis]
    engines_kits = [(k.engine, k.kit) for k in kits]
    kit_lookup = {(k.engine, k.kit): k for k in kits}

    entries = build_recipe_matrix_entries(
        source_midi_ids=source_midi_ids,
        engines_kits=engines_kits,
        k_variants=k_variants,
        master_seed=master_seed,
    )

    split_dir = output_dir / split
    split_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for entry in entries:
        kit_entry = kit_lookup[(entry.engine, entry.kit)]
        recipe_id = _recipe_id_for(entry)
        yaml_text = _recipe_yaml(
            recipe_id=recipe_id,
            split=split,
            midi_source_file=entry.source_midi_id,
            kit_entry=kit_entry,
            variant_idx=entry.variant_idx,
            seed=entry.jitter_seed,
        )
        recipe_path = split_dir / f"{recipe_id}.yaml"
        recipe_path.write_text(yaml_text, encoding="utf-8")
        # Recipe path may live outside the repo (e.g. /tmp for smoke tests);
        # store as absolute then strip the repo prefix only when applicable.
        try:
            written.append(str(recipe_path.relative_to(_REPO_ROOT)))
        except ValueError:
            written.append(str(recipe_path))

    return {
        "split": split,
        "n_entries": len(entries),
        "n_midi": len(midis),
        "n_kit": len(kits),
        "k_variants": k_variants,
        "files": written,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the F2-T1 recipe matrix (MIDI × jitter-variant × engine_kit) "
            "with kit-wise train/val split per DOSSIER §10.2 Option B."
        ),
    )
    parser.add_argument(
        "--midi-source-dir",
        type=Path,
        required=True,
        help="Directory of source MIDIs (e.g. bronze/gmd/full or bronze/gmd/mini).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Where to write the recipe YAMLs (split into train/ and val/).",
    )
    parser.add_argument(
        "--master-seed",
        type=int,
        required=True,
        help="Run-level seed — anchors both jitter seeds and the shuffle order.",
    )
    parser.add_argument(
        "--k-variants",
        type=int,
        default=2,
        help="Number of jitter variants per MIDI (LOCKED: k=2, F0-T15-pre §5).",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Smoke mode — 1 MIDI × 2 kits × (k=1)+1 baseline = 4 recipes only.",
    )
    args = parser.parse_args()

    midi_source_dir = (args.midi_source_dir if args.midi_source_dir.is_absolute()
                       else _REPO_ROOT / args.midi_source_dir)
    output_dir = (args.output_dir if args.output_dir.is_absolute()
                  else _REPO_ROOT / args.output_dir)

    if args.master_seed < 0:
        parser.error("--master-seed must be non-negative")
    if args.k_variants < 0:
        parser.error("--k-variants must be non-negative")

    midis = _collect_midis(midi_source_dir)
    if args.smoke:
        midis = midis[:1]
        train_kits = _SMOKE_TRAIN_KITS
        val_kits = _SMOKE_VAL_KITS
        k_variants = min(args.k_variants, 1)
    else:
        train_kits = _TRAIN_KITS
        val_kits = _VAL_KITS
        k_variants = args.k_variants

    print(
        f"F2-T1 recipe matrix — master_seed={args.master_seed}  k_variants={k_variants}  "
        f"smoke={args.smoke}"
    )

    def _rel(path: Path) -> str:
        try:
            return str(path.relative_to(_REPO_ROOT))
        except ValueError:
            return str(path)

    print(f"  midi_source_dir : {_rel(midi_source_dir)}")
    print(f"  n_midi          : {len(midis)}")
    print(f"  n_train_kit     : {len(train_kits)}")
    print(f"  n_val_kit       : {len(val_kits)}")

    train_summary = _build_split(
        split="train",
        midis=midis,
        kits=train_kits,
        k_variants=k_variants,
        master_seed=args.master_seed,
        output_dir=output_dir,
    )
    val_summary = _build_split(
        split="val",
        midis=midis,
        kits=val_kits,
        k_variants=k_variants,
        master_seed=args.master_seed,
        output_dir=output_dir,
    )

    manifest = {
        "manifest_version": "1.0",
        "tool": "tools/build_recipe_matrix.py",
        "master_seed": args.master_seed,
        "k_variants": k_variants,
        "smoke": args.smoke,
        "midi_source_dir": _rel(midi_source_dir),
        "splits": [train_summary, val_summary],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    train_count = train_summary["n_entries"]
    val_count = val_summary["n_entries"]
    assert isinstance(train_count, int) and isinstance(val_count, int)
    total = train_count + val_count
    print(f"  train recipes   : {train_summary['n_entries']}")
    print(f"  val   recipes   : {val_summary['n_entries']}")
    print(f"  TOTAL           : {total}")
    print(f"  manifest        : {_rel(manifest_path)}")


if __name__ == "__main__":
    main()
