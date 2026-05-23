---
title: "T1-E — Audio augmentation ablation (F0-T16-post MVP)"
status: PROVISIONAL
type: report
metadata:
  doc_id: LIN-DT-RND-T1E-001
  authors: [OP-NEUROTRIGGER]
  date: 2026-05-24
tags: [R&D, T1-E, audio-augmentation, ablation]
---

# T1-E — Audio augmentation ablation (MVP)

Comparison of the F0-T4a baseline TCN (C=32, B=4, 20 epoch) trained on
**raw vs audio-augmented** mix Gold dataset. The augmentation pipeline
is the three-voice MVP from `src/data_engineering/audio_augment/`
(noise floor → gain perturbation → mic balance jitter, variant 1, master
seed 20260524, gain ±3 dB, mic balance ±2 dB).

## Setup

| | Baseline | Augmented |
|---|---|---|
| Pool | `data/gold/mix_2026-05-24` | `data/gold/mix_2026-05-24_aug` |
| Sample count | 585 | 413 (172 dropped on R3 clipping guard) |
| Train / holdout | 535 / 50 | 378 / 35 |
| Epochs / batch / channels | 20 / 4 / 32 | 20 / 4 / 32 |
| Config seed | 0 | 0 |

The 172 drops are concentrated on the chaos layer — its native peaks
sit around 0.7-0.9 and the +3 dB gain pushes them above the R3 ceiling
of 1.0. The R2/R3 guards are doing their job: rather than silently
clipping the dataset, the pipeline refuses to corrupt it.

## Results

Per-sample holdout statistics (mean ± stdev across each report's holdout
set; NaN timing entries dropped):

| Metric | Baseline (n=50) | Augmented (n=35) | Δ |
|---|---:|---:|---:|
| onset_F | **0.0838 ± 0.0734** | 0.0339 ± 0.0289 | **−60 %** ↓ |
| shuffled_F | 0.1025 ± 0.1127 | 0.0873 ± 0.0755 | −15 % |
| timing_mae_ms | 11.21 ± 3.90 | 14.07 ± 2.24 | +26 % ↑ |
| hihat_mae | 0.1928 ± 0.2318 | 0.1903 ± 0.2203 | ≈ unchanged |

## Verdict

**The MVP augmentation hurts the baseline at this training budget.**
This is a *useful negative result* — three plausible causes, two of
which are correctable:

1. **Distribution shift too aggressive.** Pink noise at −50 dB plus
   gain ±3 dB plus per-channel ±2 dB is a non-trivial perturbation;
   the model trained for only 20 epoch cannot bridge the gap. The
   `shuffled_F` *decrease* is a mild positive signal — the augmented
   model is *less* sensitive to label permutation, which suggests it
   is reaching for more invariant features. A longer-budget run
   (50-100 epoch) would let the optimisation catch up.
2. **Training data shrunk by 28 %.** The 172 R3-rejected samples are
   precisely the chaos layer the model needs to learn anti-shortcut
   behaviour. A pre-normalizing pass (rescale to peak 0.7 before
   augmentation) would recover those samples — leaving R3 as a safety
   net rather than a filter.
3. **20-epoch ranking signal, not a verdict.** As established in T1-C
   and T1-D, the L3 floor (F ≥ 0.80) is a product-significant gate on
   E-GMD post-F2-T3, not a local-budget metric. The negative T1-E
   delta tells us the augmentation *currently* slows convergence; it
   does not tell us the augmentation is *wrong* in the limit.

## Next iterations (post-handoff)

- **Pre-normalize in `apply_audio_augmentation`:** scale input audio
  to peak ≤ 0.7 before the gain stage, so R3 stays a guard rather than
  a dataset filter. Recovers ~30 % of the dropped chaos samples.
- **Joint training (baseline ∪ augmented):** double the training
  budget rather than replacing it. The augmented examples become a
  regulariser, not a substitute.
- **Longer budget:** rerun the ablation at 50 epoch — if the
  augmented model catches up, the shift was a convergence-rate issue,
  not a structural one.
- **Per-voice ablation:** drop one voice at a time (no noise, no gain,
  no mic balance) to isolate which is the disruptor.

## Reproducibility

```
# Apply the augmentation
PYTHONPATH=src .venv/bin/python tools/t1e_apply_audio_aug.py \
    --in  data/gold/mix_2026-05-24 \
    --out data/gold/mix_2026-05-24_aug \
    --master-seed 20260524 \
    --gain-range-db -3 3 \
    --mic-balance-range-db -2 2 \
    --overwrite

# Retrain at the C=32 B=4 winner
PYTHONPATH=src .venv/bin/python tools/t1b_train_mix.py \
    --pool data/gold/mix_2026-05-24_aug \
    --epochs 20 --batch-size 4 --channels 32 --crop-samples 40960 \
    --seed 0 --run-id t1e-baseline-aug \
    --holdout-n 35
```
