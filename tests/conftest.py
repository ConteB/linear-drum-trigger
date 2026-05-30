"""Shared fixtures for the F0 pipeline test harness (F0-T9b).

All fixtures derive from the LOCKED F0-T2a data contract; they construct the
contract dataclasses directly (those types are part of the locked spec) so the
oracles do not depend on the not-yet-written parser.
"""
from __future__ import annotations

import textwrap
from collections.abc import Callable

import numpy as np
import pytest

from data_engineering.gold.dna_trace import DNA_VERSION, Barcode
from data_engineering.gold.gold_writer import R_TARGET_HZ, TARGET_COLS
from data_engineering.gold.recipe import (
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

# The canonical recipe of F0-T2a §1.2 — the harness's golden input.
VALID_RECIPE_YAML = textwrap.dedent(
    """\
    recipe_id: R-GMD042-DGZ-001
    schema_version: "1.0"
    split: train
    midi_source:
      dataset: GMD
      file: bronze/gmd/drummer1/session1/42_rock_120_beat_4-4.mid
      bus_mapping: midi_mapping_table.yaml@1.0
    midi_jitter:
      time_jitter_ms: [2, 15]
      flam_probability: 0.05
      velocity_jitter: both
      component_drop_probability: 0.10
      seed: 4242
    render:
      engine: drumgizmo
      kit: DRSKit
      kit_path: bronze/drumgizmo/DRSKit/DRSKit.xml
      sample_rate: 44100
      mic_config: glyn_johns
    augmentation:
      level: 2
      reverb_ir: openair_r2_york_minster
      mutilation: { clipping: 0.3, phase_flip: [snare_bot], comp_ratio: 8, pitch_semitones: -1 }
      saboteur: { source: SLK102, mix_ratio: 0.4 }
    output:
      target_frame_rate_hz: 344.53125
    """
)

#: The barcode of the F0-T2a §4.2 example (7-segment — Decision Lock CEO 2026-05-23).
SAMPLE_BARCODE = Barcode("GMD042", "V1T1", "J01", "DGZ", "R2", "C1H0", "SLK102")
#: Its expected ``-``-joined key.
SAMPLE_KEY = "GMD042-V1T1-J01-DGZ-R2-C1H0-SLK102"


@pytest.fixture
def valid_recipe_yaml() -> str:
    """The canonical, contract-valid recipe document (F0-T2a §1.2)."""
    return VALID_RECIPE_YAML


@pytest.fixture
def sample_recipe() -> Recipe:
    """A :class:`Recipe` matching :data:`VALID_RECIPE_YAML`, built directly."""
    return Recipe(
        recipe_id="R-GMD042-DGZ-001",
        schema_version="1.0",
        split=Split.TRAIN,
        midi_source=MidiSource(
            dataset="GMD",
            file="bronze/gmd/drummer1/session1/42_rock_120_beat_4-4.mid",
            bus_mapping="midi_mapping_table.yaml@1.0",
        ),
        midi_jitter=MidiJitter(
            time_jitter_ms=(2.0, 15.0),
            flam_probability=0.05,
            velocity_jitter=VelocityJitter.BOTH,
            component_drop_probability=0.10,
            seed=4242,
        ),
        render=RenderSpec(
            engine=Engine.DRUMGIZMO,
            kit="DRSKit",
            kit_path="bronze/drumgizmo/DRSKit/DRSKit.xml",
            sample_rate=44100,
            mic_config=MicConfig.GLYN_JOHNS,
        ),
        augmentation=AugmentationSpec(
            level=2,
            reverb_ir="openair_r2_york_minster",
            mutilation={"clipping": 0.3, "comp_ratio": 8, "pitch_semitones": -1},
            saboteur={"source": "SLK102", "mix_ratio": 0.4},
        ),
        target_frame_rate_hz=R_TARGET_HZ,
    )


@pytest.fixture
def sample_barcode() -> Barcode:
    """The barcode of the F0-T2a §4.2 example."""
    return SAMPLE_BARCODE


@pytest.fixture
def gold_dir(tmp_path) -> object:
    """An empty destination directory for a Gold sample triple."""
    d = tmp_path / "gold"
    d.mkdir()
    return d


@pytest.fixture
def make_audio() -> Callable[..., np.ndarray]:
    """Factory for a contract-valid ``audio`` buffer — float16, in [-1, 1]."""

    def _make(n_mic: int = 4, n_sample: int = 4096, *, fill: float | None = None) -> np.ndarray:
        if fill is not None:
            return np.full((n_mic, n_sample), fill, dtype=np.float16)
        rng = np.random.default_rng(42)
        return rng.uniform(-1.0, 1.0, size=(n_mic, n_sample)).astype(np.float16)

    return _make


@pytest.fixture
def make_target() -> Callable[..., np.ndarray]:
    """Factory for a contract-valid ``target`` matrix — float16, ``[n_frame, 28]``."""

    def _make(n_frame: int = 128) -> np.ndarray:
        t = np.zeros((n_frame, TARGET_COLS), dtype=np.float16)
        # A couple of plausible onsets so the matrix is not identically zero.
        if n_frame >= 8:
            t[4, 0] = 1.0  # bus 0 (kick) onset
            t[4, 1] = 0.8  # bus 0 velocity
        return t

    return _make


@pytest.fixture
def sample_dna() -> dict:
    """A minimal ``dna.json``-shaped document for writer oracles (F0-T2a §4.2)."""
    return {
        "dna_version": DNA_VERSION,
        "barcode": SAMPLE_KEY,
        "key": SAMPLE_KEY,
        "recipe_id": "R-GMD042-DGZ-001",
        "split": "train",
        "audio": {"shape": [4, 4096], "dtype": "float16", "n_nonfinite": 0},
        "target": {"shape": [128, 28], "dtype": "float16", "n_nonfinite": 0},
    }
