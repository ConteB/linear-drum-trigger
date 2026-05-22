"""§6.2 — Recipe YAML parser oracle.

Critical module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3).
Contract: F0-T2a §1.1. Written test-first (F0-T9b); implemented by F0-T2b.

Error-path tests assert on a substring of the diagnostic message (``match=``):
a fail-loud parser must name *which* field failed, and the assertion also kills
the ``ctx``-plumbing mutants (TESTING_DOCTRINE §3).
"""
from __future__ import annotations

import pytest

from data_engineering.gold.recipe import (
    Engine,
    MicConfig,
    Recipe,
    RecipeError,
    Split,
    VelocityJitter,
    load_recipe,
    parse_recipe,
)

pytestmark = pytest.mark.critical


def test_parses_canonical_recipe(valid_recipe_yaml) -> None:
    # Every field is asserted — a parser that drops or nulls any field is a
    # silent contract violation (F0-T2a §1.1).
    r = parse_recipe(valid_recipe_yaml)
    assert isinstance(r, Recipe)
    assert r.recipe_id == "R-GMD042-DGZ-001"
    assert r.schema_version == "1.0"
    assert r.split is Split.TRAIN

    assert r.midi_source.dataset == "GMD"
    assert r.midi_source.file == "bronze/gmd/drummer1/session1/42_rock_120_beat_4-4.mid"
    assert r.midi_source.bus_mapping == "midi_mapping_table.yaml@1.0"

    assert r.midi_jitter.time_jitter_ms == (2.0, 15.0)
    assert r.midi_jitter.flam_probability == 0.05
    assert r.midi_jitter.velocity_jitter is VelocityJitter.BOTH
    assert r.midi_jitter.component_drop_probability == 0.10
    assert r.midi_jitter.seed == 4242

    assert r.render.engine is Engine.DRUMGIZMO
    assert r.render.kit == "DRSKit"
    assert r.render.kit_path == "bronze/drumgizmo/DRSKit/DRSKit.xml"
    assert r.render.sample_rate == 44100
    assert r.render.mic_config is MicConfig.GLYN_JOHNS

    assert r.augmentation.level == 2
    assert r.augmentation.reverb_ir == "openair_r2_york_minster"
    assert r.augmentation.mutilation["clipping"] == 0.3
    assert r.augmentation.saboteur == {"source": "SLK102", "mix_ratio": 0.4}

    assert r.target_frame_rate_hz == 344.53125


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param("", id="empty-document"),
        pytest.param("{}", id="empty-mapping"),
        pytest.param("recipe_id: only-this-field", id="missing-required-fields"),
        pytest.param("a: b\n  c: d\n bad-indent", id="malformed-yaml"),
        pytest.param("[1, 2, 3]", id="top-level-is-a-list"),
    ],
)
def test_malformed_recipe_raises_recipe_error(bad) -> None:
    with pytest.raises(RecipeError):
        parse_recipe(bad)


def test_unknown_engine_is_rejected(valid_recipe_yaml) -> None:
    bad = valid_recipe_yaml.replace("engine: drumgizmo", "engine: fluidsynth")
    with pytest.raises(RecipeError, match="engine"):
        parse_recipe(bad)


def test_sample_rate_must_be_44100(valid_recipe_yaml) -> None:
    # F0-T2a §1.1 — sample_rate is fixed; 48 kHz is a contract violation.
    bad = valid_recipe_yaml.replace("sample_rate: 44100", "sample_rate: 48000")
    with pytest.raises(RecipeError, match="sample_rate"):
        parse_recipe(bad)


def test_unknown_split_is_rejected(valid_recipe_yaml) -> None:
    # F0-T2a §1.1 / §3.6 — only train|val; holdout is real data, never a recipe.
    bad = valid_recipe_yaml.replace("split: train", "split: holdout")
    with pytest.raises(RecipeError, match="split"):
        parse_recipe(bad)


def test_missing_seed_is_rejected(valid_recipe_yaml) -> None:
    # The RNG seed is mandatory — without it the sample is not reproducible
    # (ENGINEERING_STANDARDS §1). A partial Recipe must never be returned.
    bad = valid_recipe_yaml.replace("  seed: 4242\n", "")
    with pytest.raises(RecipeError, match="seed"):
        parse_recipe(bad)


# --------------------------------------------------------------------------
# F0-T2d coverage — unknown fields, boundary values, type strictness
# --------------------------------------------------------------------------


def test_unknown_top_level_field_is_rejected(valid_recipe_yaml) -> None:
    # A mistyped key must fail loud, never be silently dropped (F0-T2a §1.1).
    bad = valid_recipe_yaml + "mystery_field: 1\n"
    with pytest.raises(RecipeError, match="unknown field"):
        parse_recipe(bad)


def test_unknown_field_inside_block_is_rejected(valid_recipe_yaml) -> None:
    bad = valid_recipe_yaml.replace("  dataset: GMD\n", "  dataset: GMD\n  typo: x\n")
    with pytest.raises(RecipeError, match="unknown field"):
        parse_recipe(bad)


@pytest.mark.parametrize("prob", ["0.0", "1.0", "0.5"])
def test_probability_accepts_the_closed_unit_interval(valid_recipe_yaml, prob) -> None:
    # F0-T2a §1.1 — a probability is valid on the *closed* [0, 1] interval.
    ok = valid_recipe_yaml.replace("flam_probability: 0.05", f"flam_probability: {prob}")
    assert parse_recipe(ok).midi_jitter.flam_probability == float(prob)


@pytest.mark.parametrize("prob", ["-0.01", "1.01", "2.0"])
def test_probability_outside_unit_interval_is_rejected(valid_recipe_yaml, prob) -> None:
    bad = valid_recipe_yaml.replace("flam_probability: 0.05", f"flam_probability: {prob}")
    with pytest.raises(RecipeError, match="flam_probability"):
        parse_recipe(bad)


@pytest.mark.parametrize("level", ["1", "2", "3"])
def test_augmentation_level_accepts_one_two_three(valid_recipe_yaml, level) -> None:
    ok = valid_recipe_yaml.replace("level: 2", f"level: {level}")
    assert parse_recipe(ok).augmentation.level == int(level)


@pytest.mark.parametrize("level", ["0", "4"])
def test_augmentation_level_outside_range_is_rejected(valid_recipe_yaml, level) -> None:
    bad = valid_recipe_yaml.replace("level: 2", f"level: {level}")
    with pytest.raises(RecipeError, match="level"):
        parse_recipe(bad)


def test_time_jitter_accepts_equal_min_and_max(valid_recipe_yaml) -> None:
    # A degenerate-but-valid range: min == max (zero jitter).
    ok = valid_recipe_yaml.replace("time_jitter_ms: [2, 15]", "time_jitter_ms: [5, 5]")
    assert parse_recipe(ok).midi_jitter.time_jitter_ms == (5.0, 5.0)


def test_time_jitter_min_greater_than_max_is_rejected(valid_recipe_yaml) -> None:
    bad = valid_recipe_yaml.replace("time_jitter_ms: [2, 15]", "time_jitter_ms: [15, 2]")
    with pytest.raises(RecipeError, match="time_jitter_ms"):
        parse_recipe(bad)


@pytest.mark.parametrize(
    "raw", ["time_jitter_ms: [5]", "time_jitter_ms: [1, 2, 3]", "time_jitter_ms: 5"]
)
def test_time_jitter_must_be_a_pair(valid_recipe_yaml, raw) -> None:
    bad = valid_recipe_yaml.replace("time_jitter_ms: [2, 15]", raw)
    with pytest.raises(RecipeError, match="time_jitter_ms"):
        parse_recipe(bad)


def test_boolean_is_rejected_where_an_integer_is_required(valid_recipe_yaml) -> None:
    # bool is a subclass of int — the parser must reject it explicitly.
    bad = valid_recipe_yaml.replace("seed: 4242", "seed: true")
    with pytest.raises(RecipeError, match="seed"):
        parse_recipe(bad)


def test_boolean_is_rejected_where_a_number_is_required(valid_recipe_yaml) -> None:
    bad = valid_recipe_yaml.replace("flam_probability: 0.05", "flam_probability: true")
    with pytest.raises(RecipeError, match="flam_probability"):
        parse_recipe(bad)


def test_empty_string_field_is_rejected(valid_recipe_yaml) -> None:
    bad = valid_recipe_yaml.replace("recipe_id: R-GMD042-DGZ-001", 'recipe_id: ""')
    with pytest.raises(RecipeError, match="recipe_id"):
        parse_recipe(bad)


def test_non_mapping_block_is_rejected(valid_recipe_yaml) -> None:
    bad = valid_recipe_yaml.replace(
        "midi_source:\n", "midi_source: not-a-mapping\n"
    ).replace("  dataset: GMD\n", "").replace(
        "  file: bronze/gmd/drummer1/session1/42_rock_120_beat_4-4.mid\n", ""
    ).replace("  bus_mapping: midi_mapping_table.yaml@1.0\n", "")
    with pytest.raises(RecipeError, match="midi_source"):
        parse_recipe(bad)


def test_unknown_midi_dataset_is_rejected(valid_recipe_yaml) -> None:
    # F0-T2a §1.1 — only the Groove MIDI Dataset is allowed.
    bad = valid_recipe_yaml.replace("dataset: GMD", "dataset: SLAKH")
    with pytest.raises(RecipeError, match="dataset"):
        parse_recipe(bad)


def test_unsupported_schema_version_is_rejected(valid_recipe_yaml) -> None:
    bad = valid_recipe_yaml.replace('schema_version: "1.0"', 'schema_version: "9.9"')
    with pytest.raises(RecipeError, match="schema_version"):
        parse_recipe(bad)


def test_reverb_ir_may_be_null(valid_recipe_yaml) -> None:
    ok = valid_recipe_yaml.replace(
        "reverb_ir: openair_r2_york_minster", "reverb_ir: null"
    )
    assert parse_recipe(ok).augmentation.reverb_ir is None


def test_reverb_ir_of_wrong_type_is_rejected(valid_recipe_yaml) -> None:
    bad = valid_recipe_yaml.replace("reverb_ir: openair_r2_york_minster", "reverb_ir: 123")
    with pytest.raises(RecipeError, match="reverb_ir"):
        parse_recipe(bad)


def test_saboteur_of_wrong_type_is_rejected(valid_recipe_yaml) -> None:
    bad = valid_recipe_yaml.replace(
        "saboteur: { source: SLK102, mix_ratio: 0.4 }", "saboteur: 7"
    )
    with pytest.raises(RecipeError, match="saboteur"):
        parse_recipe(bad)


def test_load_recipe_reads_and_parses_a_file(tmp_path, valid_recipe_yaml) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(valid_recipe_yaml, encoding="utf-8")
    r = load_recipe(path)
    assert isinstance(r, Recipe)
    assert r.recipe_id == "R-GMD042-DGZ-001"


def test_load_recipe_accepts_a_string_path(tmp_path, valid_recipe_yaml) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(valid_recipe_yaml, encoding="utf-8")
    assert load_recipe(str(path)).render.engine is Engine.DRUMGIZMO


def test_load_recipe_missing_file_raises_recipe_error(tmp_path) -> None:
    # A missing recipe file fails loud as RecipeError, not a bare OSError.
    with pytest.raises(RecipeError, match="cannot read recipe file"):
        load_recipe(tmp_path / "does_not_exist.yaml")
