"""§6.4 — Layer-3 fuzz: hostile inputs to the F0 parsers.

A hostile input must produce a *controlled* failure — the contract exception —
never an uncaught foreign exception, a crash, or silent corruption
(TESTING_DOCTRINE §2, §6.4). Awaiting F0-T2b / F0-T2d.
"""
from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from data_engineering.gold.mic_standardize import MicStandardizeError, standardize_mics
from data_engineering.gold.recipe import RecipeError, parse_recipe
from harness import awaiting

pytestmark = pytest.mark.fuzz

_FUZZ = settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@awaiting("F0-T2b")
@_FUZZ
@given(st.text(max_size=512))
def test_recipe_parser_only_ever_raises_recipe_error(blob) -> None:
    # The parser may parse it or reject it with RecipeError. Any *other*
    # exception escaping here is a real failure (the marker only absorbs
    # NotImplementedError from the skeleton stub).
    try:
        parse_recipe(blob)
    except RecipeError:
        pass


@awaiting("F0-T2b")
@_FUZZ
@given(st.binary(max_size=512))
def test_recipe_parser_survives_binary_garbage(blob) -> None:
    try:
        parse_recipe(blob.decode("latin-1"))
    except RecipeError:
        pass


@awaiting("F0-T4b")
@_FUZZ
@given(n_mic=st.integers(min_value=-32, max_value=64))
def test_mic_standardiser_fails_loud_on_bad_channel_count(n_mic) -> None:
    audio = np.zeros((4, 128), dtype=np.float16)
    try:
        out = standardize_mics(audio, n_mic)
    except MicStandardizeError:
        return  # controlled rejection — expected for out-of-range n_mic
    # If it did not raise, it must have produced the canonical 8-slot tensor.
    assert out.shape[0] == 8


def test_atheris_harness_is_available_or_cleanly_skipped() -> None:
    """Atheris is an OPTIONAL coverage-guided fuzz dep (§6.4). Either it is
    importable, or it is absent and the standalone harness skips cleanly —
    never a hard error in the suite."""
    atheris = pytest.importorskip(
        "atheris", reason="optional coverage-guided fuzz dependency — see requirements-dev.txt"
    )
    assert hasattr(atheris, "Fuzz")
