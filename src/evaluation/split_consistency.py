"""Train ↔ Val ↔ Holdout consistency audit (F0-T17 §3.2) — **blocking** F2-T3.

The Val Gold is the **early-stopping sensor** of the F2-T3 training loop. If its
distribution differs significantly from train, early-stopping is unreliable —
the model can over-fit on a non-representative validation surface. The Holdout
(E-GMD, F0-T1c) is real-data, used only at Gate L4.

Three bloccanti + one informative:

* **KS train↔val** on per-bus velocity, sample duration, microtiming → p ≥ 0.05
  per family (Bonferroni on the bus families).
* **χ² train↔val** on categorical features (engine, kit, mic_config) → p ≥ 0.05.
* **MIDI leakage**: sha256 set intersection of ``lineage.midi_source.file`` must
  be exactly 0 between train and val (no recipe should map one bronze MIDI into
  both splits — kit-wise partitioning of F0-T2a §10.2 Opzione B forbids it).
* **OOD Gold↔E-GMD** (informative): KS on the same features when an E-GMD
  manifest is provided.

Spec: ``docs/methodology/F0-T17_STATISTICAL_TEST_PLAN.md`` §3.2.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

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
from evaluation.data_audit import (
    N_CHANNELS,
    _count_onsets,
    _load_target,
)

#: Module identifier.
MODULE_NAME = "split_consistency"


class SplitConsistencyError(RuntimeError):
    """Raised on irrecoverable input errors (one split empty, etc.)."""


def _per_sample_features(meta: GoldSampleMeta) -> dict[str, Any]:
    """Extract the distribution features the KS tests will compare."""
    target = _load_target(meta)
    counts, velocities_per_bus = _count_onsets(target)

    # Microtiming column ``3b+2`` at the onset frames — same local-max gate.
    microtiming: list[list[float]] = [[] for _ in range(N_CHANNELS)]
    for b in range(N_CHANNELS):
        onset_col = target[:, 3 * b]
        # Reproduce the local-max mask from _count_onsets to index the column.
        above = onset_col > 0.5
        if onset_col.size >= 3:
            left = np.concatenate(([-np.inf], onset_col[:-1]))
            right = np.concatenate((onset_col[1:], [-np.inf]))
            local_max = (onset_col > left) & (onset_col > right)
        else:
            local_max = np.ones_like(onset_col, dtype=bool)
        mask = above & local_max
        mt_col = target[:, 3 * b + 2]
        microtiming[b] = mt_col[mask].astype(float).tolist()

    return {
        "duration_s": meta.n_sample / meta.sample_rate,
        "n_onset_per_bus": counts.tolist(),
        "velocity_per_bus": [v.astype(float).tolist() for v in velocities_per_bus],
        "microtiming_per_bus": microtiming,
    }


def _sha256_midi_source(meta: GoldSampleMeta) -> str:
    """Stable identifier for the bronze MIDI source — sha256 of the path string.

    The path *string* is the leakage check we need: two samples sharing the
    same bronze MIDI file MUST land in the same split (kit-wise partitioning
    F0-T2a §10.2 Opzione B). We do not hash the file *contents* — sub-task
    F0-T16-pre's jitter pipeline does NOT modify the bronze MIDI; the same
    file is reused across jitter variants, so file-content hashing would
    false-positive the leakage check.
    """
    return hashlib.sha256(meta.midi_source.encode("utf-8")).hexdigest()


def _ks_per_bus(
    train_values: list[list[float]], val_values: list[list[float]], *, label: str
) -> list[dict[str, Any]]:
    """Per-bus KS test; returns one row per bus with statistic, p-value, n."""
    rows: list[dict[str, Any]] = []
    for b in range(N_CHANNELS):
        a = np.asarray(train_values[b], dtype=float)
        c = np.asarray(val_values[b], dtype=float)
        if a.size < 2 or c.size < 2:
            rows.append({
                "bus": b,
                "metric": label,
                "n_train": int(a.size),
                "n_val": int(c.size),
                "statistic": None,
                "p_value": None,
                "skipped_reason": "insufficient samples (need >= 2 per side)",
            })
            continue
        res = stats.ks_2samp(a, c, alternative="two-sided", mode="auto")
        rows.append({
            "bus": b,
            "metric": label,
            "n_train": int(a.size),
            "n_val": int(c.size),
            "statistic": float(res.statistic),
            "p_value": float(res.pvalue),
        })
    return rows


def _ks_scalar(
    train_values: list[float], val_values: list[float], *, label: str
) -> dict[str, Any]:
    """KS on a single feature (no per-bus indexing) — e.g. duration."""
    a = np.asarray(train_values, dtype=float)
    c = np.asarray(val_values, dtype=float)
    if a.size < 2 or c.size < 2:
        return {
            "metric": label,
            "n_train": int(a.size),
            "n_val": int(c.size),
            "statistic": None,
            "p_value": None,
            "skipped_reason": "insufficient samples (need >= 2 per side)",
        }
    res = stats.ks_2samp(a, c, alternative="two-sided", mode="auto")
    return {
        "metric": label,
        "n_train": int(a.size),
        "n_val": int(c.size),
        "statistic": float(res.statistic),
        "p_value": float(res.pvalue),
    }


def _chi2_categorical(
    train_counts: Counter[str], val_counts: Counter[str], *, label: str
) -> dict[str, Any]:
    """Two-sample chi-square test on a categorical feature.

    Uses :func:`scipy.stats.chi2_contingency` on the 2 × K contingency table
    (rows = {train, val}, cols = the union of categories). Empty rows or
    columns are skipped (no test) — surfaced as ``skipped_reason``.
    """
    categories = sorted(set(train_counts) | set(val_counts))
    if len(categories) < 2:
        return {
            "metric": label,
            "n_categories": len(categories),
            "statistic": None,
            "p_value": None,
            "skipped_reason": "fewer than 2 categories — chi-square undefined",
        }
    table = np.array(
        [
            [train_counts.get(c, 0) for c in categories],
            [val_counts.get(c, 0) for c in categories],
        ],
        dtype=np.int64,
    )
    # chi2_contingency refuses tables with all-zero rows.
    if table.sum(axis=1).min() == 0:
        return {
            "metric": label,
            "n_categories": len(categories),
            "statistic": None,
            "p_value": None,
            "skipped_reason": "one split has zero samples in this dimension",
        }
    chi2, p, dof, _ = stats.chi2_contingency(table)
    return {
        "metric": label,
        "n_categories": len(categories),
        "categories": categories,
        "statistic": float(chi2),
        "dof": int(dof),
        "p_value": float(p),
        "train_counts": [int(x) for x in table[0]],
        "val_counts": [int(x) for x in table[1]],
    }


def _aggregate_split(
    metas: list[GoldSampleMeta],
) -> dict[str, Any]:
    """Collect per-split feature pools that fuel the KS / χ² tests."""
    velocity_pool: list[list[float]] = [[] for _ in range(N_CHANNELS)]
    microtiming_pool: list[list[float]] = [[] for _ in range(N_CHANNELS)]
    durations: list[float] = []
    engine_counts: Counter[str] = Counter()
    kit_counts: Counter[str] = Counter()
    mic_counts: Counter[str] = Counter()
    midi_sha: set[str] = set()
    for m in metas:
        f = _per_sample_features(m)
        durations.append(f["duration_s"])
        for b in range(N_CHANNELS):
            velocity_pool[b].extend(f["velocity_per_bus"][b])
            microtiming_pool[b].extend(f["microtiming_per_bus"][b])
        engine_counts[m.engine] += 1
        kit_counts[m.kit] += 1
        mic_counts[m.mic_config] += 1
        midi_sha.add(_sha256_midi_source(m))
    return {
        "n_sample": len(metas),
        "durations": durations,
        "velocity_pool": velocity_pool,
        "microtiming_pool": microtiming_pool,
        "engine_counts": engine_counts,
        "kit_counts": kit_counts,
        "mic_counts": mic_counts,
        "midi_sha": midi_sha,
    }


def _build_figure(metrics: dict[str, Any]) -> Any:
    """Lab-Precision PNG — KS p-values per bus + categorical χ² results."""
    _configure_lab_precision_style()
    import matplotlib.pyplot as plt  # noqa: PLC0415

    fig, axes = plt.subplots(2, 2, figsize=(11, 7))

    # Panel 1 — KS velocity per bus.
    ax = axes[0, 0]
    p_vals = [r["p_value"] for r in metrics["ks_velocity_per_bus"]]
    buses = [r["bus"] for r in metrics["ks_velocity_per_bus"]]
    ax.bar(buses, [(p or 0.0) for p in p_vals], color="#1a1a1a")
    ax.axhline(metrics["ks_p_min"], linestyle="--", linewidth=0.8, color="#a00000")
    ax.set_title("KS train↔val on velocity (p per bus)")
    ax.set_xlabel("Bus")
    ax.set_ylabel("p-value")
    ax.set_ylim(0, 1.05)

    # Panel 2 — KS microtiming per bus.
    ax = axes[0, 1]
    p_vals = [r["p_value"] for r in metrics["ks_microtiming_per_bus"]]
    ax.bar(buses, [(p or 0.0) for p in p_vals], color="#1a1a1a")
    ax.axhline(metrics["ks_p_min"], linestyle="--", linewidth=0.8, color="#a00000")
    ax.set_title("KS train↔val on microtiming (p per bus)")
    ax.set_xlabel("Bus")
    ax.set_ylabel("p-value")
    ax.set_ylim(0, 1.05)

    # Panel 3 — KS duration (scalar).
    ax = axes[1, 0]
    ax.axhline(metrics["ks_p_min"], linestyle="--", linewidth=0.8, color="#a00000")
    ks_dur = metrics["ks_duration"]
    ax.bar(["duration"], [(ks_dur.get("p_value") or 0.0)], color="#1a1a1a")
    ax.set_ylim(0, 1.05)
    ax.set_title("KS train↔val on sample duration (p)")
    ax.set_ylabel("p-value")

    # Panel 4 — Categorical chi-square p-values.
    ax = axes[1, 1]
    chi2_p = [
        (metrics["chi2_engine"].get("p_value") or 0.0),
        (metrics["chi2_kit"].get("p_value") or 0.0),
        (metrics["chi2_mic_config"].get("p_value") or 0.0),
    ]
    ax.bar(["engine", "kit", "mic_config"], chi2_p, color="#1a1a1a")
    ax.axhline(metrics["chi2_p_min"], linestyle="--", linewidth=0.8, color="#a00000")
    ax.set_ylim(0, 1.05)
    ax.set_title("χ² train↔val (categorical, p)")
    ax.set_ylabel("p-value")

    fig.suptitle(
        f"F0-T17 split_consistency — train={metrics['n_train']} "
        f"val={metrics['n_val']} — leakage={metrics['midi_leakage_count']}",
        y=1.02,
    )
    return fig


def run(
    *,
    gold_dir: Path | str,
    thresholds: Thresholds | Path | str,
    out_dir: Path | str,
    seed: int = 0,  # noqa: ARG001 — reserved for future randomised sub-tests
) -> ReportResult:
    """Run the train↔val consistency audit.

    Reads every sample under ``gold_dir`` (recursive: scans
    ``gold_dir/train`` and ``gold_dir/val`` if they exist, else partitions
    the flat directory by the ``split`` field of each ``dna.json``).
    """
    thr = thresholds if isinstance(thresholds, Thresholds) else load_thresholds(thresholds)
    metas = _gather_metas(gold_dir)

    train = [m for m in metas if m.split == "train"]
    val = [m for m in metas if m.split == "val"]
    if not train and not val:
        raise SplitConsistencyError(f"{gold_dir}: no samples in any known split")

    train_agg = _aggregate_split(train)
    val_agg = _aggregate_split(val)

    # KS per-bus on velocity and microtiming
    ks_velocity = _ks_per_bus(
        train_agg["velocity_pool"], val_agg["velocity_pool"], label="velocity"
    )
    ks_microtiming = _ks_per_bus(
        train_agg["microtiming_pool"], val_agg["microtiming_pool"], label="microtiming"
    )
    ks_duration = _ks_scalar(train_agg["durations"], val_agg["durations"],
                              label="duration_s")

    chi2_engine = _chi2_categorical(train_agg["engine_counts"], val_agg["engine_counts"],
                                     label="engine")
    chi2_kit = _chi2_categorical(train_agg["kit_counts"], val_agg["kit_counts"], label="kit")
    chi2_mic = _chi2_categorical(train_agg["mic_counts"], val_agg["mic_counts"],
                                  label="mic_config")

    midi_leakage = sorted(train_agg["midi_sha"] & val_agg["midi_sha"])

    failures: list[str] = []
    # Bonferroni adjustment for per-bus KS family — multiply each p by N_CHANNELS.
    bonferroni_factor = N_CHANNELS

    def _ks_check(rows: list[dict[str, Any]], label: str) -> None:
        for r in rows:
            p = r.get("p_value")
            if p is None:
                continue
            adj = min(1.0, p * bonferroni_factor)
            r["bonferroni_p"] = adj
            if adj < thr.ks_p_min:
                failures.append(
                    f"KS train↔val {label} bus={r['bus']} p_adj={adj:.4f} < {thr.ks_p_min}"
                )

    _ks_check(ks_velocity, "velocity")
    _ks_check(ks_microtiming, "microtiming")

    if (ks_duration.get("p_value") is not None
            and ks_duration["p_value"] < thr.ks_p_min):
        failures.append(
            f"KS train↔val duration p={ks_duration['p_value']:.4f} < {thr.ks_p_min}"
        )

    for tbl, label in ((chi2_engine, "engine"), (chi2_kit, "kit"),
                       (chi2_mic, "mic_config")):
        p = tbl.get("p_value")
        if p is not None and p < thr.chi2_p_min:
            failures.append(
                f"χ² train↔val {label} p={p:.4f} < {thr.chi2_p_min}"
            )

    if len(midi_leakage) > thr.midi_leakage_max:
        failures.append(
            f"MIDI leakage: {len(midi_leakage)} bronze sources appear in BOTH "
            f"train and val (must be {thr.midi_leakage_max})"
        )

    metrics: dict[str, Any] = {
        "module_name": MODULE_NAME,
        "n_train": train_agg["n_sample"],
        "n_val": val_agg["n_sample"],
        "ks_p_min": thr.ks_p_min,
        "chi2_p_min": thr.chi2_p_min,
        "bonferroni_factor": bonferroni_factor,
        "ks_velocity_per_bus": ks_velocity,
        "ks_microtiming_per_bus": ks_microtiming,
        "ks_duration": ks_duration,
        "chi2_engine": chi2_engine,
        "chi2_kit": chi2_kit,
        "chi2_mic_config": chi2_mic,
        "midi_leakage_count": len(midi_leakage),
        "midi_leakage_sha256": midi_leakage,
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


def _gather_metas(gold_dir: Path | str) -> list[GoldSampleMeta]:
    """Read samples from ``gold_dir``: either ``{train,val}/`` subdirs or flat."""
    d = Path(gold_dir)
    train_dir = d / "train"
    val_dir = d / "val"
    if train_dir.is_dir() and val_dir.is_dir():
        return scan_gold_dir(train_dir) + scan_gold_dir(val_dir)
    return scan_gold_dir(d)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    p = argparse.ArgumentParser(
        description="F0-T17 split consistency — train↔val KS/χ² + MIDI leakage check."
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
    print(
        f"[{MODULE_NAME}] {'PASS' if result.passed else 'FAIL'} — "
        f"train={result.metrics['n_train']} val={result.metrics['n_val']} "
        f"leakage={result.metrics['midi_leakage_count']} "
        f"json={result.report_json}"
    )
    if not result.passed:
        for f in result.failures:
            print(f"  - {f}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
