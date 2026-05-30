"""F0-T20 Franken-Kit — cross-kit combinatorial render (per-instrument render + sum).

LOCKED v1.0.0 (Decision Lock CEO 2026-05-30,
``docs/methodology/F0-T20_CROSS_KIT_AUGMENTATION_SPEC.md``).

Each Gold sample becomes a *hybrid kit*: the canonical MIDI is split by instrument
family (kick / snare / hihat / tom / ride / crash / aux), each family is rendered
through a **different** kit drawn from a single-engine pool (D2 within-engine v1.0),
and the per-family 8-bus renders are **summed** (StemGMD superposition). This attacks
the *timbral* kit-fingerprint that F0-T4e could not (it only removed the channel-layout
fingerprint) — the direct cause of the saturated mini-L3 floor.

The target matrix is built from the **full** canonical MIDI and is therefore identical
to the single-kit case: the franken-kit changes only the audio, never the label.

Determinism (ENG §1): the instrument->kit assignment is derived from
``sha256(master_seed ‖ source_midi_id ‖ variant_idx ‖ instrument)`` so the hybrid kit
replays bit-identically. Fail-loud (ENG §6): every per-family render is fail-loud and
the summed buffer is checked for NaN/Inf and peak ∈ (0, 1].
"""
from __future__ import annotations

import hashlib
import tempfile
from dataclasses import replace
from pathlib import Path

import mido  # type: ignore[import-untyped]
import numpy as np

from data_engineering.gold.dna_trace import (
    build_dna_json,
    encode_barcode,
    validate_dna_json,
)
from data_engineering.gold.gold_writer import SAMPLE_RATE, write_gold_sample
from data_engineering.gold.midi_canonical import canonicalize_midi
from data_engineering.gold.orchestrate import (
    REPO_ROOT,
    TAIL_S,
    GoldSampleResult,
    OrchestrationError,
    _render,
    derive_barcode,
    n_sample_target,
    standardize_audio_tail,
    wav_to_audio_buffer,
)
from data_engineering.gold.recipe import Recipe
from data_engineering.gold.render import RenderError
from data_engineering.gold.target_builder import (
    BusMapping,
    build_target,
    last_onset_seconds,
)

# ---------------------------------------------------------------------------
# Instrument families — canonical GM render note -> family (F0-T20 §4.1).
# Each family is rendered by ONE assigned kit; the families are summed.
# Aligned with the canonical articulations in midi_source_standards.yaml
# (36 kick · 37 side_stick · 38 snare · 42/44/46 hihat · 47/48/43 tom ·
#  51 ride · 53 ride_bell · 49/57 crash · 52 china · 55 splash). The
# INSTRUMENT_NOTES set is asserted complete against the SSoT by an oracle.
# ---------------------------------------------------------------------------
INSTRUMENT_GROUPS: dict[str, frozenset[int]] = {
    "kick": frozenset({36}),
    "snare": frozenset({37, 38}),
    "hihat": frozenset({42, 44, 46}),
    "tom": frozenset({43, 47, 48}),
    "ride": frozenset({51, 53}),
    "crash": frozenset({49, 57}),
    "aux": frozenset({52, 55}),
}

#: Every canonical render note that has a family (used for fail-loud routing).
INSTRUMENT_NOTES: frozenset[int] = frozenset().union(*INSTRUMENT_GROUPS.values())

#: Stable iteration order for the families (determinism of the sum + barcode).
INSTRUMENT_ORDER: tuple[str, ...] = (
    "kick", "snare", "hihat", "tom", "ride", "crash", "aux",
)


class FrankenError(ValueError):
    """Raised when a franken-kit render cannot be assembled (fail-loud)."""


def _note_family(note: int) -> str:
    for fam, notes in INSTRUMENT_GROUPS.items():
        if note in notes:
            return fam
    raise FrankenError(
        f"canonical note {note} has no instrument family — INSTRUMENT_GROUPS "
        f"is out of sync with the canonical articulation set"
    )


def split_midi_by_instrument(midi: mido.MidiFile) -> dict[str, mido.MidiFile]:
    """Split a (canonical) MIDI into one MIDI per instrument family.

    Tempo / time-signature / key-signature meta is replicated into **every**
    family so each renders with correct timing. ``control_change`` (e.g. CC#4
    hi-hat pedal) is routed to the ``hihat`` family. Note events are routed by
    note number; a canonical note with no family is fail-loud.

    Returns only the families that carry at least one note (empty families are
    skipped — nothing to render).
    """
    # Flatten to absolute-time events on a single timeline.
    abs_events: list[tuple[int, mido.Message | mido.MetaMessage]] = []
    for track in midi.tracks:
        t = 0
        for msg in track:
            t += msg.time
            abs_events.append((t, msg))
    abs_events.sort(key=lambda e: e[0])

    META_ALL = {"set_tempo", "time_signature", "key_signature"}
    per_fam_events: dict[str, list[tuple[int, mido.Message | mido.MetaMessage]]] = {
        fam: [] for fam in INSTRUMENT_GROUPS
    }

    for t, msg in abs_events:
        if msg.is_meta:
            if msg.type in META_ALL:
                for fam in per_fam_events:
                    per_fam_events[fam].append((t, msg.copy()))
            continue
        if msg.type == "control_change":
            per_fam_events["hihat"].append((t, msg.copy()))
            continue
        if msg.type in ("note_on", "note_off"):
            fam = _note_family(int(msg.note))
            per_fam_events[fam].append((t, msg.copy()))

    out: dict[str, mido.MidiFile] = {}
    for fam in INSTRUMENT_ORDER:
        events = per_fam_events[fam]
        has_note = any(
            (not m.is_meta) and m.type in ("note_on", "note_off") for _, m in events
        )
        if not has_note:
            continue
        fam_midi = mido.MidiFile(ticks_per_beat=midi.ticks_per_beat)
        track = mido.MidiTrack()
        events.sort(key=lambda e: e[0])
        prev = 0
        for t, msg in events:
            m = msg.copy()
            m.time = t - prev
            prev = t
            track.append(m)
        track.append(mido.MetaMessage("end_of_track", time=0))
        fam_midi.tracks.append(track)
        out[fam] = fam_midi
    return out


def derive_franken_assignment(
    *,
    instruments: list[str],
    kit_labels: tuple[str, ...],
    master_seed: int,
    source_midi_id: str,
    variant_idx: int,
) -> dict[str, str]:
    """Deterministically assign a kit to each instrument family (sha256).

    Independent draw per (instrument) so the hybrid is reproducible and
    auditable. Two different families may land on the same kit — that is fine
    (a partially-franken sample is still a valid hybrid).
    """
    if not kit_labels:
        raise FrankenError("kit_labels is empty — nothing to assign")
    assignment: dict[str, str] = {}
    for instr in instruments:
        h = hashlib.sha256(
            f"{master_seed}|{source_midi_id}|{variant_idx}|{instr}".encode()
        ).digest()
        idx = int.from_bytes(h[:8], "big") % len(kit_labels)
        assignment[instr] = kit_labels[idx]
    return assignment


def build_franken_gold_sample(
    template: Recipe,
    *,
    kit_pool: dict[str, Recipe],
    out_dir: str | Path,
    bus_mapping: BusMapping,
    franken_kit_label: str,
    master_seed: int,
    variant_idx: int,
    repo_root: str | Path = REPO_ROOT,
    midi_path_override: str | Path | None = None,
) -> tuple[GoldSampleResult, dict[str, str]]:
    """Render one franken-kit Gold sample (per-instrument render + sum).

    Args:
        template: A validated recipe used for split/target/dna identity. Its
            ``render`` block is replaced per-instrument by the assigned kit.
            ``template.render.engine`` must match every kit in ``kit_pool``
            (D2 within-engine v1.0).
        kit_pool: ``{kit_label: recipe_with_that_kit}`` — the single-engine pool
            the instruments are drawn from. Each recipe's ``render`` block
            supplies engine/kit/kit_path/mic_config for that kit.
        franken_kit_label: synthetic kit label written into the barcode/dna
            (the hybrid identity, e.g. ``"FK"`` + short hash).
        master_seed / variant_idx: anchor the deterministic kit assignment.

    Returns:
        ``(GoldSampleResult, assignment)`` where ``assignment`` is the
        ``{instrument: kit_label}`` provenance (write it to a sidecar).
    """
    root = Path(repo_root)
    source_midi = root / template.midi_source.file
    if not source_midi.is_file():
        raise OrchestrationError(f"recipe MIDI source not found: {source_midi}")
    midi_path = (
        Path(midi_path_override) if midi_path_override is not None else source_midi
    )
    if not midi_path.is_file():
        raise OrchestrationError(f"midi path not found: {midi_path}")

    kit_labels = tuple(sorted(kit_pool))
    engines = {r.render.engine for r in kit_pool.values()} | {template.render.engine}
    if len(engines) != 1:
        raise FrankenError(
            f"franken pool mixes engines {engines} — D2 is within-engine v1.0"
        )

    with tempfile.TemporaryDirectory(prefix="franken_") as tmp:
        tmpd = Path(tmp)
        # 1. Canonicalize once (F0-T18) — the single canonical MIDI feeds split,
        #    target and last_onset alike (no divergence).
        if template.midi_source.standard is not None:
            canon = tmpd / "canonical.mid"
            canonicalize_midi(
                midi_path, standard=template.midi_source.standard, out_path=canon
            )
            midi_path = canon

        # 2. Geometry from the FULL canonical MIDI (engine-uniform tail).
        last_onset_s = last_onset_seconds(midi_path, bus_mapping=bus_mapping)
        n_sample_out = n_sample_target(last_onset_s, tail_s=TAIL_S)
        duration_s = n_sample_out / SAMPLE_RATE

        # 3. Split by instrument + deterministic kit assignment.
        fam_midis = split_midi_by_instrument(mido.MidiFile(str(midi_path)))
        assignment = derive_franken_assignment(
            instruments=list(fam_midis),
            kit_labels=kit_labels,
            master_seed=master_seed,
            source_midi_id=template.midi_source.file,
            variant_idx=variant_idx,
        )

        # 4. Render each family through its assigned kit, standardize, sum.
        summed: np.ndarray | None = None
        for fam in INSTRUMENT_ORDER:
            if fam not in fam_midis:
                continue
            kit_recipe = kit_pool[assignment[fam]]
            fam_midi_path = tmpd / f"{fam}.mid"
            fam_midis[fam].save(str(fam_midi_path))
            wav_path = tmpd / f"{fam}.wav"
            render_recipe = replace(template, render=kit_recipe.render)
            kit_path = root / kit_recipe.render.kit_path
            if not kit_path.is_file():
                raise OrchestrationError(f"franken kit not found: {kit_path}")
            try:
                _render(render_recipe, fam_midi_path, kit_path, wav_path)
            except RenderError as exc:
                # A single instrument family that renders silent (the assigned
                # kit lacks that articulation) is a legitimate hybrid outcome —
                # it contributes zero to the sum, it must NOT kill the sample.
                # The silent-zero guard still applies to the FULL sum below.
                if "silent-zero" in str(exc):
                    continue
                raise
            rendered, _ = wav_to_audio_buffer(wav_path)
            chunk = standardize_audio_tail(rendered, n_sample_out).astype(np.float32)
            summed = chunk if summed is None else summed + chunk

        if summed is None:
            raise FrankenError("no renderable instrument families in MIDI")

        # 5. Fail-loud on the sum (ENG §6) + peak-safety (closes audit M6).
        if not np.isfinite(summed).all():
            raise FrankenError("franken sum produced NaN/Inf")
        peak = float(np.abs(summed).max())
        if peak <= 0.0:
            raise FrankenError("franken sum is silent (peak == 0)")
        if peak > 1.0:
            summed = summed / peak  # normalize the franken superposition into [-1, 1]
        audio = np.ascontiguousarray(summed, dtype=np.float16)

        # 6. Target from the FULL canonical MIDI — identical to the single-kit case.
        target = build_target(
            midi_path,
            duration_s=duration_s,
            bus_mapping=bus_mapping,
            r_target_hz=template.target_frame_rate_hz,
        )

    # 7. Barcode/dna under the synthetic franken kit identity.
    dna_recipe = replace(
        template, render=replace(template.render, kit=franken_kit_label)
    )
    barcode = derive_barcode(dna_recipe)
    key = encode_barcode(barcode)
    dna = build_dna_json(
        barcode=barcode,
        recipe=dna_recipe,
        audio=audio,
        target=target,
        last_onset_s=last_onset_s,
        tail_s=TAIL_S,
    )
    written_dir = write_gold_sample(out_dir, key, audio=audio, target=target, dna=dna)
    validate_dna_json(dna, audio=audio, target=target)

    result = GoldSampleResult(
        key=key,
        recipe_id=template.recipe_id,
        engine=template.render.engine,
        out_dir=written_dir,
        n_mic=int(audio.shape[0]),
        n_sample=int(audio.shape[1]),
        n_frame=int(target.shape[0]),
        audio_peak=peak,
        last_onset_s=last_onset_s,
        tail_s=TAIL_S,
    )
    return result, assignment
