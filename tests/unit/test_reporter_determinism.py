"""Reporter determinism — ENGINEERING_STANDARDS §1.

The HTML report and every SVG chart must be byte-identical across two
successive runs on the same input (no embedded timestamps, no random IDs).
"""
from __future__ import annotations

import pytest

pytest.importorskip("matplotlib", reason="reporter requires matplotlib")
pytest.importorskip("jinja2", reason="reporter requires jinja2")

from neural.reporter import (  # noqa: E402
    ChartFactory,
    ReportContext,
    TldrRow,
    build_per_bus_table,
    write_training_report,
)

pytestmark = pytest.mark.core


def test_loss_curve_is_deterministic() -> None:
    history = [{"epoch": float(i), "train_loss": 1.0 / (i + 1)} for i in range(1, 21)]
    a = ChartFactory.loss_curve(history)
    b = ChartFactory.loss_curve(history)
    assert a == b, "loss_curve SVG should be byte-identical across runs"


def test_per_bus_bars_is_deterministic() -> None:
    f_per_bus = [0.9, 0.8, 0.7, None, 0.5, 0.4, 0.3, 0.2]
    n_true = [10, 10, 10, 0, 10, 10, 10, 10]
    a = ChartFactory.per_bus_f_bars(
        f_per_bus, n_true, title="t", gate_threshold=0.80
    )
    b = ChartFactory.per_bus_f_bars(
        f_per_bus, n_true, title="t", gate_threshold=0.80
    )
    assert a == b


def test_confusion_grid_is_deterministic() -> None:
    cm = [{"TP": 10, "FP": 3, "FN": 2, "TN": 985} for _ in range(8)]
    a = ChartFactory.confusion_grid(cm)
    b = ChartFactory.confusion_grid(cm)
    assert a == b


def test_timing_hist_is_deterministic() -> None:
    drifts = [(-1.0) ** i * (i % 5) * 0.7 for i in range(50)]
    a = ChartFactory.timing_mae_hist(drifts, 2.902)
    b = ChartFactory.timing_mae_hist(drifts, 2.902)
    assert a == b


def test_full_report_is_deterministic(tmp_path) -> None:
    ctx = ReportContext(
        title="smoke",
        run_id="r1",
        run_date="2026-05-23",
        git_commit="abc1234",
        status="AUTO-GENERATED",
        tier=1,
        tldr=[
            TldrRow("metric A", "0.500", "≥ 0.80", "❌ FAIL", "fail"),
        ],
        context_table=[("k", "v")],
        charts={
            "loss_curve": ChartFactory.loss_curve(
                [{"epoch": 1.0, "train_loss": 0.5}, {"epoch": 2.0, "train_loss": 0.25}]
            ),
            "per_bus_train": ChartFactory.per_bus_f_bars(
                [0.5] * 8, [10] * 8, title="t", gate_threshold=0.80,
            ),
            "per_bus_holdout": ChartFactory.per_bus_f_bars(
                [0.3] * 8, [5] * 8, title="h", gate_threshold=0.80,
            ),
            "timing_mae_hist": ChartFactory.timing_mae_hist([0.5, -0.3], 2.902),
            "confusion_grid": ChartFactory.confusion_grid(
                [{"TP": 1, "FP": 1, "FN": 1, "TN": 1}] * 8,
            ),
            "shuffle_control": ChartFactory.shuffle_control(
                [{"key": "K1-X-Y-Z-V-W", "f_real": 0.5, "f_shuffle": 0.05}], 0.10,
            ),
            "piano_roll_samples": [],
        },
        tables={
            "train_per_bus": build_per_bus_table([], gate_f_threshold=0.80),
            "holdout_per_bus": build_per_bus_table([], gate_f_threshold=0.80),
        },
        hyperparameters=[("k1", "v1"), ("k2", "v2")],
    )
    out1 = write_training_report(ctx, tmp_path / "r1")
    out2 = write_training_report(ctx, tmp_path / "r2")
    assert out1.read_bytes() == out2.read_bytes(), (
        "two consecutive renders of the same context must be byte-identical"
    )
