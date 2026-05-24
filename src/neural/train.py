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
from torch.utils.data import DataLoader, WeightedRandomSampler

from neural.data import (
    DEFAULT_LOOKAHEAD_FRAMES,
    ENCODER_STRIDE,
    HIHAT_OPENING_COL,
    MIN_CROP_SAMPLES,
    GoldDataset,
    GoldSample,
    load_pool,
)
from neural.loss import LossConfig, N_BUSES, TCNLoss
from neural.metrics import (
    FRAME_PERIOD_MS,
    L3_F_MEASURE_MIN,
    L3_HIHAT_MAE_MAX,
    L3_SHUFFLED_F_MAX,
    L3_TIMING_MAE_MAX_MS,
    R_TARGET_HZ,
    L3Verdict,
    evaluate_l3,
)
from neural.model import TCNConfig, TCNModel, count_parameters
from neural.reporter import (
    build_default_context,
    evaluate_sample_for_report,
    write_training_report,
)


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


#: Default cap on the per-sample weight produced by
#: :func:`_compute_sampler_weights` (F0-T4c B6a — Decision Lock CEO 2026-05-24).
#: Without a cap, a single groove containing a 0.7 %-density bus would get a
#: weight ~140× — likely to monopolise the epoch. Cap 200× balances foreground
#: with bus diversity (the jitter k=2 gives 3 variants per source MIDI).
SAMPLER_WEIGHT_CAP: float = 200.0


def _compute_sampler_weights(
    samples: list[GoldSample],
    *,
    pos_weight: float | tuple[float, ...],
    onset_mask_threshold: float = 0.5,
    cap: float = SAMPLER_WEIGHT_CAP,
) -> list[float] | None:
    """Return ``WeightedRandomSampler`` weights when ``pos_weight`` is per-bus.

    For each sample compute ``weight_s = max_b(pos_weight[b])`` over the buses
    ``b`` that the sample contains (≥ 1 onset above ``onset_mask_threshold``).
    Samples with no positives default to ``1.0`` (baseline weight) — they are
    still useful as negative examples. Output cap at ``cap`` (default 200) to
    prevent rare-bus monopolisation.

    Returns ``None`` when ``pos_weight`` is scalar (caller falls back to
    plain shuffled DataLoader — legacy behaviour).
    """
    if not isinstance(pos_weight, tuple):
        return None
    if len(pos_weight) != N_BUSES:
        raise ValueError(
            f"pos_weight tuple must have {N_BUSES} elements, got {len(pos_weight)}"
        )
    weights: list[float] = []
    for s in samples:
        # Onset columns 0:24:3 — F0-T2a §3.3, flat-25 layout.
        onset = s.target[:, 0:24:3]  # [n_frame, 8]
        has_bus = (onset > onset_mask_threshold).any(axis=0)  # [8]
        if not has_bus.any():
            weights.append(1.0)
            continue
        bus_weights = [pos_weight[b] for b in range(N_BUSES) if has_bus[b]]
        weights.append(min(cap, max(bus_weights)))
    return weights


def evaluate_holdout(
    model: TCNModel,
    holdout: list[GoldSample],
    *,
    device: torch.device,
    crop_samples: int,
    lookahead_frames: int = DEFAULT_LOOKAHEAD_FRAMES,
) -> dict[str, L3Verdict]:
    """Evaluate the model on each holdout sample (deterministic crop = head of the file)."""
    model.eval()
    out: dict[str, L3Verdict] = {}
    with torch.no_grad():
        for s in holdout:
            # Same look-ahead semantics as training: feed an audio window
            # shifted forward by ``L`` frames; compare the prediction with the
            # target window covering frames [0, n_frame).
            L = lookahead_frames  # noqa: N806
            crop_frames = crop_samples // ENCODER_STRIDE
            total_audio_frames = s.audio.shape[1] // ENCODER_STRIDE
            n_frame = min(crop_frames, s.target.shape[0], total_audio_frames - L)
            n_frame = max(0, n_frame)
            if n_frame == 0:
                # Sample too short — emit a placeholder zero verdict.
                out[s.key] = evaluate_l3(
                    np.zeros((1, 25), dtype=np.float32),
                    s.target[:1].astype(np.float32),
                )
                continue
            start_sample = L * ENCODER_STRIDE
            end_sample = start_sample + n_frame * ENCODER_STRIDE
            audio = torch.from_numpy(s.audio[:, start_sample:end_sample]).unsqueeze(0).to(device)
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
    # F0-T4c B2 (Decision Lock CEO 2026-05-24): default crop = 196 608 samples
    # (~4.46 s, margine 1.45× sopra MIN_CROP_SAMPLES = 135 552). Era 65536.
    crop_samples: int = 196608,
    epochs: int = 200,
    batch_size: int = 4,
    lr: float = 1e-3,
    seed: int = 0,
    force_cpu: bool = False,
    log_every: int = 10,
    save_to: Path | None = Path("artifacts/f0t4b_tcn.pt"),
    report_dir: Path | None = None,
    run_id: str = "training-run",
    run_title: str = "Training report",
    tcn_channels: int = 32,
    loss_config: LossConfig | None = None,
    include_keys: tuple[str, ...] | None = None,
    # F0-T4c B1 (Decision Lock CEO 2026-05-24): default lookahead = 35 frame
    # (= ~100 ms PDC). Era 0 (strict-causal — bug isolato dalla diagnostica
    # T1-DIAG-A che faceva collassare ogni R&D Tier 1 a F ≈ 0.09).
    lookahead_frames: int = DEFAULT_LOOKAHEAD_FRAMES,
) -> TrainResult:
    """Run the F0-T4b training. Returns the verdict for the L3 Ocular Proof.

    If ``report_dir`` is given (or :data:`AUTO_REPORT_DEFAULT_DIR` is set), the
    function also writes a Tier-1 HTML report (LIN-DT-RPTBP-001) summarising
    every metric of this run. The report path lives at
    ``<report_dir>/<YYYY-MM-DD>-<run_id>/report.html``.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = pick_device(force_cpu)
    print(f"[F0-T4b] device = {device}")

    samples = load_pool(pool_root)
    if include_keys is not None:
        # Diagnostic filter — restrict the pool to a curated subset (e.g. drop
        # the 90 'chaos' grooves whose target is structurally uncorrelated
        # from the audio — Opzione A · Step 2 finding).
        include_set = set(include_keys)
        samples = [s for s in samples if s.key in include_set]
        print(f"[F0-T4b] include_keys filter applied: pool -> {len(samples)} samples")
    train_samples, holdout_samples = split_train_holdout(samples, holdout_keys=holdout_keys)
    print(
        f"[F0-T4b] train = {len(train_samples)} samples, "
        f"holdout = {len(holdout_samples)} samples"
    )

    train_ds = GoldDataset(
        train_samples,
        crop_samples=crop_samples,
        rng=np.random.default_rng(seed),
        lookahead_frames=lookahead_frames,
    )
    # F0-T4c B6a (Decision Lock CEO 2026-05-24): auto-attiva il
    # WeightedRandomSampler quando il LossConfig usa pos_weight per-bus.
    # Senza questo, il sampler shuffled vede crash_a (0.7 % dei sample GMD)
    # nel 99.3 % dei batch come zero → strategy ottima "predici 0" → F = 0.
    cfg = loss_config or LossConfig()
    sampler_weights = _compute_sampler_weights(
        train_samples, pos_weight=cfg.pos_weight
    )
    if sampler_weights is not None:
        # n_samples per epoch = len(train) — stessa quantità di step ma con
        # probabilità ricalibrata sui bus rari. Generatore seedato per
        # determinismo (T1-DIAG-A pattern).
        gen = torch.Generator()
        gen.manual_seed(seed)
        sampler = WeightedRandomSampler(
            weights=sampler_weights,
            num_samples=len(train_samples),
            replacement=True,
            generator=gen,
        )
        print(
            f"[F0-T4b] B6a WeightedRandomSampler ON · weights range "
            f"[{min(sampler_weights):.1f}, {max(sampler_weights):.1f}]"
        )
        train_loader = DataLoader(
            train_ds,
            batch_size=batch_size,
            sampler=sampler,
            num_workers=0,
            drop_last=False,
        )
    else:
        train_loader = DataLoader(
            train_ds,
            batch_size=batch_size,
            shuffle=True,
            num_workers=0,
            drop_last=False,
        )

    model = TCNModel(TCNConfig(channels=tcn_channels)).to(device)
    n_params = count_parameters(model)
    print(f"[F0-T4b] parameters = {n_params:,}")
    loss_fn = TCNLoss(cfg).to(device)
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
    # Heads tracked separately so per-head contribution to the total is visible
    # epoch by epoch (Opzione A · Step 1 — diagnostica per-head loss).
    head_keys = ("onset", "velocity", "microtiming", "hihat")
    for epoch in range(1, epochs + 1):
        model.train()
        epoch_total = 0.0
        epoch_heads = dict.fromkeys(head_keys, 0.0)
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
            for k in head_keys:
                epoch_heads[k] += float(losses[k].detach())
            n_steps += 1
        epoch_mean = epoch_total / max(n_steps, 1)
        head_means = {k: epoch_heads[k] / max(n_steps, 1) for k in head_keys}
        final_loss = epoch_mean
        history.append({
            "epoch": float(epoch),
            "train_loss": epoch_mean,
            **{f"loss_{k}": head_means[k] for k in head_keys},
        })
        if epoch % log_every == 0 or epoch == 1:
            # Print the weighted contribution of each head (loss_k × w_k) to the
            # total — surfaces the actual gradient driver, not the raw head loss.
            wcfg = loss_fn.config
            wcontrib = {
                "onset": head_means["onset"] * wcfg.w_onset,
                "velocity": head_means["velocity"] * wcfg.w_velocity,
                "microtiming": head_means["microtiming"] * wcfg.w_microtiming,
                "hihat": head_means["hihat"] * wcfg.w_hihat,
            }
            print(
                f"[F0-T4b]   epoch {epoch:4d}  total={epoch_mean:.4f} | "
                f"on={wcontrib['onset']:.4f} vel={wcontrib['velocity']:.4f} "
                f"mt={wcontrib['microtiming']:.4f} hh={wcontrib['hihat']:.4f}"
            )

    wall = time.perf_counter() - t0
    print(f"[F0-T4b] training done in {wall:.1f} s")

    verdicts = evaluate_holdout(
        model, holdout_samples, device=device, crop_samples=crop_samples,
        lookahead_frames=lookahead_frames,
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

    # ---- Auto-emit the Tier-1 HTML report (LIN-DT-RPTBP-001) ----
    # Mandato MODEL_REPORT_BLUEPRINT §0: ogni training produce un report HTML
    # auto-contenuto. Non opzionale.
    if report_dir is not None:
        _emit_training_report(
            model=model,
            train_samples=train_samples,
            holdout_samples=holdout_samples,
            history=history,
            n_parameters=n_params,
            config={
                "epochs": epochs,
                "crop_samples": crop_samples,
                "batch_size": batch_size,
                "lr": lr,
                "seed": seed,
                "device": str(device),
            },
            run_id=run_id,
            run_title=run_title,
            out_root=report_dir,
        )

    return TrainResult(
        config={
            "epochs": epochs,
            "crop_samples": crop_samples,
            "batch_size": batch_size,
            "lr": lr,
            "seed": seed,
            "tcn_channels": tcn_channels,
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


def _emit_training_report(
    *,
    model: TCNModel,
    train_samples: list[GoldSample],
    holdout_samples: list[GoldSample],
    history: list[dict[str, float]],
    n_parameters: int,
    config: dict[str, Any],
    run_id: str,
    run_title: str,
    out_root: Path,
) -> Path:
    """Run the per-sample evaluation and write the Tier-1 HTML report."""
    import datetime as _dt  # noqa: PLC0415

    cpu_model = model.to("cpu").eval()
    train_evals: list[dict[str, Any]] = []
    holdout_evals: list[dict[str, Any]] = []
    for s in train_samples:
        ev = evaluate_sample_for_report(cpu_model, s.audio, s.target, n_sample=131072)
        ev["key"], ev["engine"], ev["mic_config"] = s.key, s.engine, s.mic_config
        train_evals.append(ev)
    for s in holdout_samples:
        ev = evaluate_sample_for_report(cpu_model, s.audio, s.target, n_sample=131072)
        ev["key"], ev["engine"], ev["mic_config"] = s.key, s.engine, s.mic_config
        holdout_evals.append(ev)

    hyperparams = {
        **config,
        "channels (C)": cpu_model.config.channels,
        "encoder_strides": list(cpu_model.config.encoder_strides),
        "trunk_dilations": list(cpu_model.config.trunk_dilations),
    }
    today = _dt.date.today().isoformat()
    ctx = build_default_context(
        run_id=run_id,
        run_date=today,
        title=run_title,
        history=history,
        n_parameters=n_parameters,
        hyperparameters=hyperparams,
        train_evals=train_evals,
        holdout_evals=holdout_evals,
        gate_f_threshold=L3_F_MEASURE_MIN,
        gate_shuffle_max=L3_SHUFFLED_F_MAX,
        gate_timing_mae_max=L3_TIMING_MAE_MAX_MS,
        gate_hihat_max=L3_HIHAT_MAE_MAX,
        frame_period_ms=FRAME_PERIOD_MS,
        frame_rate_hz=R_TARGET_HZ,
        tier=1,
    )
    out_dir = Path(out_root) / f"{today}-{run_id}"
    out = write_training_report(ctx, out_dir)
    print(f"[F0-T4b] wrote training report to {out}")
    return out


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
    # F0-T4c B2 default = 196 608 (~4.46 s); minimum enforced by GoldDataset.
    parser.add_argument("--crop-samples", type=int, default=196608,
                        help="audio crop in samples; min %d (F0-T4c B2)"
                             % MIN_CROP_SAMPLES)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cpu", action="store_true", help="force CPU (skip MPS/CUDA)")
    # F0-T4c B1 — propagation of the look-ahead PDC default.
    parser.add_argument("--lookahead-frames", type=int,
                        default=DEFAULT_LOOKAHEAD_FRAMES,
                        help="look-ahead in frames; default %d (= 100 ms PDC, F0-T4c B1)"
                             % DEFAULT_LOOKAHEAD_FRAMES)
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
    parser.add_argument(
        "--html-report-dir", type=Path, default=Path("reports"),
        help="Root directory for the Tier-1 HTML report (LIN-DT-RPTBP-001). "
             "Defaults to ./reports; use --no-html-report to skip.",
    )
    parser.add_argument(
        "--no-html-report", action="store_true",
        help="Disable the auto-generated HTML report (NOT recommended — "
             "the report is mandatory per MODEL_REPORT_BLUEPRINT §0).",
    )
    parser.add_argument(
        "--run-id", default="f0t4b-tcn-c32-seed0",
        help="Stable run identifier used in the report directory name.",
    )
    parser.add_argument(
        "--run-title", default="Training report — F0-T4b TCN",
        help="Title shown in the HTML report header.",
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
        report_dir=None if args.no_html_report else args.html_report_dir,
        run_id=args.run_id,
        run_title=args.run_title,
        lookahead_frames=args.lookahead_frames,
    )
    _write_report(result, args.report_to)
    print(f"[F0-T4b] wrote report to {args.report_to}")


if __name__ == "__main__":
    main()
