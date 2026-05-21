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


def test_flat25_layout_constants() -> None:
    # F0-T2a §3.3 — flat-25 = 8 buses x 3 channels + 1 Hi-Hat opening head.
    assert gold_writer.N_BUSES == 8
    assert gold_writer.TARGET_COLS == 25
    assert gold_writer.N_BUSES * 3 + 1 == gold_writer.TARGET_COLS
    assert gold_writer.HIHAT_OPENING_COL == 24
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


def test_barcode_has_six_ordered_segments() -> None:
    # F0-T2a §4.1 — the barcode dataclass mirrors the segment order exactly.
    assert len(dna_trace.BARCODE_SEGMENTS) == 6
    fields = tuple(f.name for f in dataclasses.fields(dna_trace.Barcode))
    assert fields == dna_trace.BARCODE_SEGMENTS


@pytest.mark.parametrize(
    "func, args",
    [
        (recipe.parse_recipe, ("",)),
        (recipe.load_recipe, ("/nonexistent.yaml",)),
        (dna_trace.decode_barcode, ("a-b-c-d-e-f",)),
        (gold_writer.n_frames, (1.0,)),
        (gold_writer.bus_columns, (0,)),
    ],
)
def test_skeleton_stubs_raise_notimplemented(func, args) -> None:
    """Every skeleton stub raises ``NotImplementedError`` — so the ``awaiting``
    oracles fail for the right reason and cannot decay into false greens."""
    with pytest.raises(NotImplementedError):
        func(*args)


def test_kwarg_stubs_raise_notimplemented(sample_barcode, sample_recipe, sample_dna,
                                          make_audio, make_target) -> None:
    audio, target = make_audio(), make_target()
    with pytest.raises(NotImplementedError):
        dna_trace.encode_barcode(sample_barcode)
    with pytest.raises(NotImplementedError):
        dna_trace.build_dna_json(
            barcode=sample_barcode, recipe=sample_recipe, audio=audio, target=target
        )
    with pytest.raises(NotImplementedError):
        dna_trace.validate_dna_json({}, audio=audio, target=target)
    with pytest.raises(NotImplementedError):
        gold_writer.write_gold_sample("/tmp", "k", audio=audio, target=target, dna=sample_dna)
    with pytest.raises(NotImplementedError):
        mic_standardize.standardize_mics(audio, 4)


def test_xfail_strict_is_enabled(pytestconfig) -> None:
    """A strict-xfail XPASS must fail the run — the self-dismantling scaffold."""
    assert pytestconfig.getini("xfail_strict") is True


def test_contract_exceptions_are_value_errors() -> None:
    # Fail-loud, recoverable contract errors — ENGINEERING_STANDARDS §6.
    for exc in (recipe.RecipeError, dna_trace.DnaTraceError,
                gold_writer.GoldWriterError, mic_standardize.MicStandardizeError):
        assert issubclass(exc, ValueError)
