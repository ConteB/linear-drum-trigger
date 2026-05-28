"""F0-T19 Canonical I/O Mapping Layer — Arrow ② (canonical → kit dialect, render).

Our internal canonical is Roland-TD11-derived GM render notes (F0-T18). Each render
kit/engine, however, wants its own dialect:

* **DrumGizmo** — we *generate* a per-kit midimap (canonical note → that kit's
  instrument name), instead of patching the vendor's shipped midimap.
* **Sfizz** — the key layout is baked into the ``.sfz``; we *remap* the canonical
  MIDI notes to the keys the ``.sfz`` declares.

The single source of truth is ``docs/specs/kit_dialect_map.yaml`` (authored from
each kit's own files, validated by ``tools/poc_validate_dialect_maps.py`` and
``tools/poc_validate_sfizz_dialect.py`` — 0 phantom on all 6 mini-DB kits). A kit
that is not in the map raises (caller decides fallback); a canonical note with no
entry for a mapped kit raises — **no silent drops** (the cardinal F0-T18 principle).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import mido  # type: ignore[import-untyped]
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DIALECT_PATH = _REPO_ROOT / "docs" / "specs" / "kit_dialect_map.yaml"

_NOTE_MESSAGES = ("note_on", "note_off")


class DialectError(ValueError):
    """Raised on any dialect-mapping fault (fail-loud)."""


def load_dialect_map(path: str | Path = DEFAULT_DIALECT_PATH) -> dict[str, Any]:
    """Load the per-kit dialect SSoT, returning its ``kits`` mapping."""
    data = yaml.safe_load(Path(path).read_text())
    kits = data.get("kits") if isinstance(data, dict) else None
    if not isinstance(kits, dict):
        raise DialectError(f"dialect map at {path} has no 'kits' mapping")
    return cast("dict[str, Any]", kits)


def has_kit(kit_label: str, *, dialect_map: dict[str, Any] | None = None) -> bool:
    """True if ``kit_label`` has a dialect entry (caller's gate for the F0-T19 path)."""
    kits = dialect_map if dialect_map is not None else load_dialect_map()
    return kit_label in kits


def _kit_cfg(kit_label: str, dialect_map: dict[str, Any] | None) -> dict[str, Any]:
    kits = dialect_map if dialect_map is not None else load_dialect_map()
    if kit_label not in kits:
        raise DialectError(
            f"kit {kit_label!r} not in dialect map (have: {sorted(kits)})"
        )
    return cast("dict[str, Any]", kits[kit_label])


def _trigger(value: Any, *, want: str) -> Any:
    """Extract the trigger from a map value (plain, or a {want|substitute} dict)."""
    if isinstance(value, dict):
        if want not in value:
            raise DialectError(f"map entry {value!r} missing required key {want!r}")
        return value[want]
    return value


def drumgizmo_note_map(
    kit_label: str, *, dialect_map: dict[str, Any] | None = None
) -> dict[int, str]:
    """``canonical note -> instrument name`` for a DrumGizmo kit (fail-loud)."""
    cfg = _kit_cfg(kit_label, dialect_map)
    if cfg.get("engine") != "drumgizmo":
        raise DialectError(f"kit {kit_label!r} is not a drumgizmo kit")
    return {int(n): str(_trigger(v, want="instr")) for n, v in cfg["map"].items()}


def sfizz_key_map(
    kit_label: str, *, dialect_map: dict[str, Any] | None = None
) -> dict[int, int]:
    """``canonical note -> .sfz key`` for a Sfizz kit (fail-loud)."""
    cfg = _kit_cfg(kit_label, dialect_map)
    if cfg.get("engine") != "sfizz":
        raise DialectError(f"kit {kit_label!r} is not a sfizz kit")
    return {int(n): int(_trigger(v, want="key")) for n, v in cfg["map"].items()}


def generate_drumgizmo_midimap(
    kit_label: str, out_path: str | Path, *, dialect_map: dict[str, Any] | None = None
) -> Path:
    """Write a DrumGizmo midimap (canonical note → kit instrument) for ``kit_label``."""
    note_map = drumgizmo_note_map(kit_label, dialect_map=dialect_map)
    rows = "\n".join(
        f'  <map note="{n}" instr="{instr}"/>' for n, instr in sorted(note_map.items())
    )
    out = Path(out_path)
    out.write_text(f"<?xml version='1.0' encoding='UTF-8'?>\n<midimap>\n{rows}\n</midimap>\n")
    return out


def remap_sfizz_midi(
    kit_label: str,
    in_midi: str | Path,
    out_midi: str | Path,
    *,
    dialect_map: dict[str, Any] | None = None,
) -> Path:
    """Rewrite ``in_midi`` note numbers to the keys ``kit_label``'s .sfz declares.

    Every drum ``note_on``/``note_off`` whose note has no entry in the kit's map
    raises :class:`DialectError` — no silent drops. Timing/velocity are preserved.
    """
    key_map = sfizz_key_map(kit_label, dialect_map=dialect_map)
    mf = mido.MidiFile(str(in_midi))
    for track in mf.tracks:
        for msg in track:
            if msg.type in _NOTE_MESSAGES:
                if msg.note not in key_map:
                    raise DialectError(
                        f"canonical note {msg.note} has no {kit_label!r} dialect "
                        f"entry (no silent drop); mapped notes: {sorted(key_map)}"
                    )
                msg.note = key_map[msg.note]
    out = Path(out_midi)
    mf.save(str(out))
    return out
