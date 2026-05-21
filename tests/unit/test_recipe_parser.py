"""§6.2 — Recipe YAML parser oracle.

Critical module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3).
Contract: F0-T2a §1.1. Written test-first (F0-T9b); implemented by F0-T2b.
"""
from __future__ import annotations

import pytest

from data_engineering.gold.recipe import (
    Engine,
    MicConfig,
    Recipe,
    RecipeError,
    Split,
    parse_recipe,
)

pytestmark = pytest.mark.critical


def test_parses_canonical_recipe(valid_recipe_yaml) -> None:
    r = parse_recipe(valid_recipe_yaml)
    assert isinstance(r, Recipe)
    assert r.recipe_id == "R-GMD042-DGZ-001"
    assert r.schema_version == "1.0"
    assert r.split is Split.TRAIN
    assert r.render.engine is Engine.DRUMGIZMO
    assert r.render.mic_config is MicConfig.GLYN_JOHNS
    assert r.render.sample_rate == 44100
    assert r.midi_jitter.seed == 4242
    assert r.augmentation.level == 2
    assert r.target_frame_rate_hz == 344.53125


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param("", id="empty-document"),
        pytest.param("{}", id="empty-mapping"),
        pytest.param("recipe_id: only-this-field", id="missing-required-fields"),
        pytest.param("a: b\n  c: d\n bad-indent", id="malformed-yaml"),
    ],
)
def test_malformed_recipe_raises_recipe_error(bad) -> None:
    with pytest.raises(RecipeError):
        parse_recipe(bad)


def test_unknown_engine_is_rejected(valid_recipe_yaml) -> None:
    bad = valid_recipe_yaml.replace("engine: drumgizmo", "engine: fluidsynth")
    with pytest.raises(RecipeError):
        parse_recipe(bad)


def test_sample_rate_must_be_44100(valid_recipe_yaml) -> None:
    # F0-T2a §1.1 — sample_rate is fixed; 48 kHz is a contract violation.
    bad = valid_recipe_yaml.replace("sample_rate: 44100", "sample_rate: 48000")
    with pytest.raises(RecipeError):
        parse_recipe(bad)


def test_unknown_split_is_rejected(valid_recipe_yaml) -> None:
    # F0-T2a §1.1 / §3.6 — only train|val; holdout is real data, never a recipe.
    bad = valid_recipe_yaml.replace("split: train", "split: holdout")
    with pytest.raises(RecipeError):
        parse_recipe(bad)


def test_missing_seed_is_rejected(valid_recipe_yaml) -> None:
    # The RNG seed is mandatory — without it the sample is not reproducible
    # (ENGINEERING_STANDARDS §1). A partial Recipe must never be returned.
    bad = valid_recipe_yaml.replace("  seed: 4242\n", "")
    with pytest.raises(RecipeError):
        parse_recipe(bad)
