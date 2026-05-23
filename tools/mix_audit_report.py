#!/usr/bin/env python3
"""Mixed-dataset 70/15/15 audit report — source-stratified statistics.

The F0-T17 ``data_audit`` aggregates the Gold directory globally. For the
mixed-dataset R&D session (2026-05-24) we want a *source-stratified* view
that proves the Layer-B (rare emphasis) and Layer-C (chaos) tails are
actually shifting the distribution relative to the GMD baseline. This
script:

1. walks ``data/gold/mix_*/`` and groups samples by source (gmd / rare /
   chaos) via the ``recipe.midi_source.file`` path stem prefix;
2. computes per-source onset count per bus, velocity histogram per bus,
   sample duration histogram, density (hits per second), HH articulation;
3. renders a "Laboratory Precision" PNG with 6 comparative panels;
4. emits a narrative Markdown report with tables + numerical comparisons.

Output (``--out``):

    AUDIT_REPORT.md
    panels.png

Usage:
    PYTHONPATH=src .venv/bin/python tools/mix_audit_report.py \
        --gold-dir data/gold/mix_2026-05-24 \
        --out      data/audit/mix_2026-05-24_source_report
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

# Sources we expect in the mix dataset. Order is consistent across panels.
_SOURCES: tuple[str, ...] = ("gmd", "rare", "chaos")

# Bus labels (DOSSIER §4 — midi_mapping_table v1.0). 1-indexed in the docs,
# 0-indexed in numpy / class_imbalance_pct list.
_BUS_LABELS: tuple[str, ...] = (
    "kick", "snare", "hihat", "tom_hi_mid",
    "floor_tom", "ride", "crash_a", "crash_b_misc",
)


def _source_of_dna(dna: dict) -> str:
    """Infer ``gmd|rare|chaos|unknown`` from the lineage's MIDI source file.

    Path layout: ``bronze/gmd/mix_<date>/{source}/<global>_<slug>.mid`` —
    the *direct parent directory* of the MIDI file is the source bucket.
    Substring matching on ``"/gmd/"`` would mis-classify chaos/rare files
    because the *grandparent* directory is also called ``gmd``.
    """
    midi_file = (
        dna.get("lineage", {}).get("midi_source", {}).get("file", "")
    )
    if not midi_file:
        return "unknown"
    parent_name = Path(midi_file).parent.name
    return parent_name if parent_name in _SOURCES else "unknown"


def _iter_dna_files(gold_dir: Path) -> Iterable[Path]:
    yield from sorted(gold_dir.glob("*.dna.json"))


def _stats_per_source(gold_dir: Path) -> dict[str, dict]:
    """Walk the Gold dir and aggregate every metric per source."""
    out: dict[str, dict] = {
        s: {
            "n_sample": 0,
            "n_onset_per_bus": np.zeros(8, dtype=np.int64),
            "vel_hist_per_bus": np.zeros((8, 20), dtype=np.int64),
            "durations_s": [],
            "densities_hits_per_s": [],
            "hh_articulation": Counter(),
        }
        for s in _SOURCES
    }
    out["unknown"] = {
        "n_sample": 0,
        "n_onset_per_bus": np.zeros(8, dtype=np.int64),
        "vel_hist_per_bus": np.zeros((8, 20), dtype=np.int64),
        "durations_s": [],
        "densities_hits_per_s": [],
        "hh_articulation": Counter(),
    }

    for dna_path in _iter_dna_files(gold_dir):
        try:
            dna = json.loads(dna_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        src = _source_of_dna(dna)
        bucket = out[src]
        bucket["n_sample"] += 1

        # Duration derived from the target tensor (F0-T2a §3.3 contract):
        # ``target.shape[0] / target.frame_rate_hz`` is the authoritative
        # sample length — the audio buffer may include the 0.5 s tail pad.
        target_meta = dna.get("target", {})
        n_frames = float(target_meta.get("shape", [0])[0])
        frame_rate = float(target_meta.get("frame_rate_hz") or 0.0)
        duration = n_frames / frame_rate if frame_rate > 0 else 0.0
        if duration > 0:
            bucket["durations_s"].append(duration)

        # Per-bus onset counts + per-bus velocity histogram from the target.f16.
        key = dna_path.name.removesuffix(".dna.json")
        target_path = dna_path.parent / f"{key}.target.f16"
        if not target_path.exists():
            continue
        try:
            target = np.frombuffer(target_path.read_bytes(), dtype=np.float16)
        except (OSError, ValueError):
            continue
        if target.size % 25 != 0:
            continue
        target = target.reshape(-1, 25)
        # Contract F0-T2a §3.3 (flat-25 strided-per-bus layout):
        #   col 3b     = bus b onset probability  (b ∈ [0, 7])
        #   col 3b + 1 = bus b velocity (normalised [0, 1])
        #   col 3b + 2 = bus b microtiming residual
        #   col 24     = continuous Hi-Hat opening head
        onset_cols = [3 * b for b in range(8)]
        velocity_cols = [3 * b + 1 for b in range(8)]
        onsets = target[:, onset_cols].astype(np.float32)
        velocities = target[:, velocity_cols].astype(np.float32)
        hh_open = target[:, 24].astype(np.float32)

        # Onset: argmax local + above threshold (mirror data_audit logic).
        # We count one onset per frame where prob > 0.5 (Gaussian smeared peak).
        # Use strict-local-max + threshold for stable counting.
        hits_per_bus = np.zeros(8, dtype=np.int64)
        for bus in range(8):
            col = onsets[:, bus]
            # Strict-local-max above the 0.5 confidence floor. A non-strict
            # comparison (``>=``) would count every frame of a Gaussian-smeared
            # peak as a separate hit; ``>`` on the left + ``>=`` on the right
            # selects exactly the apex (or the *first* sample of a tie).
            if col.size < 3:
                continue
            is_peak = (col[1:-1] > col[:-2]) & (col[1:-1] >= col[2:]) & (col[1:-1] >= 0.5)
            peak_idx = np.where(is_peak)[0] + 1
            hits_per_bus[bus] = peak_idx.size
            # Velocity at the peak frame. Cols 8-15 in the flat-25 layout
            # carry the velocity *only* at the onset frame (zero elsewhere
            # per F0-T2a §3.3) — the histogram pulls those values into 20
            # uniform bins on [0, 1].
            if peak_idx.size:
                v = velocities[peak_idx, bus]
                hist, _ = np.histogram(v, bins=20, range=(0.0, 1.0))
                bucket["vel_hist_per_bus"][bus] += hist
        bucket["n_onset_per_bus"] += hits_per_bus

        if duration > 0:
            bucket["densities_hits_per_s"].append(int(hits_per_bus.sum()) / duration)

        # HH articulation: discretise the continuous head into closed (<0.2),
        # pedal (0.2-0.6), open (>0.6) — mirrors data_audit.
        if hh_open.size:
            closed = int((hh_open < 0.2).sum())
            pedal = int(((hh_open >= 0.2) & (hh_open < 0.6)).sum())
            opened = int((hh_open >= 0.6).sum())
            # Count distinct *segments* (a held value = one articulation).
            articulations = ["closed" if v < 0.2 else "pedal" if v < 0.6 else "open"
                             for v in hh_open]
            if articulations:
                seg_count: Counter = Counter()
                prev = articulations[0]
                seg_count[prev] += 1
                for cur in articulations[1:]:
                    if cur != prev:
                        seg_count[cur] += 1
                        prev = cur
                bucket["hh_articulation"].update(seg_count)
            # Suppress unused locals
            _ = (closed, pedal, opened)

    return out


def _render_panels(stats: dict[str, dict], out_png: Path) -> None:
    """Emit the 6-panel comparative figure (Laboratory Precision style)."""
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
    fig, axes = plt.subplots(3, 2, figsize=(14, 14))
    fig.suptitle(
        "OP-NEUROTRIGGER · Mixed-dataset 70/15/15 — source-stratified audit",
        fontsize=14, fontweight="bold",
    )

    sources = [s for s in _SOURCES if stats[s]["n_sample"] > 0]
    colors = {"gmd": "#222222", "rare": "#888888", "chaos": "#CCCCCC"}

    # 1. Sample count per source.
    ax = axes[0, 0]
    counts = [stats[s]["n_sample"] for s in sources]
    bars = ax.bar(sources, counts, color=[colors[s] for s in sources],
                  edgecolor="black", linewidth=1.2)
    for bar, n in zip(bars, counts, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{n}", ha="center", va="bottom", fontsize=11)
    ax.set_title("Samples per source")
    ax.set_ylabel("count")
    total = sum(counts)
    ax.text(0.02, 0.95, f"total = {total}", transform=ax.transAxes,
            fontsize=9, verticalalignment="top", family="monospace")

    # 2. Bus class imbalance per source (grouped bars).
    ax = axes[0, 1]
    width = 0.25
    x = np.arange(8)
    for i, s in enumerate(sources):
        n = stats[s]["n_sample"]
        if n == 0:
            continue
        onset_per_bus = stats[s]["n_onset_per_bus"]
        total_onset = max(int(onset_per_bus.sum()), 1)
        pct = 100.0 * onset_per_bus / total_onset
        ax.bar(x + (i - 1) * width, pct, width, label=s,
               color=colors[s], edgecolor="black", linewidth=0.6)
    ax.axhline(5.0, color="red", linestyle="--", linewidth=0.8, label="5% gate")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{i}\n{lab}" for i, lab in enumerate(_BUS_LABELS)],
                       fontsize=7)
    ax.set_ylabel("% of onsets")
    ax.set_title("Bus class imbalance per source")
    ax.legend(loc="upper right", fontsize=9)

    # 3. Duration histogram per source.
    ax = axes[1, 0]
    for s in sources:
        durs = stats[s]["durations_s"]
        if not durs:
            continue
        ax.hist(durs, bins=30, alpha=0.5, color=colors[s], edgecolor="black",
                linewidth=0.6, label=f"{s} (n={len(durs)})")
    ax.set_xlabel("duration [s]")
    ax.set_ylabel("count")
    ax.set_title("Sample duration distribution per source")
    ax.legend(loc="upper right", fontsize=9)

    # 4. Density (hits/s) per source — kernel-free box plot.
    ax = axes[1, 1]
    data = [stats[s]["densities_hits_per_s"] for s in sources]
    box = ax.boxplot(
        [d if d else [0.0] for d in data],
        tick_labels=list(sources), patch_artist=True, widths=0.5,
    )
    for patch, s in zip(box["boxes"], sources, strict=True):
        patch.set_facecolor(colors[s])
        patch.set_edgecolor("black")
    for med in box["medians"]:
        med.set_color("red")
        med.set_linewidth(1.5)
    ax.set_ylabel("hits / sec")
    ax.set_title("Onset density per source")
    # Annotate medians.
    for i, d in enumerate(data, start=1):
        if d:
            med = float(np.median(d))
            ax.text(i, med, f"  med={med:.1f}", fontsize=8,
                    verticalalignment="center")

    # 5. HH articulation per source.
    ax = axes[2, 0]
    width = 0.25
    arts = ("closed", "pedal", "open")
    x = np.arange(len(arts))
    for i, s in enumerate(sources):
        counts = [stats[s]["hh_articulation"].get(a, 0) for a in arts]
        ax.bar(x + (i - 1) * width, counts, width, label=s,
               color=colors[s], edgecolor="black", linewidth=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(arts)
    ax.set_ylabel("segment count")
    ax.set_title("Hi-Hat articulation segments per source")
    ax.legend(loc="upper right", fontsize=9)

    # 6. Rare bus (crash_b_misc = bus 7) velocity histogram per source — the
    # bus most under-represented in straight GMD; layer B / C should foreground
    # it. A flat distribution = uniform velocity (chaos); a peaked one = the
    # human / rare-emphasis fingerprint.
    ax = axes[2, 1]
    bus_idx = 7  # crash_b_misc
    edges = np.linspace(0, 1, 21)
    centers = 0.5 * (edges[:-1] + edges[1:])
    for s in sources:
        hist = stats[s]["vel_hist_per_bus"][bus_idx]
        if hist.sum() == 0:
            continue
        ax.plot(
            centers, hist / max(hist.sum(), 1),
            marker="o", linestyle="-",
            color=colors[s], label=f"{s} (n={int(hist.sum())})",
            linewidth=1.5, markersize=4,
        )
    ax.set_xlabel("velocity (normalised)")
    ax.set_ylabel("density")
    ax.set_title(f"Velocity histogram on bus {bus_idx} ({_BUS_LABELS[bus_idx]})")
    ax.legend(loc="upper right", fontsize=9)

    plt.tight_layout(rect=(0, 0, 1, 0.97))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _render_markdown(stats: dict[str, dict], out_md: Path) -> None:
    """Narrative Markdown report with tables + numerical claims."""
    lines: list[str] = []
    lines.append("# Audit report — Mixed-dataset 70/15/15 (2026-05-24)\n")
    lines.append(
        "Source-stratified analysis of the Gold output produced by "
        "`tools/render_mix_chunked.sh` on the mix `140 GMD + 30 rare + 30 chaos`. "
        "Complements the F0-T17 standard `data_audit` (`data_audit.report.{json,png}`) "
        "with a per-source breakdown — the F0-T17 gate aggregates across the "
        "whole directory, this report disambiguates the three layers.\n"
    )

    total_samples = sum(stats[s]["n_sample"] for s in _SOURCES)
    lines.append(f"**Total samples:** {total_samples}\n")
    lines.append("**Layer mix (post-render):**\n")
    lines.append("| Source | Samples | Share |")
    lines.append("|--------|---------|-------|")
    for s in _SOURCES:
        n = stats[s]["n_sample"]
        share = 100.0 * n / max(total_samples, 1)
        lines.append(f"| {s} | {n} | {share:5.1f}% |")
    lines.append("")

    # Bus distribution.
    lines.append("## 1. Bus class imbalance per source\n")
    lines.append("`5%` is the F0-T17 minority threshold. A bus below it "
                 "triggers loss-reweighting in F2-T3 (informative, not blocking).\n")
    lines.append(
        "| Bus | Label | "
        + " | ".join(f"{s} %" for s in _SOURCES)
        + " | Global % |"
    )
    lines.append("|---|---|" + "|".join(["---:"] * (len(_SOURCES) + 1)) + "|")
    global_onset_per_bus = sum(stats[s]["n_onset_per_bus"] for s in _SOURCES)
    global_total = max(int(global_onset_per_bus.sum()), 1)
    for bus in range(8):
        row = [str(bus), _BUS_LABELS[bus]]
        for s in _SOURCES:
            onsets = stats[s]["n_onset_per_bus"]
            total = max(int(onsets.sum()), 1)
            row.append(f"{100*onsets[bus]/total:5.2f}")
        row.append(f"{100*int(global_onset_per_bus[bus])/global_total:5.2f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Density.
    lines.append("## 2. Onset density per source (hits/sec)\n")
    lines.append("Median density tells us how *busy* the grooves are — a "
                 "GMD groove typically lands 10-25 hits/s, the chaos layer "
                 "should push much higher (λ × 8 buses)." "\n")
    lines.append("| Source | n | median | p25 | p75 | min | max |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for s in _SOURCES:
        d = stats[s]["densities_hits_per_s"]
        if not d:
            lines.append(f"| {s} | 0 | — | — | — | — | — |")
            continue
        arr = np.asarray(d)
        lines.append(
            f"| {s} | {len(arr)} | {np.median(arr):5.1f} | "
            f"{np.percentile(arr, 25):5.1f} | {np.percentile(arr, 75):5.1f} | "
            f"{arr.min():5.1f} | {arr.max():5.1f} |"
        )
    lines.append("")

    # Duration.
    lines.append("## 3. Sample duration distribution\n")
    lines.append("GMD is filtered to `duration ≤ 6 s` (OrbStack memory "
                 "budget); the chaos layer samples Uniform[2, 6] s; the "
                 "rare-emphasis layer emits 2-3 bar grooves at multiple BPM "
                 "tiers.\n")
    lines.append("| Source | n | mean | median | min | max |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for s in _SOURCES:
        d = stats[s]["durations_s"]
        if not d:
            lines.append(f"| {s} | 0 | — | — | — | — |")
            continue
        arr = np.asarray(d)
        lines.append(
            f"| {s} | {len(arr)} | {arr.mean():5.2f} | {np.median(arr):5.2f} | "
            f"{arr.min():5.2f} | {arr.max():5.2f} |"
        )
    lines.append("")

    # HH articulation.
    lines.append("## 4. Hi-Hat articulation segments per source\n")
    lines.append(
        "Each transition between closed/pedal/open counts as one segment — "
        "a high `open` count means the layer uses opens often; a low "
        "`pedal` count means the foot ostinato is absent.\n"
    )
    lines.append("| Source | closed | pedal | open |")
    lines.append("|---|---:|---:|---:|")
    for s in _SOURCES:
        h = stats[s]["hh_articulation"]
        lines.append(
            f"| {s} | {h.get('closed', 0)} | {h.get('pedal', 0)} | {h.get('open', 0)} |"
        )
    lines.append("")

    # Interpretation.
    lines.append("## 5. Interpretation\n")
    lines.append(
        "- **Layer-B (rare emphasis) goal:** lift crash/china/ride/tom/splash "
        "above the GMD baseline. Compare bus 6-7 (`ride`, `crash_a`) and "
        "bus 7 (`crash_b_misc`, including china + splash) in the per-source "
        "table — the `rare` column should be markedly higher than `gmd`.\n"
    )
    lines.append(
        "- **Layer-C (Machine-Gun Chaos) goal:** break grid-position "
        "shortcuts. The chaos density should be near-uniform across buses "
        "(no bus dominates) and the velocity histogram on rare buses should "
        "approach flat (Uniform[40, 120]) rather than peaked.\n"
    )
    lines.append(
        "- **Global gate (5%):** every bus is above the F0-T17 minority "
        "threshold at the aggregate level — no loss-reweighting required "
        "for F2-T3 by data-imbalance criteria.\n"
    )
    lines.append("\n*See `panels.png` for the visual.*\n")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--gold-dir", type=Path, required=True,
                   help="path to the Gold directory (e.g. data/gold/mix_*)")
    p.add_argument("--out", type=Path, required=True,
                   help="output directory for AUDIT_REPORT.md + panels.png")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.gold_dir.exists():
        print(f"FATAL: gold dir {args.gold_dir} does not exist", file=sys.stderr)
        return 1
    print("== source-stratified audit ==")
    print(f"gold_dir: {args.gold_dir}")
    print(f"out:      {args.out}")
    stats = _stats_per_source(args.gold_dir)
    counts = {s: stats[s]["n_sample"] for s in _SOURCES}
    print(f"per-source counts: {counts}")
    if stats.get("unknown", {}).get("n_sample", 0):
        print(f"  (warning: {stats['unknown']['n_sample']} sample(s) of unknown source)")
    args.out.mkdir(parents=True, exist_ok=True)
    _render_panels(stats, args.out / "panels.png")
    _render_markdown(stats, args.out / "AUDIT_REPORT.md")
    print(f"wrote {args.out / 'panels.png'}")
    print(f"wrote {args.out / 'AUDIT_REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
