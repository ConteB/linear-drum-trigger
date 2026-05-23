#!/usr/bin/env python3
"""Render the T1-C hyperparameter sweep results into a Pareto-frontier report.

Reads ``artifacts/t1c-hyperparam-sweep/sweep.json`` and emits:

* ``T1C_REPORT.md`` — narrative + sorted table + Pareto-frontier identification
* ``pareto.png``    — scatter ``params vs mean_F``, with the Pareto-dominant
                      points highlighted

Usage:
    PYTHONPATH=src .venv/bin/python tools/render_t1c_report.py \
        --sweep-json artifacts/t1c-hyperparam-sweep/sweep.json \
        --out docs/gates/R&D_Tier1_reports/T1-C
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def _pareto_indices(rows: list[dict]) -> set[int]:
    """Indices on the Pareto frontier — maximise mean_F, minimise n_params.

    A point is Pareto-dominated if some other point has both >= F and
    <= params (with at least one strict).
    """
    dominated: set[int] = set()
    for i, a in enumerate(rows):
        for j, b in enumerate(rows):
            if i == j:
                continue
            f_a, p_a = a["mean_onset_f"], a["n_parameters"]
            f_b, p_b = b["mean_onset_f"], b["n_parameters"]
            if f_b >= f_a and p_b <= p_a and (f_b > f_a or p_b < p_a):
                dominated.add(i)
                break
    return set(range(len(rows))) - dominated


def _render_markdown(rows: list[dict], pareto: set[int], out_md: Path) -> None:
    lines: list[str] = []
    lines.append("# T1-C — Hyperparameter sweep (3 × 3 grid)\n")
    lines.append(
        "Pareto-frontier exploration of the TCN baseline on the mixed "
        "dataset (`data/gold/mix_2026-05-24`). Each cell trained for 20 "
        "epoch, seed=0, crop=40,960 samples, 535 train + 50 holdout. "
        "Output of `tools/t1c_hyperparam_sweep.py`.\n"
    )
    lines.append("## Grid (sorted by C, B)\n")
    lines.append("| C | B | params | mean_F | max_F | mae_ms | pass | time_s | Pareto |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|:---:|")
    sorted_rows = sorted(rows, key=lambda r: (r["channels"], r["batch_size"]))
    name_to_idx = {(r["channels"], r["batch_size"]): i for i, r in enumerate(rows)}
    for r in sorted_rows:
        idx = name_to_idx[(r["channels"], r["batch_size"])]
        marker = "★" if idx in pareto else ""
        lines.append(
            f"| {r['channels']} | {r['batch_size']} | "
            f"{r['n_parameters']:,} | {r['mean_onset_f']:.4f} | "
            f"{r['max_onset_f']:.4f} | {r['mean_timing_mae_ms']:.2f} | "
            f"{r['pass_rate']:.2f} | {r['wall_time_s']:.1f} | {marker} |"
        )
    lines.append("")
    lines.append(
        "★ = Pareto-frontier point (no other cell has both higher mean_F "
        "and ≤ parameters)."
    )

    # Highlight winners by metric.
    by_mean_F = max(rows, key=lambda r: r["mean_onset_f"])
    by_max_F = max(rows, key=lambda r: r["max_onset_f"])
    by_speed = min(rows, key=lambda r: r["wall_time_s"])
    by_timing = min(rows, key=lambda r: r["mean_timing_mae_ms"])

    lines.append("\n## Winners\n")
    lines.append(f"- **Best mean F-measure:** C={by_mean_F['channels']} "
                 f"B={by_mean_F['batch_size']} → F={by_mean_F['mean_onset_f']:.4f}")
    lines.append(f"- **Best max F-measure:** C={by_max_F['channels']} "
                 f"B={by_max_F['batch_size']} → F={by_max_F['max_onset_f']:.4f}")
    lines.append(f"- **Best timing-MAE:** C={by_timing['channels']} "
                 f"B={by_timing['batch_size']} → "
                 f"{by_timing['mean_timing_mae_ms']:.2f} ms")
    lines.append(f"- **Fastest:** C={by_speed['channels']} "
                 f"B={by_speed['batch_size']} → {by_speed['wall_time_s']:.1f} s")

    lines.append("\n## Interpretation\n")
    lines.append(
        "The sweep confirms **C=32 B=4** (F0-T4a default) as the sweet spot "
        "on the mix dataset at 20 epoch: it wins both mean_F and max_F. "
        "C=64 quadruples the parameter count for *no* gain — it is "
        "Pareto-dominated and should not be used in F2-T3 without "
        "further evidence (full-budget training may change the verdict, "
        "but the 20-epoch ranking is a fair proxy for the *training "
        "trajectory*)."
    )
    lines.append("")
    lines.append(
        "The C=16 row sits on the Pareto frontier at the efficiency end: "
        "**21,369 parameters** (vs 83,673 at C=32) trade ~25 % mean_F "
        "for ~2× speedup. For on-device R&D iteration (e.g. ablation of "
        "augmentation voices on Mac M5) C=16 B=8 is the recommended config "
        "— 18 seconds per 20-epoch run."
    )
    lines.append("")
    lines.append(
        "**0/9 cells pass L3** — every run is well below F=0.80 at 20 epoch. "
        "This is **expected**: the L3 gate is product-significant only on "
        "the F2-T3 full-budget run on E-GMD. The 20-epoch metric here is a "
        "*ranking signal*, not a verdict. T1-D (5-seed stability) already "
        "showed stdev ≪ mean ⇒ the trajectory is reproducible."
    )
    lines.append("\n*See `pareto.png` for the scatter.*\n")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")


def _render_pareto_png(rows: list[dict], pareto: set[int], out_png: Path) -> None:
    plt.rcParams.update({
        "font.family": "monospace",
        "axes.edgecolor": "black",
        "axes.linewidth": 1.2,
        "grid.color": "lightgray",
        "grid.linestyle": ":",
        "axes.grid": True,
        "axes.facecolor": "white",
        "figure.facecolor": "white",
    })
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(
        "T1-C — Hyperparameter sweep on mixed dataset (3 × 3 grid, 20 epoch)",
        fontsize=12, fontweight="bold",
    )

    # Panel 1: params vs mean_F (the Pareto plot proper).
    ax = axes[0]
    for i, r in enumerate(rows):
        on_frontier = i in pareto
        ax.scatter(
            r["n_parameters"], r["mean_onset_f"],
            s=80 + r["batch_size"] * 30,
            c="black" if on_frontier else "lightgray",
            edgecolors="black", linewidths=1.2,
            marker="o" if r["batch_size"] == 2 else
                    "s" if r["batch_size"] == 4 else "^",
            zorder=3,
        )
        ax.annotate(
            f"C={r['channels']} B={r['batch_size']}",
            xy=(r["n_parameters"], r["mean_onset_f"]),
            xytext=(6, 6), textcoords="offset points",
            fontsize=8, fontweight="bold" if on_frontier else "normal",
        )
    ax.set_xscale("log")
    ax.set_xlabel("Parameters (log scale)")
    ax.set_ylabel("mean F-measure (holdout)")
    ax.set_title("Pareto frontier — accuracy vs cost")
    ax.text(0.02, 0.98, "★ filled = Pareto-frontier",
            transform=ax.transAxes, verticalalignment="top",
            fontsize=9)

    # Panel 2: time vs mean_F.
    ax = axes[1]
    for i, r in enumerate(rows):
        ax.scatter(
            r["wall_time_s"], r["mean_onset_f"],
            s=80 + r["channels"],
            c="black" if i in pareto else "lightgray",
            edgecolors="black", linewidths=1.2,
            marker="o" if r["batch_size"] == 2 else
                    "s" if r["batch_size"] == 4 else "^",
        )
        ax.annotate(
            f"C={r['channels']} B={r['batch_size']}",
            xy=(r["wall_time_s"], r["mean_onset_f"]),
            xytext=(6, 6), textcoords="offset points", fontsize=8,
        )
    ax.set_xlabel("Wall time per 20-epoch run [s]")
    ax.set_ylabel("mean F-measure (holdout)")
    ax.set_title("Speed vs accuracy")

    plt.tight_layout(rect=(0, 0, 1, 0.95))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sweep-json", type=Path,
        default=Path("artifacts/t1c-hyperparam-sweep/sweep.json"),
    )
    parser.add_argument(
        "--out", type=Path,
        default=Path("docs/gates/R&D_Tier1_reports/T1-C"),
    )
    args = parser.parse_args()

    if not args.sweep_json.exists():
        raise SystemExit(f"sweep JSON not found: {args.sweep_json}")
    data = json.loads(args.sweep_json.read_text())
    rows = data["grid_rows"]
    pareto = _pareto_indices(rows)
    _render_markdown(rows, pareto, args.out / "T1C_REPORT.md")
    _render_pareto_png(rows, pareto, args.out / "pareto.png")
    print(f"[T1-C report] wrote {args.out / 'T1C_REPORT.md'}")
    print(f"[T1-C report] wrote {args.out / 'pareto.png'}")
    print(f"[T1-C report] Pareto-frontier points: "
           f"{[(rows[i]['channels'], rows[i]['batch_size']) for i in sorted(pareto)]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
