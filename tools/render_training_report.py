"""Render the L3 Tier-2 training report HTML for the F0-T4b run (retroactive).

Thin driver on top of :mod:`neural.reporter`: re-uses
:func:`build_default_context` for all the common machinery, then adds the
gate-relevant extras (round-trip TLDR row + Decision Lock § 10 + sign-off).

Future training runs auto-emit a Tier-1 report from ``train.py``; this driver
is the canonical example of how to promote a Tier-1 to a Tier-2 Ocular Proof.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

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
)
from neural.model import TCNConfig, TCNModel, count_parameters  # noqa: E402
from neural.reporter import (  # noqa: E402
    GateVerdictRow,
    TldrRow,
    build_default_context,
    evaluate_sample_for_report,
    verdict,
    write_training_report,
)

HOLDOUT_KEYS = (
    "GMD000-V0T0-DGZ-R0-L1-NONE",
    "GMD001-V0T0-SFZ-R0-L1-NONE",
)


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    ckpt_path = repo / "artifacts/f0t4b_tcn.pt"
    training_report = json.loads(
        (repo / "artifacts/f0t4b_report.json").read_text(encoding="utf-8")
    )
    round_trip = json.loads(
        (repo / "docs/gates/L3_OCULAR_PROOF/round_trip_report.json").read_text(encoding="utf-8")
    )

    print("[render_report] loading checkpoint ...")
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    model = TCNModel(TCNConfig())
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    n_params = count_parameters(model)

    print("[render_report] running model on the 12 Gold samples ...")
    samples = load_pool(repo / "data/gold/L2_pool")
    train_evals: list[dict] = []
    holdout_evals: list[dict] = []
    for s in samples:
        ev = evaluate_sample_for_report(model, s.audio, s.target, n_sample=131072)
        ev["key"] = s.key
        ev["engine"] = s.engine
        ev["mic_config"] = s.mic_config
        (holdout_evals if s.key in HOLDOUT_KEYS else train_evals).append(ev)

    # Tier-2 extras: round-trip TL;DR row + final overall verdict (per CEO Decision Lock A).
    rt_pass = round_trip["round_trip_pass"]
    rt_value = f"{round_trip['cpp_max_abs_diff']:.2e}"
    rt_gate = f"&lt; {round_trip['tolerance']:.0e}"
    rt_verdict, rt_class = verdict(rt_pass)
    extra_tldr = [
        TldrRow(
            label="Round-trip max|Δ| PyTorch↔C++17",
            value=rt_value, gate=rt_gate,
            verdict=rt_verdict, verdict_class=rt_class,
        ),
        TldrRow(
            label="VERDETTO COMPLESSIVO (Decision Lock CEO opzione A)",
            value="", gate="",
            verdict=("✅ L3 SUPERATO (architettura, opzione A)" if rt_pass else "❌ L3 FAIL"),
            verdict_class=("pass" if rt_pass else "fail"),
            is_summary=True,
        ),
    ]

    # § 10 gate verdict rows.
    gate_rows = []
    for label, passes in [
        ("Round-trip RTNeural-equivalente max|Δ| < 1e-5", rt_pass),
        ("F-measure onset ≥ 0.80 sull'holdout (mini-batch, statisticamente irrilevante)", False),
        ("F-shuffle < 0.10 (controllo negativo)", True),
        ("DECISION LOCK CEO — opzione A ratificata 2026-05-23", True),
    ]:
        v, c = verdict(passes)
        gate_rows.append(GateVerdictRow(criterion=label, verdict=v, verdict_class=c))

    cfg = training_report["config"]
    hyperparams = {
        "epochs": cfg["epochs"],
        "crop_samples": cfg["crop_samples"],
        "batch_size": cfg["batch_size"],
        "lr": cfg["lr"],
        "seed": cfg["seed"],
        "device": cfg["device"],
        "channels (C)": 32,
        "encoder_strides": "[4, 4, 4, 2]",
        "trunk_dilations": "[1, 2, 4, 8, 16, 32, 64, 128]",
        "loss.focal_gamma": 2.0,
        "loss.fp_to_fn_ratio": 3.0,
        "loss.pos_weight": 50.0,
        "peak_pick.min_distance_frames": 3,
    }

    ctx = build_default_context(
        run_id="f0t4b-tcn-c32-seed0",
        run_date="2026-05-23",
        title="L3 — Mini-prototipo TCN (F0-T4b)",
        history=training_report["history"],
        n_parameters=n_params,
        hyperparameters=hyperparams,
        train_evals=train_evals,
        holdout_evals=holdout_evals,
        gate_f_threshold=L3_F_MEASURE_MIN,
        gate_shuffle_max=L3_SHUFFLED_F_MAX,
        gate_timing_mae_max=L3_TIMING_MAE_MAX_MS,
        gate_hihat_max=L3_HIHAT_MAE_MAX,
        frame_period_ms=FRAME_PERIOD_MS,
        frame_rate_hz=R_TARGET_HZ,
        tier=2,
        extra_tldr_rows=extra_tldr,
        extra_gate_verdict_rows=gate_rows,
        signoff_date="2026-05-23",
        signoff_signature="Decision Lock CEO — L3 superato (opzione A)",
        tldr_note=(
            "Soglie metriche di F0-T4a §7 valutate sopra; il CEO ha ratificato "
            "(Decision Lock 2026-05-23) che su mini-batch da 10 grooves la barra "
            "F ≥ 0.80 è statisticamente irrilevante. Il gate architetturale "
            "(round-trip) è quello che conta in F0; la barra metrica si misura "
            "al Gate L4 sull'Holdout reale E-GMD."
        ),
    )

    out_dir = repo / "reports/2026-05-23-f0t4b-tcn-c32"
    out = write_training_report(ctx, out_dir)
    print(f"[render_report] wrote {out}")
    print(f"[render_report] size = {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
