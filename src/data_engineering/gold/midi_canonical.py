"""MIDI Standard Translation Layer — source standard -> canonical GM (F0-T18).

The single seam that reconciles the **divergent MIDI numbering standards** used
by our sources (General MIDI vs Roland TD-11) with the standards expected by the
downstream consumers (DrumGizmo midimaps, SFZ key regions, the GM->bus mapping
table). It exists because the same physical drum hit carries different note
numbers across standards — e.g. the GMD (Magenta Groove MIDI Dataset) uses the
Roland TD-11 map where the hi-hat "edge" articulations are notes 22/26, absent
from General MIDI. Without translation, those hits fall through every consumer
silently (Pipeline Audit 2026-05-28: GM 22/26 = 10 % of all GMD onsets, 34 % of
all hi-hat, dropped from both audio and target).

:func:`canonicalize_midi` reads a source MIDI, maps every drum note through the
declared source standard onto a **canonical articulation**, and emits a new MIDI
whose notes are the articulation's canonical GM render note (e.g. 22 -> 42,
26 -> 46, 58 -> 43). That single canonical MIDI then feeds BOTH the render
engines and the target builder — the two views can no longer diverge.

**Fail-loud (Decision Lock CEO 2026-05-28, the cardinal principle):** every
source note is *either* mapped to an articulation *or* listed in the standard's
``ignored`` registry with a reason. Anything in neither raises
:class:`CanonicalizationError` — never a silent drop.

Spec: ``docs/methodology/F0-T18_MIDI_STANDARD_TRANSLATION_SPEC.md``;
SSoT: ``docs/specs/midi_source_standards.yaml``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mido  # type: ignore[import-untyped]
import yaml

#: Repo root, resolved from ``src/data_engineering/gold/midi_canonical.py``.
_REPO_ROOT = Path(__file__).resolve().parents[3]
#: The versioned source-standards SSoT (F0-T18).
DEFAULT_STANDARDS_PATH = _REPO_ROOT / "docs" / "specs" / "midi_source_standards.yaml"
#: Number of logical transcription buses (F0-T2a §3.3).
N_BUSES = 8


class CanonicalizationError(ValueError):
    """Raised when a MIDI cannot be canonicalized against a source standard."""


@dataclass(frozen=True)
class Articulation:
    """One canonical articulation and its projections (SSoT ``articulations``)."""

    name: str
    render_gm: int
    bus: int  # 1-based, aligned to midi_mapping_table.yaml
    hihat_opening: float | None = None


@dataclass(frozen=True)
class SourceStandards:
    """The loaded + validated source-standards SSoT (F0-T18)."""

    articulations: dict[str, Articulation]
    #: ``standard_name -> {source_note -> articulation_name}``.
    standards: dict[str, dict[int, str]]
    #: ``standard_name -> {source_note -> reason}`` (explicit ignore registry).
    ignored: dict[str, dict[int, str]]
    schema_version: str

    def known_standards(self) -> frozenset[str]:
        return frozenset(self.standards)

    def render_note(self, standard: str, source_note: int) -> int | None:
        """Canonical render GM note for ``source_note`` under ``standard``.

        Returns ``None`` when the note is in the standard's ``ignored`` registry
        (a deliberate, documented drop). Raises when the note is in neither the
        mapping nor the ignore registry (the fail-loud guarantee).
        """
        self._require_standard(standard)
        art_name = self.standards[standard].get(source_note)
        if art_name is not None:
            return self.articulations[art_name].render_gm
        if source_note in self.ignored.get(standard, {}):
            return None
        raise CanonicalizationError(
            f"note {source_note} is not mapped by standard {standard!r} and is "
            f"not in its 'ignored' registry — refusing to drop it silently "
            f"(Decision Lock CEO 2026-05-28). Add it to "
            f"midi_source_standards.yaml under standards.{standard} or "
            f"ignored.{standard}."
        )

    def articulation_for(self, standard: str, source_note: int) -> Articulation | None:
        """The :class:`Articulation` for ``source_note`` (``None`` if ignored)."""
        self._require_standard(standard)
        art_name = self.standards[standard].get(source_note)
        if art_name is None:
            return None
        return self.articulations[art_name]

    def _require_standard(self, standard: str) -> None:
        if standard not in self.standards:
            raise CanonicalizationError(
                f"unknown source standard {standard!r}; known: "
                f"{sorted(self.standards)}"
            )


def load_source_standards(path: str | Path = DEFAULT_STANDARDS_PATH) -> SourceStandards:
    """Load + validate ``midi_source_standards.yaml`` (F0-T18).

    Raises:
        CanonicalizationError: On unreadable/invalid YAML, or any violation of
            the SSoT contract (missing blocks, bad bus ids, articulation names
            referenced by a standard but undefined, etc.).
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CanonicalizationError(f"cannot read standards SSoT {file_path}: {exc}") from exc
    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CanonicalizationError(f"standards SSoT is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise CanonicalizationError("standards SSoT: expected a top-level mapping")

    version = raw.get("schema_version")
    if not isinstance(version, str) or not version:
        raise CanonicalizationError("standards SSoT: missing 'schema_version'")

    # --- articulations ---
    raw_arts = raw.get("articulations")
    if not isinstance(raw_arts, dict) or not raw_arts:
        raise CanonicalizationError("standards SSoT: missing or empty 'articulations'")
    arts: dict[str, Articulation] = {}
    for name, body in raw_arts.items():
        if not isinstance(name, str) or not name:
            raise CanonicalizationError(f"standards SSoT: bad articulation name {name!r}")
        if not isinstance(body, dict):
            raise CanonicalizationError(f"standards SSoT: articulation {name} is not a mapping")
        render_gm = body.get("render_gm")
        bus = body.get("bus")
        if not isinstance(render_gm, int) or isinstance(render_gm, bool):
            raise CanonicalizationError(
                f"standards SSoT: articulation {name} render_gm {render_gm!r} not an int"
            )
        if not 0 <= render_gm <= 127:
            raise CanonicalizationError(
                f"standards SSoT: articulation {name} render_gm {render_gm} out of MIDI range"
            )
        if not isinstance(bus, int) or isinstance(bus, bool):
            raise CanonicalizationError(
                f"standards SSoT: articulation {name} bus {bus!r} not an int"
            )
        if not 1 <= bus <= N_BUSES:
            raise CanonicalizationError(
                f"standards SSoT: articulation {name} bus {bus} outside [1, {N_BUSES}]"
            )
        hho = body.get("hihat_opening")
        if hho is not None and not (isinstance(hho, (int, float)) and 0.0 <= float(hho) <= 1.0):
            raise CanonicalizationError(
                f"standards SSoT: articulation {name} hihat_opening {hho!r} outside [0, 1]"
            )
        arts[name] = Articulation(
            name=name, render_gm=int(render_gm), bus=int(bus),
            hihat_opening=None if hho is None else float(hho),
        )

    # --- standards ---
    raw_standards = raw.get("standards")
    if not isinstance(raw_standards, dict) or not raw_standards:
        raise CanonicalizationError("standards SSoT: missing or empty 'standards'")
    standards: dict[str, dict[int, str]] = {}
    for std_name, body in raw_standards.items():
        if not isinstance(std_name, str) or not std_name:
            raise CanonicalizationError(f"standards SSoT: bad standard name {std_name!r}")
        if not isinstance(body, dict) or not body:
            raise CanonicalizationError(f"standards SSoT: standard {std_name} is empty")
        note_map: dict[int, str] = {}
        for note, art_name in body.items():
            if not isinstance(note, int) or isinstance(note, bool) or not 0 <= note <= 127:
                raise CanonicalizationError(
                    f"standards SSoT: standard {std_name} note {note!r} not a MIDI note"
                )
            if art_name not in arts:
                raise CanonicalizationError(
                    f"standards SSoT: standard {std_name} note {note} -> undefined "
                    f"articulation {art_name!r}"
                )
            note_map[note] = art_name
        standards[std_name] = note_map

    # --- ignored (optional per standard) ---
    raw_ignored = raw.get("ignored", {})
    if not isinstance(raw_ignored, dict):
        raise CanonicalizationError("standards SSoT: 'ignored' must be a mapping")
    ignored: dict[str, dict[int, str]] = {}
    for std_name, body in raw_ignored.items():
        body = body or {}
        if not isinstance(body, dict):
            raise CanonicalizationError(f"standards SSoT: ignored.{std_name} must be a mapping")
        entry: dict[int, str] = {}
        for note, reason in body.items():
            if not isinstance(note, int) or isinstance(note, bool) or not 0 <= note <= 127:
                raise CanonicalizationError(
                    f"standards SSoT: ignored.{std_name} note {note!r} not a MIDI note"
                )
            entry[note] = str(reason)
        ignored[std_name] = entry
    for std_name in standards:
        ignored.setdefault(std_name, {})

    return SourceStandards(
        articulations=arts, standards=standards, ignored=ignored,
        schema_version=version,
    )


def canonicalize_midi(
    midi_path: str | Path,
    *,
    standard: str,
    out_path: str | Path,
    standards: SourceStandards | None = None,
) -> dict[str, int]:
    """Translate ``midi_path`` from ``standard`` into a canonical GM MIDI.

    Every drum note_on/note_off is remapped to its articulation's canonical
    render GM note (e.g. Roland TD-11 22 -> 42). Notes in the standard's
    ``ignored`` registry are dropped (both on and off). A note in neither the
    mapping nor the ignore registry raises :class:`CanonicalizationError` — the
    fail-loud guarantee against silent drops.

    Timing, velocity, and all non-note messages (tempo, time signature, etc.)
    are preserved verbatim, so the canonical MIDI is time-identical to the
    source.

    Args:
        midi_path: Source drum MIDI file.
        standard: Source standard name (must exist in the SSoT, e.g.
            ``"roland_td11"`` for the GMD).
        out_path: Where to write the canonical MIDI.
        standards: Pre-loaded SSoT; loaded from the default path if ``None``.

    Returns:
        A remap histogram ``{"<src>-><dst>": count}`` plus ``"_ignored"`` and
        ``"_total"`` keys — useful for audit logging and Ocular Proof.

    Raises:
        CanonicalizationError: On an unreadable/malformed MIDI, an unknown
            standard, or any note that is neither mapped nor explicitly ignored.
    """
    src = Path(midi_path)
    std = standards if standards is not None else load_source_standards()
    std._require_standard(standard)
    if not src.is_file():
        raise CanonicalizationError(f"MIDI file not found: {src}")
    try:
        midi = mido.MidiFile(str(src))
    except (OSError, ValueError, EOFError, KeyError, IndexError) as exc:
        raise CanonicalizationError(f"cannot parse MIDI file {src}: {exc}") from exc

    hist: dict[str, int] = {}
    n_ignored = 0
    n_total = 0

    out = mido.MidiFile(ticks_per_beat=midi.ticks_per_beat, type=midi.type)
    for track in midi.tracks:
        new_track = mido.MidiTrack()
        # When a note is dropped (ignored), we must also drop its matching
        # note_off, but preserve the delta-time so downstream events stay in
        # place: a dropped message's ``.time`` is rolled into the next kept one.
        pending_delta = 0
        for msg in track:
            is_note = msg.type in ("note_on", "note_off")
            if not is_note:
                msg2 = msg.copy(time=msg.time + pending_delta)
                pending_delta = 0
                new_track.append(msg2)
                continue
            # note_on with velocity 0 is a note_off by convention — count only
            # genuine onsets in the histogram, but remap both.
            n_total += 1 if (msg.type == "note_on" and msg.velocity > 0) else 0
            render = std.render_note(standard, msg.note)  # fail-loud here
            if render is None:
                # ignored: drop the message, carry its delta to the next one
                pending_delta += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    n_ignored += 1
                continue
            if msg.type == "note_on" and msg.velocity > 0:
                key = f"{msg.note}->{render}"
                hist[key] = hist.get(key, 0) + 1
            new_track.append(msg.copy(note=render, time=msg.time + pending_delta))
            pending_delta = 0
        out.tracks.append(new_track)

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out.save(str(out_p))

    hist["_ignored"] = n_ignored
    hist["_total"] = n_total
    return hist


__all__ = [
    "Articulation",
    "CanonicalizationError",
    "DEFAULT_STANDARDS_PATH",
    "SourceStandards",
    "canonicalize_midi",
    "load_source_standards",
]
