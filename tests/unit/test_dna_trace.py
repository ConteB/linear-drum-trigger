"""§6.2 — DNA-Trace barcode + dna.json oracle.

Critical module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3).
Contract: F0-T2a §4. Written test-first — awaiting F0-T2d.
"""
from __future__ import annotations

import pytest

from data_engineering.gold.dna_trace import (
    DNA_VERSION,
    DnaTraceError,
    build_dna_json,
    decode_barcode,
    encode_barcode,
)
from harness import awaiting

pytestmark = pytest.mark.critical


@awaiting("F0-T2d")
def test_encode_matches_spec_example(sample_barcode) -> None:
    # F0-T2a §4.1 / §4.2 example.
    assert encode_barcode(sample_barcode) == "GMD042-V1T1-DGZ-R2-C1H0-SLK102"


@awaiting("F0-T2d")
def test_decode_matches_spec_example(sample_barcode) -> None:
    assert decode_barcode("GMD042-V1T1-DGZ-R2-C1H0-SLK102") == sample_barcode


@awaiting("F0-T2d")
def test_encoded_key_is_dot_free(sample_barcode) -> None:
    # F0-T2a §3.1 — the key must survive WebDataset extension splitting.
    assert "." not in encode_barcode(sample_barcode)


@awaiting("F0-T2d")
def test_decode_is_inverse_of_encode(sample_barcode) -> None:
    # The bijection property — TESTING_DOCTRINE §6.2.
    assert decode_barcode(encode_barcode(sample_barcode)) == sample_barcode


@awaiting("F0-T2d")
@pytest.mark.parametrize(
    "bad",
    [
        pytest.param("", id="empty"),
        pytest.param("only-three-segments-here", id="too-few-segments"),
        pytest.param("a-b-c-d-e-f-g-h", id="too-many-segments"),
        pytest.param("a.b-c-d-e-f", id="contains-dot"),
        pytest.param("a--c-d-e-f", id="empty-segment"),
    ],
)
def test_malformed_key_raises_dna_trace_error(bad) -> None:
    with pytest.raises(DnaTraceError):
        decode_barcode(bad)


@awaiting("F0-T2d")
def test_dna_json_records_version_and_lineage(sample_barcode, sample_recipe,
                                              make_audio, make_target) -> None:
    dna = build_dna_json(
        barcode=sample_barcode,
        recipe=sample_recipe,
        audio=make_audio(),
        target=make_target(),
    )
    assert dna["dna_version"] == DNA_VERSION
    assert dna["key"] == "GMD042-V1T1-DGZ-R2-C1H0-SLK102"
    assert dna["recipe_id"] == sample_recipe.recipe_id


@awaiting("F0-T2d")
def test_dna_json_records_buffer_integrity(sample_barcode, sample_recipe,
                                           make_audio, make_target) -> None:
    # F0-T2a §3.7 — sha256 + zero non-finite for both buffers.
    dna = build_dna_json(
        barcode=sample_barcode,
        recipe=sample_recipe,
        audio=make_audio(),
        target=make_target(),
    )
    for block in ("audio", "target"):
        assert dna[block]["n_nonfinite"] == 0
        assert len(dna[block]["sha256"]) == 64
