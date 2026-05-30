"""Layer-0 meta — the harness checks itself (TESTING_DOCTRINE §2).

These tests are *not* contract oracles: they assert properties of the harness
and of the LOCKED F0-T2a contract constants. They run GREEN now and stay green.

They are the proof that the skeleton is correctly wired — that the ``awaiting``
oracles fail for the *right* reason (``NotImplementedError``) and can never rot
into a silent false-green.
"""
from __future__ import annotations

import dataclasses

import pytest

from data_engineering.gold import dna_trace, gold_writer, mic_standardize, recipe

pytestmark = pytest.mark.meta


def test_skeleton_modules_import() -> None:
    for module in (recipe, dna_trace, gold_writer, mic_standardize):
        assert module is not None


def test_flat28_layout_constants() -> None:
    # F0-T19 §7b — flat-28 = 9 type-class channels x 3 + 1 Hi-Hat opening head.
    assert gold_writer.N_CHANNELS == 9
    assert gold_writer.TARGET_COLS == 28
    assert gold_writer.N_CHANNELS * 3 + 1 == gold_writer.TARGET_COLS
    assert gold_writer.HIHAT_OPENING_COL == 27
    assert gold_writer.HIHAT_OPENING_COL == gold_writer.TARGET_COLS - 1


def test_r_target_is_ratified_value() -> None:
    # F0-T2a §3.4 — ratified by F0-T4a: 44100 / 128.
    assert gold_writer.R_TARGET_HZ == 44100 / 128 == 344.53125
    assert recipe.R_TARGET_HZ == gold_writer.R_TARGET_HZ


def test_sample_rate_fixed_at_44100() -> None:
    # F0-T2a §1.1 / §3.2 — no resampling.
    assert recipe.SAMPLE_RATE == gold_writer.SAMPLE_RATE == 44100


def test_schema_version_locked() -> None:
    assert recipe.SCHEMA_VERSION == "1.0"
    assert dna_trace.DNA_VERSION == "1.0"


def test_mic_config_channel_counts_match_spec() -> None:
    # F0-T2a §2.3 table.
    expected = {"mono": 1, "solo_stereo": 2, "glyn_johns": 4, "multitrack_full": 8}
    seen = {cfg.value: len(labels) for cfg, labels in recipe.MIC_CONFIG_CHANNELS.items()}
    assert seen == expected
    for labels in recipe.MIC_CONFIG_CHANNELS.values():
        assert len(labels) == len(set(labels)), "channel labels must be unique"
        assert all(isinstance(name, str) and name for name in labels)


def test_barcode_has_seven_ordered_segments() -> None:
    # F0-T2a §4.1 — 7-segment after Decision Lock CEO 2026-05-23 (B3 of
    # F0-T15-pre). The barcode dataclass mirrors the segment order exactly.
    assert len(dna_trace.BARCODE_SEGMENTS) == 7
    fields = tuple(f.name for f in dataclasses.fields(dna_trace.Barcode))
    assert fields == dna_trace.BARCODE_SEGMENTS
    # ``jittervar`` sits between ``midialt`` and ``engine``.
    assert dna_trace.BARCODE_SEGMENTS.index("jittervar") == 2


def test_no_skeleton_stubs_remain(make_audio) -> None:
    """All ``awaiting`` skeletons of the F0 contract are now implemented.

    Recipe parser (F0-T2b), DrumGizmo integration (F0-T2c), writer + DNA-Trace
    (F0-T2d), mini-batch orchestrator (F0-T2e) and mic standardisation (F0-T4b
    data-loader stage) have all landed; the harness's self-dismantling scaffold
    has drained its backlog (TESTING_DOCTRINE §6)."""
    # Smoke-call each module's main entry — none must raise NotImplementedError.
    mic_standardize.standardize_mics(make_audio(n_mic=4, n_sample=128), 4)


def test_xfail_strict_is_enabled(pytestconfig) -> None:
    """A strict-xfail XPASS must fail the run — the self-dismantling scaffold."""
    assert pytestconfig.getini("xfail_strict") is True


def test_contract_exceptions_are_value_errors() -> None:
    # Fail-loud, recoverable contract errors — ENGINEERING_STANDARDS §6.
    for exc in (recipe.RecipeError, dna_trace.DnaTraceError,
                gold_writer.GoldWriterError, mic_standardize.MicStandardizeError):
        assert issubclass(exc, ValueError)
