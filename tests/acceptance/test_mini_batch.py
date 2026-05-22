"""§6.3 acceptance oracles — F0-T2e mini-batch end-to-end.

The §6.3 acceptance check for F0-T2e is "smoke end-to-end + count of N Gold
samples" (TESTING_DOCTRINE §6.3). This module:

* proves the recipe set is well-formed and counts N — binary-free, always runs;
* smokes one Sfizz and one DrumGizmo recipe through the *whole* pipeline
  (recipe -> render -> audio.f16 + target.f16 -> dna.json) against the real
  vendored render toolchain, then re-reads the written triple from disk and
  verifies it with :func:`validate_dna_json`.

Each render smoke runs on its engine's native platform and skips elsewhere:
the vendored Sfizz build is macOS, DrumGizmo is provisioned on Linux / OrbStack
(no macOS prebuilt). The full N-sample run is the job of
``tools/run_mini_batch.py``, likewise one native pass per engine.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from data_engineering.gold.dna_trace import encode_barcode, validate_dna_json
from data_engineering.gold.gold_writer import TARGET_COLS
from data_engineering.gold.orchestrate import (
    DEFAULT_BUS_MAPPING_PATH,
    build_gold_sample,
    derive_barcode,
)
from data_engineering.gold.recipe import Engine, load_recipe
from data_engineering.gold.render import DEFAULT_SFIZZ_BINARY
from data_engineering.gold.target_builder import load_bus_mapping

pytestmark = pytest.mark.acceptance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECIPE_DIR = _REPO_ROOT / "recipes" / "mini_batch"
#: The mini-batch holds 12 scenarios — inside F0-T2e's "~10-20" target.
_EXPECTED_N = 12

#: The vendored ``sfizz_render`` is a macOS (Mach-O) build — the Sfizz smokes
#: run only on macOS. (Under OrbStack the binary loads but cannot reach the
#: Linux ``/tmp`` it is handed, so a presence check alone is not enough.)
_SFIZZ_READY = DEFAULT_SFIZZ_BINARY.is_file() and sys.platform == "darwin"
_SFIZZ_SKIP_REASON = "vendored sfizz_render is a macOS build — runs on macOS only"


def _recipes_for(engine: Engine) -> list[Path]:
    """Mini-batch recipe paths whose render engine is ``engine``."""
    return sorted(p for p in _RECIPE_DIR.glob("*.yaml") if load_recipe(p).render.engine is engine)


def _read_f16(path: Path, cols: int | None = None) -> np.ndarray:
    """Read a raw little-endian float16 buffer, optionally reshaped to ``cols``."""
    flat = np.fromfile(path, dtype="<f2")
    return flat.reshape(-1, cols) if cols is not None else flat


# --------------------------------------------------------------------------
# Recipe set — well-formed and counted (binary-free, always runs)
# --------------------------------------------------------------------------
def test_mini_batch_has_n_well_formed_recipes() -> None:
    """Every mini-batch recipe parses and the set holds the expected N."""
    recipe_paths = sorted(_RECIPE_DIR.glob("*.yaml"))
    assert len(recipe_paths) == _EXPECTED_N
    for path in recipe_paths:
        load_recipe(path)  # raises RecipeError on any schema violation


def test_mini_batch_barcode_keys_are_unique() -> None:
    """No two recipes derive the same WebDataset key — no silent overwrite."""
    keys = [
        encode_barcode(derive_barcode(load_recipe(p)))
        for p in sorted(_RECIPE_DIR.glob("*.yaml"))
    ]
    assert len(keys) == len(set(keys)), "mini-batch barcode keys must be unique"


def test_mini_batch_spans_both_render_engines() -> None:
    """The mini-batch exercises both Sfizz and DrumGizmo (F0-T2a §2)."""
    assert _recipes_for(Engine.SFIZZ)
    assert _recipes_for(Engine.DRUMGIZMO)


# --------------------------------------------------------------------------
# End-to-end smoke — Sfizz
# --------------------------------------------------------------------------
@pytest.mark.skipif(not _SFIZZ_READY, reason=_SFIZZ_SKIP_REASON)
def test_sfizz_recipe_runs_end_to_end(tmp_path: Path) -> None:
    """One Sfizz recipe yields a complete, self-consistent Gold triple."""
    recipe = load_recipe(_recipes_for(Engine.SFIZZ)[0])
    bus_mapping = load_bus_mapping(DEFAULT_BUS_MAPPING_PATH)

    result = build_gold_sample(recipe, out_dir=tmp_path, bus_mapping=bus_mapping)

    assert result.n_mic == 2  # Sfizz clean stereo stem (F0-T2a §2.1)
    assert result.audio_peak > 0.0
    for ext in ("audio.f16", "target.f16", "dna.json"):
        assert (tmp_path / f"{result.key}.{ext}").is_file()

    audio = _read_f16(tmp_path / f"{result.key}.audio.f16").reshape(result.n_mic, -1)
    target = _read_f16(tmp_path / f"{result.key}.target.f16", TARGET_COLS)
    assert target.shape[0] == result.n_frame
    # The written triple is self-consistent — hashes and shapes still verify.
    dna = json.loads((tmp_path / f"{result.key}.dna.json").read_text())
    validate_dna_json(dna, audio=audio, target=target)


@pytest.mark.skipif(not _SFIZZ_READY, reason=_SFIZZ_SKIP_REASON)
def test_sfizz_recipe_target_is_multi_bus(tmp_path: Path) -> None:
    """The transcription target carries onsets on several buses, not one."""
    recipe = load_recipe(_recipes_for(Engine.SFIZZ)[0])
    bus_mapping = load_bus_mapping(DEFAULT_BUS_MAPPING_PATH)
    result = build_gold_sample(recipe, out_dir=tmp_path, bus_mapping=bus_mapping)

    target = _read_f16(tmp_path / f"{result.key}.target.f16", TARGET_COLS).astype(np.float32)
    onset_cols = target[:, [3 * b for b in range(8)]]
    buses_with_onsets = int(np.count_nonzero(onset_cols.max(axis=0) > 0.5))
    assert buses_with_onsets >= 3, f"expected a multi-bus groove, got {buses_with_onsets}"


# --------------------------------------------------------------------------
# End-to-end smoke — DrumGizmo (Linux-only toolchain)
# --------------------------------------------------------------------------
@pytest.mark.skipif(
    shutil.which("drumgizmo") is None,
    reason="drumgizmo CLI not on PATH — provisioned on Linux, see vendor/README.md",
)
def test_drumgizmo_recipe_runs_end_to_end(tmp_path: Path) -> None:
    """One DrumGizmo recipe yields a standardised 8-mic Gold triple with bleed."""
    recipe = load_recipe(_recipes_for(Engine.DRUMGIZMO)[0])
    bus_mapping = load_bus_mapping(DEFAULT_BUS_MAPPING_PATH)

    result = build_gold_sample(recipe, out_dir=tmp_path, bus_mapping=bus_mapping)

    assert result.n_mic == 8  # standardised industry 8-channel layout (F0-T2a §2.3)
    assert result.audio_peak > 0.0
    for ext in ("audio.f16", "target.f16", "dna.json"):
        assert (tmp_path / f"{result.key}.{ext}").is_file()

    audio = _read_f16(tmp_path / f"{result.key}.audio.f16").reshape(result.n_mic, -1)
    target = _read_f16(tmp_path / f"{result.key}.target.f16", TARGET_COLS)
    dna = json.loads((tmp_path / f"{result.key}.dna.json").read_text())
    validate_dna_json(dna, audio=audio, target=target)
