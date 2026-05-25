#!/usr/bin/env python3
"""Mini-L3 cross-kit runner — local Gold (~12 GB) + cross-kit holdout training.

CEO directive 2026-05-24: prima del burn F2-T1/T3 su Azure, validare empiricamente
che la rete (F0-T4a topology + F0-T4c defaults) **generalizzi cross-kit**, non
solo cross-sample. Replica in mini il workflow F2-T1 → F2-T3 → L4 a costo $0:

* 3 kit train  (DRSKit, MuldjordKit, CrocellKit)
* 1 kit val "vergine" (ShittyKit — Decision Lock 2026-05-23 Opzione B,
  ratificato nel vendor/README.md)
* 250 grooves GMD ≥ 5s (deterministico, seed=20260524)
* 2 jitter variants (baseline + 1 jittered) sul train, 1 sul val
* Storage Gold: ~11 GB (sotto i 20 GB cap CEO)
* Wall-time stimato: provisioning + render train (~100 min) + val (~15 min) +
  training MPS (~10 min) ≈ 2-3 h

Pipeline riusa moduli LOCKED (zero nuova logica di pipeline):
  - data_engineering.gold.recipe / orchestrate / target_builder
  - data_engineering.midi_augment.jitter / recipe_matrix
  - neural.data / loss / model (defaults F0-T4c)
  - neural.reporter (MODEL_REPORT_BLUEPRINT LIN-DT-RPTBP-001)
  - tools.scan_density (per pos_weight per-bus)

Gate metrica (mini-L3, sotto L4): F-measure cross-kit val ≥ **0.55** (mean
sample con almeno un onset). Non è il gate L4 (≥ 0.80 sul Holdout reale E-GMD)
ma è la prima evidenza empirica di generalizzazione timbro-indipendente.

Run:
    # Step-by-step (più sicuro, riprendibile):
    python tools/mini_l3_runner.py --stage select-midi
    python tools/mini_l3_runner.py --stage render-train
    python tools/mini_l3_runner.py --stage render-val
    python tools/mini_l3_runner.py --stage train
    python tools/mini_l3_runner.py --stage report

    # All-in-one:
    python tools/mini_l3_runner.py --stage all
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import random
import sys
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
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


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: CEO directive 2026-05-24 — Variante B (~20 GB cap, ~3h totale).
#:
#: Adjusted 2026-05-24 (in-session): originale era 250 grooves, ma il filtro
#: durata 5..50s con tutti gli split inflated lo storage Gold a ~70 GB (sample
#: lunghi fino a 50s → ~70 MB ciascuno). Cap superiore ridotto a 15 s per
#: bilanciare # grooves vs storage; risultato 117 grooves × 3 kit × 2 jitter =
#: 702 train + 117 val × 1 jitter × 1 kit = 819 sample × ~12 MB avg ≈ 10 GB.
#: Diversità rimane 7× sopra il regression test (18 sample) — sufficiente per
#: testare cross-kit generalization.
N_GROOVES = 117

#: 2 jitter variants per groove (baseline + 1 jittered).
K_VARIANTS = 1  # k augmented; total = k + 1 baseline = 2

#: Master seed (replay-invariant).
MASTER_SEED = 20260524

#: Minimum MIDI duration in seconds (Gold sample must satisfy crop ≥
#: MIN_CROP_SAMPLES = 135_552 + lookahead_frames = ~3.07 s + 100 ms = ~3.17 s
#: → with 2× safety margin we want ≥ 5 s, allineato con la spec F0-T4c B4.
MIN_MIDI_DURATION_S = 5.0

#: Maximum MIDI duration — caps the Gold sample size (linear in audio length).
#: Tradeoff: > 15 s would yield > 117 grooves but explode the storage budget
#: well past the 20 GB cap.
MAX_MIDI_DURATION_S = 15.0

#: Train kits — roster F0-T1b training partition.
#: Decision Lock CEO 2026-05-25 (post C=64 FAIL): paradigma misto DG+SFZ per
#: chiudere il distribution shift cross-kit. Sfizz è single-stereo → ricade
#: sui canali OH_L/OH_R del layout 8-canale canonico (data.py: solo_stereo
#: → slots 5,6); gli altri 6 canali sono zero (channel masking della aug
#: B3 li gestisce). Aasimonster aggiunto come 4° kit DG (provisioning
#: 2026-05-25 mattina), Big Rusty Drums come 1° kit Sfizz (già provisioned
#: in vendor/sfz/).
#:
#: Schema: tuple[(engine, kit_label, kit_path_or_xml), ...]
TRAIN_KITS_MIXED: tuple[tuple[str, str, str], ...] = (
    ("drumgizmo", "DRSKit",      "vendor/drumgizmo/DRSKit/DRSKit_full.xml"),
    ("drumgizmo", "MuldjordKit", "vendor/drumgizmo/MuldjordKit3/MuldjordKit3.xml"),
    ("drumgizmo", "CrocellKit",  ""),    # filled at runtime
    ("drumgizmo", "Aasimonster", ""),    # filled at runtime
    ("sfizz",     "BigRustyDrums", "vendor/sfz/big-rusty-drums/Programs/01-full.sfz"),
)

#: Val "vergine" kit — Decision Lock 2026-05-23 (vendor/README.md):
#: ShittyKit tenuto fuori dal training pool per misurare cross-kit generalization.
VAL_KIT: tuple[str, str] = ("ShittyKit", "")  # filled at runtime

#: GMD roots.
GMD_ROOT = _REPO_ROOT / "bronze" / "gmd" / "v1" / "groove"
MIDI_SUBSET_DIR = _REPO_ROOT / "bronze" / "gmd" / "mini_l3"

#: Gold output dirs (separate train/val for clean cross-kit split).
GOLD_TRAIN_DIR = _REPO_ROOT / "data" / "gold" / "mini_l3_train"
GOLD_VAL_DIR = _REPO_ROOT / "data" / "gold" / "mini_l3_val"

#: Density JSON + report root.
DENSITY_JSON = _REPO_ROOT / "artifacts" / "mini_l3_density.json"
REGRESSION_KEYS_JSON = _REPO_ROOT / "artifacts" / "mini_l3_holdout_keys.json"
REPORT_ROOT_REPORTS = _REPO_ROOT / "reports"
REPORT_ROOT_GATE = _REPO_ROOT / "docs" / "gates" / "F0-T4c_MINI_L3"

#: Gate threshold for the mini-L3 verdict (CEO directive 2026-05-24).
GATE_F_MEAN_VAL = 0.55


# ---------------------------------------------------------------------------
# Stage 1: select MIDI subset
# ---------------------------------------------------------------------------


def _find_main_kit_xml(kit_dir: Path) -> str:
    """Locate the 'main' kit XML inside ``kit_dir`` (relative to repo root).

    Resolution order (most specific first):
      1. ``<stem>_full.xml`` / ``*_full*`` (DRSKit / CrocellKit convention)
      2. ``<dirname>.xml`` (Aasimonster: ``aasimonster.xml`` in
         ``Aasimonster/``)
      3. First XML that is *not* labelled ``-minimal`` / ``midimap`` /
         contains a per-component XML (drop ``china_*.xml`` etc.)

    The ``-minimal`` and per-component XMLs are explicitly excluded —
    they expose a tiny subset of the kit (designed for low-RAM previews)
    and crash with -9 when fed full GMD grooves.
    """
    skip = {"midimap", "minimal"}
    candidates = [
        c for c in sorted(kit_dir.glob("*.xml"))
        if not any(s in c.name.lower() for s in skip)
    ]
    if not candidates:
        return ""
    # Preference order.
    dir_stem = kit_dir.name.lower()
    for c in candidates:
        stem = c.stem.lower()
        if stem.endswith("_full") or "_full" in stem:
            return str(c.relative_to(_REPO_ROOT))
    for c in candidates:
        if c.stem.lower() == dir_stem:
            return str(c.relative_to(_REPO_ROOT))
    # Last resort: first non-minimal XML.
    return str(candidates[0].relative_to(_REPO_ROOT))


def _resolve_kit_paths() -> tuple[list[tuple[str, str, str]], tuple[str, str]]:
    """Resolve the kit XML paths for the mini-L3 train + val pools.

    Returns ``(train_kits, val_kit)`` where train_kits is a list of
    ``(engine, label, path)`` triples (mixed engines DG+SFZ) and val_kit
    is a single DG kit tuple ``(label, xml_path)``.
    """
    dg_base = _REPO_ROOT / "vendor" / "drumgizmo"
    # Default hardcoded paths for the kits that are stable and already
    # provisioned; for newer kits use a directory-prefix scan.
    crocell_xml = ""
    aasimonster_xml = ""
    shitty_xml = ""
    if dg_base.exists():
        for d in dg_base.iterdir():
            if not d.is_dir():
                continue
            if d.name.startswith("Crocell"):
                crocell_xml = _find_main_kit_xml(d)
            elif d.name.lower().startswith("aasi"):
                aasimonster_xml = _find_main_kit_xml(d)
            elif d.name.startswith("Shitty"):
                shitty_xml = _find_main_kit_xml(d)
    # SFZ kit path — Big Rusty Drums (CC0, full kit GM-compatible).
    big_rusty_sfz = "vendor/sfz/big-rusty-drums/Programs/01-full.sfz"
    if not (_REPO_ROOT / big_rusty_sfz).exists():
        big_rusty_sfz = ""
    train_kits = [
        ("drumgizmo", "DRSKit",        "vendor/drumgizmo/DRSKit/DRSKit_full.xml"),
        ("drumgizmo", "MuldjordKit",   "vendor/drumgizmo/MuldjordKit3/MuldjordKit3.xml"),
        ("drumgizmo", "CrocellKit",    crocell_xml),
        ("drumgizmo", "Aasimonster",   aasimonster_xml),
        ("sfizz",     "BigRustyDrums", big_rusty_sfz),
    ]
    val_kit = ("ShittyKit", shitty_xml)
    return train_kits, val_kit


def select_midi_subset() -> list[Path]:
    """Pick N_GROOVES MIDIs from GMD with duration in [MIN, MAX] seconds.

    Filters by info.csv: time_signature=4-4 AND duration in
    ``[MIN_MIDI_DURATION_S, MAX_MIDI_DURATION_S]``.

    **Includes all GMD splits** (train/test/eval) — rationale: il val
    "vergine" del mini-L3 è ShittyKit (kit diverso), non un subset MIDI
    diverso. La dottrina "tenere test/eval intoccati per honest evaluation"
    si applica al gate L4, che userà E-GMD — un dataset esterno a GMD.
    Includere test/eval qui non compromette nulla a valle, e amplia la
    base disponibile da 90 grooves (cap 5..12s train) a 117 (cap 5..15s
    all-splits) — sweet spot del tradeoff diversità × storage.
    """
    csv_path = GMD_ROOT / "info.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"GMD info.csv missing: {csv_path}")
    eligible: list[tuple[str, Path, float]] = []
    with csv_path.open() as fh:
        for row in csv.DictReader(fh):
            if row.get("time_signature") != "4-4":
                continue
            try:
                dur = float(row.get("duration") or "0")
            except ValueError:
                continue
            if not (MIN_MIDI_DURATION_S <= dur <= MAX_MIDI_DURATION_S):
                continue
            midi_rel = row.get("midi_filename")
            if not midi_rel:
                continue
            midi_path = GMD_ROOT / midi_rel
            if not midi_path.exists():
                continue
            label = row.get("id") or midi_rel
            eligible.append((label, midi_path, dur))
    if len(eligible) < N_GROOVES:
        raise RuntimeError(
            f"GMD has only {len(eligible)} eligible grooves "
            f"(4-4 + train + {MIN_MIDI_DURATION_S}s ≤ dur ≤ 12s + on-disk), "
            f"need {N_GROOVES}"
        )
    # Deterministic sort + sample.
    eligible.sort(key=lambda p: p[0])
    rng = random.Random(MASTER_SEED)
    sampled = rng.sample(eligible, k=N_GROOVES)
    sampled.sort(key=lambda p: p[0])

    # Copy into the mini-L3 MIDI subset dir, prefixed by global index for
    # unique barcodes (same trick as mix_dataset.py).
    if MIDI_SUBSET_DIR.exists():
        for f in MIDI_SUBSET_DIR.glob("*.mid"):
            f.unlink()
    MIDI_SUBSET_DIR.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    import shutil  # noqa: PLC0415
    for i, (label, src_path, _dur) in enumerate(sampled):
        slug = label.replace("/", "_").replace(":", "_")
        slug = "".join(c for c in slug if c.isalnum() or c in "._-")
        dst = MIDI_SUBSET_DIR / f"{i:04d}_{slug}.mid"
        shutil.copy2(src_path, dst)
        out.append(dst)
    return out


# ---------------------------------------------------------------------------
# Stage 2: build recipes + render
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MiniL3Entry:
    """One render entry — wraps RecipeMatrixEntry + the resolved kit path.

    Decision Lock CEO 2026-05-25: extended with ``engine`` to support the
    mixed DG+SFZ training pool. The Sfizz path is the absolute ``.sfz`` file
    (e.g. ``Programs/01-full.sfz``); for DrumGizmo it is the main XML.
    """

    source_midi_id: str
    variant_idx: int
    jitter_seed: int
    engine: str       # "drumgizmo" | "sfizz"
    kit_label: str
    kit_xml: str      # XML for DG; .sfz for Sfizz


def build_entries_for_split(
    midi_ids: list[str],
    kits: list[tuple[str, str, str]],
    *,
    k_variants: int,
) -> list[MiniL3Entry]:
    """Build the per-split entries: M × kits × (k + 1) variants.

    ``kits`` is a list of ``(engine, label, path)`` triples (mixed engines
    supported since the C=64 capacity bump branched into the mixed-paradigm
    train pool). The recipe-matrix machinery uses ``(engine, label)`` for
    barcode derivation; we resolve the path locally.
    """
    base_entries = build_recipe_matrix_entries(
        source_midi_ids=midi_ids,
        engines_kits=[(eng, lbl) for eng, lbl, _ in kits],
        k_variants=k_variants,
        master_seed=MASTER_SEED,
    )
    path_by_kit = {lbl: path for _eng, lbl, path in kits}
    engine_by_kit = {lbl: eng for eng, lbl, _ in kits}
    out: list[MiniL3Entry] = []
    for e in base_entries:
        out.append(MiniL3Entry(
            source_midi_id=e.source_midi_id,
            variant_idx=e.variant_idx,
            jitter_seed=e.jitter_seed,
            engine=engine_by_kit[e.kit],
            kit_label=e.kit,
            kit_xml=path_by_kit[e.kit],
        ))
    return out


def _recipe_from_mini_entry(
    entry: MiniL3Entry, midi_relpath: str, split: Split,
) -> Recipe:
    """Build a Recipe directly — no YAML.

    Engine-aware: Sfizz renders single stereo (``mic_config=solo_stereo``),
    while DrumGizmo renders 8-mic multitrack (``mic_config=multitrack_full``).
    On the consumer side, ``src/neural/data.py:_apply_canonical_slots`` lifts
    Sfizz stereo to the 8-channel canonical layout placing L/R on the OH
    slots (5,6) and zeroing the rest — exactly what the F0-T15-post B3
    channel-mask trains the network to handle.
    """
    if entry.engine == "drumgizmo":
        engine_enum = Engine.DRUMGIZMO
        mic_cfg = MicConfig.MULTITRACK_FULL
    elif entry.engine == "sfizz":
        engine_enum = Engine.SFIZZ
        mic_cfg = MicConfig.SOLO_STEREO
    else:
        raise ValueError(f"unknown engine {entry.engine!r}")
    return Recipe(
        recipe_id=f"R-MINI_L3-{entry.source_midi_id}-V{entry.variant_idx}-{entry.kit_label}",
        schema_version="1.0",
        split=split,
        midi_source=MidiSource(
            dataset="MINI_L3",
            file=midi_relpath,
            bus_mapping="midi_mapping_table.yaml@1.0",
        ),
        midi_jitter=MidiJitter(
            time_jitter_ms=(0.0, 0.0) if entry.variant_idx == 0 else (2.0, 15.0),
            flam_probability=0.0 if entry.variant_idx == 0 else 0.05,
            velocity_jitter=(
                VelocityJitter.NONE if entry.variant_idx == 0 else VelocityJitter.BOTH
            ),
            component_drop_probability=0.0 if entry.variant_idx == 0 else 0.10,
            seed=entry.jitter_seed,
            variant_idx=entry.variant_idx,
        ),
        render=RenderSpec(
            engine=engine_enum,
            kit=entry.kit_label,
            kit_path=entry.kit_xml,
            sample_rate=44100,
            mic_config=mic_cfg,
        ),
        augmentation=AugmentationSpec(
            level=1,                  # raw — no audio aug (F0-T16-post out of scope)
            reverb_ir=None,
            mutilation={},
            saboteur=None,
        ),
        target_frame_rate_hz=344.53125,
    )


def render_entries(
    entries: list[MiniL3Entry],
    midi_paths: dict[str, Path],
    out_dir: Path,
    split: Split,
    *,
    bus_mapping: object,
    skip_existing: bool = True,
    gc_every: int = 10,
    log_every: int = 25,
) -> tuple[int, int, int, float]:
    """Render every entry. Returns (generated, skipped, failed, elapsed_s).

    Writes one sub-directory per kit (``out_dir / kit_label``) so the same
    barcode key (which does NOT carry the kit info — F0-T2a §4.1 has 7
    segments, kit collapsed into the recipe context) does not collide between
    different kits rendering the same MIDI source. ``load_pool`` is recursive
    (``rglob("*.dna.json")``) so the consumer side just works.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = skipped = failed = 0
    started = time.monotonic()
    total = len(entries)
    with tempfile.TemporaryDirectory(prefix="mini_l3_jitter_") as tmp_root:
        tmp_dir = Path(tmp_root)
        for i, entry in enumerate(entries):
            src_midi = midi_paths[entry.source_midi_id]
            recipe = _recipe_from_mini_entry(
                entry, str(src_midi.relative_to(_REPO_ROOT)), split,
            )
            kit_out_dir = out_dir / entry.kit_label
            kit_out_dir.mkdir(exist_ok=True)

            # Idempotent: skip if the on-disk triple already exists.
            if skip_existing:
                barcode = derive_barcode(recipe)
                key = encode_barcode(barcode)
                if (kit_out_dir / f"{key}.dna.json").exists():
                    skipped += 1
                    continue

            # Apply jitter in-memory; write transient MIDI.
            source_midi = mido.MidiFile(str(src_midi))
            jittered = apply_midi_jitter(
                source_midi,
                variant_idx=entry.variant_idx,
                master_seed=MASTER_SEED,
                source_midi_id=entry.source_midi_id,
            )
            transient = tmp_dir / f"{entry.source_midi_id}_v{entry.variant_idx}_{entry.kit_label}.mid"
            jittered.save(str(transient))

            try:
                build_gold_sample(
                    recipe,
                    out_dir=kit_out_dir,
                    bus_mapping=bus_mapping,
                    midi_path_override=transient,
                )
                generated += 1
            except Exception as exc:  # noqa: BLE001 — log + continue
                failed += 1
                print(
                    f"  ✗ [{i + 1}/{total}] {entry.source_midi_id} v{entry.variant_idx} "
                    f"{entry.kit_label}: {type(exc).__name__}: {exc}",
                    flush=True,
                )

            del source_midi, jittered
            try:
                transient.unlink()
            except OSError:
                pass

            if (i + 1) % gc_every == 0:
                gc.collect()
            if (i + 1) % log_every == 0:
                elapsed = time.monotonic() - started
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (total - (i + 1)) / rate if rate > 0 else 0
                print(
                    f"  [{i + 1}/{total}] gen={generated} skip={skipped} fail={failed} "
                    f"· {rate:.2f} sample/s · ETA {eta / 60:.1f} min",
                    flush=True,
                )

    return generated, skipped, failed, time.monotonic() - started


# ---------------------------------------------------------------------------
# Stage entry-points (called by CLI)
# ---------------------------------------------------------------------------


def stage_select_midi() -> None:
    print(f"[mini-L3] selecting {N_GROOVES} MIDIs from GMD ≥ {MIN_MIDI_DURATION_S}s …")
    midi_paths = select_midi_subset()
    print(f"[mini-L3] wrote {len(midi_paths)} MIDIs → {MIDI_SUBSET_DIR}")


def _discover_midi_paths() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for f in sorted(MIDI_SUBSET_DIR.glob("*.mid")):
        # source_midi_id = stem (first numeric prefix is part of it).
        out[f.stem] = f
    return out


def _render_split(split_name: str, kits: list[tuple[str, str, str]],
                  k_variants: int, out_dir: Path, split: Split) -> None:
    midi_paths = _discover_midi_paths()
    if not midi_paths:
        raise RuntimeError("No MIDIs found — run --stage select-midi first.")
    midi_ids = sorted(midi_paths.keys())
    entries = build_entries_for_split(midi_ids, kits, k_variants=k_variants)
    print(f"[mini-L3:{split_name}] {len(entries)} entries to render "
          f"({len(midi_ids)} MIDIs × {len(kits)} kits × {k_variants + 1} variants)")

    bus_mapping = load_bus_mapping(DEFAULT_BUS_MAPPING_PATH)
    gen, skip, fail, elapsed = render_entries(
        entries, midi_paths, out_dir, split, bus_mapping=bus_mapping,
    )
    print(f"[mini-L3:{split_name}] done: gen={gen} skip={skip} fail={fail} "
          f"elapsed={elapsed:.0f}s ({elapsed/60:.1f} min)")


def stage_render_train(engine_filter: str = "all") -> None:
    train_kits, _ = _resolve_kit_paths()
    # Skip kits not yet extracted (path empty) — supports the "start now,
    # add later" workflow. Re-run with the missing kit available will add
    # the remaining samples (skip_existing=True keeps the run idempotent).
    available_kits = [k for k in train_kits if k[2]]
    missing = [k[1] for k in train_kits if not k[2]]
    if missing:
        print(f"[mini-L3:train] ⚠ SKIPPING (not yet provisioned): {missing}")
    # Engine filter — Decision Lock CEO 2026-05-25 (mixed DG+SFZ pool).
    # Sfizz binary is macOS-only (vendor/sfizz/sfizz_render), DrumGizmo
    # binary is Linux-only (apt in OrbStack VM). The render is split
    # across two hosts: `--engine-filter drumgizmo` on OrbStack,
    # `--engine-filter sfizz` on macOS. Idempotent skip via
    # skip_existing means the second pass only adds the missing kits.
    if engine_filter != "all":
        before = len(available_kits)
        available_kits = [k for k in available_kits if k[0] == engine_filter]
        print(f"[mini-L3:train] --engine-filter={engine_filter}: "
              f"{before} → {len(available_kits)} kits")
    print(f"[mini-L3:train] kits = "
          f"{[(eng, lbl) for eng, lbl, _ in available_kits]}")
    if not available_kits:
        print("ERROR: no train kits available — nothing to render.")
        sys.exit(1)
    _render_split("train", available_kits, K_VARIANTS, GOLD_TRAIN_DIR, Split.TRAIN)


def stage_render_val() -> None:
    _, val_kit = _resolve_kit_paths()
    if not val_kit[1]:
        print(f"ERROR: val kit '{val_kit[0]}' not yet provisioned "
              f"(no XML found under vendor/drumgizmo/Shitty*).")
        sys.exit(1)
    print(f"[mini-L3:val] kit = {val_kit[0]}")
    # Val: 1 DG kit, 1 variant (baseline only — no jitter).
    val_triple = [("drumgizmo", val_kit[0], val_kit[1])]
    _render_split("val", val_triple, 0, GOLD_VAL_DIR, Split.VAL)


# Training is delegated to a sibling tool (next file) — keeps this runner
# focused on the data-pipeline side, which is the long pole.


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mini-L3 cross-kit runner (CEO directive 2026-05-24)"
    )
    parser.add_argument(
        "--stage", required=True,
        choices=("select-midi", "render-train", "render-val", "all"),
    )
    parser.add_argument(
        "--engine-filter", default="all",
        choices=("all", "drumgizmo", "sfizz"),
        help="Filter train kits by engine (mixed DG+SFZ pool, 2026-05-25).",
    )
    args = parser.parse_args()

    if args.stage in ("select-midi", "all"):
        stage_select_midi()
    if args.stage in ("render-train", "all"):
        stage_render_train(engine_filter=args.engine_filter)
    if args.stage in ("render-val", "all"):
        stage_render_val()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
