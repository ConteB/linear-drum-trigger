#!/usr/bin/env python3
"""MIDI Coherence Validator — gate pre-render (F0-T18, Decision Lock CEO 2026-05-28).

The coherence gate the Pipeline Audit 2026-05-28 mandated: it makes every
translation gap between the source MIDI standard, the render engine, and the
transcription bus EXPLICIT before a render burns compute. It answers, for each
``(source standard × kit)`` pair:

1. **Standard coverage** — does the source standard map (or explicitly ignore)
   every drum note that appears in the corpus? An un-handled note would fail
   loud at canonicalization time; this surfaces it ahead of the render.
2. **Render coverage** — does every articulation the standard can emit have its
   canonical ``render_gm`` note present in the kit's DrumGizmo midimap? A
   missing one means the canonical MIDI carries an onset the kit cannot voice
   → phantom-target mismatch (audio silent, target populated — the Plan-A bug
   class).
3. **Bus coverage** — does every articulation project onto a valid bus?
   (Guaranteed by the SSoT loader, re-asserted here for completeness.)

Severity:
* **BLOCKER** — a corpus note neither mapped nor ignored (canonicalization
  would crash mid-render). Exit non-zero.
* **WARN** — an articulation's render note absent from a kit midimap (phantom
  target risk). Reported; non-zero only with ``--strict``.
* **OK** — full coherence.

Usage::

    python tools/audit_midi_coherence.py                 # all kits, default standard
    python tools/audit_midi_coherence.py --corpus bronze/gmd/v1 --standard roland_td11
    python tools/audit_midi_coherence.py --strict        # WARN -> non-zero (CI gate)

Spec: ``docs/methodology/F0-T18_MIDI_STANDARD_TRANSLATION_SPEC.md``.
"""
from __future__ import annotations

import argparse
import glob
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

import mido  # type: ignore[import-untyped]  # noqa: E402

from data_engineering.gold.midi_canonical import (  # noqa: E402
    SourceStandards,
    load_source_standards,
)

#: Default kit midimaps to validate (DrumGizmo roster, F0-T1b).
DEFAULT_KIT_MIDIMAPS: dict[str, str] = {
    "DRSKit": "vendor/drumgizmo/DRSKit/Midimap_full.xml",
    "MuldjordKit3": "vendor/drumgizmo/MuldjordKit3/Midimap.xml",
    "CrocellKit": "vendor/drumgizmo/CrocellKit/Midimap_full.xml",
    "Aasimonster": "vendor/drumgizmo/Aasimonster/midimap.xml",
    "ShittyKit": "vendor/drumgizmo/ShittyKit/midimap.xml",
}


def midimap_notes(path: Path) -> set[int]:
    """Parse a DrumGizmo ``midimap.xml`` and return the set of mapped notes."""
    notes: set[int] = set()
    tree = ET.parse(str(path))
    for elem in tree.iter():
        # DrumGizmo: <map note="42" instr="..."/>
        note_attr = elem.attrib.get("note")
        if note_attr is not None:
            try:
                notes.add(int(note_attr))
            except ValueError:
                continue
    return notes


def corpus_notes(corpus_dir: Path) -> Counter[int]:
    """Count every note-on (velocity > 0) across all MIDI in ``corpus_dir``."""
    counts: Counter[int] = Counter()
    for f in glob.glob(str(corpus_dir / "**" / "*.mid*"), recursive=True):
        try:
            midi = mido.MidiFile(f)
        except Exception:  # noqa: BLE001 — corpus survey: skip unreadable
            continue
        for msg in midi:
            if msg.type == "note_on" and msg.velocity > 0:
                counts[msg.note] += 1
    return counts


def emittable_render_notes(std: SourceStandards, standard: str) -> set[int]:
    """The set of canonical ``render_gm`` notes the standard can produce."""
    out: set[int] = set()
    for src_note, art_name in std.standards[standard].items():  # noqa: B007
        out.add(std.articulations[art_name].render_gm)
    return out


def audit(
    std: SourceStandards,
    standard: str,
    kit_midimaps: dict[str, str],
    corpus_dir: Path | None,
) -> tuple[list[str], list[str]]:
    """Run the coherence audit. Returns ``(blockers, warnings)`` message lists."""
    blockers: list[str] = []
    warnings: list[str] = []

    # 1. Standard coverage against the corpus (if provided).
    if corpus_dir is not None and corpus_dir.exists():
        counts = corpus_notes(corpus_dir)
        mapped = set(std.standards[standard])
        ignored = set(std.ignored.get(standard, {}))
        for note, n in sorted(counts.items()):
            if note not in mapped and note not in ignored:
                blockers.append(
                    f"[BLOCKER] corpus note {note} ({n} onsets) is neither mapped "
                    f"by standard {standard!r} nor in its ignored registry — "
                    f"canonicalization would crash. Add it to the SSoT."
                )

    # 2. Render coverage per kit.
    emittable = emittable_render_notes(std, standard)
    # which articulations route to which render note (for messages)
    render_to_arts: dict[int, list[str]] = {}
    for name, art in std.articulations.items():
        render_to_arts.setdefault(art.render_gm, []).append(name)

    for kit, mm_path in kit_midimaps.items():
        p = Path(mm_path)
        if not p.is_file():
            warnings.append(f"[WARN] kit {kit}: midimap not found at {p} — skipped")
            continue
        kit_notes = midimap_notes(p)
        missing = sorted(emittable - kit_notes)
        for note in missing:
            arts = ",".join(render_to_arts.get(note, ["?"]))
            warnings.append(
                f"[WARN] kit {kit}: canonical render note {note} ({arts}) absent "
                f"from its midimap — onsets routed here render SILENT while the "
                f"target is populated (phantom-target mismatch)."
            )

    # 3. Bus coverage (re-assert SSoT invariant).
    for name, art in std.articulations.items():
        if not 1 <= art.bus <= 8:
            blockers.append(f"[BLOCKER] articulation {name} bus {art.bus} out of [1,8]")

    return blockers, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="MIDI coherence validator (F0-T18)")
    ap.add_argument("--standard", default="roland_td11",
                    help="Source standard to validate (default: roland_td11 = GMD).")
    ap.add_argument("--corpus", type=Path, default=Path("bronze/gmd/v1"),
                    help="MIDI corpus dir for standard-coverage check (default: GMD v1).")
    ap.add_argument("--no-corpus", action="store_true",
                    help="Skip the corpus-coverage check (SSoT + kit checks only).")
    ap.add_argument("--strict", action="store_true",
                    help="Treat WARN (phantom-target risk) as non-zero exit.")
    args = ap.parse_args()

    std = load_source_standards()
    if args.standard not in std.known_standards():
        print(f"ERROR: unknown standard {args.standard!r}; "
              f"known: {sorted(std.known_standards())}")
        return 2

    corpus = None if args.no_corpus else args.corpus
    blockers, warnings = audit(std, args.standard, DEFAULT_KIT_MIDIMAPS, corpus)

    print(f"=== MIDI Coherence Audit — standard={args.standard} ===")
    print(f"corpus: {corpus if corpus else '(skipped)'}")
    print(f"kits: {', '.join(DEFAULT_KIT_MIDIMAPS)}")
    print()
    if blockers:
        print(f"BLOCKERS ({len(blockers)}):")
        for m in blockers:
            print(f"  {m}")
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for m in warnings:
            print(f"  {m}")
    if not blockers and not warnings:
        print("✓ full coherence: every corpus note is handled, every canonical "
              "render note is present in every kit.")

    print()
    if blockers:
        print(f"RESULT: FAIL ({len(blockers)} blockers)")
        return 1
    if warnings and args.strict:
        print(f"RESULT: FAIL (--strict: {len(warnings)} warnings)")
        return 1
    print(f"RESULT: PASS ({len(warnings)} warnings, non-blocking)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
