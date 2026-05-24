#!/usr/bin/env python3
"""Mini-L3 cross-kit training — TCN F0-T4a + F0-T4c defaults · CEO 2026-05-24.

Trains the C=32 TCN on ``data/gold/mini_l3_train/`` (3 kits) and evaluates
on ``data/gold/mini_l3_val/`` (ShittyKit — **never seen during training**).

This is the real cross-kit test the regression test (self-overfit) could not
deliver: does the network learn the *physical event* (transient onset
shape, multi-mic phase) or just the *timbre* (kit-specific frequency
signature)?

Gate: **F-measure (mean across non-empty samples) ≥ 0.55** on the val pool.
Below that, the network is timbre-bound; passing means we have empirical
evidence that the F0-T4c defaults generalize cross-kit, which is the only
piece L4 can really validate (with E-GMD on a much larger scale).

Run::

    python tools/mini_l3_train.py --epochs 120
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader, WeightedRandomSampler

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from neural.data import (  # noqa: E402
    DEFAULT_LOOKAHEAD_FRAMES,
    ENCODER_STRIDE,
    GoldDataset,
    GoldSample,
    load_pool,
)
from neural.loss import LossConfig, TCNLoss  # noqa: E402
from neural.metrics import (  # noqa: E402
    evaluate_l3,
    onset_report,
    tune_threshold,
)
from neural.model import TCNConfig, TCNModel, count_parameters  # noqa: E402
from neural.reporter import (  # noqa: E402
    GateVerdictRow,
    TldrRow,
    build_default_context,
    evaluate_sample_for_report,
    verdict as verdict_label,
    write_training_report,
)
from neural.train import _compute_sampler_weights  # noqa: E402


CRASH_A_BUS_IDX = 6
GATE_F_MEAN_VAL = 0.55


def pick_device(force_cpu: bool = False) -> torch.device:
    if force_cpu:
        return torch.device("cpu")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mini-L3 cross-kit training (CEO 2026-05-24)",
    )
    parser.add_argument("--train-pool", type=Path,
                        default=Path("data/gold/mini_l3_train"))
    parser.add_argument("--val-pool", type=Path,
                        default=Path("data/gold/mini_l3_val"))
    parser.add_argument("--density-json", type=Path,
                        default=Path("artifacts/mini_l3_density.json"))
    parser.add_argument("--crop-samples", type=int, default=196608)
    parser.add_argument("--lookahead-frames", type=int,
                        default=DEFAULT_LOOKAHEAD_FRAMES)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--tcn-channels", type=int, default=32)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--run-id", default="mini-l3-crosskit-2026-05-24")
    parser.add_argument("--reports-root", type=Path, default=Path("reports"))
    parser.add_argument("--gate-root", type=Path,
                        default=Path("docs/gates/F0-T4c_MINI_L3"))
    parser.add_argument("--save-to", type=Path,
                        default=Path("artifacts/mini_l3_tcn.pt"))
    parser.add_argument("--max-train-samples", type=int, default=0,
                        help="Subsample train pool to N samples (deterministic, "
                             "via stride). 0 = use all (default). Useful when "
                             "macOS memory pressure pushes swap past 90 percent.")
    parser.add_argument("--baseline-only", action="store_true",
                        help="Restrict train pool to variant_idx=0 (baseline, "
                             "no jitter). Halves the loaded RAM (656 → ~328) "
                             "and is the recommended workaround for the "
                             "mini-L3 on a 16 GB Mac.")
    args = parser.parse_args()

    # --- Load train + val + density ---
    # Force unbuffered stdout — `python -u` equivalent inside the script
    # (mini-L3 on macOS w/ tee pipe was hitting buffering on a 4 GB process).
    import sys as _sys  # noqa: PLC0415
    _sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    print(f"[mini-L3] loading val pool ({args.val_pool})…", flush=True)
    val_samples = load_pool(args.val_pool)
    print(f"[mini-L3] val pool: {len(val_samples)} samples", flush=True)
    print(f"[mini-L3] loading train pool ({args.train_pool})…", flush=True)
    train_samples = load_pool(args.train_pool)
    print(f"[mini-L3] train pool: {len(train_samples)} samples (before subsample)",
          flush=True)
    # Optional subsample to reduce RAM footprint on small-memory macs.
    if args.baseline_only:
        # The mini-L3 barcode J segment is J00 = baseline, J01 = jittered v1.
        before = len(train_samples)
        train_samples = [s for s in train_samples if "-J00-" in s.key]
        print(f"[mini-L3] --baseline-only: pool reduced {before} → "
              f"{len(train_samples)}", flush=True)
    if args.max_train_samples and len(train_samples) > args.max_train_samples:
        before = len(train_samples)
        stride = before // args.max_train_samples
        train_samples = train_samples[::stride][:args.max_train_samples]
        print(f"[mini-L3] --max-train-samples={args.max_train_samples}: "
              f"pool reduced {before} → {len(train_samples)} (stride={stride})",
              flush=True)
    print(f"[mini-L3] train pool FINAL: {len(train_samples)} samples", flush=True)
    if not train_samples or not val_samples:
        print("ERROR: empty pool.", flush=True)
        return 1

    density = json.loads(args.density_json.read_text())
    pos_weight_tuple: tuple[float, ...] = tuple(
        float(w) for w in density["pos_weight_per_bus"]
    )
    print(f"[mini-L3] pos_weight_per_bus = {pos_weight_tuple}")
    assert len(pos_weight_tuple) == 8

    device = pick_device(args.cpu)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    print(f"[mini-L3] device = {device}")

    loss_cfg = LossConfig(pos_weight=pos_weight_tuple)
    train_ds = GoldDataset(
        train_samples,
        crop_samples=args.crop_samples,
        rng=np.random.default_rng(args.seed),
        lookahead_frames=args.lookahead_frames,
    )

    # B6a sampler ON for cross-kit training (rationale: 1500 samples is large
    # enough that the rare-bus oversampling has a real signal, and ShittyKit
    # is *only* in val so it cannot be starved by the sampler weights).
    sampler_weights = _compute_sampler_weights(
        train_samples, pos_weight=pos_weight_tuple,
    )
    assert sampler_weights is not None
    print(f"[mini-L3] B6a sampler weights range "
          f"[{min(sampler_weights):.1f}, {max(sampler_weights):.1f}]")
    gen = torch.Generator()
    gen.manual_seed(args.seed)
    sampler = WeightedRandomSampler(
        weights=sampler_weights,
        num_samples=len(train_samples),
        replacement=True,
        generator=gen,
    )
    loader = DataLoader(
        train_ds, batch_size=args.batch_size, sampler=sampler,
        num_workers=0, drop_last=False,
    )

    model = TCNModel(TCNConfig(channels=args.tcn_channels)).to(device)
    n_params = count_parameters(model)
    print(f"[mini-L3] parameters = {n_params:,}")
    loss_fn = TCNLoss(loss_cfg).to(device)
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    use_amp = device.type in {"cuda", "mps"}
    autocast_ctx: Any
    if use_amp:
        autocast_ctx = torch.autocast(device_type=device.type, dtype=torch.float16)
    else:
        autocast_ctx = contextlib.nullcontext()

    # --- Training loop ---
    t0 = time.perf_counter()
    last_loss = math.nan
    history: list[dict[str, float]] = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_total = 0.0
        n_steps = 0
        for batch in loader:
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
        last_loss = epoch_total / max(n_steps, 1)
        history.append({"epoch": float(epoch), "train_loss": last_loss})
        if epoch % 10 == 0 or epoch == 1:
            print(f"[mini-L3] epoch {epoch:4d}  train_loss = {last_loss:.4f}")
    wall = time.perf_counter() - t0
    print(f"[mini-L3] training done in {wall:.1f} s")

    # Save checkpoint.
    if args.save_to:
        args.save_to.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "model_state": model.state_dict(),
            "config": {"channels": model.config.channels},
            "seed": args.seed,
            "crop_samples": args.crop_samples,
            "lookahead_frames": args.lookahead_frames,
            "epochs": args.epochs,
        }, args.save_to)
        print(f"[mini-L3] saved checkpoint → {args.save_to}")

    # --- Cross-kit evaluation on val pool (ShittyKit only) ---
    print(f"[mini-L3] evaluating on val pool ({len(val_samples)} ShittyKit samples)…")
    cpu_model = model.to("cpu").eval()
    val_evals: list[dict[str, Any]] = []
    for s in val_samples:
        ev = evaluate_sample_for_report(
            cpu_model, s.audio, s.target,
            n_sample=args.crop_samples,
            lookahead_frames=args.lookahead_frames,
        )
        ev["key"], ev["engine"], ev["mic_config"] = s.key, s.engine, s.mic_config
        val_evals.append(ev)

    f_means = [e["f_mean"] for e in val_evals if not math.isnan(e["f_mean"])]
    val_f_mean = float(np.mean(f_means)) if f_means else float("nan")
    val_f_max = max(f_means) if f_means else float("nan")
    val_f_min = min(f_means) if f_means else float("nan")
    pass_gate = (not math.isnan(val_f_mean)) and val_f_mean >= GATE_F_MEAN_VAL
    print(f"\n[mini-L3] ======== CROSS-KIT VERDICT (ShittyKit) ========")
    print(f"[mini-L3] val F_mean = {val_f_mean:.3f}  (gate ≥ {GATE_F_MEAN_VAL})  "
          f"→ {'PASS ✅' if pass_gate else 'FAIL ❌'}")
    print(f"[mini-L3] val F range = [{val_f_min:.3f}, {val_f_max:.3f}]")

    # Also evaluate on a sample of train for the report (every 10th to keep it light).
    train_subset = train_samples[::max(1, len(train_samples) // 12)][:12]
    train_evals: list[dict[str, Any]] = []
    for s in train_subset:
        ev = evaluate_sample_for_report(
            cpu_model, s.audio, s.target,
            n_sample=args.crop_samples,
            lookahead_frames=args.lookahead_frames,
        )
        ev["key"], ev["engine"], ev["mic_config"] = s.key, s.engine, s.mic_config
        train_evals.append(ev)

    # --- Build the blueprint-compliant HTML report ---
    extra_tldr = [
        TldrRow(
            label="Mini-L3 cross-kit gate (val F_mean ≥ 0.55)",
            value=f"{val_f_mean:.3f}",
            gate=f"≥ {GATE_F_MEAN_VAL}",
            verdict=verdict_label(pass_gate)[0],
            verdict_class=verdict_label(pass_gate)[1],
            is_summary=True,
        ),
        TldrRow(
            label="Val F range (min..max)",
            value=f"[{val_f_min:.3f}, {val_f_max:.3f}]",
            gate="—",
            verdict="info",
            verdict_class="",
        ),
    ]
    gate_rows = [
        GateVerdictRow(
            criterion=f"Cross-kit val F_mean ≥ {GATE_F_MEAN_VAL}",
            verdict=verdict_label(pass_gate)[0],
            verdict_class=verdict_label(pass_gate)[1],
        ),
        GateVerdictRow(
            criterion="Train kits: DRSKit + MuldjordKit + CrocellKit",
            verdict="✅ APPLIED",
            verdict_class="pass",
        ),
        GateVerdictRow(
            criterion="Val kit (vergine): ShittyKit",
            verdict="✅ APPLIED",
            verdict_class="pass",
        ),
        GateVerdictRow(
            criterion="F0-T4c defaults applicati (B1/B2/B3/B6a/B6b)",
            verdict="✅ APPLIED",
            verdict_class="pass",
        ),
    ]
    hp = {
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "crop_samples": args.crop_samples,
        "lookahead_frames": args.lookahead_frames,
        "lr": args.lr,
        "seed": args.seed,
        "tcn_channels": args.tcn_channels,
        "pos_weight_per_bus": list(pos_weight_tuple),
        "loss.w_onset": loss_cfg.w_onset,
        "loss.w_velocity": loss_cfg.w_velocity,
        "loss.w_microtiming": loss_cfg.w_microtiming,
        "loss.w_hihat": loss_cfg.w_hihat,
        "loss.focal_gamma": loss_cfg.focal_gamma,
        "loss.fp_to_fn_ratio": loss_cfg.fp_to_fn_ratio,
        "device": str(device),
        "n_parameters": n_params,
        "wall_time_s": f"{wall:.1f}",
        "n_train_samples": len(train_samples),
        "n_val_samples": len(val_samples),
    }

    import datetime as _dt
    today = _dt.date.today().isoformat()
    ctx = build_default_context(
        run_id=args.run_id,
        run_date=today,
        title=f"Mini-L3 cross-kit (train 3 kit → val ShittyKit) · {today}",
        history=history,
        n_parameters=n_params,
        hyperparameters=hp,
        train_evals=train_evals,
        holdout_evals=val_evals,
        gate_f_threshold=GATE_F_MEAN_VAL,
        gate_shuffle_max=0.10,
        gate_timing_mae_max=5.0,
        gate_hihat_max=0.15,
        tier=2,
        extra_tldr_rows=extra_tldr,
        extra_gate_verdict_rows=gate_rows,
        tldr_note=(
            "Mini-L3 cross-kit — train su 3 kit DrumGizmo (DRSKit + Muldjord "
            "+ Crocell), holdout su ShittyKit (mai visto). "
            "Risponde alla domanda: la rete impara l'evento fisico o il timbro? "
            "Gate F_mean ≥ 0.55 (sotto L4 = 0.80, sopra il regression test "
            "che era self-overfit)."
        ),
    )

    html_reports = write_training_report(
        ctx, args.reports_root / f"{today}-{args.run_id}",
    )
    html_gate = write_training_report(
        ctx, args.gate_root / args.run_id,
    )
    print(f"[mini-L3] HTML report (reports/) → {html_reports}")
    print(f"[mini-L3] HTML report (gate/)    → {html_gate}")
    return 0 if pass_gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
