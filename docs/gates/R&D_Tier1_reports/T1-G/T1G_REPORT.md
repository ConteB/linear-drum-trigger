---
title: "T1-G — Per-voice ablation"
status: PROVISIONAL
type: report
metadata:
  doc_id: LIN-DT-RND-T1G-001
  authors: [OP-NEUROTRIGGER]
  date: 2026-05-24
tags: [R&D, T1-G, audio-augmentation, ablation]
---

# T1-G — Per-voice ablation

Third follow-up from T1-E: isolate which audio-augmentation voice is
the disruptor. Three augmented datasets are built, each enabling
exactly one voice (with pre-normalize on for all). The full T1-B
trainer is then run on each pool at the T1-C winner config
(C=32 B=4 20 epoch).

| Voice | onset_F | shuffled_F | mae_ms | hh_mae |
|---|---:|---:|---:|---:|
| `noise_only`       | 0.0485 | 0.1273 | 11.90 | 0.1769 |
| `gain_only`        | 0.0466 | 0.1239 | 12.18 | 0.1768 |
| `mic_balance_only` | 0.0478 | 0.1259 | 12.07 | 0.1769 |

For reference (from T1-E + baseline):

| | onset_F |
|---|---:|
| baseline (no augmentation) | 0.0838 |
| **all 3 voices + pre-norm** | **0.0484** |
| noise_only | 0.0485 |
| gain_only  | 0.0466 |
| mic_balance_only | 0.0478 |

## Verdict

**No single voice is a disruptor — the three are statistically
equivalent.** Every cell of the ablation lands in the same ~0.047
band; the joint pipeline with *all three* voices on (T1-E v2)
gives 0.0484, indistinguishable from any single voice.

Interpretation: the augmentation cost (the −42 % gap on
augmented-only training) is **not** dominated by one voice; it
is intrinsic to the distribution shift introduced by *any*
non-trivial augmentation at this training budget (20 epoch).

The earlier hypothesis ("noise floor is the disruptor, drop it
first") is **falsified**. The voice configuration in F0-T16-post v2
should preserve all three voices.

The right lever is **not** which voice to drop, but **how much**:

- Lower noise floor (e.g. −60 dB)
- Tighter gain bounds (±2 dB instead of ±3 dB)
- Reduced mic balance (±1 dB instead of ±2 dB)

And, of course, the **joint-training strategy** from T1-F that
recovers virtually all the baseline performance.

## Tooling

- `tools/t1g_per_voice_ablation.py` — builds 3 single-voice augmented
  pools and trains each; emits `per_voice_results.json`.

## Reproducibility

```
PYTHONPATH=src .venv/bin/python tools/t1g_per_voice_ablation.py \
    --baseline-pool data/gold/mix_2026-05-24 \
    --epochs 20 --batch-size 4 --channels 32 --crop-samples 40960
```
