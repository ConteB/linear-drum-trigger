---
title: "T1-DIAG-A — Opzione A diagnostic: causality is the dominant bug"
status: PROVISIONAL
type: report
metadata:
  doc_id: LIN-DT-RND-T1DIAGA-001
  authors: [OP-NEUROTRIGGER]
  date: 2026-05-23
tags: [R&D, diagnostic, causality, lookahead, F0-T4a, pre-Azure]
---

# T1-DIAG-A — Opzione A diagnostic: causality is the dominant bug

CEO directive (`[[next-session-option-a-diagnostic]]`): before committing
A100 quota to F2-T3, run a serious diagnostic on the local R&D mix dataset
to explain *why* the network plateaus at F ≈ 0.09 (10× under the L3 floor
of 0.80) — and falsify or confirm the three hypotheses on the table:
loss imbalance, input normalisation, capacity.

## Method

Five experiments + one structural input audit + one self-overfit sanity
test. All ran on Mac M5 / MPS, ~5 minutes of wall time each. Dataset =
`data/gold/mix_2026-05-24` (585 sample, 140 GMD + 30 rare-emphasis +
30 chaos × 3 jitter variants).

| Tool | Purpose |
| :-- | :-- |
| `tools/diagnose_pipeline.py` (new) | Per-channel audio statistics + per-bus target sparsity (Step 2). |
| `src/neural/train.py` per-head logging (new) | Expose the contribution of onset/velocity/microtiming/hihat to the total loss every epoch (Step 1). |
| `src/neural/data.py::lookahead_frames` (new) | Shift the audio crop forward of L frames vs. the target — turns the strict-causal model into a causal-with-look-ahead model (PDC). |
| `tools/t1b_train_mix.py` CLI overrides (new) | Loss weights, key filter, look-ahead — drive every experiment from one entry point. |

## Findings (in the order they fell)

### F1 — 3/8 onset buses have empty targets

The MIDI mapping in `flat-25` defines 8 buses, but the dataset only
populates 5 (kick, snare, hihat, tom, floor). Overhead L/R and Room never
fire an onset — they exist as **mic positions**, not as trigger buses.
The model still parametrises 3 dead heads → wasted capacity + diluted
gradient. **Not catastrophic** (BCE on always-zero target is fine), but
it inflates the loss baseline and explains part of the 4× under-tuning
of `pos_weight=50` vs the measured density 0.4–1.5 %.

### F2 — Loss imbalance is real but secondary (+50 % F)

Per-head decomposition at epoch 20, default `LossConfig`:

| Head | Weighted contribution | % of total |
| :-- | --: | --: |
| onset | 0.354 | **42.5 %** |
| velocity (masked) | 0.134 | 16.1 % |
| microtiming (masked) | 0.108 | 13.0 % |
| **hihat (dense L1)** | 0.236 | **28.4 %** |

The hihat head, with `w_hihat=1.0` and dense L1 on a target whose
median sample has std = 0 (always-closed), dilutes the onset gradient
by ~30 %. Rebalancing (`pos_w=200, w_on=2.0, w_hh=0.25, w_vel/mt=0.1`)
moves the onset to 93 % of the total and lifts F_mean from
**0.061 → 0.091** (+49 %).

### F3 — Capacity is *not* the bottleneck (and C=128 over-fits)

40-epoch runs with the rebalanced loss, same holdout:

| Model | params | F_mean | F_max | F ≥ 0.10 |
| :-- | --: | --: | --: | --: |
| C=32 | 83 K | 0.091 | 0.333 | 20/50 |
| C=64 | 331 K | 0.096 | **0.557** | 23/50 |
| C=128 | 1 317 K | 0.088 | 0.267 | 20/50 |

16× more parameters does not move the mean. C=128 actually *drops* a
hair, the textbook sign of over-fitting on 535 training samples. **The
F0-T4a baseline (C=32) is not the wall.**

### F4 — F_mean ≈ F_shuffled — the model isn't learning audio→onset

The most diagnostic number of the session:

| Run | F_mean | **F_shuf_mean** | **F > F_shuf** |
| :-- | --: | --: | --: |
| baseline (orig loss) | 0.061 | 0.116 | **4/50** |
| rebal C=32 | 0.091 | 0.120 | 14/50 |
| rebal C=64 | 0.096 | 0.112 | 11/50 |
| rebal C=128 | 0.088 | 0.101 | 16/50 |

On 50 holdout grooves the model beats the shuffled-truth control only
**22–32 %** of the time. Most of what the network "learns" is the
**marginal density per bus**, which is invariant to a temporal shuffle.
The audio→target causal mapping never emerges.

### F5 — Chaos contaminates F_shuf, not F_real

Dropping the 90 chaos samples (Poisson off-grid, target densely populated
on *all* 8 buses including OH/ROO):

| Run | F_mean | F_shuf | F − F_shuf |
| :-- | --: | --: | --: |
| with chaos | 0.091 | 0.120 | **−0.029** |
| no chaos | 0.076 | **0.075** | +0.001 |

F_shuf drops 38 % (the chaos was inflating the marginal floor), but
F_mean does not move. **Chaos is a metric contaminant, not the cause of
the plateau.**

### F6 — **The smoking gun: self-overfit fails**

Train 200 epochs on 18 grooves, evaluate on the *same 20 grooves*
(memorisation test):

| Self-overfit on 20 keys | F_mean | F_max | F > F_shuf | F ≥ 0.50 |
| :-- | --: | --: | --: | --: |
| strict-causal (current) | **0.080** | 0.292 | 4/20 | 0/20 |
| **+ lookahead = 35 frames (100 ms)** | **0.150** | **0.413** | **12/20** | 0/20 |

A 83 K-parameter network *cannot* memorise 18 samples after 200 epochs
when the model is strict-causal. With a 100 ms look-ahead (35 frames at
the 344 Hz target grid — exactly the F0-T4a §3 prescription), F nearly
doubles. **The strict-causality is a real architectural bug.**

But F = 0.15 on its own training set after 200 epochs is still 5× under
the F = 0.80 a memorising network should reach — **a second bug remains
open**.

## Root cause attribution

| Bug | Severity | Lift | Status |
| :-- | :-- | --: | :-- |
| Strict-causality (no look-ahead applied) | **Critical** | +87 % (overfit) | `data.py` patched, *not committed as default* |
| Loss imbalance (`pos_w`, `w_hihat`) | High | +49 % (holdout) | `LossConfig` overridable via CLI, *defaults unchanged* |
| Dead OH/ROO/Room onset heads | Medium | (qual.) | Open — needs bus mask or `N_BUSES → 5` decision |
| Chaos generator targets uncoupled | Low | F_shuf contamin. | Open — `chaos_generator.py` design Q |
| Capacity | Not a bug | 0 | Closed — F0-T4a C=32 stays |

## Why this matters before A100

The diagnostic ran in ~30 minutes total on Mac M5, **cost = 0 Azure
dollars**. Committing F2-T3 (A100 training, $50–80) now — with the
network failing to learn even an overfit signal — would have burned the
credit on a *structurally broken* training run. The L3 gap is **not** a
data problem; it is at least a causality bug + a still-unknown second
factor.

**Recommended order of operations:**

1. **Decision lock the look-ahead** as a permanent change to F0-T4a §3
   and the data pipeline (and the RTNeural export path — the streaming
   model gets 35 frames of latency, which is exactly the PDC the spec
   already plans). Path: revisit F0-T4a §8 open items.
2. **Investigate the residual plateau at F = 0.15 on overfit** — likely
   suspects:
   - Onset target peak < 1.0 on isolated transients (Gaussian σ vs frame
     period)
   - Bias initialisation of the onset head (logit collapse)
   - LR schedule (current AdamW 1e-3 constant — possible plateau)
3. **Bus-mask the dead OH/ROO/Room onset heads** to stop wasting capacity.
4. *Only then* commit to F2-T1 render → F2-T3 training on A100.

The Step-3 capacity stress test (`tools/diagnose_capacity` was in the
plan) is **closed without execution**: F2 already showed C=128 doesn't
help.

## Artifacts

All under `artifacts/`:

- `pipeline_diagnostic.json` — Step 2 raw numbers
- `diag-perhead-c32_report.json` — baseline (default `LossConfig`)
- `diag-rebal-c32_report.json` — rebalanced loss, C=32
- `diag-rebal-c64_report.json` — rebalanced, C=64
- `diag-rebal-c128_report.json` — rebalanced, C=128
- `diag-nochaos-c32_report.json` — rebalanced + chaos excluded
- `diag-overfit-c32_report.json` — strict-causal self-overfit
- `diag-overfit-la35-c32_report.json` — **+ look-ahead self-overfit**
- `clean_keys_no_chaos.json`, `overfit_20_keys.json` — key lists

Tools (new):
- `tools/diagnose_pipeline.py`

Code surface touched (default behaviour preserved; new knobs are opt-in):
- `src/neural/data.py` — `GoldDataset(lookahead_frames=0)` (default 0 keeps
  the current behaviour)
- `src/neural/train.py` — per-head loss logging, `loss_config`,
  `include_keys`, `lookahead_frames`
- `tools/t1b_train_mix.py` — CLI for the above + `history` in summary JSON

## What is *not* committed

- **No change** to `LossConfig` defaults — the rebalanced numbers are
  diagnostic findings, not a Decision Lock. Adoption requires CEO sign-off
  and `F0-T4a §6` amendment.
- **No change** to the default `lookahead_frames` — still 0. The +100 ms
  look-ahead is a F0-T4a §3 design decision and should be ratified there
  before becoming the default.

Diagnostic done at zero Azure cost. A100 commit is **NOT** recommended until
the residual F=0.15 overfit plateau is also explained.
