"""Recipe schema — declarative render scenario (F0-T2a §1).

SKELETON / CONTRACT INTERFACE.  The public types, enums, constants and
exception classes below are LOCKED here so the F0-T9b test-oracle suite can be
written *before* the implementation (test-first — TESTING_DOCTRINE §1.3, §6.2).

The parsing *logic* (:func:`parse_recipe`, :func:`load_recipe`) is owned by
**F0-T2b** and currently raises :class:`NotImplementedError`.

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §1.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

#: Recipe schema version (F0-T2a §1.1).
SCHEMA_VERSION = "1.0"
#: Fixed render sample rate — no resampling (F0-T2a §1.1, DOSSIER §6.1).
SAMPLE_RATE = 44100
#: Target frame-rate, ratified by F0-T4a: 44100 / 128 (F0-T2a §3.4).
R_TARGET_HZ = 344.53125


class Split(str, Enum):
    """Dataset split of a recipe (F0-T2a §1.1). Holdout is real data, not Gold."""

    TRAIN = "train"
    VAL = "val"


class Engine(str, Enum):
    """Render engine selector (F0-T2a §2)."""

    SFIZZ = "sfizz"
    DRUMGIZMO = "drumgizmo"


class MicConfig(str, Enum):
    """Microphone configuration (F0-T2a §2.3)."""

    MONO = "mono"
    SOLO_STEREO = "solo_stereo"
    GLYN_JOHNS = "glyn_johns"
    MULTITRACK_FULL = "multitrack_full"


class VelocityJitter(str, Enum):
    """Velocity-jitter mode (F0-T2a §1.1)."""

    NONE = "none"
    GHOST_MASK = "ghost_mask"
    GAIN_SHIFT = "gain_shift"
    BOTH = "both"


#: Canonical microphone channel order per ``mic_config`` (F0-T2a §2.3).
MIC_CONFIG_CHANNELS: dict[MicConfig, tuple[str, ...]] = {
    MicConfig.MONO: ("mix",),
    MicConfig.SOLO_STEREO: ("mix_L", "mix_R"),
    MicConfig.GLYN_JOHNS: ("kick", "snare", "oh_L", "oh_R"),
    MicConfig.MULTITRACK_FULL: (
        "kick",
        "snare_top",
        "snare_bot",
        "tom",
        "floor",
        "oh_L",
        "oh_R",
        "room",
    ),
}


class RecipeError(ValueError):
    """Raised when a recipe document violates the F0-T2a §1.1 schema.

    The parser MUST fail loud with this exception and MUST NOT return a
    partially-populated :class:`Recipe` (F0-T2a §1.1; ENGINEERING_STANDARDS §6
    — fail-loud).
    """


@dataclass(frozen=True)
class MidiSource:
    """``midi_source`` block (F0-T2a §1.1)."""

    dataset: str
    file: str
    bus_mapping: str


@dataclass(frozen=True)
class MidiJitter:
    """``midi_jitter`` block (F0-T2a §1.1)."""

    time_jitter_ms: tuple[float, float]
    flam_probability: float
    velocity_jitter: VelocityJitter
    component_drop_probability: float
    seed: int


@dataclass(frozen=True)
class RenderSpec:
    """``render`` block (F0-T2a §1.1)."""

    engine: Engine
    kit: str
    kit_path: str
    sample_rate: int
    mic_config: MicConfig


@dataclass(frozen=True)
class AugmentationSpec:
    """``augmentation`` block (F0-T2a §1.1)."""

    level: int
    reverb_ir: str | None
    mutilation: dict
    saboteur: dict | None


@dataclass(frozen=True)
class Recipe:
    """A fully-validated, immutable render recipe (F0-T2a §1)."""

    recipe_id: str
    schema_version: str
    split: Split
    midi_source: MidiSource
    midi_jitter: MidiJitter
    render: RenderSpec
    augmentation: AugmentationSpec
    target_frame_rate_hz: float


def parse_recipe(text: str) -> Recipe:
    """Parse a recipe YAML document into a validated :class:`Recipe`.

    Args:
        text: Raw YAML recipe document (F0-T2a §1.2).

    Returns:
        A fully-validated, immutable :class:`Recipe`.

    Raises:
        RecipeError: If any field violates the F0-T2a §1.1 schema. The parser
            fails loud and never returns partial state.

    Note:
        SKELETON — implementation owned by F0-T2b.
    """
    raise NotImplementedError("recipe parser — owned by F0-T2b")


def load_recipe(path: str | Path) -> Recipe:
    """Read a recipe YAML file from disk and parse it.

    See :func:`parse_recipe` for the contract.

    Note:
        SKELETON — implementation owned by F0-T2b.
    """
    raise NotImplementedError("recipe loader — owned by F0-T2b")
