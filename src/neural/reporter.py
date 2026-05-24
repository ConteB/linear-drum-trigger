"""Model training report engine — single-file HTML with inline SVG charts.

Implements `LIN-DT-RPTBP-001` (``04_INTELLIGENCE/MODEL_REPORT_BLUEPRINT.md``).
Generates a self-contained HTML report from a :class:`ReportContext` dict and
the Jinja2 templates under ``templates/``.

Determinism is mandated by ``ENGINEERING_STANDARDS §1`` — same input → same
output, byte-by-byte:

* matplotlib uses backend ``Agg`` and a fixed ``svg.hashsalt``.
* float formatting is fixed-precision.
* dict iteration goes through pre-sorted lists.

The same engine will serve dataset cards (``LIN-DT-DCBP-001``) when F0-T5
materialises a dataset to describe.
"""
from __future__ import annotations

import io
import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "op-neurotrigger"
matplotlib.rcParams["svg.fonttype"] = "none"
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = ["Helvetica", "Arial", "DejaVu Sans"]
matplotlib.rcParams["figure.dpi"] = 100
matplotlib.rcParams["axes.spines.top"] = False
matplotlib.rcParams["axes.spines.right"] = False

import matplotlib.pyplot as plt  # noqa: E402 — needs the rcParams above
import numpy as np  # noqa: E402
from jinja2 import Environment, FileSystemLoader, StrictUndefined  # noqa: E402

#: Blueprint spec version (synchronise with the doc's frontmatter).
BLUEPRINT_VERSION = "1.0.0"

#: Canonical bus names (mapping table). Index = bus slot 0..7.
BUS_NAMES: tuple[str, ...] = (
    "kick", "snare", "hihat", "tom_hi_mid",
    "floor_tom", "ride", "crash_a", "crash_b_misc",
)

#: Templates directory (relative to repo root).
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


# ----------------------------------------------------------------------------
# Chart factory — matplotlib → SVG string.
# ----------------------------------------------------------------------------


#: matplotlib SVG output embeds metadata (`<dc:date>...</dc:date>`) and
#: timestamps in `<metadata>` blocks that break byte-by-byte determinism
#: (ENGINEERING_STANDARDS §1). We strip them.
_SVG_DATE = re.compile(r"<dc:date>[^<]*</dc:date>")
_SVG_META = re.compile(r"<metadata>.*?</metadata>", re.DOTALL)


def _fig_to_svg(fig: matplotlib.figure.Figure) -> str:
    """Render a figure to an inline-able SVG string and close it.

    The output is normalised to be deterministic: the XML declaration is
    stripped (so the SVG can live in an HTML body) and matplotlib's timestamp
    metadata is removed.
    """
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", transparent=False)
    plt.close(fig)
    svg = buf.getvalue()
    # Strip the XML declaration so the SVG can live inside an HTML body.
    decl_end = svg.find("?>")
    if decl_end != -1:
        svg = svg[decl_end + 2 :].lstrip()
    # Strip non-deterministic metadata.
    svg = _SVG_META.sub("", svg)
    svg = _SVG_DATE.sub("", svg)
    return svg


class ChartFactory:
    """Container of chart-builders. Each method returns a self-contained SVG."""

    DEFAULT_SIZE = (8.0, 4.0)  # inches

    @staticmethod
    def loss_curve(history: list[dict[str, float]]) -> str:
        """Train loss vs epoch (one line; future runs may add per-head curves)."""
        if not history:
            fig, ax = plt.subplots(figsize=ChartFactory.DEFAULT_SIZE)
            ax.text(0.5, 0.5, "no training history available",
                    ha="center", va="center", transform=ax.transAxes,
                    color="#999", fontsize=12)
            ax.set_axis_off()
            return _fig_to_svg(fig)
        epochs = [h["epoch"] for h in history]
        losses = [h["train_loss"] for h in history]
        fig, ax = plt.subplots(figsize=ChartFactory.DEFAULT_SIZE)
        ax.plot(epochs, losses, color="#1f6feb", linewidth=1.5, label="train loss (total)")
        ax.set_xlabel("epoch")
        ax.set_ylabel("loss")
        ax.set_title("Loss vs epoch", loc="left", fontsize=12, fontweight="bold")
        ax.legend(loc="upper right", frameon=False)
        ax.grid(True, alpha=0.25)
        return _fig_to_svg(fig)

    @staticmethod
    def per_bus_f_bars(
        f_per_bus: list[float | None],
        n_true_per_bus: list[int],
        *,
        title: str,
        gate_threshold: float,
    ) -> str:
        """Bar chart of F-measure per bus. Bars with ``n_true == 0`` are dimmed."""
        fig, ax = plt.subplots(figsize=ChartFactory.DEFAULT_SIZE)
        xs = list(range(len(BUS_NAMES)))
        # Replace None / nan with 0 for plotting but mark them visually.
        heights = []
        colors = []
        for f, n_true in zip(f_per_bus, n_true_per_bus, strict=True):
            if f is None or (isinstance(f, float) and math.isnan(f)):
                heights.append(0.0)
                colors.append("#cccccc")  # n/a
            elif n_true == 0:
                heights.append(0.0)
                colors.append("#cccccc")
            else:
                heights.append(float(f))
                if f >= gate_threshold:
                    colors.append("#1a7f3a")
                elif f >= 0.4:
                    colors.append("#1f6feb")
                else:
                    colors.append("#b76d00")
        ax.bar(xs, heights, color=colors, edgecolor="#333", linewidth=0.5)
        # Annotate "n/a" above bars without ground truth.
        for i, (h, n_true) in enumerate(zip(heights, n_true_per_bus, strict=True)):
            if n_true == 0:
                ax.text(i, 0.02, "n/a", ha="center", va="bottom",
                        fontsize=10, color="#666", fontfamily="monospace")
            else:
                ax.text(i, h + 0.02, f"{h:.2f}",
                        ha="center", va="bottom", fontsize=9, fontfamily="monospace")
        ax.axhline(gate_threshold, color="#b00020", linestyle="--", linewidth=1.0,
                   label=f"gate threshold = {gate_threshold:.2f}")
        ax.set_xticks(xs)
        ax.set_xticklabels(BUS_NAMES, rotation=30, ha="right", fontsize=10)
        ax.set_ylim(0, 1.10)
        ax.set_ylabel("F-measure (±20 ms)")
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
        ax.legend(loc="upper right", frameon=False, fontsize=10)
        ax.grid(True, axis="y", alpha=0.25)
        return _fig_to_svg(fig)

    @staticmethod
    def confusion_grid(
        per_bus_confusion: list[dict[str, int]],
        bus_names: tuple[str, ...] = BUS_NAMES,
    ) -> str:
        """Grid of 8 mini confusion matrices (one per bus)."""
        fig, axes = plt.subplots(2, 4, figsize=(10, 5))
        for b, ax in enumerate(axes.flatten()):
            cm = per_bus_confusion[b]
            mat = np.array([[cm["TP"], cm["FP"]],
                            [cm["FN"], cm["TN"]]], dtype=float)
            # Normalise within each cell for color scaling; keep raw count for label.
            im = ax.imshow(np.log1p(mat), cmap="viridis", aspect="equal")
            for i in range(2):
                for j in range(2):
                    value = int(mat[i, j])
                    # Use white text on dark cells, black on light.
                    cell_color = im.cmap(im.norm(np.log1p(value)))[:3]
                    luminance = cell_color[0] + cell_color[1] + cell_color[2]
                    fg = "white" if luminance < 1.5 else "black"
                    ax.text(j, i, f"{value}", ha="center", va="center",
                            color=fg, fontfamily="monospace", fontsize=10)
            ax.set_xticks([0, 1])
            ax.set_yticks([0, 1])
            ax.set_xticklabels(["pred=1", "pred=0"], fontsize=8)
            ax.set_yticklabels(["vero=1", "vero=0"], fontsize=8)
            ax.set_title(bus_names[b], fontsize=10, fontweight="bold")
        fig.suptitle("Confusion matrix per-bus (log-scaled colormap)",
                     fontsize=12, fontweight="bold", x=0.02, y=0.99, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        return _fig_to_svg(fig)

    @staticmethod
    def timing_mae_hist(drifts_ms: list[float], frame_period_ms: float) -> str:
        """Histogram of matched-onset drift in ms."""
        fig, ax = plt.subplots(figsize=ChartFactory.DEFAULT_SIZE)
        if not drifts_ms:
            ax.text(0.5, 0.5, "no matched onsets",
                    ha="center", va="center", transform=ax.transAxes,
                    color="#999", fontsize=12)
            ax.set_axis_off()
            return _fig_to_svg(fig)
        drifts = np.array(drifts_ms)
        # Bin width ≈ one frame; cover ±25 ms.
        bins = list(np.arange(-25.0, 25.0 + frame_period_ms, frame_period_ms))
        ax.hist(drifts, bins=bins, color="#1f6feb", edgecolor="#333", linewidth=0.5)
        ax.axvspan(-20, 20, color="#1a7f3a", alpha=0.10, label="match window ±20 ms")
        ax.axvline(0.0, color="#b00020", linestyle="--", linewidth=1.0, label="zero drift (ideal)")
        ax.set_xlabel("drift (ms) — pred − vero")
        ax.set_ylabel("# onset matchati")
        ax.set_title(
            f"Distribuzione dei drift onset (MAE = {np.mean(np.abs(drifts)):.2f} ms, "
            f"N = {len(drifts)})",
            loc="left", fontsize=12, fontweight="bold",
        )
        ax.legend(loc="upper right", frameon=False)
        ax.grid(True, alpha=0.25)
        return _fig_to_svg(fig)

    @staticmethod
    def shuffle_control(
        per_sample: list[dict[str, Any]],
        gate_shuffle_max: float,
    ) -> str:
        """Grouped bar: F-real vs F-shuffled, per sample of the holdout."""
        if not per_sample:
            fig, ax = plt.subplots(figsize=ChartFactory.DEFAULT_SIZE)
            ax.text(0.5, 0.5, "no holdout samples",
                    ha="center", va="center", transform=ax.transAxes,
                    color="#999", fontsize=12)
            ax.set_axis_off()
            return _fig_to_svg(fig)
        labels = [s["key"] for s in per_sample]
        f_real = [s["f_real"] for s in per_sample]
        f_shuf = [s["f_shuffle"] for s in per_sample]
        x = np.arange(len(labels))
        width = 0.38
        fig, ax = plt.subplots(figsize=ChartFactory.DEFAULT_SIZE)
        ax.bar(x - width/2, f_real, width, label="F-measure reale",
               color="#1f6feb", edgecolor="#333", linewidth=0.5)
        ax.bar(x + width/2, f_shuf, width, label="F-measure shuffato",
               color="#b76d00", edgecolor="#333", linewidth=0.5)
        ax.axhline(gate_shuffle_max, color="#b00020", linestyle="--",
                   linewidth=1.0,
                   label=f"gate F-shuffle &lt; {gate_shuffle_max:.2f}")
        ax.set_xticks(x)
        # Shorten labels — keep only the first segment + engine.
        short = [_short_key(lbl) for lbl in labels]
        ax.set_xticklabels(short, rotation=15, ha="right", fontsize=10)
        ax.set_ylim(0, 1.0)
        ax.set_ylabel("F-measure")
        ax.set_title("Controllo negativo — reale vs shuffato",
                     loc="left", fontsize=12, fontweight="bold")
        ax.legend(loc="upper right", frameon=False, fontsize=9)
        ax.grid(True, axis="y", alpha=0.25)
        return _fig_to_svg(fig)

    @staticmethod
    def piano_roll(
        *,
        key: str,
        target_onsets: list[list[int]],     # per-bus list of frame indices (ground truth)
        pred_onsets: list[list[int]],       # per-bus list of frame indices (predicted)
        n_frames: int,
        frame_rate_hz: float,
        bus_names: tuple[str, ...] = BUS_NAMES,
    ) -> str:
        """Piano-roll overlay: ground-truth dots + predicted crosses, per bus."""
        seconds = n_frames / frame_rate_hz
        fig, ax = plt.subplots(figsize=(10.0, 4.0))
        for b in range(len(bus_names)):
            t_true = np.array(target_onsets[b]) / frame_rate_hz
            t_pred = np.array(pred_onsets[b]) / frame_rate_hz
            ax.scatter(t_true, np.full_like(t_true, b, dtype=float),
                       marker="o", s=60, c="#1a7f3a", alpha=0.7, label="vero" if b == 0 else None)
            ax.scatter(t_pred, np.full_like(t_pred, b, dtype=float),
                       marker="x", s=50, c="#b00020", alpha=0.9, label="pred" if b == 0 else None)
        ax.set_yticks(list(range(len(bus_names))))
        ax.set_yticklabels(list(bus_names), fontsize=9)
        ax.set_xlim(0, seconds)
        ax.set_xlabel("tempo (s)")
        ax.set_title(f"Piano-roll: {key}",
                     loc="left", fontsize=12, fontweight="bold")
        ax.legend(loc="upper right", frameon=False)
        ax.grid(True, axis="x", alpha=0.25)
        ax.invert_yaxis()
        return _fig_to_svg(fig)


def _short_key(key: str) -> str:
    """Shorten a barcode key for chart labels — first segment only."""
    return key.split("-")[0] + " / " + key.split("-")[2]  # e.g. "GMD000 / DGZ"


# ----------------------------------------------------------------------------
# ReportContext — what the template renders.
# ----------------------------------------------------------------------------


@dataclass
class TldrRow:
    label: str
    value: str
    gate: str
    verdict: str
    verdict_class: str  # 'pass' | 'warn' | 'fail' | ''
    is_summary: bool = False


@dataclass
class HiHatRow:
    key: str
    mae: float
    verdict: str
    verdict_class: str


@dataclass
class GateVerdictRow:
    criterion: str
    verdict: str
    verdict_class: str


@dataclass
class ReportContext:
    title: str
    run_id: str
    run_date: str  # ISO 8601
    git_commit: str
    status: str  # 'AUTO-GENERATED' | 'APPROVED' | 'PENDING_CEO_DECISION'
    tier: int = 1  # 1 = auto, 2 = ocular proof
    tldr: list[TldrRow] = field(default_factory=list)
    tldr_note: str | None = None
    context_table: list[tuple[str, str]] = field(default_factory=list)
    charts: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, str] = field(default_factory=dict)
    hihat_mae_table: list[HiHatRow] = field(default_factory=list)
    hyperparameters: list[tuple[str, str]] = field(default_factory=list)
    gate_verdict: list[GateVerdictRow] = field(default_factory=list)
    signoff_date: str | None = None
    signoff_signature: str | None = None

    # Gate thresholds visualised in the report. Defaults are L3 (F0-T4a §7).
    gate_f_threshold: float = 0.80
    gate_shuffle_max: float = 0.10
    gate_timing_mae_max: float = 5.0
    gate_hihat_max: float = 0.15
    frame_period_ms: float = 2.902

    # Computed once at write time.
    blueprint_version: str = BLUEPRINT_VERSION

    @property
    def status_class(self) -> str:
        return {
            "AUTO-GENERATED": "auto",
            "APPROVED": "approved",
            "PENDING_CEO_DECISION": "pending",
        }.get(self.status, "auto")


# ----------------------------------------------------------------------------
# Verdict helpers — convert raw numbers into ✅/⚠️/❌ + CSS class.
# ----------------------------------------------------------------------------


def verdict(passes: bool | None, *, soft: bool = False) -> tuple[str, str]:
    """Return ``(label, css_class)`` for the report's verdict cells."""
    if passes is None:
        return "n/a", ""
    if passes:
        return "✅ PASS", "pass"
    return ("⚠️ WARN", "warn") if soft else ("❌ FAIL", "fail")


# ----------------------------------------------------------------------------
# Table builders — produce inline HTML strings.
# ----------------------------------------------------------------------------


def _format_float(x: float | None, fmt: str = "{:.3f}") -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return fmt.format(x)


def build_per_bus_table(
    samples: list[dict[str, Any]],
    *,
    gate_f_threshold: float,
) -> str:
    """Render a per-bus F-measure table — one row per (sample, bus) pair."""
    rows: list[str] = ["<table>"]
    rows.append(
        "<thead><tr>"
        "<th>Sample</th><th>Bus</th>"
        '<th class="num">n_true</th>'
        '<th class="num">n_pred</th>'
        '<th class="num">n_match</th>'
        '<th class="num">P</th>'
        '<th class="num">R</th>'
        '<th class="num">F</th>'
        '<th class="num">thr</th>'
        "</tr></thead><tbody>"
    )
    for s in samples:
        short_key = _short_key(s["key"])
        for b, bus in enumerate(BUS_NAMES):
            n_true = s["n_true_per_bus"][b]
            n_pred = s["n_pred_per_bus"][b]
            n_match = s["n_matched_per_bus"][b]
            p = s["p_per_bus"][b]
            r = s["r_per_bus"][b]
            f = s["f_per_bus"][b]
            f_str = _format_float(f)
            css = ""
            if f is not None and not math.isnan(f) and n_true > 0:
                if f >= gate_f_threshold:
                    css = "pass"
                elif f >= 0.4:
                    css = ""
                else:
                    css = "warn"
            rows.append(
                f"<tr><td>{short_key}</td><td>{bus}</td>"
                f'<td class="num">{n_true}</td>'
                f'<td class="num">{n_pred}</td>'
                f'<td class="num">{n_match}</td>'
                f'<td class="num">{_format_float(p, "{:.2f}")}</td>'
                f'<td class="num">{_format_float(r, "{:.2f}")}</td>'
                f'<td class="num"><span class="{css}">{f_str}</span></td>'
                f'<td class="num">{s["threshold"]:.2f}</td>'
                "</tr>"
            )
    rows.append("</tbody></table>")
    return "\n".join(rows)


# ----------------------------------------------------------------------------
# Public API — write_training_report
# ----------------------------------------------------------------------------


def get_git_commit() -> str:
    """Return short SHA of HEAD, or 'unknown' if not a git repo."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except FileNotFoundError:
        pass
    return "unknown"


def write_training_report(
    ctx: ReportContext, out_dir: Path | str
) -> Path:
    """Render ``ctx`` to ``out_dir/report.html`` and return the path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        undefined=StrictUndefined,
        autoescape=False,  # we emit raw SVG/HTML chunks deliberately
    )
    template = env.get_template("training_report.html.j2")
    # tldr / hihat_mae_table / hyperparameters / gate_verdict are dataclasses —
    # convert to dicts for the template (Jinja accesses by attr already, but
    # this guarantees deterministic ordering).
    html = template.render(ctx=ctx)
    out = out_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    return out


# ----------------------------------------------------------------------------
# Default Tier-1 builder — used by train.py to emit a report after every run.
# ----------------------------------------------------------------------------


def evaluate_sample_for_report(
    model: Any,
    audio_np: Any,
    target_np: Any,
    *,
    n_sample: int,
    lookahead_frames: int = 0,
) -> dict[str, Any]:
    """Run the model on one sample, return all the metrics the report needs.

    This is the canonical evaluation pass for the report builder; the driver
    ``tools/render_training_report.py`` and the auto-report call from
    ``train.py`` both use it (single source of truth for the numbers).

    **F0-T4c bugfix 2026-05-24** (Decision Lock CEO): the function now applies
    the same lookahead shift as :func:`neural.train.evaluate_holdout`. Without
    it, ``pred[t]`` was being compared with ``target[t]`` even though the
    model — trained with ``lookahead_frames=L`` — emits a prediction for
    frame ``t`` from audio up to frame ``t+L``. The mismatch produced an
    apparent ``L * frame_period_ms`` drift in every piano-roll and zeroed
    per-bus F-scores on samples where the GT was actually well-tracked.
    """
    import torch  # noqa: PLC0415 — torch is heavy; imported lazily.

    from neural.metrics import (  # noqa: PLC0415
        match_onsets,
        peak_pick,
        shuffled_control,
        tune_threshold,
    )
    from neural.model import HIHAT_OPENING_COL  # noqa: PLC0415

    # Lookahead shift: the model at frame t needs audio up to t+L (in frames).
    L = max(0, int(lookahead_frames))  # noqa: N806
    # Trim n_sample down so the available audio is enough.
    if audio_np.shape[1] < n_sample:
        n_sample = (audio_np.shape[1] // 128) * 128
    n_frame_requested = n_sample // 128
    total_af_frames = audio_np.shape[1] // 128
    # Cap n_frame so the audio window [L .. L+n_frame) fits in the buffer.
    n_frame = max(0, min(n_frame_requested, target_np.shape[0], total_af_frames - L))
    start_sample = L * 128
    end_sample = start_sample + n_frame * 128
    with torch.no_grad():
        pred = (
            model(torch.from_numpy(audio_np[:, start_sample:end_sample]).unsqueeze(0).float())
            .squeeze(0).numpy().astype(np.float32, copy=False)
        )
    target_cut = target_np[:n_frame].astype(np.float32, copy=False)
    onset_pred = pred[:, 0:24:3]
    onset_target = target_cut[:, 0:24:3]
    hihat_pred = pred[:, HIHAT_OPENING_COL]
    hihat_target = target_cut[:, HIHAT_OPENING_COL]

    thr, _ = tune_threshold(onset_pred, onset_target)

    n_true_per_bus: list[int] = []
    n_pred_per_bus: list[int] = []
    n_matched_per_bus: list[int] = []
    p_per_bus: list[float | None] = []
    r_per_bus: list[float | None] = []
    f_per_bus: list[float | None] = []
    confusion: list[dict[str, int]] = []
    drifts_all: list[float] = []
    target_peak_frames: list[list[int]] = []
    pred_peak_frames: list[list[int]] = []

    for b in range(8):
        pred_pks = peak_pick(onset_pred[:, b], threshold=thr, min_distance_frames=3)
        true_pks = peak_pick(onset_target[:, b], threshold=thr, min_distance_frames=3)
        n_matched, drifts = match_onsets(pred_pks, true_pks)
        n_pred, n_true = len(pred_pks), len(true_pks)
        if n_pred == 0 and n_true == 0:
            p = r = f = None
        elif n_pred == 0 or n_true == 0:
            p = r = f = 0.0
        else:
            p = n_matched / n_pred
            r = n_matched / n_true
            f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        n_true_per_bus.append(n_true)
        n_pred_per_bus.append(n_pred)
        n_matched_per_bus.append(n_matched)
        p_per_bus.append(p)
        r_per_bus.append(r)
        f_per_bus.append(f)
        confusion.append({
            "TP": n_matched,
            "FP": n_pred - n_matched,
            "FN": n_true - n_matched,
            "TN": max(n_frame - n_pred - (n_true - n_matched), 0),
        })
        drifts_all.extend(drifts)
        target_peak_frames.append(true_pks)
        pred_peak_frames.append(pred_pks)

    f_clean = [x for x in f_per_bus if x is not None and not math.isnan(x)]
    f_mean = float(np.mean(f_clean)) if f_clean else float("nan")
    f_shuffled = shuffled_control(onset_pred, onset_target)
    timing_mae = float(np.mean(np.abs(drifts_all))) if drifts_all else float("nan")
    hihat_mae = float(np.mean(np.abs(hihat_pred - hihat_target)))

    return {
        "threshold": thr,
        "n_true_per_bus": n_true_per_bus,
        "n_pred_per_bus": n_pred_per_bus,
        "n_matched_per_bus": n_matched_per_bus,
        "p_per_bus": p_per_bus,
        "r_per_bus": r_per_bus,
        "f_per_bus": f_per_bus,
        "confusion": confusion,
        "drifts_ms": drifts_all,
        "f_mean": f_mean,
        "f_shuffled": f_shuffled,
        "timing_mae_ms": timing_mae,
        "hihat_mae": hihat_mae,
        "n_frames": n_frame,
        "target_peak_frames": target_peak_frames,
        "pred_peak_frames": pred_peak_frames,
    }


def _short_sample_key(key: str) -> str:
    parts = key.split("-")
    return f"{parts[0]} / {parts[2]}" if len(parts) >= 3 else key


def build_default_context(
    *,
    run_id: str,
    run_date: str,
    title: str,
    history: list[dict[str, float]],
    n_parameters: int,
    hyperparameters: dict[str, Any],
    train_evals: list[dict[str, Any]],
    holdout_evals: list[dict[str, Any]],
    gate_f_threshold: float = 0.80,
    gate_shuffle_max: float = 0.10,
    gate_timing_mae_max: float = 5.0,
    gate_hihat_max: float = 0.15,
    frame_period_ms: float = 2.902,
    frame_rate_hz: float = 344.53125,
    tier: int = 1,
    extra_tldr_rows: list[TldrRow] | None = None,
    extra_gate_verdict_rows: list[GateVerdictRow] | None = None,
    signoff_date: str | None = None,
    signoff_signature: str | None = None,
    tldr_note: str | None = None,
) -> ReportContext:
    """Build a fully-populated :class:`ReportContext` from training evidence.

    The function is intentionally signature-rich: it accepts every numeric
    value the report needs as a plain argument, so it can be called from
    ``train.py`` (Tier-1, no extras) or from a gate driver (Tier-2, with
    round-trip rows + sign-off block).
    """
    # ---- TL;DR rows from holdout metrics ----
    f_means = [e["f_mean"] for e in holdout_evals]
    f_shuffles = [e["f_shuffled"] for e in holdout_evals]
    timing_maes = [
        e["timing_mae_ms"] for e in holdout_evals
        if not math.isnan(e["timing_mae_ms"])
    ]
    hihat_maes = [e["hihat_mae"] for e in holdout_evals]
    f_min = min(f_means) if f_means else float("nan")
    f_shuf_max = max(f_shuffles) if f_shuffles else float("nan")
    timing_mae_max = max(timing_maes) if timing_maes else float("nan")
    hihat_mae_max = max(hihat_maes) if hihat_maes else float("nan")

    def vrow(label: str, val: str, gate: str, passes: bool | None,
             *, is_summary: bool = False) -> TldrRow:
        v, c = verdict(passes)
        return TldrRow(label=label, value=val, gate=gate,
                       verdict=v, verdict_class=c, is_summary=is_summary)

    tldr: list[TldrRow] = [
        vrow(
            "F-measure onset (holdout, min per-sample)",
            _format_float(f_min),
            f"≥ {gate_f_threshold:.2f}",
            (None if math.isnan(f_min) else f_min >= gate_f_threshold),
        ),
        vrow(
            "F-measure shuffato (max per-sample)",
            _format_float(f_shuf_max),
            f"&lt; {gate_shuffle_max:.2f}",
            (None if math.isnan(f_shuf_max) else f_shuf_max < gate_shuffle_max),
        ),
        vrow(
            "Timing-MAE matched (max per-sample, ms)",
            ("n/a" if math.isnan(timing_mae_max) else f"{timing_mae_max:.2f}"),
            f"&lt; {gate_timing_mae_max:.1f}",
            (None if math.isnan(timing_mae_max) else timing_mae_max < gate_timing_mae_max),
        ),
        vrow(
            "HiHat-opening MAE (max per-sample)",
            _format_float(hihat_mae_max),
            f"&lt; {gate_hihat_max:.2f}",
            (None if math.isnan(hihat_mae_max) else hihat_mae_max < gate_hihat_max),
        ),
    ]
    if extra_tldr_rows:
        tldr.extend(extra_tldr_rows)

    # ---- Charts ----
    cf = ChartFactory()
    charts: dict[str, Any] = {}
    charts["loss_curve"] = cf.loss_curve(history)

    # Aggregate per-bus mean F on train.
    per_bus_train_mean: list[float | None] = []
    per_bus_train_ntrue: list[int] = []
    for b in range(8):
        f_values = [e["f_per_bus"][b] for e in train_evals]
        n_true_total = sum(e["n_true_per_bus"][b] for e in train_evals)
        clean = [x for x in f_values if x is not None and not math.isnan(x)]
        per_bus_train_mean.append(float(np.mean(clean)) if clean else None)
        per_bus_train_ntrue.append(n_true_total)
    charts["per_bus_train"] = cf.per_bus_f_bars(
        per_bus_train_mean, per_bus_train_ntrue,
        title=f"F-measure per-bus — TRAIN (media su {len(train_evals)} sample)",
        gate_threshold=gate_f_threshold,
    )

    # Worst-case holdout (the most pessimistic view).
    worst = min(holdout_evals, key=lambda e: e["f_mean"]) if holdout_evals else None
    if worst is not None:
        charts["per_bus_holdout"] = cf.per_bus_f_bars(
            worst["f_per_bus"], worst["n_true_per_bus"],
            title=f"F-measure per-bus — HOLDOUT (peggior caso: {_short_sample_key(worst['key'])})",
            gate_threshold=gate_f_threshold,
        )
    else:
        charts["per_bus_holdout"] = cf.per_bus_f_bars(
            [None] * 8, [0] * 8,
            title="F-measure per-bus — HOLDOUT (n/a)",
            gate_threshold=gate_f_threshold,
        )

    # Timing-MAE histogram.
    all_drifts = [d for e in holdout_evals for d in e["drifts_ms"]]
    charts["timing_mae_hist"] = cf.timing_mae_hist(all_drifts, frame_period_ms)

    # Confusion grid aggregated over holdout.
    if holdout_evals:
        agg = []
        for b in range(8):
            cell = {"TP": 0, "FP": 0, "FN": 0, "TN": 0}
            for e in holdout_evals:
                for k in cell:
                    cell[k] += e["confusion"][b][k]
            agg.append(cell)
        charts["confusion_grid"] = cf.confusion_grid(agg)
    else:
        charts["confusion_grid"] = ""

    # Shuffle control.
    shuffle_data = [
        {"key": e["key"], "f_real": e["f_mean"], "f_shuffle": e["f_shuffled"]}
        for e in holdout_evals
    ]
    charts["shuffle_control"] = cf.shuffle_control(shuffle_data, gate_shuffle_max)

    # Piano-roll samples.
    piano_rolls: list[tuple[str, str]] = []
    for e in holdout_evals:
        svg = cf.piano_roll(
            key=e["key"],
            target_onsets=e["target_peak_frames"],
            pred_onsets=e["pred_peak_frames"],
            n_frames=e["n_frames"],
            frame_rate_hz=frame_rate_hz,
        )
        cap = (
            f"Piano-roll {e['key']}. Verde = ground-truth, rosso = predetto. "
            f"F-mean = {_format_float(e['f_mean'])}, "
            f"Timing-MAE = {_format_float(e['timing_mae_ms'], '{:.2f}')} ms."
        )
        piano_rolls.append((svg, cap))
    charts["piano_roll_samples"] = piano_rolls

    # ---- Tables ----
    train_for_tbl = [{
        "key": e["key"], "threshold": e["threshold"],
        "n_true_per_bus": e["n_true_per_bus"], "n_pred_per_bus": e["n_pred_per_bus"],
        "n_matched_per_bus": e["n_matched_per_bus"],
        "p_per_bus": e["p_per_bus"], "r_per_bus": e["r_per_bus"],
        "f_per_bus": e["f_per_bus"],
    } for e in train_evals]
    holdout_for_tbl = [{
        "key": e["key"], "threshold": e["threshold"],
        "n_true_per_bus": e["n_true_per_bus"], "n_pred_per_bus": e["n_pred_per_bus"],
        "n_matched_per_bus": e["n_matched_per_bus"],
        "p_per_bus": e["p_per_bus"], "r_per_bus": e["r_per_bus"],
        "f_per_bus": e["f_per_bus"],
    } for e in holdout_evals]
    tables = {
        "train_per_bus": build_per_bus_table(train_for_tbl, gate_f_threshold=gate_f_threshold),
        "holdout_per_bus": build_per_bus_table(holdout_for_tbl, gate_f_threshold=gate_f_threshold),
    }

    # ---- HiHat MAE rows ----
    hihat_rows: list[HiHatRow] = []
    for e in holdout_evals:
        passes = e["hihat_mae"] < gate_hihat_max
        v, c = verdict(passes)
        hihat_rows.append(HiHatRow(key=e["key"], mae=e["hihat_mae"], verdict=v, verdict_class=c))

    # ---- Hyperparameters table — sorted for determinism ----
    hp_list = sorted({k: str(v) for k, v in hyperparameters.items()}.items())

    # ---- Status ----
    status = "APPROVED" if tier == 2 and signoff_signature else (
        "PENDING_CEO_DECISION" if tier == 2 else "AUTO-GENERATED"
    )

    return ReportContext(
        title=title,
        run_id=run_id,
        run_date=run_date,
        git_commit=get_git_commit(),
        status=status,
        tier=tier,
        tldr=tldr,
        tldr_note=tldr_note,
        context_table=[
            ("Dataset", f"{len(train_evals)} train + {len(holdout_evals)} holdout sample"),
            (
                "Modello",
                "F0-T4a TCN — Input-Agnostic Projection → Strided Encoder → "
                "Dilated Causal Trunk → 4 teste",
            ),
            ("n parametri", f"{n_parameters:,}"),
        ],
        charts=charts,
        tables=tables,
        hihat_mae_table=hihat_rows,
        hyperparameters=hp_list,
        gate_verdict=(extra_gate_verdict_rows or []),
        signoff_date=signoff_date,
        signoff_signature=signoff_signature,
        gate_f_threshold=gate_f_threshold,
        gate_shuffle_max=gate_shuffle_max,
        gate_timing_mae_max=gate_timing_mae_max,
        gate_hihat_max=gate_hihat_max,
        frame_period_ms=frame_period_ms,
    )


__all__ = [
    "BLUEPRINT_VERSION",
    "BUS_NAMES",
    "ChartFactory",
    "GateVerdictRow",
    "HiHatRow",
    "ReportContext",
    "TldrRow",
    "build_default_context",
    "build_per_bus_table",
    "evaluate_sample_for_report",
    "get_git_commit",
    "verdict",
    "write_training_report",
]
