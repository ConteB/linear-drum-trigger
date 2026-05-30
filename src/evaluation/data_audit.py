"""Gold-tensor distribution audit (F0-T17 §3.1) — informative, pre-F2-T3.

Walks a Gold directory and produces:

* class-imbalance — fraction of onsets per bus over the 8 transcription buses;
* velocity histogram per bus — ``[0, 1]`` in ``thresholds.velocity_n_bin`` bins;
* duration histogram — Gold sample length in seconds, in
  ``thresholds.duration_n_bin`` bins;
* HH-articulation histogram — closed / pedal / open counts from the
  continuous HH-opening column (24, F0-T2a §5);
* mic_config histogram;
* engine × kit contingency table.

The gate is **informative**: a bus carrying less than ``bus_minority_pct``
of the total onsets is flagged as *minoritario* so the F2-T3 trainer can
apply loss reweighting; nothing here blocks F2-T3 by itself
(:mod:`evaluation.split_consistency` and :mod:`evaluation.anti_leak_audit`
do).

Spec: ``docs/methodology/F0-T17_STATISTICAL_TEST_PLAN.md`` §3.1.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

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

#: Module identifier — anchors the report filename.
MODULE_NAME = "data_audit"

#: Number of transcription channels in the F0-T19 flat-28 layout (9 type-classes).
N_CHANNELS = 9
#: Column index of the continuous HH-opening head (F0-T19 §7b — 9*3 = 27).
HIHAT_OPENING_COL = 27
#: Total columns of the flat-28 target layout.
TARGET_COLS = 28

#: Onset detection floor — a frame counts as an onset only when its smeared
#: probability column ``3b`` exceeds this AND is a strict local maximum. The
#: 0.5 floor is robust to the Gaussian smearing of :mod:`target_builder`
#: (DOSSIER §6.2 — σ ≈ ±3 ms ≈ ±1 frame at 344 Hz, so the local-max rule
#: collapses a 2-3 frame skirt down to a single event).
ONSET_PROB_FLOOR = 0.5

#: HH-articulation bins applied to column 24 (F0-T2a §5). The continuous HH
#: head is quantised to {closed, pedal, open} by the renderer's mapping;
#: these three thresholds are the inverse projection.
_HH_CLOSED_MAX = 0.20
_HH_PEDAL_MAX = 0.60


class DataAuditError(RuntimeError):
    """Raised when a Gold sample cannot be audited (corrupt target, etc.)."""


def _load_target(meta: GoldSampleMeta) -> np.ndarray:
    """Read ``meta.target_path`` as a ``[n_frame, TARGET_COLS]`` float32 array."""
    buf = np.fromfile(meta.target_path, dtype=np.float16)
    expected = meta.n_frame * TARGET_COLS
    if buf.size != expected:
        raise DataAuditError(
            f"{meta.target_path}: expected {expected} float16 values "
            f"({meta.n_frame}×{TARGET_COLS}), got {buf.size}"
        )
    return buf.reshape(meta.n_frame, TARGET_COLS).astype(np.float32)


def _count_onsets(target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(per-bus onset counts, per-bus list of velocities)``.

    An onset frame is a frame where the bus's onset column (``3b``) exceeds
    :data:`ONSET_PROB_FLOOR` *and* is a strict local maximum (the local-max
    rule collapses the Gaussian skirt to a single event).

    Output:
        counts: shape ``(N_CHANNELS,)``, dtype ``int64``.
        velocities: shape ``(N_CHANNELS,)``, dtype ``object`` (each cell a
            ``np.ndarray[float32]`` of normalised velocities at the detected
            onset frames).
    """
    counts = np.zeros(N_CHANNELS, dtype=np.int64)
    velocities: list[np.ndarray] = []
    for b in range(N_CHANNELS):
        onset_col = target[:, 3 * b]
        vel_col = target[:, 3 * b + 1]
        above = onset_col > ONSET_PROB_FLOOR
        if onset_col.size >= 3:
            left = np.concatenate(([-np.inf], onset_col[:-1]))
            right = np.concatenate((onset_col[1:], [-np.inf]))
            local_max = (onset_col > left) & (onset_col > right)
        else:
            local_max = np.ones_like(onset_col, dtype=bool)
        is_onset = above & local_max
        counts[b] = int(is_onset.sum())
        velocities.append(vel_col[is_onset].astype(np.float32))
    return counts, np.asarray(velocities, dtype=object)


def _hh_articulation_counts(target: np.ndarray) -> dict[str, int]:
    """Quantise the continuous HH head (col 24) into {closed, pedal, open}.

    Counts the step-held *segments*, not the per-frame samples — a 4-bar
    segment of "open" hi-hat counts as one open event.
    """
    head = target[:, HIHAT_OPENING_COL]
    if head.size == 0:
        return {"closed": 0, "pedal": 0, "open": 0}
    states = np.where(
        head <= _HH_CLOSED_MAX,
        0,  # closed
        np.where(head <= _HH_PEDAL_MAX, 1, 2),  # pedal / open
    )
    # A "segment" begins where the state transitions; the first frame is
    # always a transition by definition.
    transitions = np.concatenate(([True], states[1:] != states[:-1]))
    seg_states = states[transitions]
    counts = Counter(int(s) for s in seg_states)
    return {
        "closed": int(counts.get(0, 0)),
        "pedal": int(counts.get(1, 0)),
        "open": int(counts.get(2, 0)),
    }


def _build_velocity_histogram(
    velocities_per_sample: list[np.ndarray], n_bin: int
) -> list[list[int]]:
    """Per-bus velocity histogram, ``n_bin`` bins on ``[0, 1]``.

    ``velocities_per_sample[i]`` is the per-bus velocity array of sample ``i``.
    """
    edges = np.linspace(0.0, 1.0, n_bin + 1)
    histograms: list[list[int]] = []
    for b in range(N_CHANNELS):
        all_v = np.concatenate([s[b] for s in velocities_per_sample if s[b].size > 0]) \
            if any(s[b].size > 0 for s in velocities_per_sample) else np.array([])
        hist, _ = np.histogram(all_v, bins=edges)
        histograms.append([int(x) for x in hist])
    return histograms


def _build_duration_histogram(metas: list[GoldSampleMeta], n_bin: int) -> dict[str, Any]:
    """Histogram of sample durations (seconds) in ``n_bin`` bins."""
    durations = np.array([m.n_sample / m.sample_rate for m in metas], dtype=np.float64)
    if durations.size == 0:
        return {"bin_edges": [], "counts": []}
    edges = np.linspace(durations.min(), durations.max(), n_bin + 1)
    hist, _ = np.histogram(durations, bins=edges)
    return {
        "bin_edges": [float(x) for x in edges],
        "counts": [int(x) for x in hist],
        "min_s": float(durations.min()),
        "max_s": float(durations.max()),
        "mean_s": float(durations.mean()),
    }


def _engine_kit_contingency(metas: list[GoldSampleMeta]) -> dict[str, dict[str, int]]:
    """``contingency[engine][kit] = count``."""
    table: dict[str, dict[str, int]] = {}
    for m in metas:
        table.setdefault(m.engine, {}).setdefault(m.kit, 0)
        table[m.engine][m.kit] += 1
    # Sort keys for deterministic JSON.
    return {e: dict(sorted(table[e].items())) for e in sorted(table)}


def _mic_config_histogram(metas: list[GoldSampleMeta]) -> dict[str, int]:
    """``mic_histogram[mic_config] = count``."""
    counts: Counter[str] = Counter(m.mic_config for m in metas)
    return dict(sorted(counts.items()))


def _split_histogram(metas: list[GoldSampleMeta]) -> dict[str, int]:
    """``split_histogram[split] = count``."""
    counts: Counter[str] = Counter(m.split for m in metas)
    return dict(sorted(counts.items()))


def _build_figure(metrics: dict[str, Any]) -> Any:
    """Compose the Laboratory-Precision PNG (4-panel)."""
    _configure_lab_precision_style()
    import matplotlib.pyplot as plt  # noqa: PLC0415

    fig, axes = plt.subplots(2, 2, figsize=(10, 7))

    # Panel 1 — class imbalance
    ax = axes[0, 0]
    class_pct = metrics["class_imbalance_pct"]
    ax.bar(range(N_CHANNELS), class_pct, color="#1a1a1a")
    ax.axhline(metrics["bus_minority_pct"], linestyle="--", linewidth=0.8, color="#a00000")
    ax.set_title("Class imbalance (% of onsets per bus)")
    ax.set_xlabel("Bus index")
    ax.set_ylabel("% onsets")
    ax.set_xticks(range(N_CHANNELS))

    # Panel 2 — duration histogram
    ax = axes[0, 1]
    dur = metrics["duration_histogram"]
    if dur["counts"]:
        widths = np.diff(dur["bin_edges"])
        ax.bar(dur["bin_edges"][:-1], dur["counts"], width=widths, align="edge", color="#1a1a1a")
    ax.set_title(f"Duration histogram (mean={dur.get('mean_s', 0):.2f} s)")
    ax.set_xlabel("Duration [s]")
    ax.set_ylabel("Count")

    # Panel 3 — mic_config + engine totals
    ax = axes[1, 0]
    mic_h = metrics["mic_config_histogram"]
    if mic_h:
        ax.bar(list(mic_h.keys()), list(mic_h.values()), color="#1a1a1a")
    ax.set_title("Mic config distribution")
    ax.tick_params(axis="x", rotation=20)

    # Panel 4 — HH articulation
    ax = axes[1, 1]
    hh = metrics["hh_articulation"]
    ax.bar(list(hh.keys()), list(hh.values()), color="#1a1a1a")
    ax.set_title("Hi-Hat articulation (segments)")
    ax.set_ylabel("Count")

    fig.suptitle(f"F0-T17 data_audit — {metrics['n_sample']} samples", y=1.02)
    return fig


def run(
    *,
    gold_dir: Path | str,
    thresholds: Thresholds | Path | str,
    out_dir: Path | str,
    seed: int = 0,  # noqa: ARG001 — included for CLI uniformity (F0-T17 §5)
) -> ReportResult:
    """Run the data audit on the Gold directory.

    Args:
        gold_dir: Directory of Gold sample triples.
        thresholds: Either a loaded :class:`Thresholds` or a path to the
            ``thresholds.yaml`` file.
        out_dir: Destination for ``data_audit.report.json`` and ``.report.png``.
        seed: Reserved for symmetry with other modules (no randomness here).

    Returns:
        A :class:`ReportResult` with the gate verdict and the JSON metrics.
    """
    thr = thresholds if isinstance(thresholds, Thresholds) else load_thresholds(thresholds)
    metas = scan_gold_dir(gold_dir)

    total_onsets = np.zeros(N_CHANNELS, dtype=np.int64)
    velocities_per_sample: list[np.ndarray] = []
    hh_total: Counter[str] = Counter({"closed": 0, "pedal": 0, "open": 0})
    for m in metas:
        target = _load_target(m)
        counts, velocities = _count_onsets(target)
        total_onsets += counts
        velocities_per_sample.append(velocities)
        for k, v in _hh_articulation_counts(target).items():
            hh_total[k] += v

    n_all = int(total_onsets.sum())
    class_pct = (
        (total_onsets.astype(np.float64) / n_all * 100.0).tolist()
        if n_all > 0
        else [0.0] * N_CHANNELS
    )
    minority_buses = [
        b for b, pct in enumerate(class_pct) if 0.0 < pct < thr.bus_minority_pct
    ]
    # An empty bus (0 onsets) is a *different* failure mode than minority —
    # surface it separately so the trainer can refuse to fit it.
    empty_buses = [b for b, pct in enumerate(class_pct) if pct == 0.0]

    # Warnings — surfaced in metrics, but do NOT enter `failures`. The spec
    # (F0-T17 §7) classifies data_audit as *informativo*: it flags extreme
    # class imbalance (empty buses, minority buses) but never *blocks* F2-T3
    # on its own — that decision is reserved for the CEO via escalation. The
    # two blocking modules are split_consistency and anti_leak_audit.
    warnings: list[str] = []
    if empty_buses:
        warnings.append(f"empty bus(es) detected — zero onsets on {empty_buses}")
    if minority_buses:
        warnings.append(
            f"minority bus(es) under {thr.bus_minority_pct} %: {minority_buses} — "
            f"consider loss reweighting in F2-T3"
        )

    metrics: dict[str, Any] = {
        "module_name": MODULE_NAME,
        "n_sample": len(metas),
        "n_onset_total": n_all,
        "class_imbalance_pct": class_pct,
        "bus_minority_pct": thr.bus_minority_pct,
        "minority_buses": minority_buses,
        "empty_buses": empty_buses,
        "warnings": warnings,
        "velocity_histogram_per_bus": _build_velocity_histogram(
            velocities_per_sample, thr.velocity_n_bin
        ),
        "velocity_n_bin": thr.velocity_n_bin,
        "duration_histogram": _build_duration_histogram(metas, thr.duration_n_bin),
        "hh_articulation": dict(hh_total),
        "mic_config_histogram": _mic_config_histogram(metas),
        "engine_kit_contingency": _engine_kit_contingency(metas),
        "split_histogram": _split_histogram(metas),
    }

    # Informative module — never fails on distribution. Reserve `failures`
    # for irrecoverable conditions (corrupt target, malformed DNA); those
    # are raised as exceptions by the readers before we ever get here.
    failures: list[str] = []
    passed = True

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
    """CLI entry point — ``python -m evaluation.data_audit --gold-dir ...``."""
    p = argparse.ArgumentParser(
        description="F0-T17 data audit — Gold-tensor distribution stats."
    )
    p.add_argument("--gold-dir", type=Path, required=True)
    p.add_argument("--thresholds", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)
    result = run(
        gold_dir=args.gold_dir,
        thresholds=args.thresholds,
        out_dir=args.out,
        seed=args.seed,
    )
    warnings = result.metrics.get("warnings", [])
    print(
        f"[{MODULE_NAME}] {'PASS' if result.passed else 'FAIL'} — "
        f"{len(result.metrics.get('class_imbalance_pct', []))} buses, "
        f"{result.metrics.get('n_onset_total', 0)} onsets, "
        f"warnings={len(warnings)}, json={result.report_json}"
    )
    for w in warnings:
        print(f"  ⚠ {w}", file=sys.stderr)
    if not result.passed:
        for f in result.failures:
            print(f"  - {f}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
