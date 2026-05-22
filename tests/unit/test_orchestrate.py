"""Layer-1 unit oracles for the pipeline orchestrator (F0-T2e).

Binary-free: these cover the orchestrator's pure glue — the recipe -> barcode
derivation and the WAV -> ``audio`` buffer conversion — plus the DrumGizmo
MIDI-map resolution convention. The end-to-end render path is exercised by the
§6.3 acceptance suite (``tests/acceptance/test_mini_batch.py``).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf  # type: ignore[import-untyped]

from data_engineering.gold.dna_trace import decode_barcode, encode_barcode
from data_engineering.gold.orchestrate import (
    OrchestrationError,
    _resolve_drumgizmo_midimap,
    derive_barcode,
    wav_to_audio_buffer,
)
from data_engineering.gold.recipe import Engine, Recipe


def _with_engine(recipe: Recipe, engine: Engine) -> Recipe:
    """Clone ``recipe`` with a different render engine."""
    return dataclasses.replace(
        recipe, render=dataclasses.replace(recipe.render, engine=engine)
    )


# --------------------------------------------------------------------------
# derive_barcode
# --------------------------------------------------------------------------
def test_barcode_round_trips_through_the_codec(sample_recipe: Recipe) -> None:
    """The derived barcode encodes to a key that decodes back unchanged."""
    barcode = derive_barcode(sample_recipe)
    key = encode_barcode(barcode)
    assert decode_barcode(key) == barcode
    assert "." not in key  # dot-free — survives WebDataset extension splitting


def test_barcode_is_deterministic(sample_recipe: Recipe) -> None:
    """A recipe is a pure function of its barcode — same in, same out."""
    assert derive_barcode(sample_recipe) == derive_barcode(sample_recipe)


def test_barcode_segments_reflect_the_recipe(sample_recipe: Recipe) -> None:
    """Each segment encodes the matching recipe field (F0-T2a §4.1)."""
    barcode = derive_barcode(sample_recipe)
    # midi_source.file '.../42_rock_120_beat_4-4.mid' -> first digit-run '42'.
    assert barcode.midisrc == "GMD042"
    assert barcode.engine == "DGZ"  # sample_recipe renders with DrumGizmo
    assert barcode.reverb == "R1"  # sample_recipe carries a reverb IR
    assert barcode.saboteur == "SLK102"  # from augmentation.saboteur.source
    assert barcode.midialt.startswith("V")  # velocity/time jitter codes


def test_barcode_engine_segment_tracks_the_engine(sample_recipe: Recipe) -> None:
    """The ENGINE segment is SFZ for Sfizz, DGZ for DrumGizmo."""
    assert derive_barcode(_with_engine(sample_recipe, Engine.SFIZZ)).engine == "SFZ"
    assert derive_barcode(_with_engine(sample_recipe, Engine.DRUMGIZMO)).engine == "DGZ"


def test_barcode_reverb_segment_is_r0_when_dry(sample_recipe: Recipe) -> None:
    """A recipe with no reverb IR gets the dry ``R0`` segment."""
    dry = dataclasses.replace(
        sample_recipe,
        augmentation=dataclasses.replace(sample_recipe.augmentation, reverb_ir=None),
    )
    assert derive_barcode(dry).reverb == "R0"


def test_barcode_saboteur_segment_is_none_when_absent(sample_recipe: Recipe) -> None:
    """A recipe with no saboteur gets the ``NONE`` segment."""
    clean = dataclasses.replace(
        sample_recipe,
        augmentation=dataclasses.replace(sample_recipe.augmentation, saboteur=None),
    )
    assert derive_barcode(clean).saboteur == "NONE"


def test_distinct_recipes_yield_distinct_keys(sample_recipe: Recipe) -> None:
    """Changing the engine changes the barcode key — no silent collision."""
    sfizz = encode_barcode(derive_barcode(_with_engine(sample_recipe, Engine.SFIZZ)))
    drumgizmo = encode_barcode(derive_barcode(_with_engine(sample_recipe, Engine.DRUMGIZMO)))
    assert sfizz != drumgizmo


# --------------------------------------------------------------------------
# wav_to_audio_buffer
# --------------------------------------------------------------------------
def _write_wav(path: Path, n_sample: int, n_ch: int, sr: int = 44100) -> Path:
    """Write a non-silent test WAV of the given shape."""
    rng = np.random.default_rng(0)
    sf.write(str(path), rng.uniform(-0.5, 0.5, size=(n_sample, n_ch)), sr, subtype="FLOAT")
    return path


def test_wav_becomes_channels_first_float16(tmp_path: Path) -> None:
    """A WAV is read into a ``[n_mic, n_sample]`` float16 buffer (F0-T2a §3.2)."""
    wav = _write_wav(tmp_path / "r.wav", n_sample=8192, n_ch=4)
    audio, duration_s = wav_to_audio_buffer(wav)
    assert audio.shape == (4, 8192)
    assert audio.dtype == np.float16
    assert audio.flags["C_CONTIGUOUS"]
    assert duration_s == pytest.approx(8192 / 44100)


def test_wav_wrong_sample_rate_fails_loud(tmp_path: Path) -> None:
    """A WAV not at 44.1 kHz violates the no-resampling contract — fail loud."""
    wav = _write_wav(tmp_path / "r.wav", n_sample=4096, n_ch=2, sr=22050)
    with pytest.raises(OrchestrationError, match="sample rate"):
        wav_to_audio_buffer(wav)


def test_wav_missing_file_fails_loud(tmp_path: Path) -> None:
    """An unreadable WAV fails loud rather than yielding an empty buffer."""
    with pytest.raises(OrchestrationError, match="cannot read"):
        wav_to_audio_buffer(tmp_path / "absent.wav")


# --------------------------------------------------------------------------
# _resolve_drumgizmo_midimap
# --------------------------------------------------------------------------
def test_midimap_resolved_by_kit_naming_convention(tmp_path: Path) -> None:
    """``<Name>_<variant>.xml`` resolves to the sibling ``Midimap_<variant>.xml``."""
    kit = tmp_path / "DRSKit_full.xml"
    kit.write_text("<kit/>", encoding="utf-8")
    midimap = tmp_path / "Midimap_full.xml"
    midimap.write_text("<midimap/>", encoding="utf-8")
    assert _resolve_drumgizmo_midimap(kit) == midimap


def test_midimap_unresolvable_kit_name_fails_loud(tmp_path: Path) -> None:
    """A kit file with no ``_variant`` suffix cannot yield a map — fail loud."""
    kit = tmp_path / "kit.xml"
    kit.write_text("<kit/>", encoding="utf-8")
    with pytest.raises(OrchestrationError, match="derive a MIDI map"):
        _resolve_drumgizmo_midimap(kit)


def test_midimap_absent_file_fails_loud(tmp_path: Path) -> None:
    """A kit whose ``Midimap_<variant>.xml`` is missing fails loud."""
    kit = tmp_path / "DRSKit_full.xml"
    kit.write_text("<kit/>", encoding="utf-8")
    with pytest.raises(OrchestrationError, match="MIDI map not found"):
        _resolve_drumgizmo_midimap(kit)
