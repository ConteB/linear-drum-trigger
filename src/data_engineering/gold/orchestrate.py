"""Pipeline orchestrator — recipe -> Gold sample (F0-T2e).

The single seam that joins the F0 render pipeline end-to-end: it takes one
validated :class:`~data_engineering.gold.recipe.Recipe` and drives it through

    recipe -> render (Sfizz / DrumGizmo) -> audio.f16 + target.f16 -> dna.json

It owns no DSP of its own — it wires the modules built by F0-T2b/c/d plus the
:mod:`~data_engineering.gold.target_builder`, and verifies the result with
:func:`~data_engineering.gold.dna_trace.validate_dna_json` before returning.

Fail-loud (ENGINEERING_STANDARDS §6): any failure of any stage raises
:class:`OrchestrationError` (or the stage's own error) and no partial Gold
sample is left behind for a caller to mistake for a complete one.

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §3;
``04_INTELLIGENCE/MASTER_SCHEDULING.md`` §6 F0-T2e.
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import mido  # type: ignore[import-untyped]
import numpy as np
import soundfile as sf  # type: ignore[import-untyped]

from data_engineering.gold.dna_trace import (
    Barcode,
    build_dna_json,
    encode_barcode,
    validate_dna_json,
)
from data_engineering.gold.gold_writer import SAMPLE_RATE, write_gold_sample
from data_engineering.gold.recipe import Engine, Recipe
from data_engineering.gold.render import (
    DRSKIT_MULTITRACK8,
    channel_map_for_kit,
    DrumGizmoRenderer,
    RenderError,
    SfizzRenderer,
)
from data_engineering.gold.target_builder import (
    BusMapping,
    build_target,
    last_onset_seconds,
)

#: Repo root, resolved from ``src/data_engineering/gold/orchestrate.py``.
REPO_ROOT = Path(__file__).resolve().parents[3]
#: The versioned GM <-> 8-bus mapping table (F0-T2a §1.1).
DEFAULT_BUS_MAPPING_PATH = REPO_ROOT / "docs" / "specs" / "midi_mapping_table.yaml"
#: Standardized tail after the last mapped onset (F0-T2a §3.8, Decision Lock
#: 2026-05-23). Uniform across engines — anti-shortcut against the model
#: learning ``tail signature -> engine``.
TAIL_S = 0.5
#: Tail appended to a DrumGizmo render so the cymbal / ambience decay is captured
#: in the renderer's output before being trimmed to :data:`TAIL_S`. DrumGizmo
#: needs the output length up front (CLI ``--endpos``); Sfizz stops on its own,
#: so this value is engine-internal — it does NOT leak to the Gold sample, the
#: standardisation in :func:`standardize_audio_tail` is the source of truth.
_DRUMGIZMO_RENDER_TAIL_S = 5.0
#: Velocity-jitter ordinal for the barcode ``MIDIALT`` segment (F0-T2a §4.1).
_VELOCITY_JITTER_CODE = {"none": 0, "ghost_mask": 1, "gain_shift": 2, "both": 3}


def n_sample_target(last_onset_s: float, *, tail_s: float = TAIL_S) -> int:
    """Gold-sample target audio length in samples (F0-T2a §3.8).

    The same formula for every engine: ``round((last_onset_s + tail_s) *
    sample_rate)``. This is the only contractually visible duration — the
    rendered tail beyond it is engine-internal and trimmed away.

    Args:
        last_onset_s: Time of the last mapped drum onset, in seconds.
        tail_s: Standardised tail length; defaults to the locked
            :data:`TAIL_S`.

    Returns:
        The standardised audio sample count.

    Raises:
        OrchestrationError: If either argument is negative.
    """
    if last_onset_s < 0.0:
        raise OrchestrationError(f"last_onset_s must be >= 0, got {last_onset_s}")
    if tail_s < 0.0:
        raise OrchestrationError(f"tail_s must be >= 0, got {tail_s}")
    return int(round((last_onset_s + tail_s) * SAMPLE_RATE))


def standardize_audio_tail(audio: np.ndarray, n_sample_out: int) -> np.ndarray:
    """Trim or zero-pad ``audio`` to exactly ``n_sample_out`` samples.

    The engine-uniform writer policy (F0-T2a §3.8, Decision Lock 2026-05-23):
    every engine renders past the last onset with its own natural decay; the
    Gold writer crops that decay (or pads with silence when the engine stopped
    early) so the Gold-sample duration is determined only by the MIDI source.

    Args:
        audio: A ``[n_mic, n_sample]`` float16 buffer produced by the renderer.
        n_sample_out: Target sample count (typically from
            :func:`n_sample_target`).

    Returns:
        A ``[n_mic, n_sample_out]`` float16 buffer, C-contiguous. The original
        buffer is returned unchanged when its length already matches.

    Raises:
        OrchestrationError: If ``audio`` is not 2-D or ``n_sample_out`` is
            not strictly positive.
    """
    if audio.ndim != 2:
        raise OrchestrationError(
            f"standardize_audio_tail expects a 2-D buffer, got {audio.ndim}-D"
        )
    if n_sample_out <= 0:
        raise OrchestrationError(
            f"n_sample_out must be > 0, got {n_sample_out}"
        )
    n_mic, n_sample = audio.shape
    if n_sample == n_sample_out:
        return np.ascontiguousarray(audio, dtype=np.float16)
    if n_sample > n_sample_out:
        return np.ascontiguousarray(audio[:, :n_sample_out], dtype=np.float16)
    # Renderer stopped before the standardised tail; pad with silence so the
    # padded region carries no engine signature at all.
    out = np.zeros((n_mic, n_sample_out), dtype=np.float16)
    out[:, :n_sample] = audio
    return out


class OrchestrationError(RuntimeError):
    """Raised when the recipe -> Gold-sample pipeline cannot complete."""


@dataclass(frozen=True)
class GoldSampleResult:
    """Verified outcome of one orchestrated Gold sample.

    Attributes:
        key: The WebDataset sample key (the DNA barcode, dot-free).
        recipe_id: The originating recipe's id.
        engine: The render engine used.
        out_dir: Directory holding the ``{key}.audio.f16`` / ``.target.f16`` /
            ``.dna.json`` triple.
        n_mic: Microphone channel count of the ``audio`` buffer.
        n_sample: Samples per channel of the ``audio`` buffer (= ``round(
            (last_onset_s + tail_s) * sample_rate)``, F0-T2a §3.8).
        n_frame: Frame count of the ``target`` matrix.
        audio_peak: Largest absolute audio amplitude (strictly ``> 0``).
        last_onset_s: Time of the last mapped drum onset in the MIDI source,
            in seconds — the anchor of the engine-uniform tail standardisation.
        tail_s: Standardised tail length (F0-T2a §3.8) — uniform across engines.
    """

    key: str
    recipe_id: str
    engine: Engine
    out_dir: Path
    n_mic: int
    n_sample: int
    n_frame: int
    audio_peak: float
    last_onset_s: float
    tail_s: float


def _digit_token(text: str) -> str:
    """Return the first digit-run of ``text`` as a 3-char token, else a hash."""
    match = re.search(r"\d+", text)
    if match:
        return match.group()[-3:].rjust(3, "0")
    return f"{abs(hash(text)) % 1000:03d}"


def derive_barcode(recipe: Recipe) -> Barcode:
    """Derive a deterministic seven-segment DNA barcode from a recipe (F0-T2a §4.1).

    Every segment is dot-free and dash-free by construction, so the encoded key
    survives WebDataset's extension splitting (F0-T2a §3.1). The mapping is a
    pure function of the recipe: the same recipe always yields the same key.

    The ``jittervar`` segment (``J{idx:02d}``) — added by the 7-segment
    amendment of Decision Lock CEO 2026-05-23 (B3 of F0-T15-pre) — disambiguates
    the ``k+1`` jittered variants produced by the MIDI augmentation pipeline.

    Args:
        recipe: The validated recipe.

    Returns:
        The sample's :class:`Barcode`.
    """
    midi_stem = Path(recipe.midi_source.file).stem
    midisrc = f"{recipe.midi_source.dataset}{_digit_token(midi_stem)}"

    v_code = _VELOCITY_JITTER_CODE[recipe.midi_jitter.velocity_jitter.value]
    low, high = recipe.midi_jitter.time_jitter_ms
    t_code = 0 if low == 0.0 and high == 0.0 else 1
    midialt = f"V{v_code}T{t_code}"
    jittervar = f"J{recipe.midi_jitter.variant_idx:02d}"

    engine = "SFZ" if recipe.render.engine is Engine.SFIZZ else "DGZ"
    reverb = "R0" if recipe.augmentation.reverb_ir is None else "R1"
    audioalt = f"L{recipe.augmentation.level}"

    saboteur = "NONE"
    if recipe.augmentation.saboteur is not None:
        source = str(recipe.augmentation.saboteur.get("source", "SAB"))
        cleaned = re.sub(r"[^0-9A-Za-z]", "", source) or "SAB"
        saboteur = cleaned

    return Barcode(
        midisrc=midisrc,
        midialt=midialt,
        jittervar=jittervar,
        engine=engine,
        reverb=reverb,
        audioalt=audioalt,
        saboteur=saboteur,
    )


def wav_to_audio_buffer(wav_path: str | Path) -> tuple[np.ndarray, float]:
    """Read a rendered WAV into a Gold ``audio`` buffer (F0-T2a §3.2).

    Args:
        wav_path: The WAV produced by a render engine.

    Returns:
        ``(audio, duration_s)`` — ``audio`` is float16, shape ``[n_mic,
        n_sample]`` (channels-first, C-contiguous); ``duration_s`` is the
        buffer length in seconds.

    Raises:
        OrchestrationError: If the WAV is unreadable, empty, or not at the
            contract sample rate.
    """
    wav = Path(wav_path)
    try:
        data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    except (sf.LibsndfileError, OSError) as exc:
        raise OrchestrationError(f"cannot read rendered WAV {wav}: {exc}") from exc
    if sr != SAMPLE_RATE:
        raise OrchestrationError(
            f"rendered WAV sample rate is {sr}, expected {SAMPLE_RATE}: {wav}"
        )
    if data.shape[0] == 0:
        raise OrchestrationError(f"rendered WAV is empty (zero frames): {wav}")
    # soundfile gives [n_sample, n_mic]; the contract is channels-first.
    audio = np.ascontiguousarray(data.T, dtype=np.float16)
    duration_s = data.shape[0] / SAMPLE_RATE
    return audio, duration_s


def _resolve_drumgizmo_midimap(kit_path: Path) -> Path:
    """Resolve a DrumGizmo kit's MIDI map by the kit-file naming convention.

    Two layouts in the wild:

    1. **Variant-bearing kits** (e.g. DRSKit): `<Name>_<variant>.xml` kit file
       paired with `Midimap_<variant>.xml` map. The variant lets one kit ship
       multiple mic configurations.
    2. **Single-XML kits** (e.g. MuldjordKit3, ShittyKit, most older
       DrumGizmo kits): just `<Name>.xml` paired with `Midimap.xml` (or the
       case-variant `midimap.xml`). Pre-2018-style kits.

    The recipe schema (F0-T2a §1.1) carries only the kit path, so the map is
    derived here. Fail-loud if no candidate map file exists.
    """
    parent = kit_path.parent
    stem = kit_path.stem
    candidates: list[Path] = []
    if "_" in stem:
        # Variant-bearing convention — try Midimap_<variant>.xml first.
        variant = stem.split("_", 1)[1]
        candidates.append(parent / f"Midimap_{variant}.xml")
    # Single-XML fallback — Midimap.xml / midimap.xml in the kit dir.
    candidates.extend((parent / "Midimap.xml", parent / "midimap.xml"))
    for cand in candidates:
        if cand.is_file():
            return cand
    available = sorted(
        p.name for p in parent.glob("*idimap*.xml")
    ) or ["(none)"]
    raise OrchestrationError(
        f"DrumGizmo MIDI map not found alongside kit {kit_path.name} "
        f"(tried: {[c.name for c in candidates]}; available in dir: {available})"
    )


def _render(recipe: Recipe, midi_path: Path, kit_path: Path, wav_path: Path) -> None:
    """Drive the recipe's render engine into ``wav_path`` (fail-loud)."""
    if recipe.render.engine is Engine.SFIZZ:
        SfizzRenderer().render(sfz_path=kit_path, midi_path=midi_path, wav_path=wav_path)
        return

    midimap = _resolve_drumgizmo_midimap(kit_path)
    try:
        midi_len = mido.MidiFile(str(midi_path)).length
    except (OSError, ValueError, EOFError, KeyError, IndexError) as exc:
        raise OrchestrationError(f"cannot read MIDI length of {midi_path}: {exc}") from exc
    DrumGizmoRenderer().render(
        kit_path=kit_path,
        midimap_path=midimap,
        midi_path=midi_path,
        wav_path=wav_path,
        duration_s=midi_len + _DRUMGIZMO_RENDER_TAIL_S,
        # F0-T4c CEO 2026-05-24: per-kit dispatch from docs/specs/kit_mic_mapping.yaml.
        # Was DRSKIT_MULTITRACK8 hardcoded (worked only for DRSKit; broke on
        # MuldjordKit / ShittyKit etc. in the mini-L3 cross-kit run).
        channel_map=channel_map_for_kit(recipe.render.kit),
    )


def build_gold_sample(
    recipe: Recipe,
    *,
    out_dir: str | Path,
    bus_mapping: BusMapping,
    repo_root: str | Path = REPO_ROOT,
    midi_path_override: str | Path | None = None,
) -> GoldSampleResult:
    """Run one recipe end-to-end and write its Gold sample triple.

    The pipeline: render the recipe's MIDI through its engine, read the WAV
    into the ``audio`` buffer, build the companion ``target`` matrix from the
    same MIDI, assemble the ``dna.json``, write the triple, and verify it.

    Args:
        recipe: The validated recipe to realise.
        out_dir: Destination directory for the ``{key}.*`` sample triple.
        bus_mapping: GM-note -> 8-bus mapping for the target builder.
        repo_root: Root the recipe's relative ``midi_source.file`` and
            ``render.kit_path`` are resolved against.
        midi_path_override: Use this MIDI file for render/target/duration
            instead of ``recipe.midi_source.file``. Intended for the F2-T1
            runner, which applies :mod:`data_engineering.midi_augment` to
            the source MIDI and saves a transient jittered file. The
            ``dna.json`` still records the *original* ``recipe.midi_source.file``
            as the lineage anchor — the augmentation is encoded in the
            recipe's ``midi_jitter.variant_idx`` and ``jitter_seed``, which
            already flow into the barcode and the ``midi_jitter`` lineage
            block; bit-replay is preserved.

    Returns:
        A :class:`GoldSampleResult` describing the written, verified sample.

    Raises:
        OrchestrationError: If a recipe input is missing.
        RenderError / TargetBuilderError / GoldWriterError / DnaTraceError:
            Propagated from the stage that failed — fail-loud, no partial
            sample is written.
    """
    root = Path(repo_root)
    source_midi = root / recipe.midi_source.file
    if not source_midi.is_file():
        raise OrchestrationError(f"recipe MIDI source not found: {source_midi}")
    if midi_path_override is not None:
        midi_path = Path(midi_path_override)
        if not midi_path.is_file():
            raise OrchestrationError(
                f"midi_path_override not found: {midi_path}"
            )
    else:
        midi_path = source_midi
    kit_path = root / recipe.render.kit_path
    if not kit_path.is_file():
        raise OrchestrationError(f"recipe render kit not found: {kit_path}")

    # Tail standardization (F0-T2a §3.8): derive last_onset_s from the MIDI and
    # crop/pad the renderer's natural tail to a uniform value — engine-agnostic
    # by construction.
    last_onset_s = last_onset_seconds(midi_path, bus_mapping=bus_mapping)
    n_sample_out = n_sample_target(last_onset_s, tail_s=TAIL_S)
    duration_s = n_sample_out / SAMPLE_RATE

    with tempfile.TemporaryDirectory(prefix="orchestrate_") as tmp:
        wav_path = Path(tmp) / "render.wav"
        try:
            _render(recipe, midi_path, kit_path, wav_path)
        except RenderError as exc:
            raise OrchestrationError(
                f"render failed for recipe {recipe.recipe_id}: {exc}"
            ) from exc
        rendered, _ = wav_to_audio_buffer(wav_path)

    audio = standardize_audio_tail(rendered, n_sample_out)

    target = build_target(
        midi_path,
        duration_s=duration_s,
        bus_mapping=bus_mapping,
        r_target_hz=recipe.target_frame_rate_hz,
    )

    barcode = derive_barcode(recipe)
    key = encode_barcode(barcode)
    dna = build_dna_json(
        barcode=barcode,
        recipe=recipe,
        audio=audio,
        target=target,
        last_onset_s=last_onset_s,
        tail_s=TAIL_S,
    )

    written_dir = write_gold_sample(out_dir, key, audio=audio, target=target, dna=dna)
    validate_dna_json(dna, audio=audio, target=target)

    return GoldSampleResult(
        key=key,
        recipe_id=recipe.recipe_id,
        engine=recipe.render.engine,
        out_dir=written_dir,
        n_mic=int(audio.shape[0]),
        n_sample=int(audio.shape[1]),
        n_frame=int(target.shape[0]),
        audio_peak=float(np.abs(audio.astype(np.float32)).max()),
        last_onset_s=last_onset_s,
        tail_s=TAIL_S,
    )
