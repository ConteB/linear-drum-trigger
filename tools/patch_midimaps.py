#!/usr/bin/env python3
"""Patch DrumGizmo midimap.xml — Decision Lock CEO 2026-05-25 (Plan A).

Aggiunge note GM mancanti e corregge mappature semantically wrong nei
midimap.xml dei 5 kit DG del mini-L3. Backup l'originale in `*.orig.xml`.

PATCHES (decisi via audit `tools/build_kitaware_targets.py --dry-run`):

  DRSKit:
    + GM 48 → Tom1   (high_mid_tom)
    + GM 50 → Tom1   (high_tom)
    + GM 45 → Tom2   (low_tom → use Tom2 mid)

  MuldjordKit (file Midimap.xml):
    + GM 50 → Tom1
    + GM 43 → Tom4   (high_floor_tom, shared with 41 which is low_floor)

  CrocellKit:
    + GM 50 → Tom1
    + GM 45 → Tom2

  Aasimonster:
    ~ GM 50: crash1_stop → tom_1    (was: erroneous fire of crash damper)
    ~ GM 41: hihat_closed2 → tom_4  (was: erroneous hi-hat trigger on floor tom)

  ShittyKit:
    + GM 48 → Tom-RH
    + GM 50 → Tom-RH
    (Note: GM 45 → Tom-LH kept as-is. The "wrong" flag was a false positive
    of the audit script — GM 45 is semantically a low-tom, not a floor, and
    Tom-LH is an appropriate instrument. The midi_mapping_table classifies
    GM 45 to the floor_tom bus, but that's an editorial choice that affects
    all kits; we don't change it here.)
"""
from __future__ import annotations

import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

PATCHES: dict[str, dict[str, list[tuple[int, str]]]] = {
    "DRSKit": {
        "path": "vendor/drumgizmo/DRSKit/Midimap_full.xml",
        "add": [(48, "Tom1"), (50, "Tom1"), (45, "Tom2")],
        "fix": [],
    },
    "MuldjordKit": {
        # 2026-05-26 audit: + GM 40 (Electric Snare), + GM 44 (HHpedal).
        # GM 40 is the most common alt snare note in GMD; was producing
        # silent audio with target=snare → 64+ phantom onsets/30 grooves.
        # GM 44 (Hi-Hat Pedal) → closed hi-hat (best available proxy).
        "path": "vendor/drumgizmo/MuldjordKit3/Midimap.xml",
        "add": [(50, "Tom1"), (43, "Tom4"), (40, "Snare"), (44, "HihatClosed")],
        "fix": [],
    },
    "CrocellKit": {
        # 2026-05-26 audit bugfix: the original Plan A patched
        # `Midimap_default.xml`, but the render uses `CrocellKit_full.xml`
        # which resolves to `Midimap_full.xml` via _resolve_drumgizmo_midimap.
        # All 687 CrocellKit train samples were rendered with the UNPATCHED
        # midimap → phantom onsets on tom_hi_mid (GM 50) and floor_tom
        # (GM 45). Patch the correct file.
        "path": "vendor/drumgizmo/CrocellKit/Midimap_full.xml",
        "add": [(50, "Tom1"), (45, "Tom2")],
        "fix": [],
    },
    "Aasimonster": {
        "path": "vendor/drumgizmo/Aasimonster/midimap.xml",
        "add": [],
        "fix": [(50, "crash1_stop", "tom_1"), (41, "hihat_closed2", "tom_4")],
    },
    "ShittyKit": {
        "path": "vendor/drumgizmo/ShittyKit/midimap.xml",
        "add": [(48, "Tom-RH"), (50, "Tom-RH")],
        "fix": [],
    },
}


def patch_kit(kit: str, info: dict) -> bool:
    path = _REPO_ROOT / info["path"]
    if not path.exists():
        print(f"  ERROR: {path} not found")
        return False
    # Backup original
    backup = path.with_suffix(path.suffix + ".orig")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"  backup → {backup.name}")

    # Parse + patch (avoid namespace mess: read raw, find <midimap> element)
    tree = ET.parse(path)
    root = tree.getroot()

    # Find the parent of map elements (typically <midimap> root or a sub)
    parent = root
    # Build set of existing note→instr (for verification)
    existing = {}
    for el in root.iter():
        if el.tag.endswith("map"):
            note = el.get("note")
            instr = el.get("instr")
            if note and instr:
                existing[int(note)] = instr
                # Remember the parent
                # Iter doesn't give parents — find via traversal
    # Locate parent of the first map element
    map_parent = None
    for parent_el in root.iter():
        for child in parent_el:
            if child.tag.endswith("map"):
                map_parent = parent_el
                break
        if map_parent is not None:
            break

    if map_parent is None:
        print(f"  ERROR: no <map> elements found in {kit}")
        return False

    # Apply fixes
    for note, old_instr, new_instr in info["fix"]:
        existing_match = None
        for el in map_parent.iter():
            if el.tag.endswith("map") and el.get("note") == str(note):
                existing_match = el
                break
        if existing_match is None:
            print(f"  WARN: GM {note} not found for fix")
            continue
        if existing_match.get("instr") != old_instr:
            print(f"  WARN: GM {note} expected '{old_instr}', found "
                  f"'{existing_match.get('instr')}'")
        existing_match.set("instr", new_instr)
        print(f"  ~ fixed GM {note}: '{old_instr}' → '{new_instr}'")

    # Apply additions
    for note, instr in info["add"]:
        if note in existing:
            print(f"  WARN: GM {note} already mapped to '{existing[note]}', skipping add")
            continue
        # Create new <map> element (preserve XML namespace from siblings)
        sample_map = next((c for c in map_parent if c.tag.endswith("map")), None)
        if sample_map is None:
            print(f"  ERROR: no sibling <map> to clone tag from")
            continue
        new_el = ET.SubElement(map_parent, sample_map.tag,
                                {"note": str(note), "instr": instr})
        new_el.tail = sample_map.tail  # preserve indent
        print(f"  + added GM {note} → '{instr}'")

    # Write back
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return True


def main() -> int:
    print("Patching DG midimaps — Plan A (Decision Lock CEO 2026-05-25)")
    print("=" * 64)
    for kit, info in PATCHES.items():
        print(f"\n{kit}  ({info['path']})")
        patch_kit(kit, info)
    print("\n" + "=" * 64)
    print("✓ All midimap patches applied. Originals backed up in *.orig.")
    print("  Next: delete J00 audio for affected kits + re-render.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
