"""Anti-shortcut audit — verifica numerica dei Decision Lock A+C (F0-T17 §3.3).

The Decision Lock CEO 2026-05-23 (sessione T1-prep-A/B) closed the
``duration → engine`` shortcut at two seams:

* **(A) Pairing forzato MIDI × Engine** in the F2-T1 recipe matrix — every
  bronze MIDI is rendered with every active engine, so the recipe-level
  contingency ``MIDI ⫫ engine`` is perfectly preserved.
* **(C) Tail standardization** ``tail_s = 0.5 s`` uniform in
  :mod:`orchestrate` — every audio buffer is trimmed/padded to
  ``last_onset_s + tail_s`` cross-engine, so audio duration carries no engine
  information beyond what's already in the MIDI structure.

This module verifies *numerically* that both Decision Locks actually hold on a
materialised Gold directory — the spec writes the theory, this code refuses
to start F2-T3 unless the theory is empirically confirmed.

Four tests, all blocking F2-T3:

1. **Duration-Engine independence** — χ² on the contingency table
   ``(audio_duration_bin × engine)``. We require ``p ≥ 0.95`` (H0 indipendenza
   non rifiutata). The high bar is on purpose: any p that drops below 0.95
   means the tail standardisation is leaking some duration signal.
2. **MI(audio_first_1s ; engine)** — mutual information between a tiny
   feature vector (RMS, spectral centroid, zero-crossing rate of the first
   1 s of the audio buffer) and the engine label, in bits. Must be ≤ 0.10
   bits.
3. **Cross-engine ``n_sample`` consistency** — for every bronze MIDI paired
   across engines in the recipe matrix, the audio buffer length must match
   exactly. 100 % match required.
4. **Tail-zero policy coherence** — the average ``|amplitude|`` over the
   last ``min(n_sample, sr·tail_s)`` samples must follow a coherent
   distribution across engines (silent or near-silent everywhere). Surfaced
   as a per-engine summary; failure threshold is 1 % of full-scale on the
   median.

Spec: ``docs/methodology/F0-T17_STATISTICAL_TEST_PLAN.md`` §3.3.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats  # type: ignore[import-untyped]
from sklearn.feature_selection import mutual_info_classif  # type: ignore[import-untyped]

from evaluation.common import (
    GoldSampleMeta,
    ReportResult,
    Thresholds,
    _configure_lab_precision_style,
    load_thresholds,
    save_lab_precision_figure,
    scan_gold_dir,
    write_report_json,
)

#: Module identifier.
MODULE_NAME = "anti_leak_audit"

#: Tail duration enforced by orchestrate.py — F0-T2a §3.8 v1.2.0.
TAIL_S = 0.5

#: Tail-zero failure threshold — 1 % of full-scale on the median per-engine
#: tail amplitude. A tail standardised by pad-zero (orchestrate.py
#: standardize_audio_tail) is genuinely silent; a tail that retained the
#: engine's natural decay would carry an engine signature.
TAIL_ZERO_MEDIAN_MAX = 0.01

#: Number of duration bins used for the χ² duration-engine test. Few bins
#: keep cell counts large enough for χ² validity (Cochran's rule of thumb,
#: expected count ≥ 5); the test is robust to the exact choice as long as
#: bins are equiprobable on the duration marginal.
_DURATION_N_BIN = 5


class AntiLeakAuditError(RuntimeError):
    """Raised when the audit cannot run (no engine paired, audio unreadable)."""


def _audio_first_second(meta: GoldSampleMeta) -> np.ndarray:
    """Read the first 1 s of the audio buffer as a mono float32 array.

    The buffer is stored as ``[n_mic, n_sample]`` float16 little-endian
    (F0-T2a §3.1). We average across mics — the engine signature we're
    auditing is not channel-specific.
    """
    n_take = min(meta.sample_rate, meta.n_sample)
    expected = meta.n_mic * meta.n_sample
    buf = np.fromfile(meta.audio_path, dtype=np.float16)
    if buf.size != expected:
        raise AntiLeakAuditError(
            f"{meta.audio_path}: expected {expected} float16 values, got {buf.size}"
        )
    audio = buf.reshape(meta.n_mic, meta.n_sample).astype(np.float32)
    out: np.ndarray = audio[:, :n_take].mean(axis=0)
    return out


def _audio_tail(meta: GoldSampleMeta) -> np.ndarray:
    """Read the last ``min(n_sample, sr·TAIL_S)`` samples (mono mean)."""
    n_take = min(int(meta.sample_rate * TAIL_S), meta.n_sample)
    expected = meta.n_mic * meta.n_sample
    buf = np.fromfile(meta.audio_path, dtype=np.float16)
    if buf.size != expected:
        raise AntiLeakAuditError(
            f"{meta.audio_path}: expected {expected} float16 values, got {buf.size}"
        )
    audio = buf.reshape(meta.n_mic, meta.n_sample).astype(np.float32)
    out: np.ndarray = audio[:, -n_take:].mean(axis=0)
    return out


def _audio_features(x: np.ndarray) -> np.ndarray:
    """Compact feature vector for the MI test: ``[rms, centroid_norm, zcr]``.

    * RMS over the whole 1 s window — captures loudness signature.
    * Spectral centroid normalised by ``sr/2`` — captures timbral brightness.
    * Zero-crossing rate — captures transient density.

    Three features keep the MI estimator stable at the small N typical of
    pre-F2-T1 mini-batches.
    """
    if x.size == 0:
        return np.array([0.0, 0.0, 0.0], dtype=np.float64)
    # RMS
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    # Spectral centroid (single-frame FFT — coarse but consistent).
    spectrum = np.abs(np.fft.rfft(x.astype(np.float64)))
    freqs = np.fft.rfftfreq(x.size, d=1.0)  # bin units; cancels in normalisation
    total = float(spectrum.sum())
    if total > 0:
        centroid = float((spectrum * freqs).sum() / total)
    else:
        centroid = 0.0
    # ZCR
    if x.size >= 2:
        zcr = float(np.mean(np.diff(np.sign(x)) != 0))
    else:
        zcr = 0.0
    return np.array([rms, centroid, zcr], dtype=np.float64)


def _engine_label_encoder(engines: list[str]) -> tuple[list[int], list[str]]:
    """Encode engine strings to small integer labels, return ``(labels, vocab)``."""
    vocab = sorted(set(engines))
    table = {e: i for i, e in enumerate(vocab)}
    return [table[e] for e in engines], vocab


def _duration_engine_chi2(metas: list[GoldSampleMeta]) -> dict[str, Any]:
    """χ² test on the (duration_bin × engine) contingency table."""
    durations = np.array([m.n_sample / m.sample_rate for m in metas], dtype=np.float64)
    engines = [m.engine for m in metas]
    engine_vocab = sorted(set(engines))
    if len(engine_vocab) < 2:
        return {
            "statistic": None,
            "p_value": None,
            "n_engine": len(engine_vocab),
            "skipped_reason": "fewer than 2 engines — independence test undefined",
        }
    # Equi-quantile bins for the duration marginal (Cochran-friendly).
    edges = np.quantile(durations, np.linspace(0, 1, _DURATION_N_BIN + 1))
    # If durations are degenerate (all equal), no χ² is meaningful.
    if np.all(edges == edges[0]):
        return {
            "statistic": None,
            "p_value": None,
            "n_engine": len(engine_vocab),
            "skipped_reason": "audio durations identical — no variance to test",
        }
    # np.digitize binned with edges; clip into [0, _DURATION_N_BIN-1].
    bin_ids = np.clip(np.digitize(durations, edges[1:-1], right=False),
                       0, _DURATION_N_BIN - 1)
    table = np.zeros((_DURATION_N_BIN, len(engine_vocab)), dtype=np.int64)
    for b, e in zip(bin_ids, engines, strict=True):
        table[b, engine_vocab.index(e)] += 1
    # Drop any row that's all zero (no observations in that bin for any engine).
    nonempty_rows = table.sum(axis=1) > 0
    table = table[nonempty_rows]
    if table.shape[0] < 2:
        return {
            "statistic": None,
            "p_value": None,
            "n_engine": len(engine_vocab),
            "skipped_reason": "all observations fall in a single duration bin",
        }
    chi2, p, dof, _ = stats.chi2_contingency(table)
    return {
        "statistic": float(chi2),
        "p_value": float(p),
        "dof": int(dof),
        "n_engine": len(engine_vocab),
        "engines": engine_vocab,
        "contingency": table.tolist(),
        "duration_bin_edges": [float(x) for x in edges],
    }


def _mi_audio_engine(metas: list[GoldSampleMeta], *, seed: int) -> dict[str, Any]:
    """MI between the 3-D audio feature and the engine label, in bits."""
    if len({m.engine for m in metas}) < 2:
        return {
            "mi_bits": None,
            "skipped_reason": "fewer than 2 engines — MI is trivially 0",
        }
    X = np.vstack([_audio_features(_audio_first_second(m)) for m in metas])
    labels, vocab = _engine_label_encoder([m.engine for m in metas])
    # sklearn returns MI in nats per feature; sum -> joint upper bound, then convert.
    mi_nats = mutual_info_classif(X, np.asarray(labels), random_state=seed,
                                   discrete_features=False)
    # Conservative aggregate — take the *maximum* per-feature MI as the leak
    # signal (any single feature carrying engine info is a leak).
    mi_bits = float(mi_nats.max() / math.log(2))
    return {
        "mi_bits": mi_bits,
        "engines": vocab,
        "feature_mi_nats": [float(x) for x in mi_nats],
        "feature_names": ["rms", "spectral_centroid", "zcr"],
        "n_sample": len(metas),
    }


def _cross_engine_n_sample_match(metas: list[GoldSampleMeta]) -> dict[str, Any]:
    """For each bronze MIDI paired across ≥2 engines, check n_sample equality."""
    by_midi: dict[str, list[GoldSampleMeta]] = defaultdict(list)
    for m in metas:
        by_midi[m.midi_source].append(m)
    paired = [(midi, group) for midi, group in by_midi.items()
              if len({s.engine for s in group}) >= 2]
    if not paired:
        return {
            "match_pct": 100.0,
            "n_paired_midi": 0,
            "n_match": 0,
            "n_mismatch": 0,
            "skipped_reason": "no MIDI paired across engines (pairing not enforced)",
        }
    n_match = 0
    mismatches: list[dict[str, Any]] = []
    for midi, group in paired:
        n_samples = {s.engine: s.n_sample for s in group}
        if len(set(n_samples.values())) == 1:
            n_match += 1
        else:
            mismatches.append({"midi_source": midi, "n_sample_by_engine": n_samples})
    pct = 100.0 * n_match / len(paired)
    return {
        "match_pct": pct,
        "n_paired_midi": len(paired),
        "n_match": n_match,
        "n_mismatch": len(mismatches),
        "mismatches": mismatches,
    }


def _tail_zero_per_engine(metas: list[GoldSampleMeta]) -> dict[str, Any]:
    """Per-engine median of ``mean|amplitude|`` over the standardised tail."""
    by_engine: dict[str, list[float]] = defaultdict(list)
    for m in metas:
        tail = _audio_tail(m)
        by_engine[m.engine].append(float(np.mean(np.abs(tail))) if tail.size else 0.0)
    summary: dict[str, dict[str, float]] = {}
    for e, vals in by_engine.items():
        arr = np.asarray(vals, dtype=np.float64)
        summary[e] = {
            "median": float(np.median(arr)),
            "max": float(arr.max()),
            "n": int(arr.size),
        }
    return {"per_engine": dict(sorted(summary.items())), "tail_s": TAIL_S}


def _build_figure(metrics: dict[str, Any]) -> Any:
    _configure_lab_precision_style()
    import matplotlib.pyplot as plt  # noqa: PLC0415

    fig, axes = plt.subplots(2, 2, figsize=(11, 7))

    # Panel 1 — duration-engine χ² p
    ax = axes[0, 0]
    p = metrics["duration_engine"].get("p_value")
    ax.bar(["p_value"], [p if p is not None else 0.0], color="#1a1a1a")
    ax.axhline(metrics["duration_engine_chi2_p_min"], linestyle="--",
                linewidth=0.8, color="#a00000")
    ax.set_title("χ²(duration_bin × engine) p")
    ax.set_ylim(0, 1.05)

    # Panel 2 — MI(audio; engine) bits
    ax = axes[0, 1]
    mi = metrics["mi_audio_engine"].get("mi_bits")
    ax.bar(["MI bits"], [mi if mi is not None else 0.0], color="#1a1a1a")
    ax.axhline(metrics["mi_audio_engine_max_bits"], linestyle="--",
                linewidth=0.8, color="#a00000")
    ax.set_title("MI(audio_first_1s ; engine) [bits]")

    # Panel 3 — cross-engine n_sample match
    ax = axes[1, 0]
    pct = metrics["cross_engine_n_sample"].get("match_pct", 0.0)
    ax.bar(["match %"], [pct], color="#1a1a1a")
    ax.axhline(metrics["cross_engine_match_pct_min"], linestyle="--",
                linewidth=0.8, color="#a00000")
    ax.set_ylim(0, 105)
    ax.set_title("Cross-engine n_sample match (%)")

    # Panel 4 — tail-zero per engine
    ax = axes[1, 1]
    per = metrics["tail_zero"]["per_engine"]
    if per:
        ax.bar(list(per.keys()), [v["median"] for v in per.values()], color="#1a1a1a")
    ax.axhline(TAIL_ZERO_MEDIAN_MAX, linestyle="--", linewidth=0.8, color="#a00000")
    ax.set_title(f"Tail median |amplitude| per engine (last {TAIL_S} s)")
    ax.tick_params(axis="x", rotation=20)

    fig.suptitle(
        f"F0-T17 anti_leak_audit — n={metrics['n_sample']}", y=1.02
    )
    return fig


def run(
    *,
    gold_dir: Path | str,
    thresholds: Thresholds | Path | str,
    out_dir: Path | str,
    seed: int = 4242,
) -> ReportResult:
    """Run the four anti-leak tests on the Gold directory."""
    thr = thresholds if isinstance(thresholds, Thresholds) else load_thresholds(thresholds)
    metas = scan_gold_dir(gold_dir)
    if not metas:
        raise AntiLeakAuditError(f"{gold_dir}: empty Gold directory")

    duration_engine = _duration_engine_chi2(metas)
    mi = _mi_audio_engine(metas, seed=seed)
    pairing = _cross_engine_n_sample_match(metas)
    tail = _tail_zero_per_engine(metas)

    failures: list[str] = []

    # Test 1 — independence (p must NOT be too low; >= 0.95 required).
    p_dur = duration_engine.get("p_value")
    if p_dur is not None and p_dur < thr.duration_engine_chi2_p_min:
        failures.append(
            f"duration-engine independence violated: p={p_dur:.4f} < "
            f"{thr.duration_engine_chi2_p_min} — tail standardisation leaks "
            f"duration signal"
        )

    # Test 2 — MI bits
    mi_bits = mi.get("mi_bits")
    if mi_bits is not None and mi_bits > thr.mi_audio_engine_max_bits:
        failures.append(
            f"MI(audio_first_1s ; engine) = {mi_bits:.4f} bits > "
            f"{thr.mi_audio_engine_max_bits} — engine inferrable from short audio"
        )

    # Test 3 — cross-engine pairing
    pct = pairing.get("match_pct", 100.0)
    if pairing.get("n_paired_midi", 0) > 0 and pct < thr.cross_engine_match_pct_min:
        failures.append(
            f"cross-engine n_sample match = {pct:.1f}% < "
            f"{thr.cross_engine_match_pct_min}% — pairing forzato broken"
        )

    # Test 4 — tail-zero policy coherence
    for e, summary in tail["per_engine"].items():
        if summary["median"] > TAIL_ZERO_MEDIAN_MAX:
            failures.append(
                f"tail-zero policy violated for engine {e!r}: median tail "
                f"amplitude {summary['median']:.4f} > {TAIL_ZERO_MEDIAN_MAX}"
            )

    metrics: dict[str, Any] = {
        "module_name": MODULE_NAME,
        "n_sample": len(metas),
        "duration_engine_chi2_p_min": thr.duration_engine_chi2_p_min,
        "mi_audio_engine_max_bits": thr.mi_audio_engine_max_bits,
        "cross_engine_match_pct_min": thr.cross_engine_match_pct_min,
        "duration_engine": duration_engine,
        "mi_audio_engine": mi,
        "cross_engine_n_sample": pairing,
        "tail_zero": tail,
    }
    passed = not failures

    json_path = write_report_json(out_dir, MODULE_NAME, {**metrics, "passed": passed,
                                                          "failures": failures})
    fig = _build_figure(metrics)
    png_path = save_lab_precision_figure(out_dir, MODULE_NAME, fig)

    return ReportResult(
        module_name=MODULE_NAME,
        passed=passed,
        metrics=metrics,
        failures=failures,
        report_json=json_path,
        report_png=png_path,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="F0-T17 anti-leak audit — Decision Lock A+C numerical verification."
    )
    p.add_argument("--gold-dir", type=Path, required=True)
    p.add_argument("--thresholds", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=4242)
    args = p.parse_args(argv)
    result = run(
        gold_dir=args.gold_dir,
        thresholds=args.thresholds,
        out_dir=args.out,
        seed=args.seed,
    )
    print(
        f"[{MODULE_NAME}] {'PASS' if result.passed else 'FAIL'} — "
        f"n={result.metrics['n_sample']} "
        f"chi2_p={result.metrics['duration_engine'].get('p_value')} "
        f"mi={result.metrics['mi_audio_engine'].get('mi_bits')} "
        f"json={result.report_json}"
    )
    if not result.passed:
        for f in result.failures:
            print(f"  - {f}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
