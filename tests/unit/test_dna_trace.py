"""§6.2 — DNA-Trace barcode + dna.json oracle.

Critical module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3).
Contract: F0-T2a §4. Written test-first (F0-T9b); implemented by F0-T2d.
"""
from __future__ import annotations

import numpy as np
import pytest

from data_engineering.gold.dna_trace import (
    DNA_VERSION,
    Barcode,
    DnaTraceError,
    build_dna_json,
    decode_barcode,
    encode_barcode,
    validate_dna_json,
)

pytestmark = pytest.mark.critical


def test_encode_matches_spec_example(sample_barcode) -> None:
    # F0-T2a §4.1 / §4.2 example.
    assert encode_barcode(sample_barcode) == "GMD042-V1T1-DGZ-R2-C1H0-SLK102"


def test_decode_matches_spec_example(sample_barcode) -> None:
    assert decode_barcode("GMD042-V1T1-DGZ-R2-C1H0-SLK102") == sample_barcode


def test_encoded_key_is_dot_free(sample_barcode) -> None:
    # F0-T2a §3.1 — the key must survive WebDataset extension splitting.
    assert "." not in encode_barcode(sample_barcode)


def test_decode_is_inverse_of_encode(sample_barcode) -> None:
    # The bijection property — TESTING_DOCTRINE §6.2.
    assert decode_barcode(encode_barcode(sample_barcode)) == sample_barcode


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
    with pytest.raises(DnaTraceError, match="barcode key"):
        decode_barcode(bad)


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


# --------------------------------------------------------------------------
# F0-T2d coverage — codec validation, lineage detail, dna.json verification
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "segment, why",
    [
        pytest.param("HAS-DASH", "separator", id="dash"),
        pytest.param("HAS.DOT", "WebDataset-reserved", id="dot"),
        pytest.param("", "non-empty", id="empty"),
    ],
)
def test_encode_rejects_invalid_segment(segment, why) -> None:
    bad = Barcode(segment, "V1T1", "DGZ", "R2", "C1H0", "SLK102")
    with pytest.raises(DnaTraceError, match=why):
        encode_barcode(bad)


def test_decode_rejects_non_string() -> None:
    with pytest.raises(DnaTraceError, match="barcode key"):
        decode_barcode(12345)  # type: ignore[arg-type]


def test_decode_rejects_dotted_six_segment_key() -> None:
    # Six segments but a dot inside one — the dot check, not the count check.
    with pytest.raises(DnaTraceError, match="reserved"):
        decode_barcode("a.x-b-c-d-e-f")


def test_dna_json_records_full_lineage(sample_barcode, sample_recipe,
                                       make_audio, make_target) -> None:
    dna = build_dna_json(
        barcode=sample_barcode, recipe=sample_recipe,
        audio=make_audio(), target=make_target(),
    )
    lineage = dna["lineage"]
    assert lineage["midi_jitter"]["seed"] == sample_recipe.midi_jitter.seed
    assert lineage["render"]["engine"] == sample_recipe.render.engine.value
    assert lineage["render"]["mic_config"] == sample_recipe.render.mic_config.value
    assert lineage["augmentation"]["level"] == sample_recipe.augmentation.level
    assert lineage["midi_source"]["file"] == sample_recipe.midi_source.file
    assert dna["target"]["layout"] == "flat-25"
    assert dna["target"]["frame_rate_hz"] == sample_recipe.target_frame_rate_hz


def test_recipe_sha256_is_deterministic(sample_barcode, sample_recipe,
                                        make_audio, make_target) -> None:
    kwargs = dict(barcode=sample_barcode, recipe=sample_recipe,
                  audio=make_audio(), target=make_target())
    first = build_dna_json(**kwargs)["recipe_sha256"]
    second = build_dna_json(**kwargs)["recipe_sha256"]
    assert first == second
    assert len(first) == 64


def test_dna_json_honours_explicit_timestamp(sample_barcode, sample_recipe,
                                             make_audio, make_target) -> None:
    dna = build_dna_json(
        barcode=sample_barcode, recipe=sample_recipe,
        audio=make_audio(), target=make_target(),
        generated_at="2026-05-22T00:00:00Z",
    )
    assert dna["generated_at"] == "2026-05-22T00:00:00Z"


def test_dna_json_counts_non_finite_values(sample_barcode, sample_recipe,
                                           make_audio, make_target) -> None:
    audio = make_audio()
    audio[0, 0] = np.nan
    audio[0, 1] = np.inf
    dna = build_dna_json(
        barcode=sample_barcode, recipe=sample_recipe, audio=audio, target=make_target(),
    )
    assert dna["audio"]["n_nonfinite"] == 2


def test_validate_dna_json_accepts_freshly_built(sample_barcode, sample_recipe,
                                                 make_audio, make_target) -> None:
    audio, target = make_audio(), make_target()
    dna = build_dna_json(
        barcode=sample_barcode, recipe=sample_recipe, audio=audio, target=target,
    )
    validate_dna_json(dna, audio=audio, target=target)  # must not raise


def test_validate_dna_json_detects_altered_buffer(sample_barcode, sample_recipe,
                                                  make_audio, make_target) -> None:
    audio, target = make_audio(), make_target()
    dna = build_dna_json(
        barcode=sample_barcode, recipe=sample_recipe, audio=audio, target=target,
    )
    tampered = audio.copy()
    tampered[0, 0] = np.float16(tampered[0, 0] + 0.5)
    with pytest.raises(DnaTraceError, match="sha256 mismatch"):
        validate_dna_json(dna, audio=tampered, target=target)


def test_validate_dna_json_detects_shape_mismatch(sample_barcode, sample_recipe,
                                                  make_audio, make_target) -> None:
    audio, target = make_audio(n_mic=4, n_sample=4096), make_target()
    dna = build_dna_json(
        barcode=sample_barcode, recipe=sample_recipe, audio=audio, target=target,
    )
    with pytest.raises(DnaTraceError, match="shape"):
        validate_dna_json(dna, audio=make_audio(n_mic=4, n_sample=2048), target=target)


def test_validate_dna_json_rejects_missing_block(make_audio, make_target) -> None:
    with pytest.raises(DnaTraceError, match="missing"):
        validate_dna_json({}, audio=make_audio(), target=make_target())


def test_validate_dna_json_rejects_recorded_non_finite(sample_barcode, sample_recipe,
                                                       make_audio, make_target) -> None:
    audio, target = make_audio(), make_target()
    dna = build_dna_json(
        barcode=sample_barcode, recipe=sample_recipe, audio=audio, target=target,
    )
    dna["audio"]["n_nonfinite"] = 3
    with pytest.raises(DnaTraceError, match="non-finite"):
        validate_dna_json(dna, audio=audio, target=target)


def test_validate_dna_json_detects_non_finite_buffer(sample_barcode, sample_recipe,
                                                     make_audio, make_target) -> None:
    # The dna.json claims a clean buffer, but the buffer handed in has a NaN.
    audio, target = make_audio(), make_target()
    dna = build_dna_json(
        barcode=sample_barcode, recipe=sample_recipe, audio=audio, target=target,
    )
    tainted = audio.copy()
    tainted[0, 0] = np.nan
    with pytest.raises(DnaTraceError, match="NaN/Inf"):
        validate_dna_json(dna, audio=tainted, target=target)


def test_validate_dna_json_rejects_block_without_shape(sample_barcode, sample_recipe,
                                                       make_audio, make_target) -> None:
    # An integrity block missing its 'shape' is a malformed dna.json, not a crash.
    audio, target = make_audio(), make_target()
    dna = build_dna_json(
        barcode=sample_barcode, recipe=sample_recipe, audio=audio, target=target,
    )
    del dna["audio"]["shape"]
    with pytest.raises(DnaTraceError, match="shape"):
        validate_dna_json(dna, audio=audio, target=target)


# --------------------------------------------------------------------------
# F0-T2a §3.8 — tail standardisation parameters in dna.json
# --------------------------------------------------------------------------
def test_dna_json_records_tail_standardization(sample_barcode, sample_recipe,
                                                make_audio, make_target) -> None:
    """The tail-policy parameters live under the audio block (F0-T2a §3.8)."""
    dna = build_dna_json(
        barcode=sample_barcode, recipe=sample_recipe,
        audio=make_audio(), target=make_target(),
        last_onset_s=4.273, tail_s=0.5,
    )
    assert dna["audio"]["last_onset_s"] == pytest.approx(4.273)
    assert dna["audio"]["tail_s"] == pytest.approx(0.5)


def test_dna_json_rejects_negative_last_onset_or_tail(sample_barcode, sample_recipe,
                                                       make_audio, make_target) -> None:
    """Negative ``last_onset_s`` / ``tail_s`` violate the contract — fail loud."""
    with pytest.raises(DnaTraceError, match="last_onset_s"):
        build_dna_json(
            barcode=sample_barcode, recipe=sample_recipe,
            audio=make_audio(), target=make_target(),
            last_onset_s=-0.1, tail_s=0.5,
        )
    with pytest.raises(DnaTraceError, match="tail_s"):
        build_dna_json(
            barcode=sample_barcode, recipe=sample_recipe,
            audio=make_audio(), target=make_target(),
            last_onset_s=1.0, tail_s=-0.01,
        )
