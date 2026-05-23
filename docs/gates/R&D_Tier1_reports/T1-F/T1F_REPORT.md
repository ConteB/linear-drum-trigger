---
title: "T1-F — Joint training (baseline ∪ augmented)"
status: PROVISIONAL
type: report
metadata:
  doc_id: LIN-DT-RND-T1F-001
  authors: [OP-NEUROTRIGGER]
  date: 2026-05-24
tags: [R&D, T1-F, audio-augmentation, joint-training]
---

# T1-F — Joint training (baseline ∪ augmented)

Second follow-up from T1-E's negative result: instead of *replacing* the
baseline pool with the augmented one (which dropped onset_F by 60 %),
we *concatenate* the two pools — every sample appears once with the
original audio, once with the augmented audio — so the augmentation
becomes a regulariser rather than a substitute.

The augmented pool used is `mix_2026-05-24_aug_v2` (pre-normalize peak
0.5, noise −50 dB, gain ±3 dB, mic balance ±2 dB, 585/585 sample
retained). The joint dataset is built by
`tools/t1f_build_joint_dataset.py` via symlinks: pool A samples keep
their original key, pool B samples get the `-AUG` suffix.

## Setup

| | Baseline only | v2 aug only | Joint |
|---|---|---|---|
| Pool | `mix_2026-05-24` | `mix_2026-05-24_aug_v2` | `mix_2026-05-24_joint` |
| Samples | 585 | 585 | **1170** |
| Train / holdout | 535 / 50 | 535 / 50 | 1070 / 100 |
| Epochs / batch / C | 20 / 4 / 32 | 20 / 4 / 32 | 20 / 4 / 32 |
| Seed | 0 | 0 | 0 |

## Results

| Variant | n_hold | onset_F | shuf_F | mae_ms | hh_mae | wall_s |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 50 | **0.0838** | 0.1025 | **11.21** | 0.193 | 31.6 |
| v1 aug (no pn) | 35 | 0.0339 | 0.0873 | 14.07 | 0.190 | 23.1 |
| v2 aug + pre-norm | 50 | 0.0484 | 0.1270 | 12.57 | 0.177 | 32.5 |
| **joint** | **100** | **0.0808** | **0.0981** | **11.25** | 0.195 | 65.7 |

## Verdict

**Joint training closes the T1-E gap.** Three quantitative signals back this:

1. **onset_F drops only −3.6 % vs baseline** (0.081 vs 0.084), against
   −42 % for the v2-aug-only variant. The augmented samples no longer
   *shift* the training distribution — they *enlarge* it.
2. **shuffled_F is *better* than the baseline** (0.098 vs 0.103). The
   joint model is *less* sensitive to label permutation, which is the
   expected regularisation signature: the model relies less on
   spurious local patterns.
3. **timing-MAE matches the baseline** (11.25 vs 11.21 ms). The
   augmentation does not interfere with the regression head.

The wall time roughly doubles (65 s vs 32 s) because the train set
roughly doubles — proportional, no overhead.

## Recommendation for F2-T3

When the A100 quota arrives and F2-T3 is on the clock, the **joint
training strategy is the F2-T3 default**:

- Render the full Gold dataset once (F2-T1).
- Apply the audio_augment pipeline to produce an `_aug` parallel pool
  (F2-T2 single-pass — no need for k=3 variants if joint training works
  with k=1).
- Train on `pool ∪ pool_aug` (joint).

This gives us the regularisation benefit of augmentation *without* the
training-data shift cost that nearly killed the F-measure in T1-E v2.

## Open follow-ups

- **T1-G per-voice ablation** (`tools/t1g_per_voice_ablation.py`) — isolate
  which voice (noise / gain / mic_balance) contributes most to the small
  residual −3.6 % gap.
- **Longer budget** (50-100 epoch) — confirm that the trajectory
  continues to favour joint > baseline alone past convergence.
- **Multi-variant joint** (k=2 or k=3 augmentation variants stacked)
  — does more augmented data continue to help, or does it saturate?

## Tooling

- `tools/t1f_build_joint_dataset.py` — builds the joint pool via
  symlinks; pool-B samples get a configurable suffix (default `-AUG`)
  so collide-free with pool-A keys.

## Reproducibility

```
PYTHONPATH=src .venv/bin/python tools/t1f_build_joint_dataset.py \
    --pool-a data/gold/mix_2026-05-24 \
    --pool-b data/gold/mix_2026-05-24_aug_v2 \
    --out    data/gold/mix_2026-05-24_joint \
    --suffix-b=-AUG

PYTHONPATH=src .venv/bin/python tools/t1b_train_mix.py \
    --pool data/gold/mix_2026-05-24_joint \
    --epochs 20 --batch-size 4 --channels 32 --crop-samples 40960 \
    --seed 0 --holdout-n 100 --run-id t1f-joint
```
