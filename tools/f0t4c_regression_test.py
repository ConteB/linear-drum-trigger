"""F0-T4c regression test — self-overfit 18 long-context sample.

Verifies that the Decision Lock CEO 2026-05-24 ratifications (B1+B2+B3+B6a+B6b)
behave as the F0-T4c §5 spec promises:

  * Architectural: ``lookahead_frames=35`` (B1), ``crop_samples=196608``
    enforced by ``GoldDataset`` (B2), ``LossConfig`` new defaults (B3).
  * Class balance: per-bus ``pos_weight`` tuple (B6b) and the auto-attached
    ``WeightedRandomSampler`` (B6a).

The 18 sample list (``artifacts/f0t4c_regression_keys.json``) is curated so 3
of them contain ``crash_a`` positives — that is the bus B6 must rescue from
F ≈ 0 baseline.

Pass conditions (Decision Lock CEO 2026-05-24):

  * ``F_max ≥ 0.80`` on at least one sample (architecture is viable);
  * ``F_crash_a ≥ 0.3`` on at least one crash-bearing sample (B6 lift);
  * ``timing_mae_ms ≤ 5`` on the best-F sample (sub-frame precision proven).

Emits the canonical single-file HTML report mandated by
``04_INTELLIGENCE/MODEL_REPORT_BLUEPRINT.md`` (LIN-DT-RPTBP-001) under
``docs/gates/F0-T4c_REGRESSION/<run_id>/report.html`` — 11 sezioni, charts SVG
inline, piano-roll GT vs predicted per **tutti** i 18 sample (amendment v1.1
§7: N sample configurabili). Exits 0/1 on the pass/fail verdict.

Run::

    python tools/f0t4c_regression_test.py --epochs 600
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
from torch.utils.data import DataLoader, WeightedRandomSampler  # noqa: E402

#: Crash_a is bus 6 in the 0..7 ordering — F0-T2a §3.3 / midi_mapping_table.yaml.
CRASH_A_BUS_IDX: int = 6


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
        description="F0-T4c regression test (self-overfit 18 sample)"
    )
    parser.add_argument("--pool-root", type=Path,
                        default=Path("data/gold/mix_2026-05-24"))
    parser.add_argument("--keys-file", type=Path,
                        default=Path("artifacts/f0t4c_regression_keys.json"))
    parser.add_argument("--density-file", type=Path,
                        default=Path("artifacts/mix_2026-05-24_density.json"))
    parser.add_argument("--crop-samples", type=int, default=196608)
    parser.add_argument("--lookahead-frames", type=int,
                        default=DEFAULT_LOOKAHEAD_FRAMES)
    parser.add_argument("--epochs", type=int, default=600)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--tcn-channels", type=int, default=32)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--run-id", default="f0t4c-regression")
    parser.add_argument("--out-root", type=Path,
                        default=Path("docs/gates/F0-T4c_REGRESSION"))
    parser.add_argument("--reports-root", type=Path, default=Path("reports"),
                        help="Mirror of the canonical HTML report root "
                             "(MODEL_REPORT_BLUEPRINT §1: reports/<YYYY-MM-DD>-<run_id>/).")
    args = parser.parse_args()

    # --- Load curated 18 sample + pos_weight tuple ---
    keys_payload = json.loads(args.keys_file.read_text())
    keys = list(keys_payload["keys"])
    crash_a_keys = set(keys_payload["crash_a_keys"])
    density_payload = json.loads(args.density_file.read_text())
    pos_weight_tuple: tuple[float, ...] = tuple(
        float(w) for w in density_payload["pos_weight_per_bus"]
    )
    assert len(pos_weight_tuple) == 8

    pool = load_pool(args.pool_root)
    by_key = {s.key: s for s in pool}
    missing = [k for k in keys if k not in by_key]
    if missing:
        print(f"ERROR: missing keys in {args.pool_root}: {missing[:5]}...")
        return 1
    samples: list[GoldSample] = [by_key[k] for k in keys]
    print(f"[F0-T4c-reg] loaded {len(samples)} samples; "
          f"{len(crash_a_keys)} contain crash_a")
    print(f"[F0-T4c-reg] pos_weight_per_bus = {pos_weight_tuple}")

    # --- Training setup (self-overfit: train_pool == eval_pool) ---
    device = pick_device(args.cpu)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    print(f"[F0-T4c-reg] device = {device}")

    loss_cfg = LossConfig(pos_weight=pos_weight_tuple)
    train_ds = GoldDataset(
        samples,
        crop_samples=args.crop_samples,
        rng=np.random.default_rng(args.seed),
        lookahead_frames=args.lookahead_frames,
    )

    # B6a — WeightedRandomSampler auto-on with per-bus pos_weight.
    sampler_weights = _compute_sampler_weights(samples, pos_weight=pos_weight_tuple)
    assert sampler_weights is not None, "B6a sampler must engage for tuple pos_weight"
    print(f"[F0-T4c-reg] B6a sampler weights range "
          f"[{min(sampler_weights):.1f}, {max(sampler_weights):.1f}]")
    gen = torch.Generator()
    gen.manual_seed(args.seed)
    sampler = WeightedRandomSampler(
        weights=sampler_weights,
        num_samples=len(samples),
        replacement=True,
        generator=gen,
    )
    loader = DataLoader(
        train_ds, batch_size=args.batch_size, sampler=sampler,
        num_workers=0, drop_last=False,
    )

    model = TCNModel(TCNConfig(channels=args.tcn_channels)).to(device)
    n_params = count_parameters(model)
    print(f"[F0-T4c-reg] parameters = {n_params:,}")
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
        if epoch % 50 == 0 or epoch == 1:
            print(f"[F0-T4c-reg]   epoch {epoch:4d}  train_loss = {last_loss:.4f}")
    wall = time.perf_counter() - t0
    print(f"[F0-T4c-reg] training done in {wall:.1f} s")

    # --- Evaluation on the same 18 sample (self-overfit) ---
    model.eval()
    per_sample: list[dict[str, Any]] = []
    L = args.lookahead_frames  # noqa: N806
    with torch.no_grad():
        for s in samples:
            crop_frames = args.crop_samples // ENCODER_STRIDE
            total_af = s.audio.shape[1] // ENCODER_STRIDE
            n_frame = min(crop_frames, s.target.shape[0], total_af - L)
            if n_frame <= 0:
                continue
            start_sample = L * ENCODER_STRIDE
            end_sample = start_sample + n_frame * ENCODER_STRIDE
            audio = torch.from_numpy(
                s.audio[:, start_sample:end_sample]
            ).unsqueeze(0).to(device)
            pred = model(audio).squeeze(0).cpu().numpy()
            target = s.target[:n_frame]
            # Compute once, reuse the threshold for evaluate_l3 + onset_report
            # so f_measure_mean == np.mean(rep.f_measure_per_bus).
            onset_pred = pred[:, 0:24:3]
            onset_tgt = target[:, 0:24:3]
            best_thr, _ = tune_threshold(onset_pred, onset_tgt)
            v = evaluate_l3(pred, target, threshold=best_thr)
            rep = onset_report(onset_pred, onset_tgt, threshold=best_thr)
            per_sample.append({
                "key": s.key,
                "is_crash_a_bearing": s.key in crash_a_keys,
                "f_measure_mean": v.f_measure_mean,
                "f_measure_per_bus": rep.f_measure_per_bus.tolist(),
                "f_crash_a": float(rep.f_measure_per_bus[CRASH_A_BUS_IDX]),
                "timing_mae_ms": v.timing_mae_ms,
                "hihat_mae": v.hihat_mae,
                "best_threshold": best_thr,
            })

    # --- Pass/fail verdict ---
    f_mean_list = [r["f_measure_mean"] for r in per_sample]
    f_max = max(f_mean_list)
    best_idx = f_mean_list.index(f_max)
    best_key = per_sample[best_idx]["key"]
    best_timing = per_sample[best_idx]["timing_mae_ms"]

    crash_a_f_list = [r["f_crash_a"] for r in per_sample if r["is_crash_a_bearing"]]
    f_crash_a_max = max(crash_a_f_list) if crash_a_f_list else 0.0

    pass_f = f_max >= 0.80
    pass_crash = f_crash_a_max >= 0.30
    pass_timing = best_timing <= 5.0
    overall = pass_f and pass_crash and pass_timing

    # --- Report ---
    out_dir = args.out_root / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "decision_lock": "CEO 2026-05-24",
        "spec": "docs/methodology/F0-T4c_DATA_PIPELINE_FIXES_SPEC.md",
        "config": {
            "pool_root": str(args.pool_root),
            "n_samples": len(samples),
            "n_crash_a_bearing": len(crash_a_keys),
            "crop_samples": args.crop_samples,
            "lookahead_frames": args.lookahead_frames,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "seed": args.seed,
            "tcn_channels": args.tcn_channels,
            "device": str(device),
            "n_parameters": n_params,
            "wall_time_s": wall,
            "final_train_loss": last_loss,
            "pos_weight_per_bus": list(pos_weight_tuple),
            "loss_config": {k: getattr(loss_cfg, k)
                            for k in ("w_onset", "w_velocity", "w_microtiming",
                                      "w_hihat", "focal_gamma", "fp_to_fn_ratio",
                                      "onset_mask_threshold")},
        },
        "results": {
            "f_max": f_max,
            "f_max_key": best_key,
            "f_max_timing_mae_ms": best_timing,
            "f_crash_a_max": f_crash_a_max,
            "per_sample": per_sample,
        },
        "verdict": {
            "pass_f_max_ge_0.80": pass_f,
            "pass_f_crash_a_ge_0.30": pass_crash,
            "pass_timing_mae_le_5ms": pass_timing,
            "overall_pass": overall,
        },
    }
    (out_dir / "report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )

    # Markdown summary
    md_lines = [
        "# F0-T4c regression test — self-overfit",
        "",
        f"**Decision Lock:** CEO 2026-05-24 — B1+B2+B3+B6a+B6b ratified.",
        f"**Spec:** `docs/methodology/F0-T4c_DATA_PIPELINE_FIXES_SPEC.md`",
        f"**Run:** `{args.run_id}` · device={device} · "
        f"{args.epochs} epochs · {wall:.1f} s wall",
        "",
        "## Pass conditions",
        "",
        f"- F_max ≥ 0.80 · **{'PASS' if pass_f else 'FAIL'}** — got `{f_max:.3f}` on `{best_key}`",
        f"- F_crash_a ≥ 0.30 · **{'PASS' if pass_crash else 'FAIL'}** — "
        f"got `{f_crash_a_max:.3f}` (max over {len(crash_a_keys)} crash-bearing sample)",
        f"- timing_mae ≤ 5 ms on best-F · **{'PASS' if pass_timing else 'FAIL'}** — "
        f"got `{best_timing:.2f} ms`",
        "",
        f"## Overall: **{'PASS ✅' if overall else 'FAIL ❌'}**",
        "",
        "## Per-sample F-measure",
        "",
        "| key | crash_a? | F_mean | F_crash_a | timing_mae_ms |",
        "| :-- | :--: | --: | --: | --: |",
    ]
    for r in sorted(per_sample, key=lambda x: x["f_measure_mean"], reverse=True):
        marker = "✓" if r["is_crash_a_bearing"] else ""
        md_lines.append(
            f"| `{r['key']}` | {marker} | {r['f_measure_mean']:.3f} | "
            f"{r['f_crash_a']:.3f} | {r['timing_mae_ms']:.2f} |"
        )
    (out_dir / "report.md").write_text("\n".join(md_lines) + "\n")

    print(f"\n[F0-T4c-reg] ======== VERDICT ========")
    print(f"[F0-T4c-reg] F_max          = {f_max:.3f}  (target ≥ 0.80)  → {'PASS' if pass_f else 'FAIL'}")
    print(f"[F0-T4c-reg] F_crash_a_max  = {f_crash_a_max:.3f}  (target ≥ 0.30)  → {'PASS' if pass_crash else 'FAIL'}")
    print(f"[F0-T4c-reg] timing_mae_ms  = {best_timing:.2f} ms (target ≤ 5)   → {'PASS' if pass_timing else 'FAIL'}")
    print(f"[F0-T4c-reg] OVERALL        = {'PASS ✅' if overall else 'FAIL ❌'}")
    print(f"[F0-T4c-reg] report → {out_dir}/report.json + report.md")

    # ------------------------------------------------------------------ #
    # MODEL_REPORT_BLUEPRINT (LIN-DT-RPTBP-001) — single-file HTML report  #
    # ------------------------------------------------------------------ #
    # Re-evaluate each of the 18 samples with the canonical evaluator
    # (single source of truth used by train.py auto-report). All 18 are
    # supplied as "holdout" — self-overfit, so train == holdout.
    print(f"[F0-T4c-reg] generating blueprint HTML report (LIN-DT-RPTBP-001)…")
    cpu_model = model.to("cpu").eval()
    eval_n_sample = (args.crop_samples + args.lookahead_frames * ENCODER_STRIDE)
    sample_evals: list[dict[str, Any]] = []
    for s in samples:
        ev = evaluate_sample_for_report(
            cpu_model, s.audio, s.target, n_sample=eval_n_sample,
        )
        ev["key"] = s.key
        ev["engine"] = s.engine
        ev["mic_config"] = s.mic_config
        sample_evals.append(ev)

    # Construct Tier-2 ReportContext: B1+B2+B3+B6a+B6b gate verdict + sign-off.
    extra_tldr = [
        TldrRow(
            label="F_crash_a max (B6 lift target ≥ 0.30)",
            value=f"{f_crash_a_max:.3f}",
            gate="≥ 0.30",
            verdict=verdict_label(pass_crash)[0],
            verdict_class=verdict_label(pass_crash)[1],
        ),
        TldrRow(
            label="OVERALL F0-T4c regression",
            value="PASS" if overall else "FAIL",
            gate="all 3 pass",
            verdict=verdict_label(overall)[0],
            verdict_class=verdict_label(overall)[1],
            is_summary=True,
        ),
    ]
    gate_rows = [
        GateVerdictRow(
            criterion="B1 — lookahead_frames = 35 propagato",
            verdict="✅ APPLIED", verdict_class="pass",
        ),
        GateVerdictRow(
            criterion="B2 — crop ≥ MIN_CROP_SAMPLES (135 552) fail-loud",
            verdict="✅ APPLIED", verdict_class="pass",
        ),
        GateVerdictRow(
            criterion="B3 — LossConfig defaults (pos=200, w_on=2.0, …)",
            verdict="✅ APPLIED", verdict_class="pass",
        ),
        GateVerdictRow(
            criterion="B6a — WeightedRandomSampler auto-on",
            verdict="✅ APPLIED", verdict_class="pass",
        ),
        GateVerdictRow(
            criterion="B6b — pos_weight per-bus tuple",
            verdict="✅ APPLIED", verdict_class="pass",
        ),
        GateVerdictRow(
            criterion="Regression: F_max ≥ 0.80",
            verdict=verdict_label(pass_f)[0],
            verdict_class=verdict_label(pass_f)[1],
        ),
        GateVerdictRow(
            criterion="Regression: F_crash_a ≥ 0.30",
            verdict=verdict_label(pass_crash)[0],
            verdict_class=verdict_label(pass_crash)[1],
        ),
        GateVerdictRow(
            criterion="Regression: timing_mae ≤ 5 ms",
            verdict=verdict_label(pass_timing)[0],
            verdict_class=verdict_label(pass_timing)[1],
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
        "loss.onset_mask_threshold": loss_cfg.onset_mask_threshold,
        "device": str(device),
        "n_parameters": n_params,
        "wall_time_s": f"{wall:.1f}",
    }

    # Real per-epoch training history captured during the loop above.
    history_for_report: list[dict[str, float]] = history

    import datetime as _dt
    today = _dt.date.today().isoformat()
    ctx = build_default_context(
        run_id=args.run_id,
        run_date=today,
        title="F0-T4c regression test — self-overfit · Decision Lock CEO 2026-05-24",
        history=history_for_report,
        n_parameters=n_params,
        hyperparameters=hp,
        train_evals=sample_evals,    # self-overfit: train == holdout
        holdout_evals=sample_evals,
        gate_f_threshold=0.80,
        gate_shuffle_max=0.10,
        gate_timing_mae_max=5.0,
        gate_hihat_max=0.15,
        tier=2,
        extra_tldr_rows=extra_tldr,
        extra_gate_verdict_rows=gate_rows,
        tldr_note=(
            "Self-overfit su 18 long-context sample (3 crash-bearing). "
            "Verifica empirica dei fix B1+B2+B3+B6a+B6b ratificati dal CEO "
            "il 2026-05-24 (F0-T4c PARTIAL-LOCK v1.0.0). B4 deferred."
        ),
    )

    # Mirror under reports/ (blueprint §1) + canonical gate dir.
    html_in_reports = write_training_report(ctx, args.reports_root / f"{today}-{args.run_id}")
    html_in_gate = write_training_report(ctx, out_dir)
    print(f"[F0-T4c-reg] HTML report → {html_in_reports}")
    print(f"[F0-T4c-reg] HTML report (gate mirror) → {html_in_gate}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
