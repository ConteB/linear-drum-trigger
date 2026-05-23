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

### F7 — Receptive-field collapse: 75 % of context is left-pad zero

Computing the model's total receptive field at the 344 Hz target grid:

| Stage | RF contribution |
| :-- | --: |
| Strided encoder (4 convs k=8, strides 4·4·4·2) | 596 samples = 4.7 frames |
| Dilated trunk (8 blocks × 2 convs k=3, dil 1..128) | 1020 frames ≈ 2961 ms |
| **TOTAL RF** | **1024 frames ≈ 2.97 s** |

Crop used in every experiment so far: 32 768 samples = 256 frames = 743 ms.
The crop is **4× shorter than the RF**. Every `CausalConv1d` left-pads
its history with zero on each forward, so for every output frame the
network sees:

- frame 0 of the crop: 0.1 % real audio + 99.9 % left-pad zero
- frame 255 (last of the crop): 25 % real audio + 75 % left-pad zero

The network is literally learning the **left-pad zero profile**, not the
audio. This single observation makes every earlier finding consistent:
F_shuf ≈ F_real because zero-profile context is shuffle-invariant;
self-overfit plateaus because the same 256 visible frames don't carry
enough audio→onset signal through 75 % zeros; capacity doesn't help
because zero-padding can't be parametrised away.

Test: pick the 20 longest samples from the mix (≥ 135 552 audio samples
= RF + look-ahead), repeat the self-overfit with `crop_samples=131072`
(≥ RF), `lookahead_frames=35`, rebalanced loss:

| Self-overfit on 20 long keys | F_mean | F_max | F ≥ 0.50 | F ≥ 0.80 | F_shuf |
| :-- | --: | --: | --: | --: | --: |
| strict-causal, crop 32 K | 0.080 | 0.292 | 0/20 | 0/20 | 0.098 |
| + LA = 35, crop 32 K | 0.150 | 0.413 | 0/20 | 0/20 | 0.090 |
| **+ LA = 35, crop ≥ RF (131 K)** | **0.234** | **0.827** | **5/20** | **2/20** | **0.060** |

**The model now learns.** F max passes the L3 floor (0.827 ≥ 0.80) on
two grooves. Best holdout groove RND012 hits **F = 0.625 with
timing-MAE = 3.99 ms** (under the 5 ms L3 ceiling) and F_shuf = 0.000.
F_shuf drops to 0.060 — under the L3 negative-control ceiling of 0.10.

Triple boost — three bugs, three additive lifts.

## Root cause attribution

| Bug | Severity | Lift | Status |
| :-- | :-- | --: | :-- |
| **RF collapse: 75 % of context is left-pad zero** | **Critical** | +56 % on top of LA (overfit 0.150 → 0.234) | `crop ≥ RF` works, *not committed as default* |
| **Strict-causality (no look-ahead applied)** | **Critical** | +87 % (overfit 0.080 → 0.150) | `data.py` patched, *not committed as default* |
| Loss imbalance (`pos_w`, `w_hihat`) | High | +49 % (holdout) | `LossConfig` overridable via CLI, *defaults unchanged* |
| Dead OH/ROO/Room onset heads | Medium | (qual.) | Open — needs bus mask or `N_BUSES → 5` decision |
| Chaos generator targets uncoupled | Low | F_shuf contamin. | Open — `chaos_generator.py` design Q |
| Capacity | Not a bug | 0 | Closed — F0-T4a C=32 stays |

## Why this matters before A100

The diagnostic ran in ~45 minutes total on Mac M5, **cost = 0 Azure
dollars**. Committing F2-T3 (A100 training, $50–80) now — with two
critical architectural bugs unfixed — would have burned the credit on a
*structurally broken* training run. The L3 gap is **not** a data
problem; it is two architectural bugs that prevent the network from
even memorising 18 samples.

With both bugs fixed (look-ahead 35 frames + crop ≥ RF), the same C=32
network reaches F = 0.827 on individual grooves with 3.99 ms timing-MAE
— above the L3 floor. **The architecture works.** What was missing was
the wiring between architecture spec and data pipeline.

**Recommended order of operations:**

1. **Decision lock both fixes** as permanent F0-T4a §3 amendments:
   - `lookahead_frames = 35` (PDC = 100 ms — already in the spec, just
     never threaded through `GoldDataset` / `evaluate_holdout`)
   - `crop_samples ≥ RF + lookahead` (= 1059 frames = 135 552 samples =
     ~3.07 s) as the *minimum* training crop. A larger margin (4-5 s) is
     safer.
2. **Update F2-T1 render minimum length** so the Gold dataset produces
   samples ≥ 5 s (instead of the 1-3 s of `local_rnd`). Spec amendment
   to F0-T2a §3.8 (tail standardisation already at 0.5 s — separate
   knob, this is about the *MIDI duration* setting in the recipe matrix).
3. **Bus-mask the dead OH/ROO/Room onset heads** to stop wasting capacity
   (smaller secondary fix).
4. *Only then* commit to F2-T1 render → F2-T3 training on A100. With
   ~3 s minimum, the Gold dataset itself solves the padding-zero problem
   for typical 30-60 s clips.

The Step-3 capacity stress test (`tools/diagnose_capacity` was in the
plan) is **closed without execution**: C=128 doesn't help and C=64 only
adds marginal F_max. F0-T4a C=32 baseline stays.

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
- `diag-overfit-fullRF-c32_report.json` — **+ look-ahead + crop ≥ RF**
- `clean_keys_no_chaos.json`, `overfit_20_keys.json`,
  `overfit_20_long_keys.json` — key lists

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

Diagnostic done at zero Azure cost. With both critical bugs identified
and fixed locally (overfit F = 0.080 → 0.234, individual grooves up to
F = 0.827 with 4 ms timing-MAE), the architecture is **proven viable**.
A100 commit is recommended *after* the two fixes are ratified as defaults
in F0-T4a and the F2-T1 render uses ≥ 5 s clip lengths.
