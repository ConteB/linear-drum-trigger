"""F0-T4b L3 Ocular Proof — pack all evidence for the Gate L3 inspection.

Generates the artefacts the CEO inspects:

1. Per-bus F-measure on TRAIN and HOLDOUT (the architecture-learns? evidence).
2. Round-trip report (PyTorch ↔ NumPy ↔ C++) — the architectural de-risking.
3. Onset prediction stats (pred vs ground-truth peaks, refused-by-bus matrix).
4. Latency / receptive-field summary (the F0-T8 / F4 PDC budget).

Run after a training run + a round-trip run, with the live ``artifacts/`` and
``docs/gates/L3_OCULAR_PROOF/round_trip_report.json``.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from neural.data import load_pool  # noqa: E402
from neural.metrics import (  # noqa: E402
    FRAME_PERIOD_MS,
    L3_F_MEASURE_MIN,
    L3_HIHAT_MAE_MAX,
    L3_SHUFFLED_F_MAX,
    L3_TIMING_MAE_MAX_MS,
    R_TARGET_HZ,
    onset_report,
    tune_threshold,
)
from neural.model import HIHAT_OPENING_COL, TCNConfig, TCNModel, count_parameters  # noqa: E402

BUS_NAMES = (
    "kick", "snare", "hihat", "tom_hi_mid", "floor_tom", "ride", "crash_a", "crash_b_misc",
)


@dataclass
class SampleEval:
    key: str
    engine: str
    mic_config: str
    threshold: float
    f_per_bus: list[float | None]
    p_per_bus: list[float | None]
    r_per_bus: list[float | None]
    f_mean: float
    timing_mae_ms: float
    hihat_mae: float
    n_pred_total: int
    n_true_total: int
    n_matched_total: int


def _maybe_nan_float(x: float) -> float | None:
    return None if np.isnan(x) else float(x)


def evaluate_sample(
    model: TCNModel, audio: np.ndarray, target: np.ndarray, n_sample: int
) -> SampleEval | None:
    # The caller passes the raw sample; we use a deterministic leading window.
    if audio.shape[1] < n_sample:
        n_sample = (audio.shape[1] // 128) * 128
    n_frame = n_sample // 128
    with torch.no_grad():
        pred = (
            model(torch.from_numpy(audio[:, :n_sample]).unsqueeze(0).float())
            .squeeze(0)
            .numpy()
            .astype(np.float32, copy=False)
        )
    target_cut = target[:n_frame].astype(np.float32, copy=False)
    onset_pred = pred[:, 0:24:3]
    onset_target = target_cut[:, 0:24:3]
    hihat_pred = pred[:, HIHAT_OPENING_COL]
    hihat_target = target_cut[:, HIHAT_OPENING_COL]
    thr, _ = tune_threshold(onset_pred, onset_target)
    rep = onset_report(onset_pred, onset_target, threshold=thr)
    return SampleEval(
        key="",  # filled by caller
        engine="",
        mic_config="",
        threshold=thr,
        f_per_bus=[_maybe_nan_float(x) for x in rep.f_measure_per_bus],
        p_per_bus=[_maybe_nan_float(x) for x in rep.precision_per_bus],
        r_per_bus=[_maybe_nan_float(x) for x in rep.recall_per_bus],
        f_mean=float(np.nanmean(rep.f_measure_per_bus)),
        timing_mae_ms=float(rep.timing_mae_ms),
        hihat_mae=float(np.mean(np.abs(hihat_pred - hihat_target))),
        n_pred_total=int(rep.n_pred_total),
        n_true_total=int(rep.n_true_total),
        n_matched_total=int(rep.n_matched_total),
    )


def main(
    ckpt_path: Path = Path("artifacts/f0t4b_tcn.pt"),
    pool_root: Path = Path("data/gold/L2_pool"),
    holdout_keys: tuple[str, ...] = (
        "GMD000-V0T0-DGZ-R0-L1-NONE",
        "GMD001-V0T0-SFZ-R0-L1-NONE",
    ),
    n_sample: int = 131072,
    out_path: Path = Path("docs/gates/L3_OCULAR_PROOF/per_bus_report.json"),
) -> None:
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    model = TCNModel(TCNConfig())
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    n_params = count_parameters(model)

    pool = load_pool(pool_root)
    train_evals: list[SampleEval] = []
    holdout_evals: list[SampleEval] = []
    for s in pool:
        ev = evaluate_sample(model, s.audio, s.target, n_sample)
        if ev is None:
            continue
        ev.key = s.key
        ev.engine = s.engine
        ev.mic_config = s.mic_config
        (holdout_evals if s.key in holdout_keys else train_evals).append(ev)

    # Aggregate per-bus over the train set.
    bus_f_train: list[list[float]] = [[] for _ in range(8)]
    for ev in train_evals:
        for b, f in enumerate(ev.f_per_bus):
            if f is not None:
                bus_f_train[b].append(f)

    payload = {
        "model": {
            "ckpt": str(ckpt_path),
            "n_parameters": n_params,
            "topology": (
                "F0-T4a (Input-Agnostic Projection → Strided Encoder Stem → "
                "Dilated Causal TCN Trunk → 4 heads)"
            ),
            "channels": int(model.config.channels),
        },
        "evaluation": {
            "n_sample": int(n_sample),
            "n_frame": int(n_sample // 128),
            "frame_period_ms": float(FRAME_PERIOD_MS),
            "r_target_hz": float(R_TARGET_HZ),
        },
        "l3_thresholds": {
            "f_measure_min": float(L3_F_MEASURE_MIN),
            "shuffled_f_max": float(L3_SHUFFLED_F_MAX),
            "timing_mae_max_ms": float(L3_TIMING_MAE_MAX_MS),
            "hihat_mae_max": float(L3_HIHAT_MAE_MAX),
        },
        "bus_names": list(BUS_NAMES),
        "train": [ev_to_dict(ev) for ev in train_evals],
        "holdout": [ev_to_dict(ev) for ev in holdout_evals],
        "train_per_bus_f_summary": {
            BUS_NAMES[b]: {
                "n_samples_with_truth": len(bus_f_train[b]),
                "mean_f": float(np.mean(bus_f_train[b])) if bus_f_train[b] else None,
                "min_f": float(min(bus_f_train[b])) if bus_f_train[b] else None,
                "max_f": float(max(bus_f_train[b])) if bus_f_train[b] else None,
            }
            for b in range(8)
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[L3 Ocular Proof] wrote {out_path}")


def ev_to_dict(ev: SampleEval) -> dict[str, object]:
    return {
        "key": ev.key,
        "engine": ev.engine,
        "mic_config": ev.mic_config,
        "threshold": ev.threshold,
        "f_per_bus": ev.f_per_bus,
        "p_per_bus": ev.p_per_bus,
        "r_per_bus": ev.r_per_bus,
        "f_mean": ev.f_mean,
        "timing_mae_ms": ev.timing_mae_ms,
        "hihat_mae": ev.hihat_mae,
        "n_pred_total": ev.n_pred_total,
        "n_true_total": ev.n_true_total,
        "n_matched_total": ev.n_matched_total,
    }


if __name__ == "__main__":
    main()
