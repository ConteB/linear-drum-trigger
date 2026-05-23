"""Layer-1 oracles for :mod:`evaluation.anti_leak_audit` (F0-T17 §3.3).

The Decision Lock A+C verification module is the most delicate of the four:
we synthesise audio fixtures that pass / fail each of the four tests in
isolation.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from tests.unit.test_evaluation_common import _make_dna

from evaluation.anti_leak_audit import (
    MODULE_NAME,
    TAIL_S,
    AntiLeakAuditError,
    _audio_features,
    _cross_engine_n_sample_match,
    _duration_engine_chi2,
    _tail_zero_per_engine,
    run,
)
from evaluation.common import GoldSampleMeta

pytestmark = pytest.mark.evaluation


THRESHOLDS = Path("src/evaluation/thresholds.yaml")
SR = 44100


# --- _audio_features ----------------------------------------------------------


def test_audio_features_silence_is_zero() -> None:
    x = np.zeros(SR, dtype=np.float32)
    f = _audio_features(x)
    assert list(f) == [0.0, 0.0, 0.0]


def test_audio_features_loud_signal_has_high_rms() -> None:
    x = np.ones(SR, dtype=np.float32) * 0.5
    f = _audio_features(x)
    assert f[0] == pytest.approx(0.5)  # rms of constant 0.5 is 0.5


def test_audio_features_zcr_for_alternating_signal() -> None:
    # alternating +1/-1 → ZCR ≈ 1.0 (sign changes every sample)
    x = np.array([1, -1] * (SR // 2), dtype=np.float32)
    f = _audio_features(x)
    assert f[2] > 0.99


# --- _duration_engine_chi2 ----------------------------------------------------


def _stub_meta(
    *,
    audio_path: Path,
    n_sample: int,
    engine: str,
    midi_source: str,
    n_mic: int = 2,
) -> GoldSampleMeta:
    return GoldSampleMeta(
        key=audio_path.stem.replace(".audio", ""),
        dna_path=audio_path.parent / f"{audio_path.stem}.dna.json",
        audio_path=audio_path,
        target_path=audio_path.parent / f"{audio_path.stem}.target.f16",
        split="train",
        engine=engine,
        kit="DRSKit",
        mic_config="multitrack_full",
        sample_rate=SR,
        midi_source=midi_source,
        n_mic=n_mic,
        n_sample=n_sample,
        n_frame=128,
        audio_sha256="", target_sha256="", recipe_sha256="",
        jitter_variant_idx=None,
        augmentation_level=1,
    )


def test_duration_engine_chi2_skips_when_single_engine() -> None:
    metas = [_stub_meta(audio_path=Path(f"/x{i}.audio.f16"), n_sample=SR,
                         engine="sfizz", midi_source=f"m{i}.mid") for i in range(10)]
    res = _duration_engine_chi2(metas)
    assert res["p_value"] is None
    assert "fewer than 2 engines" in res["skipped_reason"]


def test_duration_engine_chi2_independent_when_paired() -> None:
    """Paired MIDI×engine with identical n_sample → chi2 finds independence (high p)."""
    metas: list[GoldSampleMeta] = []
    for i in range(20):
        n_s = SR * (1 + i % 3)
        for engine in ("sfizz", "drumgizmo"):
            metas.append(_stub_meta(
                audio_path=Path(f"/m{i}-{engine}.audio.f16"),
                n_sample=n_s, engine=engine, midi_source=f"m{i}.mid",
            ))
    res = _duration_engine_chi2(metas)
    assert res["p_value"] is not None and res["p_value"] > 0.95


def test_duration_engine_chi2_dependent_when_engine_dictates_length() -> None:
    """Every engine systematically longer/shorter → low p (independence violated)."""
    metas: list[GoldSampleMeta] = []
    for i in range(30):
        metas.append(_stub_meta(
            audio_path=Path(f"/sfizz-{i}.audio.f16"),
            n_sample=SR, engine="sfizz", midi_source=f"m{i}.mid",
        ))
        metas.append(_stub_meta(
            audio_path=Path(f"/dgz-{i}.audio.f16"),
            n_sample=SR * 4, engine="drumgizmo", midi_source=f"m{i}.mid",
        ))
    res = _duration_engine_chi2(metas)
    assert res["p_value"] is not None and res["p_value"] < 0.05


def test_duration_engine_chi2_skips_when_all_durations_equal() -> None:
    metas: list[GoldSampleMeta] = []
    for i in range(10):
        metas.append(_stub_meta(audio_path=Path(f"/s{i}.audio.f16"), n_sample=SR,
                                 engine="sfizz", midi_source=f"m{i}.mid"))
        metas.append(_stub_meta(audio_path=Path(f"/d{i}.audio.f16"), n_sample=SR,
                                 engine="drumgizmo", midi_source=f"m{i}.mid"))
    res = _duration_engine_chi2(metas)
    assert "identical" in (res.get("skipped_reason") or "")


# --- _cross_engine_n_sample_match ---------------------------------------------


def test_cross_engine_match_100pct_when_lengths_equal() -> None:
    metas = []
    for i in range(5):
        for engine in ("sfizz", "drumgizmo"):
            metas.append(_stub_meta(audio_path=Path(f"/{engine}-{i}.audio.f16"),
                                     n_sample=SR * 2, engine=engine,
                                     midi_source=f"m{i}.mid"))
    res = _cross_engine_n_sample_match(metas)
    assert res["match_pct"] == 100.0
    assert res["n_paired_midi"] == 5
    assert res["n_mismatch"] == 0


def test_cross_engine_match_below_100_when_lengths_differ() -> None:
    metas = [
        _stub_meta(audio_path=Path("/s-0.audio.f16"), n_sample=SR,
                    engine="sfizz", midi_source="m0.mid"),
        _stub_meta(audio_path=Path("/d-0.audio.f16"), n_sample=SR * 2,
                    engine="drumgizmo", midi_source="m0.mid"),
    ]
    res = _cross_engine_n_sample_match(metas)
    assert res["n_mismatch"] == 1
    assert res["match_pct"] == 0.0


def test_cross_engine_match_skips_when_no_pairing() -> None:
    metas = [_stub_meta(audio_path=Path(f"/s-{i}.audio.f16"), n_sample=SR,
                         engine="sfizz", midi_source=f"m{i}.mid") for i in range(3)]
    res = _cross_engine_n_sample_match(metas)
    assert res["n_paired_midi"] == 0
    assert "skipped_reason" in res


# --- _tail_zero_per_engine ----------------------------------------------------


def _write_audio(path: Path, *, n_mic: int, n_sample: int, body_amp: float,
                  tail_amp: float, sr: int = SR, midi_idx: int = 0) -> None:
    """Write an audio.f16 with body |amp|=body_amp and tail |amp|=tail_amp.

    The body amplitude varies *with the MIDI index* (NOT with engine), so the
    MI estimator sees genuine feature variance unrelated to the engine label —
    which is exactly the situation Decision Lock A pairing forzato produces
    (each MIDI's audio is the same across engines once paired).
    """
    n_tail = int(sr * TAIL_S)
    n_body = n_sample - n_tail
    # Modulate amplitude AND ZCR by midi_idx so all three audio features
    # (rms / centroid / zcr) have genuine variance uncorrelated with engine.
    midi_body_amp = body_amp * (0.3 + 0.7 * ((midi_idx % 7) / 7.0))
    # Per-MIDI carrier frequency (50-450 Hz) → drives centroid + ZCR.
    f0 = 50.0 + 50.0 * (midi_idx % 9)
    t = np.arange(n_body, dtype=np.float32) / sr
    carrier = np.sin(2.0 * np.pi * f0 * t).astype(np.float32)
    body = np.broadcast_to(midi_body_amp * carrier, (n_mic, n_body)).copy()
    tail = np.full((n_mic, n_tail), tail_amp, dtype=np.float32)
    audio = np.concatenate([body, tail], axis=1).astype(np.float16)
    path.write_bytes(audio.tobytes())


def test_tail_zero_clean_tail_passes_threshold(tmp_path: Path) -> None:
    p = tmp_path / "s-0.audio.f16"
    _write_audio(p, n_mic=2, n_sample=SR * 2, body_amp=0.5, tail_amp=0.0)
    meta = _stub_meta(audio_path=p, n_sample=SR * 2, engine="sfizz",
                       midi_source="m0.mid")
    res = _tail_zero_per_engine([meta])
    assert res["per_engine"]["sfizz"]["median"] == pytest.approx(0.0)


def test_tail_zero_loud_tail_exceeds_threshold(tmp_path: Path) -> None:
    p = tmp_path / "s-0.audio.f16"
    _write_audio(p, n_mic=2, n_sample=SR * 2, body_amp=0.5, tail_amp=0.5)
    meta = _stub_meta(audio_path=p, n_sample=SR * 2, engine="sfizz",
                       midi_source="m0.mid")
    res = _tail_zero_per_engine([meta])
    assert res["per_engine"]["sfizz"]["median"] == pytest.approx(0.5, rel=0.01)


# --- run() — fixture-driven end-to-end ----------------------------------------


def _make_gold_with_engines(
    tmp_path: Path,
    *,
    n_midi: int,
    engines: list[str],
    n_sample: int,
    body_amp: float,
    tail_amp: float,
) -> Path:
    """Build a Gold dir with N MIDI × len(engines) samples (perfect pairing)."""
    gold = tmp_path / "gold"
    gold.mkdir(parents=True, exist_ok=True)
    for i in range(n_midi):
        for engine in engines:
            key = f"M{i:03d}-{engine.upper()}"
            _make_dna(gold, key=key, engine=engine, n_mic=2, n_sample=n_sample,
                      midi_source=f"bronze/gmd/m{i:03d}.mid", n_frame=64)
            _write_audio(gold / f"{key}.audio.f16", n_mic=2, n_sample=n_sample,
                          body_amp=body_amp, tail_amp=tail_amp, midi_idx=i)
            # target zeros — anti_leak doesn't read it.
            (gold / f"{key}.target.f16").write_bytes(
                np.zeros(64 * 25, dtype=np.float16).tobytes()
            )
    return gold


def test_run_passes_for_clean_paired_dataset(tmp_path: Path) -> None:
    gold = _make_gold_with_engines(
        tmp_path, n_midi=12, engines=["sfizz", "drumgizmo"],
        n_sample=SR * 2, body_amp=0.5, tail_amp=0.0,
    )
    result = run(gold_dir=gold, thresholds=THRESHOLDS, out_dir=tmp_path / "out")
    assert result.passed is True, result.failures


def test_run_fails_on_loud_tail(tmp_path: Path) -> None:
    gold = _make_gold_with_engines(
        tmp_path, n_midi=8, engines=["sfizz", "drumgizmo"],
        n_sample=SR * 2, body_amp=0.5, tail_amp=0.3,
    )
    result = run(gold_dir=gold, thresholds=THRESHOLDS, out_dir=tmp_path / "out")
    assert result.passed is False
    assert any("tail-zero" in f for f in result.failures)


def test_run_writes_json_and_png(tmp_path: Path) -> None:
    gold = _make_gold_with_engines(
        tmp_path, n_midi=6, engines=["sfizz", "drumgizmo"],
        n_sample=SR * 2, body_amp=0.4, tail_amp=0.0,
    )
    result = run(gold_dir=gold, thresholds=THRESHOLDS, out_dir=tmp_path / "out")
    assert result.report_json.exists()
    assert result.report_png.exists()
    doc = json.loads(result.report_json.read_text())
    assert doc["module_name"] == MODULE_NAME


def test_run_is_deterministic_for_same_seed(tmp_path: Path) -> None:
    gold = _make_gold_with_engines(
        tmp_path, n_midi=8, engines=["sfizz", "drumgizmo"],
        n_sample=SR * 2, body_amp=0.3, tail_amp=0.0,
    )
    r1 = run(gold_dir=gold, thresholds=THRESHOLDS, out_dir=tmp_path / "out1", seed=99)
    r2 = run(gold_dir=gold, thresholds=THRESHOLDS, out_dir=tmp_path / "out2", seed=99)
    assert r1.report_json.read_bytes() == r2.report_json.read_bytes()


def test_run_corrupt_audio_fails_loud(tmp_path: Path) -> None:
    gold = tmp_path / "gold"
    gold.mkdir()
    _make_dna(gold, key="A", n_mic=2, n_sample=SR * 2, n_frame=64,
              midi_source="m0.mid")
    # Truncate the audio file so the buffer size is wrong.
    (gold / "A.audio.f16").write_bytes(b"\x00" * 100)
    with pytest.raises(AntiLeakAuditError, match="expected"):
        run(gold_dir=gold, thresholds=THRESHOLDS, out_dir=tmp_path / "out")


def test_run_cli_exit_code(tmp_path: Path) -> None:
    from evaluation.anti_leak_audit import main

    gold = _make_gold_with_engines(
        tmp_path, n_midi=6, engines=["sfizz", "drumgizmo"],
        n_sample=SR * 2, body_amp=0.3, tail_amp=0.0,
    )
    rc = main([
        "--gold-dir", str(gold),
        "--thresholds", str(THRESHOLDS),
        "--out", str(tmp_path / "out"),
    ])
    assert rc == 0

    gold2 = _make_gold_with_engines(
        tmp_path / "two", n_midi=6, engines=["sfizz", "drumgizmo"],
        n_sample=SR * 2, body_amp=0.3, tail_amp=0.5,
    )
    rc = main([
        "--gold-dir", str(gold2),
        "--thresholds", str(THRESHOLDS),
        "--out", str(tmp_path / "out2"),
    ])
    assert rc == 1
