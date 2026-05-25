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
from neural.preprocessing import PreprocessingFrontend  # noqa: E402
from data_engineering.audio_augment import (  # noqa: E402
    apply_audio_augmentation, AudioAugmentError,
)
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
    # F0-T4d (Decision Lock CEO 2026-05-25) — preprocessing harness + efficiency.
    parser.add_argument("--preprocessing", choices=("none", "p1", "p1p2"),
                        default="none",
                        help="Front-end preprocessing (F0-T4d): none (default, "
                             "audio raw); p1 (pre-emphasis + per-channel z-score, "
                             "8 chan); p1p2 (P1 + onset envelope, 9 chan).")
    parser.add_argument("--use-cosine-lr", action="store_true",
                        help="F0-T4d B6 E3 — cosine LR schedule with warmup.")
    parser.add_argument("--early-stop-patience", type=int, default=0,
                        help="F0-T4d B6 E4 — early stop after N epochs without "
                             "loss improvement (0 = disabled).")
    # F0-T16-post (Decision Lock CEO 2026-05-25) — audio augmentation on-the-fly.
    parser.add_argument("--audio-aug", action="store_true",
                        help="F0-T16-post — apply audio augmentation pipeline "
                             "(pink noise + gain + mic balance + channel mask) "
                             "on every training batch. Per-sample seed derived "
                             "from sha256(master_seed|key|epoch).")
    parser.add_argument("--audio-aug-master-seed", type=int, default=20260525,
                        help="Master seed for the audio augmentation pipeline.")
    # 2026-05-25 (post-listening-test): concorrente loss design experiment.
    # Preset choices fissano un design di loss distinto a parità di pool, arch
    # e training schedule. Il "ctrl" è il status-quo (AFL + per-bus pos_weight
    # density-based + γ=2, fp_ratio=3). A/B/C/D sono i 4 candidati ratificati
    # dal CEO 2026-05-25.
    parser.add_argument("--loss-preset", default="ctrl",
                        choices=("ctrl", "A", "B", "C", "D", "E", "F", "G"),
                        help="ctrl = status quo (AFL + per-bus + γ=2 + fp=3); "
                             "A = cap pos_weight 50 (fix minimal); "
                             "B = per-bus + fp_ratio=30 (compensa asimmetria); "
                             "C = γ=4 + cap 50 (focal aggressivo); "
                             "D = Tversky α=0.7 β=0.3 (paradigma alternativo); "
                             "E = A+B combinato (cap 50 + fp_ratio=30, γ=2); "
                             "F = Tversky con warmup AFL (CTRL per N epoch, "
                             "poi switch a Tversky); "
                             "G = smart-cap (50 bus comuni, 150 bus rari) + "
                             "fp_ratio=30, γ=2.")
    parser.add_argument("--loss-warmup-epochs", type=int, default=30,
                        help="For preset F: number of epochs to train with "
                             "AFL (CTRL config) before switching to Tversky.")
    parser.add_argument("--loss-edge-skip-frames", type=int, default=0,
                        help="Skip the first N frames from the loss "
                             "calculation (Decision Lock CEO 2026-05-25). "
                             "Use 1024 (= TCN F0-T4a RF size) to mask the "
                             "zone where the causal convolution sees zero-pad. "
                             "Default 0 = backcompat with previous training.")
    # F0-T16-post bugfix 2026-05-25 (post-abandon): clip e skip non-finite
    # parametrizzati, dopo che `clip_grad_norm=1.0` non bastava nel regime
    # audio_aug (Inf @ epoch 110, run mini-l3-crosskit-p1p2-audioaug).
    parser.add_argument("--grad-clip-max-norm", type=float, default=1.0,
                        help="Max norm for gradient clipping (default 1.0). "
                             "Reduce to 0.5 in the audio_aug regime where the "
                             "added variance pushed grads past the prev cap.")
    parser.add_argument("--skip-nonfinite-step", action="store_true",
                        help="Skip the optimizer step when loss or grad_norm "
                             "are NaN/Inf (zero-grad + log, no explosion). "
                             "Safety net for unstable regimes.")
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

    # Loss preset dispatch — Decision Lock CEO 2026-05-25 (post-listening-test).
    # The status-quo (ctrl) uses the density-derived per-bus pos_weight. The
    # competing candidates A..D vary along orthogonal axes to discriminate
    # *which* part of the loss design causes the predict-everywhere collapse.
    if args.loss_preset == "ctrl":
        loss_cfg = LossConfig(pos_weight=pos_weight_tuple)
    elif args.loss_preset == "A":
        # A — cap pos_weight a 50 per ogni bus (uniforme, asimmetria max 17×).
        capped = tuple(min(float(w), 50.0) for w in pos_weight_tuple)
        loss_cfg = LossConfig(pos_weight=capped)
    elif args.loss_preset == "B":
        # B — mantiene density-based pos_weight, alza fp_to_fn_ratio a 30.
        loss_cfg = LossConfig(
            pos_weight=pos_weight_tuple, fp_to_fn_ratio=30.0,
        )
    elif args.loss_preset == "C":
        # C — focal γ=4 + cap pos_weight=50.
        capped = tuple(min(float(w), 50.0) for w in pos_weight_tuple)
        loss_cfg = LossConfig(pos_weight=capped, focal_gamma=4.0)
    elif args.loss_preset == "D":
        # D — paradigma Tversky α=0.7 β=0.3. pos_weight resta (per backcompat
        # del LossConfig schema) ma non viene usato dal forward su kind=tversky.
        loss_cfg = LossConfig(
            pos_weight=pos_weight_tuple, kind="tversky",
            tversky_alpha=0.7, tversky_beta=0.3,
        )
    elif args.loss_preset == "E":
        # E — cap pos_weight 50 (da A) + fp_to_fn_ratio=30 (da B) + γ=2.
        # Ipotesi: i due fix sono ortogonali, la combinazione calibra TUTTI
        # i bus (rari + comuni). Vedi `LOSS_COMPETITION_2026-05-25.md` §
        # "Hypothesis: A+B combinato".
        capped = tuple(min(float(w), 50.0) for w in pos_weight_tuple)
        loss_cfg = LossConfig(
            pos_weight=capped, fp_to_fn_ratio=30.0,
        )
    elif args.loss_preset == "F":
        # F — Tversky con warmup AFL (CTRL config). Train loop selects which
        # of two TCNLoss instances to use based on epoch number. The warmup
        # config is the CTRL (status quo) — it gives the network non-zero
        # confidence on the true positives before Tversky takes over (the
        # smooth=1.0 term then no longer dominates the gradient).
        loss_cfg = LossConfig(
            pos_weight=pos_weight_tuple, kind="tversky",
            tversky_alpha=0.7, tversky_beta=0.3,
        )
    elif args.loss_preset == "G":
        # G — smart-cap differenziato (post-E findings). E ha avuto
        # `crash zero-detect` (pos_weight 50 troppo basso per crash con
        # density 0.7-1.5 %). G ripristina pos_weight più alto sui bus rari
        # (ride/crash_a/crash_b, indici 5-7) mantenendo 50 sui bus comuni
        # (0-4 = kick/snare/hihat/tom/floor). Cap 150 = punto medio tra
        # CTRL (1000) e E (50). fp_ratio resta 30 come E/B.
        rare_indices = {5, 6, 7}  # ride, crash_a, crash_b_misc
        capped = tuple(
            min(float(w), 150.0) if i in rare_indices else min(float(w), 50.0)
            for i, w in enumerate(pos_weight_tuple)
        )
        loss_cfg = LossConfig(pos_weight=capped, fp_to_fn_ratio=30.0)
    else:
        raise ValueError(args.loss_preset)
    # Propagate edge skip override to the loss config (LossConfig is frozen,
    # so rebuild it preserving the preset's other fields).
    if args.loss_edge_skip_frames > 0:
        from dataclasses import replace  # noqa: PLC0415
        loss_cfg = replace(loss_cfg, edge_skip_frames=args.loss_edge_skip_frames)
    print(f"[mini-L3] loss_preset = {args.loss_preset}  kind = {loss_cfg.kind}",
          flush=True)
    if loss_cfg.kind == "afl":
        print(f"[mini-L3]   pos_weight = {loss_cfg.pos_weight}  "
              f"γ = {loss_cfg.focal_gamma}  fp_ratio = {loss_cfg.fp_to_fn_ratio}",
              flush=True)
    else:
        print(f"[mini-L3]   tversky α = {loss_cfg.tversky_alpha}  "
              f"β = {loss_cfg.tversky_beta}", flush=True)
    print(f"[mini-L3]   edge_skip_frames = {loss_cfg.edge_skip_frames}",
          flush=True)
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

    # F0-T4d preprocessing harness.
    if args.preprocessing == "none":
        preprocess = None
        in_channels = 8
    elif args.preprocessing == "p1":
        preprocess = PreprocessingFrontend(n_mic=8, onset_envelope=False).to(device)
        in_channels = 8
    elif args.preprocessing == "p1p2":
        preprocess = PreprocessingFrontend(n_mic=8, onset_envelope=True).to(device)
        in_channels = 9
    else:
        raise ValueError(args.preprocessing)
    print(f"[mini-L3] preprocessing = {args.preprocessing} → in_channels = {in_channels}",
          flush=True)

    model = TCNModel(TCNConfig(channels=args.tcn_channels, in_channels=in_channels)).to(device)
    n_params = count_parameters(model)
    if preprocess is not None:
        n_params_pre = count_parameters(preprocess)
        print(f"[mini-L3] preprocessing params = {n_params_pre}", flush=True)
    print(f"[mini-L3] model parameters = {n_params:,}")
    loss_fn = TCNLoss(loss_cfg).to(device)
    # F-preset warmup: instantiate a second loss (CTRL AFL config) used for
    # the first `loss_warmup_epochs` epochs. The training loop dispatches to
    # this loss until the warmup window closes, then switches to the target
    # loss (Tversky). The warmup gives the network non-zero confidence on
    # true positives before Tversky takes over.
    loss_fn_warmup: TCNLoss | None = None
    if args.loss_preset == "F" and args.loss_warmup_epochs > 0:
        warmup_cfg = LossConfig(pos_weight=pos_weight_tuple)  # CTRL AFL
        loss_fn_warmup = TCNLoss(warmup_cfg).to(device)
        print(f"[mini-L3]   F warmup: AFL (CTRL) for first "
              f"{args.loss_warmup_epochs} epochs, then Tversky.",
              flush=True)
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    # F0-T4d B6 E3 — cosine LR schedule with warmup (10% of training).
    if args.use_cosine_lr:
        warmup_epochs = max(1, args.epochs // 10)
        from torch.optim.lr_scheduler import LambdaLR  # noqa: PLC0415
        def _lr_lambda(epoch: int) -> float:
            if epoch < warmup_epochs:
                return (epoch + 1) / warmup_epochs
            progress = (epoch - warmup_epochs) / max(1, args.epochs - warmup_epochs)
            return 0.5 * (1.0 + math.cos(math.pi * progress))
        scheduler = LambdaLR(optim, lr_lambda=_lr_lambda)
        print(f"[mini-L3] cosine LR + warmup ({warmup_epochs} epoch)", flush=True)
    else:
        scheduler = None

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
    # F0-T4d B6 E4 — early stop tracking.
    best_loss = float("inf")
    epochs_without_improvement = 0
    early_stopped_at = None
    # F0-T16-post bugfix 2026-05-25: diagnostic counters for non-finite events.
    n_nonfinite_loss = 0
    n_nonfinite_grad = 0
    epoch_grad_norm_max = 0.0
    print(f"[mini-L3] grad_clip_max_norm = {args.grad_clip_max_norm}  "
          f"skip_nonfinite = {args.skip_nonfinite_step}", flush=True)
    for epoch in range(1, args.epochs + 1):
        model.train()
        if preprocess is not None:
            preprocess.train()
        # F-preset warmup: pick loss_fn based on epoch.
        if loss_fn_warmup is not None and epoch <= args.loss_warmup_epochs:
            active_loss = loss_fn_warmup
            if epoch == 1:
                print("[mini-L3]   F-warmup phase ACTIVE (AFL CTRL)", flush=True)
        else:
            active_loss = loss_fn
            if (loss_fn_warmup is not None
                    and epoch == args.loss_warmup_epochs + 1):
                print(f"[mini-L3]   F-warmup phase ENDED at epoch {epoch} "
                      f"— switching to Tversky", flush=True)
        epoch_total = 0.0
        n_steps = 0
        epoch_grad_norm_max = 0.0
        for batch in loader:
            audio = batch["audio"].to(device, non_blocking=True)
            target = batch["target"].to(device, non_blocking=True)
            # F0-T16-post (Decision Lock CEO 2026-05-25) — audio augmentation
            # on-the-fly PRIMA del preprocessing P1+P2 (per simulare audio
            # reale che entra nel plugin).
            if args.audio_aug:
                # Per-sample augmentation: build a key per batch position +
                # epoch index to ensure determinism + diversity.
                audio_np = audio.detach().cpu().float().numpy()
                augmented = np.empty_like(audio_np)
                for i in range(audio_np.shape[0]):
                    try:
                        augmented[i] = apply_audio_augmentation(
                            audio_np[i],
                            sample_key=f"batch_{epoch}_pos_{i}",
                            variant_idx=1,                      # always variant 1 (always augment)
                            master_seed=args.audio_aug_master_seed,
                            enable_channel_mask=True,
                            channel_mask_prob=0.20,
                        )
                    except AudioAugmentError:
                        # R2/R3 violation — fallback to non-augmented sample.
                        augmented[i] = audio_np[i]
                audio = torch.from_numpy(augmented).to(device)
            optim.zero_grad(set_to_none=True)
            # F0-T4d B1+B2 bugfix 2026-05-25 (post-NaN diagnosis): preprocessing
            # runs OUTSIDE autocast in fp32. STFT in fp16/MPS, divisions in
            # ChannelNorm with small variance, and OnsetEnvelope normalization
            # all explode in mixed-precision. Keep them fp32; only the TCN
            # itself goes through autocast.
            if preprocess is not None:
                audio = preprocess(audio.float())
            with autocast_ctx:
                pred = model(audio)
                losses = active_loss(pred, target)
            loss_val = losses["total"]
            # F0-T16-post bugfix 2026-05-25: skip step when loss is non-finite.
            # The audio_aug regime occasionally produced Inf loss at epoch 110
            # (run mini-l3-crosskit-p1p2-audioaug-2026-05-25); fp16 autocast +
            # the added variance from the channel-mask + gain perturbation
            # can spike loss beyond range. Skip = zero_grad + log + continue.
            if args.skip_nonfinite_step and not torch.isfinite(loss_val):
                n_nonfinite_loss += 1
                optim.zero_grad(set_to_none=True)
                continue
            loss_val.backward()
            # F0-T4d B6 bugfix 2026-05-25: gradient clipping per evitare
            # gradient explosion (osservata epoch 70: loss 0.93 → inf con
            # autocast fp16 + cosine LR). Max norm parametrizzato — 0.5
            # raccomandato nel regime audio_aug (F0-T16-post handoff).
            grad_norm = torch.nn.utils.clip_grad_norm_(
                model.parameters(), max_norm=args.grad_clip_max_norm,
            )
            grad_norm_val = float(grad_norm)
            if args.skip_nonfinite_step and not math.isfinite(grad_norm_val):
                # Non-finite grad even after clipping (sentinel returned by
                # clip_grad_norm_ when any param has NaN/Inf). Skip step.
                n_nonfinite_grad += 1
                optim.zero_grad(set_to_none=True)
                continue
            epoch_grad_norm_max = max(epoch_grad_norm_max, grad_norm_val)
            optim.step()
            epoch_total += float(loss_val.detach())
            n_steps += 1
        if scheduler is not None:
            scheduler.step()
        last_loss = epoch_total / max(n_steps, 1)
        history.append({
            "epoch": float(epoch),
            "train_loss": last_loss,
            "grad_norm_max": epoch_grad_norm_max,
        })
        if epoch % 10 == 0 or epoch == 1:
            lr_now = optim.param_groups[0]["lr"]
            extra = ""
            if n_nonfinite_loss or n_nonfinite_grad:
                extra = (f"  skip(loss={n_nonfinite_loss}, "
                         f"grad={n_nonfinite_grad})")
            print(f"[mini-L3] epoch {epoch:4d}  train_loss = {last_loss:.4f}  "
                  f"lr = {lr_now:.2e}  grad_max = {epoch_grad_norm_max:.2f}{extra}")
        # F0-T4d B6 E4 — early stop.
        if args.early_stop_patience > 0:
            if last_loss < best_loss - 1e-4:
                best_loss = last_loss
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1
                if epochs_without_improvement >= args.early_stop_patience:
                    early_stopped_at = epoch
                    print(f"[mini-L3] EARLY STOP at epoch {epoch} "
                          f"(no improvement for {args.early_stop_patience} epochs)")
                    break
    wall = time.perf_counter() - t0
    print(f"[mini-L3] training done in {wall:.1f} s "
          f"(epochs run: {len(history)}, early_stopped={early_stopped_at})")
    if n_nonfinite_loss or n_nonfinite_grad:
        print(f"[mini-L3] non-finite skips: loss={n_nonfinite_loss}, "
              f"grad={n_nonfinite_grad}")

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
    cpu_preprocess = preprocess.to("cpu").eval() if preprocess is not None else None

    # If preprocessing is active, wrap the model so evaluate_sample_for_report
    # sees the pre-processed input. We compose a simple nn.Sequential-like
    # callable that does preprocess → model in one forward.
    class _ComposedModel(torch.nn.Module):
        def __init__(self, pre: torch.nn.Module | None, mdl: torch.nn.Module) -> None:
            super().__init__()
            self.pre = pre
            self.mdl = mdl
            # evaluate_sample_for_report checks .config.channels; forward it.
            self.config = mdl.config
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            if self.pre is not None:
                x = self.pre(x)
            return self.mdl(x)
    eval_model = _ComposedModel(cpu_preprocess, cpu_model)
    eval_model.eval()

    val_evals: list[dict[str, Any]] = []
    for s in val_samples:
        ev = evaluate_sample_for_report(
            eval_model, s.audio, s.target,
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
            eval_model, s.audio, s.target,
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
        "grad_clip_max_norm": args.grad_clip_max_norm,
        "skip_nonfinite_step": args.skip_nonfinite_step,
        "n_nonfinite_loss_skips": n_nonfinite_loss,
        "n_nonfinite_grad_skips": n_nonfinite_grad,
        "audio_aug": args.audio_aug,
        "preprocessing": args.preprocessing,
        "loss_preset": args.loss_preset,
        "loss_kind": loss_cfg.kind,
        "loss_focal_gamma": loss_cfg.focal_gamma,
        "loss_fp_to_fn_ratio": loss_cfg.fp_to_fn_ratio,
        "loss_tversky_alpha": loss_cfg.tversky_alpha,
        "loss_tversky_beta": loss_cfg.tversky_beta,
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
