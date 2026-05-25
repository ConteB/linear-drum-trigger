#!/usr/bin/env python3
"""Build kit-aware targets — Decision Lock CEO 2026-05-25 (post-piano-roll).

Diagnostic Plan B: per ogni Gold sample, rebuild ``target.f16`` filtrando
le note GM che il midimap.xml del kit NON copre. Risultato: target onesto
(no più "tom!" quando l'audio non ha tom).

Per ciascun kit DrumGizmo del mini-L3:
  - Parsare il midimap.xml → set di GM notes coperte
  - Per ogni sample (.dna.json) di quel kit:
    - Caricare il MIDI sorgente dal `dna.json` (campo lineage)
    - Costruire un BusMapping filtrato (solo note coperte)
    - Re-eseguire build_target con il mapping filtrato
    - Sovrascrivere ``target.f16``
    - Aggiornare ``dna.json.target.sha256`` + ``n_onset``

Per kit Sfizz (BigRustyDrums): il MIDI mapping è in `.sfz` non in midimap.xml.
Per ora, **assumiamo coverage completa** (TODO: vero audit dell'.sfz). In pratica
significa che i target Sfizz NON vengono modificati.

Output: console summary + ``docs/gates/F0-T4c_MINI_L3/kitaware_audit_2026-05-25.json``.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.gold.target_builder import (  # noqa: E402
    BusMapping,
    build_target,
    load_bus_mapping,
)


KIT_DIRS = {
    "DRSKit": ("data/gold/mini_l3_train/DRSKit", "train"),
    "MuldjordKit": ("data/gold/mini_l3_train/MuldjordKit", "train"),
    "CrocellKit": ("data/gold/mini_l3_train/CrocellKit", "train"),
    "Aasimonster": ("data/gold/mini_l3_train/Aasimonster", "train"),
    "BigRustyDrums": ("data/gold/mini_l3_train/BigRustyDrums", "train"),
    "ShittyKit": ("data/gold/mini_l3_val/ShittyKit", "val"),
}

# Midimap.xml paths for each DG kit (the one used in render — see runner).
DG_MIDIMAP_PATHS = {
    "DRSKit": "vendor/drumgizmo/DRSKit/Midimap_full.xml",
    "MuldjordKit": "vendor/drumgizmo/MuldjordKit3/Midimap.xml",
    "CrocellKit": "vendor/drumgizmo/CrocellKit/Midimap_default.xml",
    "Aasimonster": "vendor/drumgizmo/Aasimonster/midimap.xml",
    "ShittyKit": "vendor/drumgizmo/ShittyKit/midimap.xml",
}

MIDI_ROOT = _REPO_ROOT / "bronze" / "gmd" / "mini_l3"


def parse_midimap_covered_notes(xml_path: Path) -> set[int]:
    """Extract the set of GM note numbers covered by a DrumGizmo midimap."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    covered: set[int] = set()
    for el in root.iter():
        if el.tag.endswith("map"):
            note = el.get("note")
            instr = el.get("instr")
            if note and instr:
                # Only count if the instrument exists in the kit (we don't
                # have the kit XML loaded here; assume any non-empty instr
                # name = covered). Aasimonster's `crash1_stop` mapping for GM
                # 50 is technically "covered" but semantically wrong; we
                # surface it separately in the audit but DO drop it from
                # coverage since the listener will hear a crash-stop, NOT a
                # tom, while the target says "tom".
                if _is_semantically_correct(note, instr):
                    covered.add(int(note))
    return covered


def _is_semantically_correct(note_str: str, instr: str) -> bool:
    """Heuristic: does the instrument name match the GM family of the note?

    GM 41/43/45 = floor tom, 47/48/50 = high/mid tom. Instrument should
    contain "tom"/"ftom" (case-insensitive). 35/36=kick → "kick"/"kdrum".
    37/38/40=snare → "snare". 42/44/46=hihat → "hihat"/"hh". 51/53/59=ride →
    "ride". 49=crash → "crash". Etc. If the instrument name DOESN'T match
    the GM family, mark as NOT covered (semantic mismatch — same effect on
    target builder).
    """
    n = int(note_str)
    instr_low = instr.lower()
    families = {
        frozenset([35, 36]): ("kick", "kdrum", "bass"),
        frozenset([37, 38, 40]): ("snare", "sn"),
        frozenset([42, 44, 46]): ("hihat", "hh"),
        frozenset([41, 43, 45]): ("tom", "ftom", "floor"),
        frozenset([47, 48, 50]): ("tom",),
        frozenset([51, 53, 59]): ("ride",),
        frozenset([49]): ("crash",),
        frozenset([52, 55, 57]): ("crash", "splash", "china"),
    }
    for note_set, ok_words in families.items():
        if n in note_set:
            return any(w in instr_low for w in ok_words)
    # Not a target drum note: ignore
    return False


def filtered_bus_mapping(original: BusMapping, covered: set[int]) -> BusMapping:
    """Return a new BusMapping with only the GM notes in ``covered``."""
    new_map = {gm: bus for gm, bus in original.gm_to_bus.items() if gm in covered}
    return BusMapping(gm_to_bus=new_map, schema_version=original.schema_version)


def main() -> int:
    import argparse  # noqa: PLC0415
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Audit only — don't rewrite target.f16 / dna.json.")
    parser.add_argument("--out", type=Path,
                         default=_REPO_ROOT / "docs" / "gates" /
                                 "F0-T4c_MINI_L3" /
                                 "kitaware_audit_2026-05-25.json")
    args = parser.parse_args()

    bus_mapping = load_bus_mapping(_REPO_ROOT / "docs" / "specs" /
                                     "midi_mapping_table.yaml")

    # Build covered-notes per DG kit
    coverage: dict[str, set[int]] = {}
    for kit, path in DG_MIDIMAP_PATHS.items():
        covered = parse_midimap_covered_notes(_REPO_ROOT / path)
        coverage[kit] = covered
        all_target_notes = set(bus_mapping.gm_to_bus.keys())
        missing = sorted(all_target_notes - covered)
        print(f"{kit:<15}: {len(covered)} covered, missing {missing}")

    # BigRustyDrums (Sfizz): assume full coverage (not technically correct but
    # not the dominant bug — SFZ stereo lands on OH slots).
    coverage["BigRustyDrums"] = set(bus_mapping.gm_to_bus.keys())

    audit = {"per_sample": [], "per_kit": {}}

    total_before = 0
    total_after = 0

    for kit, (rel_dir, split) in KIT_DIRS.items():
        kit_dir = _REPO_ROOT / rel_dir
        covered_notes = coverage[kit]
        kit_filtered_mapping = filtered_bus_mapping(bus_mapping, covered_notes)

        kit_stat = {
            "split": split, "covered_notes": sorted(covered_notes),
            "missing_notes": sorted(set(bus_mapping.gm_to_bus.keys()) - covered_notes),
            "n_samples": 0, "n_onsets_before": 0, "n_onsets_after": 0,
        }
        print(f"\n[kitaware] processing {kit} ({kit_dir})…")

        # Only process baseline (J00) samples — jittered (J01+) would need
        # the jitter pipeline re-applied to get the right MIDI events.
        dna_files = sorted(kit_dir.glob("*-J00-*.dna.json"))
        for dna_path in dna_files:
            kit_stat["n_samples"] += 1
            # Load dna to find source MIDI
            dna = json.loads(dna_path.read_text())
            midi_rel = dna.get("lineage", {}).get("midi_source", {}).get("file")
            if not midi_rel:
                continue
            midi_path = _REPO_ROOT / midi_rel
            if not midi_path.exists():
                # fallback by id
                m = re.match(r"(MINI_L3\d+)", dna_path.stem.replace(".dna", ""))
                if m:
                    midi_files = list(MIDI_ROOT.glob(f"{m.group(1)}_*.mid"))
                    if midi_files:
                        midi_path = midi_files[0]
            if not midi_path.exists():
                continue

            # Compute duration in seconds from audio shape (last_onset + tail).
            audio_meta = dna.get("audio", {})
            shape = audio_meta.get("shape") or [8, 0]
            sr = dna.get("lineage", {}).get("render", {}).get("sample_rate", 44100)
            duration_s = shape[1] / sr
            # Build the ORIGINAL target (for delta count)
            try:
                tgt_orig = build_target(
                    midi_path, duration_s=duration_s,
                    bus_mapping=bus_mapping, allow_empty=False,
                )
                n_onset_before = int((tgt_orig[:, 0:24:3] > 0.5).sum())
                tgt_filtered = build_target(
                    midi_path, duration_s=duration_s,
                    bus_mapping=kit_filtered_mapping, allow_empty=True,
                )
                n_onset_after = int((tgt_filtered[:, 0:24:3] > 0.5).sum())
            except Exception as e:
                print(f"  ! {dna_path.name}: build_target error {e}")
                continue

            kit_stat["n_onsets_before"] += n_onset_before
            kit_stat["n_onsets_after"] += n_onset_after
            total_before += n_onset_before
            total_after += n_onset_after

            if not args.dry_run:
                # Rewrite target.f16 in float16 little-endian, update dna
                target_path = dna_path.with_name(
                    dna_path.name.replace(".dna.json", ".target.f16")
                )
                tgt_le = np.ascontiguousarray(tgt_filtered.astype(np.float16))
                target_bytes = tgt_le.tobytes()
                target_path.write_bytes(target_bytes)
                new_sha = hashlib.sha256(target_bytes).hexdigest()
                # Update dna.json target sha + n_onset
                if isinstance(dna.get("target"), dict):
                    dna["target"]["sha256"] = new_sha
                    dna["target"]["n_onset"] = n_onset_after
                dna_path.write_text(json.dumps(dna, indent=2, sort_keys=True))

        delta = kit_stat["n_onsets_before"] - kit_stat["n_onsets_after"]
        delta_pct = (delta / max(kit_stat["n_onsets_before"], 1)) * 100
        kit_stat["onsets_dropped"] = delta
        kit_stat["onsets_dropped_pct"] = delta_pct
        audit["per_kit"][kit] = kit_stat
        print(f"  → {kit_stat['n_samples']} samples · "
              f"{kit_stat['n_onsets_before']} → {kit_stat['n_onsets_after']} onsets · "
              f"-{delta} ({delta_pct:.1f} %)")

    audit["total"] = {
        "onsets_before": total_before,
        "onsets_after": total_after,
        "dropped": total_before - total_after,
        "dropped_pct": (total_before - total_after) / max(total_before, 1) * 100,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True))
    print(f"\n[kitaware] audit JSON → {args.out}")
    print(f"[kitaware] global: {total_before} → {total_after} onsets "
          f"(-{total_before - total_after}, "
          f"{(total_before - total_after) / max(total_before, 1) * 100:.1f} %)")
    if args.dry_run:
        print("[kitaware] DRY RUN — no files modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
