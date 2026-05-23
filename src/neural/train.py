"""Training loop — F0-T4b mini-prototype on the 12 Gold samples.

Targets the L3 gate (F0-T4a §7):

* Onset F-measure ±20 ms ≥ 0.80 (mean per-bus)
* Shuffled-label F-measure < 0.10 (negative control)
* Timing-MAE matched onsets < 5 ms
* Hihat-opening MAE < 0.15

On a mini-batch this is a *de-risking* gate, not a product claim
(F0-T4a §7 — "soglie di de-risking architetturale, non claim di prodotto").

Run:  ``python -m neural.train --epochs 200 --crop-samples 65536``
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from neural.data import (
    ENCODER_STRIDE,
    GoldDataset,
    GoldSample,
    load_pool,
)
from neural.loss import LossConfig, TCNLoss
from neural.metrics import L3Verdict, evaluate_l3
from neural.model import TCNConfig, TCNModel, count_parameters


@dataclass(frozen=True)
class TrainResult:
    """Final state of a training run — for the L3 Ocular Proof."""

    config: dict[str, Any]
    n_parameters: int
    train_keys: list[str]
    holdout_keys: list[str]
    wall_time_s: float
    final_train_loss: float
    holdout_verdicts: dict[str, L3Verdict]
    history: list[dict[str, float]]


def pick_device(force_cpu: bool = False) -> torch.device:
    if force_cpu:
        return torch.device("cpu")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def split_train_holdout(
    samples: list[GoldSample], *, holdout_keys: tuple[str, ...]
) -> tuple[list[GoldSample], list[GoldSample]]:
    train: list[GoldSample] = []
    holdout: list[GoldSample] = []
    for s in samples:
        (holdout if s.key in holdout_keys else train).append(s)
    if not train:
        raise RuntimeError("split_train_holdout: empty train set")
    if not holdout:
        raise RuntimeError("split_train_holdout: empty holdout set")
    return train, holdout


def evaluate_holdout(
    model: TCNModel,
    holdout: list[GoldSample],
    *,
    device: torch.device,
    crop_samples: int,
) -> dict[str, L3Verdict]:
    """Evaluate the model on each holdout sample (deterministic crop = head of the file)."""
    model.eval()
    out: dict[str, L3Verdict] = {}
    with torch.no_grad():
        for s in holdout:
            # Use a fixed crop = leading window. Holdout metrics are reproducible.
            n_sample = min(s.audio.shape[1], crop_samples)
            # Round down to a multiple of ENCODER_STRIDE for frame alignment.
            n_sample = (n_sample // ENCODER_STRIDE) * ENCODER_STRIDE
            n_frame = n_sample // ENCODER_STRIDE
            audio = torch.from_numpy(s.audio[:, :n_sample]).unsqueeze(0).to(device)
            pred = model(audio).squeeze(0).cpu().numpy()  # [T, 25]
            target = s.target[:n_frame]
            out[s.key] = evaluate_l3(pred, target)
    model.train()
    return out


def train(
    *,
    pool_root: Path = Path("data/gold/L2_pool"),
    holdout_keys: tuple[str, ...] = (
        "GMD000-V0T0-DGZ-R0-L1-NONE",
        "GMD001-V0T0-SFZ-R0-L1-NONE",
    ),
    crop_samples: int = 65536,
    epochs: int = 200,
    batch_size: int = 4,
    lr: float = 1e-3,
    seed: int = 0,
    force_cpu: bool = False,
    log_every: int = 10,
    save_to: Path | None = Path("artifacts/f0t4b_tcn.pt"),
) -> TrainResult:
    """Run the F0-T4b training. Returns the verdict for the L3 Ocular Proof."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = pick_device(force_cpu)
    print(f"[F0-T4b] device = {device}")

    samples = load_pool(pool_root)
    train_samples, holdout_samples = split_train_holdout(samples, holdout_keys=holdout_keys)
    print(
        f"[F0-T4b] train = {len(train_samples)} samples, "
        f"holdout = {len(holdout_samples)} samples"
    )

    train_ds = GoldDataset(
        train_samples,
        crop_samples=crop_samples,
        rng=np.random.default_rng(seed),
    )
    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        drop_last=False,
    )

    model = TCNModel(TCNConfig()).to(device)
    n_params = count_parameters(model)
    print(f"[F0-T4b] parameters = {n_params:,}")
    loss_fn = TCNLoss(LossConfig()).to(device)
    optim = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    # MPS autocast is supported as of PyTorch 2.x; CPU autocast adds little.
    use_amp = device.type in {"cuda", "mps"}
    autocast_ctx: Any
    if use_amp:
        autocast_ctx = torch.autocast(device_type=device.type, dtype=torch.float16)
    else:
        autocast_ctx = contextlib.nullcontext()

    history: list[dict[str, float]] = []
    t0 = time.perf_counter()
    final_loss = math.nan
    for epoch in range(1, epochs + 1):
        model.train()
        epoch_total = 0.0
        n_steps = 0
        for batch in train_loader:
            audio = batch["audio"].to(device, non_blocking=True)
            target = batch["target"].to(device, non_blocking=True)
            optim.zero_grad(set_to_none=True)
            with autocast_ctx:
                pred = model(audio)
                losses = loss_fn(pred, target)
            losses["total"].backward()
            optim.step()
            epoch_total += float(losses["total"].detach())
            n_steps += 1
        epoch_mean = epoch_total / max(n_steps, 1)
        final_loss = epoch_mean
        history.append({"epoch": float(epoch), "train_loss": epoch_mean})
        if epoch % log_every == 0 or epoch == 1:
            print(f"[F0-T4b]   epoch {epoch:4d}  train_loss={epoch_mean:.4f}")

    wall = time.perf_counter() - t0
    print(f"[F0-T4b] training done in {wall:.1f} s")

    verdicts = evaluate_holdout(
        model, holdout_samples, device=device, crop_samples=crop_samples
    )
    for k, v in verdicts.items():
        print(
            f"[F0-T4b] holdout {k}: "
            f"F={v.f_measure_mean:.3f} (≥0.80? {v.passes_f_measure}) · "
            f"F_shuf={v.f_shuffled:.3f} (<0.10? {v.passes_shuffled}) · "
            f"TimingMAE={v.timing_mae_ms:.2f} ms (<5? {v.passes_timing}) · "
            f"HiHatMAE={v.hihat_mae:.3f} (<0.15? {v.passes_hihat}) · "
            f"PASS={v.passes}"
        )

    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state": model.state_dict(),
                "config": {
                    "channels": model.config.channels,
                    "encoder_strides": list(model.config.encoder_strides),
                    "trunk_dilations": list(model.config.trunk_dilations),
                },
                "seed": seed,
                "crop_samples": crop_samples,
                "epochs": epochs,
            },
            save_to,
        )
        print(f"[F0-T4b] saved model to {save_to}")

    return TrainResult(
        config={
            "epochs": epochs,
            "crop_samples": crop_samples,
            "batch_size": batch_size,
            "lr": lr,
            "seed": seed,
            "device": str(device),
        },
        n_parameters=n_params,
        train_keys=[s.key for s in train_samples],
        holdout_keys=[s.key for s in holdout_samples],
        wall_time_s=wall,
        final_train_loss=final_loss,
        holdout_verdicts=verdicts,
        history=history,
    )


def _verdict_to_dict(v: L3Verdict) -> dict[str, Any]:
    return {
        "f_measure_mean": v.f_measure_mean,
        "f_shuffled": v.f_shuffled,
        "timing_mae_ms": v.timing_mae_ms,
        "hihat_mae": v.hihat_mae,
        "passes_f_measure": v.passes_f_measure,
        "passes_shuffled": v.passes_shuffled,
        "passes_timing": v.passes_timing,
        "passes_hihat": v.passes_hihat,
        "passes": v.passes,
    }


def _write_report(result: TrainResult, path: Path) -> None:
    payload = {
        "config": result.config,
        "n_parameters": result.n_parameters,
        "train_keys": result.train_keys,
        "holdout_keys": result.holdout_keys,
        "wall_time_s": result.wall_time_s,
        "final_train_loss": result.final_train_loss,
        "holdout_verdicts": {k: _verdict_to_dict(v) for k, v in result.holdout_verdicts.items()},
        "history": result.history,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="F0-T4b TCN mini-prototype training")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--crop-samples", type=int, default=65536)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cpu", action="store_true", help="force CPU (skip MPS/CUDA)")
    parser.add_argument(
        "--pool", type=Path, default=Path("data/gold/L2_pool"),
        help="Gold mini-batch root",
    )
    parser.add_argument(
        "--save-to", type=Path, default=Path("artifacts/f0t4b_tcn.pt"),
        help="checkpoint path (PyTorch)",
    )
    parser.add_argument(
        "--report-to", type=Path, default=Path("artifacts/f0t4b_report.json"),
        help="JSON report path",
    )
    args = parser.parse_args()

    result = train(
        pool_root=args.pool,
        crop_samples=args.crop_samples,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        seed=args.seed,
        force_cpu=args.cpu,
        save_to=args.save_to,
    )
    _write_report(result, args.report_to)
    print(f"[F0-T4b] wrote report to {args.report_to}")


if __name__ == "__main__":
    main()
