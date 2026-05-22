"""Recipe schema — declarative render scenario (F0-T2a §1).

The public types, enums and constants are LOCKED on the F0-T2a contract; the
parser (:func:`parse_recipe`, :func:`load_recipe`) was implemented by **F0-T2b**.
It is a *critical* module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3).

The parser is strict and fails loud: any schema violation raises
:class:`RecipeError` and no partial :class:`Recipe` is ever returned
(ENGINEERING_STANDARDS §6).

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §1.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

#: Recipe schema version (F0-T2a §1.1).
SCHEMA_VERSION = "1.0"
#: Fixed render sample rate — no resampling (F0-T2a §1.1, DOSSIER §6.1).
SAMPLE_RATE = 44100
#: Target frame-rate, ratified by F0-T4a: 44100 / 128 (F0-T2a §3.4).
R_TARGET_HZ = 344.53125


class Split(StrEnum):
    """Dataset split of a recipe (F0-T2a §1.1). Holdout is real data, not Gold."""

    TRAIN = "train"
    VAL = "val"


class Engine(StrEnum):
    """Render engine selector (F0-T2a §2)."""

    SFIZZ = "sfizz"
    DRUMGIZMO = "drumgizmo"


class MicConfig(StrEnum):
    """Microphone configuration (F0-T2a §2.3)."""

    MONO = "mono"
    SOLO_STEREO = "solo_stereo"
    GLYN_JOHNS = "glyn_johns"
    MULTITRACK_FULL = "multitrack_full"


class VelocityJitter(StrEnum):
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
    # multitrack_full — the industry-standard 8-channel layout (Superior
    # Drummer 3 / EZdrummer / Steven Slate / GetGood Drums; Decision Lock CEO
    # 2026-05-22): every kit zone gets one close mic, stereo overheads, a room.
    MicConfig.MULTITRACK_FULL: (
        "kick",
        "snare",
        "hihat",
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
    mutilation: dict[str, Any]
    saboteur: dict[str, Any] | None


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


#: Recognised top-level recipe keys. ``dna_trace`` is generated downstream
#: (F0-T2a §1.1 / §4) and accepted-but-ignored by the parser.
_ROOT_KEYS = frozenset(
    {
        "recipe_id",
        "schema_version",
        "split",
        "midi_source",
        "midi_jitter",
        "render",
        "augmentation",
        "output",
        "dna_trace",
    }
)
#: MIDI source datasets allowed by the contract (F0-T2a §1.1).
_ALLOWED_MIDI_DATASETS = frozenset({"GMD"})


def _as_mapping(value: Any, ctx: str) -> dict[str, Any]:
    """Return ``value`` as a mapping or raise :class:`RecipeError`."""
    if not isinstance(value, dict):
        raise RecipeError(f"{ctx}: expected a mapping, got {type(value).__name__}")
    return value


def _require(mapping: dict[str, Any], key: str, ctx: str) -> Any:
    """Return ``mapping[key]`` or raise :class:`RecipeError` if absent."""
    if key not in mapping:
        raise RecipeError(f"{ctx}: missing required field '{key}'")
    return mapping[key]


def _reject_unknown(mapping: dict[str, Any], allowed: frozenset[str], ctx: str) -> None:
    """Raise :class:`RecipeError` on any key outside ``allowed``.

    Strict-by-construction: a mistyped key (``mic_confgi``) must fail loud, not
    be silently dropped — a silent drop renders the wrong scenario and burns
    Azure credit (ENGINEERING_STANDARDS §6).
    """
    extra = sorted(set(mapping) - allowed)
    if extra:
        raise RecipeError(f"{ctx}: unknown field(s) {extra}")


def _as_str(value: Any, ctx: str) -> str:
    """Return ``value`` as a non-empty string or raise :class:`RecipeError`."""
    if not isinstance(value, str) or not value:
        raise RecipeError(f"{ctx}: must be a non-empty string")
    return value


def _as_number(value: Any, ctx: str) -> float:
    """Return ``value`` as a float or raise :class:`RecipeError` (``bool`` rejected)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecipeError(f"{ctx}: must be a number")
    return float(value)


def _as_probability(value: Any, ctx: str) -> float:
    """Return ``value`` as a float in ``[0, 1]`` or raise :class:`RecipeError`."""
    number = _as_number(value, ctx)
    if not 0.0 <= number <= 1.0:
        raise RecipeError(f"{ctx}: must be in [0, 1], got {number}")
    return number


def _as_int(value: Any, ctx: str) -> int:
    """Return ``value`` as an int or raise :class:`RecipeError` (``bool`` rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecipeError(f"{ctx}: must be an integer")
    return value


def _as_enum[E: StrEnum](enum_cls: type[E], value: Any, ctx: str) -> E:
    """Return the ``enum_cls`` member for ``value`` or raise :class:`RecipeError`."""
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        valid = [member.value for member in enum_cls.__members__.values()]
        raise RecipeError(f"{ctx}: invalid value {value!r}; expected one of {valid}") from None


def _parse_midi_source(value: Any) -> MidiSource:
    ctx = "recipe.midi_source"
    block = _as_mapping(value, ctx)
    _reject_unknown(block, frozenset({"dataset", "file", "bus_mapping"}), ctx)
    dataset = _require(block, "dataset", ctx)
    if dataset not in _ALLOWED_MIDI_DATASETS:
        raise RecipeError(
            f"{ctx}.dataset: unknown dataset {dataset!r}; "
            f"expected one of {sorted(_ALLOWED_MIDI_DATASETS)}"
        )
    return MidiSource(
        dataset=dataset,
        file=_as_str(_require(block, "file", ctx), f"{ctx}.file"),
        bus_mapping=_as_str(_require(block, "bus_mapping", ctx), f"{ctx}.bus_mapping"),
    )


def _parse_midi_jitter(value: Any) -> MidiJitter:
    ctx = "recipe.midi_jitter"
    block = _as_mapping(value, ctx)
    _reject_unknown(
        block,
        frozenset(
            {
                "time_jitter_ms",
                "flam_probability",
                "velocity_jitter",
                "component_drop_probability",
                "seed",
            }
        ),
        ctx,
    )
    raw_range = _require(block, "time_jitter_ms", ctx)
    if not isinstance(raw_range, list) or len(raw_range) != 2:
        raise RecipeError(f"{ctx}.time_jitter_ms: expected a [min, max] pair")
    low = _as_number(raw_range[0], f"{ctx}.time_jitter_ms[0]")
    high = _as_number(raw_range[1], f"{ctx}.time_jitter_ms[1]")
    if low > high:
        raise RecipeError(f"{ctx}.time_jitter_ms: min ({low}) exceeds max ({high})")
    return MidiJitter(
        time_jitter_ms=(low, high),
        flam_probability=_as_probability(
            _require(block, "flam_probability", ctx), f"{ctx}.flam_probability"
        ),
        velocity_jitter=_as_enum(
            VelocityJitter, _require(block, "velocity_jitter", ctx), f"{ctx}.velocity_jitter"
        ),
        component_drop_probability=_as_probability(
            _require(block, "component_drop_probability", ctx),
            f"{ctx}.component_drop_probability",
        ),
        seed=_as_int(_require(block, "seed", ctx), f"{ctx}.seed"),
    )


def _parse_render(value: Any) -> RenderSpec:
    ctx = "recipe.render"
    block = _as_mapping(value, ctx)
    _reject_unknown(
        block,
        frozenset({"engine", "kit", "kit_path", "sample_rate", "mic_config"}),
        ctx,
    )
    sample_rate = _as_int(_require(block, "sample_rate", ctx), f"{ctx}.sample_rate")
    if sample_rate != SAMPLE_RATE:
        raise RecipeError(
            f"{ctx}.sample_rate: must be {SAMPLE_RATE} (no resampling); got {sample_rate}"
        )
    return RenderSpec(
        engine=_as_enum(Engine, _require(block, "engine", ctx), f"{ctx}.engine"),
        kit=_as_str(_require(block, "kit", ctx), f"{ctx}.kit"),
        kit_path=_as_str(_require(block, "kit_path", ctx), f"{ctx}.kit_path"),
        sample_rate=sample_rate,
        mic_config=_as_enum(MicConfig, _require(block, "mic_config", ctx), f"{ctx}.mic_config"),
    )


def _parse_augmentation(value: Any) -> AugmentationSpec:
    ctx = "recipe.augmentation"
    block = _as_mapping(value, ctx)
    _reject_unknown(block, frozenset({"level", "reverb_ir", "mutilation", "saboteur"}), ctx)
    level = _as_int(_require(block, "level", ctx), f"{ctx}.level")
    if level not in (1, 2, 3):
        raise RecipeError(f"{ctx}.level: must be 1, 2 or 3; got {level}")
    reverb_ir = block.get("reverb_ir")
    if reverb_ir is not None and not isinstance(reverb_ir, str):
        raise RecipeError(f"{ctx}.reverb_ir: must be a string or null")
    mutilation = block.get("mutilation", {})
    if not isinstance(mutilation, dict):
        raise RecipeError(f"{ctx}.mutilation: must be a mapping")
    saboteur = block.get("saboteur")
    if saboteur is not None and not isinstance(saboteur, dict):
        raise RecipeError(f"{ctx}.saboteur: must be a mapping or null")
    return AugmentationSpec(
        level=level, reverb_ir=reverb_ir, mutilation=mutilation, saboteur=saboteur
    )


def parse_recipe(text: str) -> Recipe:
    """Parse a recipe YAML document into a validated :class:`Recipe`.

    Args:
        text: Raw YAML recipe document (F0-T2a §1.2).

    Returns:
        A fully-validated, immutable :class:`Recipe`.

    Raises:
        RecipeError: If the document is not valid YAML or any field violates
            the F0-T2a §1.1 schema. The parser fails loud and never returns
            partial state.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RecipeError(f"recipe is not valid YAML: {exc}") from exc
    if raw is None:
        raise RecipeError("recipe document is empty")

    root = _as_mapping(raw, "recipe")
    _reject_unknown(root, _ROOT_KEYS, "recipe")

    schema_version = _as_str(_require(root, "schema_version", "recipe"), "recipe.schema_version")
    if schema_version != SCHEMA_VERSION:
        raise RecipeError(
            f"recipe.schema_version: unsupported {schema_version!r}; expected {SCHEMA_VERSION!r}"
        )

    output = _as_mapping(_require(root, "output", "recipe"), "recipe.output")
    _reject_unknown(output, frozenset({"target_frame_rate_hz"}), "recipe.output")

    return Recipe(
        recipe_id=_as_str(_require(root, "recipe_id", "recipe"), "recipe.recipe_id"),
        schema_version=schema_version,
        split=_as_enum(Split, _require(root, "split", "recipe"), "recipe.split"),
        midi_source=_parse_midi_source(_require(root, "midi_source", "recipe")),
        midi_jitter=_parse_midi_jitter(_require(root, "midi_jitter", "recipe")),
        render=_parse_render(_require(root, "render", "recipe")),
        augmentation=_parse_augmentation(_require(root, "augmentation", "recipe")),
        target_frame_rate_hz=_as_number(
            _require(output, "target_frame_rate_hz", "recipe.output"),
            "recipe.output.target_frame_rate_hz",
        ),
    )


def load_recipe(path: str | Path) -> Recipe:
    """Read a recipe YAML file from disk and parse it.

    Args:
        path: Filesystem path to the recipe YAML file.

    Returns:
        A fully-validated, immutable :class:`Recipe`.

    Raises:
        RecipeError: If the file cannot be read, or its contents violate the
            F0-T2a §1.1 schema (see :func:`parse_recipe`).
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RecipeError(f"cannot read recipe file {file_path}: {exc}") from exc
    return parse_recipe(text)
