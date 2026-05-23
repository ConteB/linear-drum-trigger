"""Layer-1 oracles for :mod:`evaluation.common` (F0-T17 §5).

Covers the thresholds loader (LOCKED contract — fail-loud on malformed YAML)
and the Gold directory scanner (sort order, missing-triple fail-loud,
barcode decoding for 6-segment legacy keys vs 7-segment F0-T15-pre keys).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from evaluation.common import (
    GoldScanError,
    Thresholds,
    ThresholdsError,
    load_thresholds,
    scan_gold_dir,
    write_report_json,
)

pytestmark = pytest.mark.evaluation


# --- thresholds ---------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCKED_THRESHOLDS = REPO_ROOT / "src" / "evaluation" / "thresholds.yaml"


def test_locked_thresholds_loads_with_expected_values() -> None:
    thr = load_thresholds(LOCKED_THRESHOLDS)
    # Spot-check the LOCKED values from F0-T17 §4 — modifying any of these
    # without a new Decision Lock CEO is a violation of process.
    assert thr.bus_minority_pct == 5.0
    assert thr.ks_p_min == 0.05
    assert thr.duration_engine_chi2_p_min == 0.95
    assert thr.mi_audio_engine_max_bits == 0.10
    assert thr.cross_engine_match_pct_min == 100.0
    assert thr.onset_tolerance_ms == 25.0
    assert thr.bootstrap_n_resamples == 1000
    assert thr.per_bus_f_min == 0.80
    assert thr.f_macro_min == 0.85


def test_load_thresholds_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ThresholdsError, match="not found"):
        load_thresholds(tmp_path / "missing.yaml")


def test_load_thresholds_not_a_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just_a_list\n", encoding="utf-8")
    with pytest.raises(ThresholdsError, match="must be a mapping"):
        load_thresholds(bad)


def test_load_thresholds_missing_section(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("data_audit: {bpm_min: 40, bpm_max: 240}\n", encoding="utf-8")
    with pytest.raises(ThresholdsError, match="missing or malformed section"):
        load_thresholds(bad)


def test_load_thresholds_bpm_order_inverted(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        _build_yaml({"data_audit": {"bpm_min": 240, "bpm_max": 40}}),
        encoding="utf-8",
    )
    with pytest.raises(ThresholdsError, match="bpm_min"):
        load_thresholds(bad)


def test_load_thresholds_probability_out_of_range(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        _build_yaml({"split_consistency": {"ks_p_min": 1.5}}),
        encoding="utf-8",
    )
    with pytest.raises(ThresholdsError, match="must be in"):
        load_thresholds(bad)


def test_thresholds_is_immutable() -> None:
    from dataclasses import FrozenInstanceError

    thr = load_thresholds(LOCKED_THRESHOLDS)
    with pytest.raises(FrozenInstanceError):
        thr.ks_p_min = 0.99  # type: ignore[misc]


def _build_yaml(override: dict[str, dict[str, object]]) -> str:
    """Helper — start from the locked thresholds, apply ``override`` keys."""
    import yaml

    base = yaml.safe_load(LOCKED_THRESHOLDS.read_text(encoding="utf-8"))
    for section, fields in override.items():
        base.setdefault(section, {})
        base[section].update(fields)
    return yaml.safe_dump(base)


# --- scan_gold_dir ------------------------------------------------------------


def _make_dna(
    tmp_path: Path,
    *,
    key: str,
    split: str = "train",
    engine: str = "drumgizmo",
    kit: str = "DRSKit",
    mic_config: str = "multitrack_full",
    sample_rate: int = 44100,
    n_mic: int = 4,
    n_sample: int = 44100,
    n_frame: int = 128,
    midi_source: str = "bronze/gmd/groove_00.mid",
    augmentation_level: int = 1,
) -> Path:
    """Write a minimal but contract-valid {key}.dna.json + sibling f16 stubs."""
    doc = {
        "key": key,
        "barcode": key,
        "split": split,
        "recipe_sha256": "0" * 64,
        "audio": {
            "dtype": "float16",
            "shape": [n_mic, n_sample],
            "sha256": "1" * 64,
            "n_nonfinite": 0,
        },
        "target": {
            "dtype": "float16",
            "shape": [n_frame, 25],
            "sha256": "2" * 64,
            "n_nonfinite": 0,
            "frame_rate_hz": 344.53125,
            "layout": "flat-25",
        },
        "lineage": {
            "midi_source": {"dataset": "GMD", "file": midi_source},
            "render": {
                "engine": engine,
                "kit": kit,
                "mic_config": mic_config,
                "sample_rate": sample_rate,
            },
            "augmentation": {"level": augmentation_level},
            "midi_jitter": {"seed": 42},
        },
    }
    dna = tmp_path / f"{key}.dna.json"
    dna.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    audio = tmp_path / f"{key}.audio.f16"
    target = tmp_path / f"{key}.target.f16"
    audio.write_bytes(np.zeros(n_mic * n_sample, dtype=np.float16).tobytes())
    target.write_bytes(np.zeros(n_frame * 25, dtype=np.float16).tobytes())
    return dna


def test_scan_returns_sorted_metas(tmp_path: Path) -> None:
    _make_dna(tmp_path, key="ZZZ-LAST")
    _make_dna(tmp_path, key="AAA-FIRST")
    _make_dna(tmp_path, key="MMM-MIDDLE")
    metas = scan_gold_dir(tmp_path)
    assert [m.key for m in metas] == ["AAA-FIRST", "MMM-MIDDLE", "ZZZ-LAST"]


def test_scan_missing_audio_fails_loud(tmp_path: Path) -> None:
    _make_dna(tmp_path, key="GMD000")
    (tmp_path / "GMD000.audio.f16").unlink()
    with pytest.raises(GoldScanError, match="missing sibling audio file"):
        scan_gold_dir(tmp_path)


def test_scan_missing_target_fails_loud(tmp_path: Path) -> None:
    _make_dna(tmp_path, key="GMD000")
    (tmp_path / "GMD000.target.f16").unlink()
    with pytest.raises(GoldScanError, match="missing sibling target file"):
        scan_gold_dir(tmp_path)


def test_scan_empty_dir_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(GoldScanError, match="no .dna.json files"):
        scan_gold_dir(tmp_path)


def test_scan_dir_does_not_exist_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(GoldScanError, match="not a directory"):
        scan_gold_dir(tmp_path / "nope")


def test_scan_invalid_json_fails_loud(tmp_path: Path) -> None:
    (tmp_path / "GMD000.dna.json").write_text("not json", encoding="utf-8")
    with pytest.raises(GoldScanError, match="invalid JSON"):
        scan_gold_dir(tmp_path)


def test_scan_missing_required_dna_key(tmp_path: Path) -> None:
    bad = {"key": "GMD000"}  # missing split/audio/target/lineage/...
    (tmp_path / "GMD000.dna.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(GoldScanError, match="missing required key"):
        scan_gold_dir(tmp_path)


def test_scan_decodes_jitter_variant_from_7segment_barcode(tmp_path: Path) -> None:
    """F0-T15-pre barcode segment ``Jnn`` must surface as jitter_variant_idx."""
    _make_dna(tmp_path, key="GMD042-V1T1-J02-DGZ-R2-C1H0-SLK102")
    metas = scan_gold_dir(tmp_path)
    assert metas[0].jitter_variant_idx == 2


def test_scan_legacy_6segment_barcode_yields_none(tmp_path: Path) -> None:
    """Pre-F0-T15-pre keys (F0-T2e) have no ``Jnn`` slot — surface as None."""
    _make_dna(tmp_path, key="GMD000-V0T0-DGZ-R0-L1-NONE")
    metas = scan_gold_dir(tmp_path)
    assert metas[0].jitter_variant_idx is None


def test_scan_populates_all_fields(tmp_path: Path) -> None:
    _make_dna(
        tmp_path,
        key="GMD007",
        split="val",
        engine="sfizz",
        kit="Frankensnare",
        mic_config="glyn_johns",
        n_mic=2,
        n_sample=88200,
        n_frame=256,
        midi_source="bronze/gmd/drummer3/take7.mid",
        augmentation_level=2,
    )
    meta = scan_gold_dir(tmp_path)[0]
    assert meta.split == "val"
    assert meta.engine == "sfizz"
    assert meta.kit == "Frankensnare"
    assert meta.mic_config == "glyn_johns"
    assert meta.sample_rate == 44100
    assert (meta.n_mic, meta.n_sample) == (2, 88200)
    assert meta.n_frame == 256
    assert meta.midi_source == "bronze/gmd/drummer3/take7.mid"
    assert meta.augmentation_level == 2


# --- write_report_json --------------------------------------------------------


def test_write_report_json_is_deterministic_byte_per_byte(tmp_path: Path) -> None:
    payload = {"z": 1, "a": [3, 1, 2], "nested": {"y": 1, "x": 2}}
    p1 = write_report_json(tmp_path / "out1", "mod", payload)
    p2 = write_report_json(tmp_path / "out2", "mod", payload)
    assert p1.read_bytes() == p2.read_bytes()


def test_write_report_json_sorted_keys(tmp_path: Path) -> None:
    p = write_report_json(tmp_path, "mod", {"z": 1, "a": 2})
    body = p.read_text(encoding="utf-8")
    # 'a' must appear before 'z'.
    assert body.index('"a"') < body.index('"z"')


def test_thresholds_dataclass_construction_explicit() -> None:
    """Sanity — the dataclass must accept all fields the loader populates."""
    thr = Thresholds(
        bus_minority_pct=5.0,
        bpm_min=40,
        bpm_max=240,
        velocity_n_bin=20,
        duration_n_bin=30,
        ks_p_min=0.05,
        chi2_p_min=0.05,
        midi_leakage_max=0,
        duration_engine_chi2_p_min=0.95,
        mi_audio_engine_max_bits=0.10,
        cross_engine_match_pct_min=100.0,
        onset_tolerance_ms=25.0,
        bootstrap_n_resamples=1000,
        bootstrap_ci_max_width=0.05,
        per_bus_f_min=0.80,
        f_macro_min=0.85,
    )
    assert thr.bus_minority_pct == 5.0
