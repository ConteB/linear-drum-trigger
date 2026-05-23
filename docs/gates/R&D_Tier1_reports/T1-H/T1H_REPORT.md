---
title: "T1-H — Long-budget baseline (100 epoch)"
status: PROVISIONAL
type: report
metadata:
  doc_id: LIN-DT-RND-T1H-001
  authors: [OP-NEUROTRIGGER]
  date: 2026-05-24
tags: [R&D, T1-H, budget, convergence]
---

# T1-H — Long-budget baseline (100 epoch)

Fourth and final T1-E follow-up — answers the question opened by every
prior R&D Tier 1 report: *is the residual gap to the L3 floor a
budget problem or a structural one?*

Run: the T1-C winner (C=32 B=4) on the mix Gold dataset, identical
holdout split (seed=42, 50 samples), training extended from
20 → **100 epoch**.

## Results

| Variant | epochs | n_hold | onset_F | shuf_F | mae_ms | hh_mae | wall_min |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 20 | 50 | 0.0838 | 0.1025 | 11.21 | 0.1928 | 0.5 |
| joint | 20 | 100 | 0.0808 | 0.0981 | 11.25 | 0.1950 | 1.1 |
| **long-budget** | **100** | **50** | **0.0882** | **0.0886** | **9.16** | 0.2189 | 2.5 |

Δ long-budget vs baseline (same holdout, only epoch count differs):

- **onset_F: +5.3 %** (0.0838 → 0.0882)
- **shuffled_F: −13.6 %** (0.1025 → 0.0886) — better, less spurious
- **timing-MAE: −18.3 %** (11.21 → 9.16 ms) — substantially tighter
- **hihat_mae: +13.5 %** (0.193 → 0.219) — slightly worse, hint of overfit
- **Wall time: 5×** (0.5 → 2.5 min)

## Verdict

**The gap to the L3 floor (F ≥ 0.80) is structural, not budget.**
5× more epoch buys only +5.3 % on onset F-measure; the model has
clearly reached an asymptote on this dataset.

The other metrics improve more meaningfully:

- **Timing-MAE drops by 18 %** — more epoch sharpens the regression
  head substantially.
- **Shuffled-F drops by 14 %** — the model converges toward less
  spurious local patterns (the desired behaviour).
- **HiHat-MAE drifts up slightly** — early sign of overfitting on
  the continuous head.

## Interpretation

The 200-groove mix is **too small** to drive onset_F above 0.10
regardless of budget. Closing the gap to L3 requires:

1. **More data** — E-GMD post-F2-T1 will give us ~14 k human grooves,
   ~70× the current count. The baseline F-measure will rise
   substantially on volume alone, even without architectural changes.
2. **Audio-domain augmentation (F2-T2)** — Studio Mutilation, IR
   convolution, codec, hum — multiply the effective training data
   without re-rendering on Azure.
3. **Possibly a larger model** — T1-C showed C=64 Pareto-dominated
   at this dataset size, but on a 70× dataset the extra capacity
   could finally pay off (test in early F2-T3).

The L3 gate (F ≥ 0.80) is a **product-significance threshold** on the
E-GMD real holdout, not a constraint on R&D mini-batches. T1-D
(stability) + T1-C (Pareto) + T1-F (joint training) + T1-G (per-voice)
+ T1-H (budget) together give F2-T3 a fully-validated recipe:

- Architecture: **C=32, B=4** (F0-T4a default, confirmed)
- Training data: full Gold + joint augmented pool
- Budget: as much as the A100 credit allows (Tier 2/3 from MASTER_SCHEDULING §4)

## Reproducibility

```
PYTHONPATH=src .venv/bin/python tools/t1b_train_mix.py \
    --pool data/gold/mix_2026-05-24 \
    --epochs 100 --batch-size 4 --channels 32 --crop-samples 40960 \
    --seed 0 --run-id t1h-baseline-100ep
```

Wall time: 2.5 min on Mac M5 / MPS.
