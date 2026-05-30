---
title: "Pipeline Audit 2026-05-29 — post-F0-T19 (flat-28), local improvement hunt"
id: LIN-DT-AUDIT-2026-05-29
status: FINDINGS (for CEO Decision Lock)
created: 2026-05-29
related:
  - PIPELINE_AUDIT_2026-05-28.md
  - F0-T19_PER_KIT_MIDI_TRANSLATION_SPEC.md
  - F0-T4f_STEP_B_LOSS_REDESIGN_SPEC.md
---

# Pipeline Audit 2026-05-29

**Mandate (CEO).** After F0-T19 landed production-flat (0.1455 vs baseline 0.149) on the
mini-L3, audit the pipeline point-by-point — **locally, without adding kit variety** — to
find what can still be improved and surface any further anomalies (as the 2026-05-28 audit
found the Roland TD-11 / hi-hat 22-26 bug).

Subject: the F0-T19 Gold (`data/gold/mini_l3_{train,val}`, 1150 train + 115 val) and the
F0-T19 checkpoint (`artifacts/mini_l3_tcn_F0T19.pt`).

## 0. Verified healthy — ruled out (do not chase)

| Check | Result |
|:--|:--|
| **Audio↔target time base** | **EXACT.** Tail invariant `audio_end − (last_onset_s + tail_s)` = **0.0 ms over 60/60 samples**. (A crude RMS/spectral-flux onset xcorr looked decorrelated — that is a *probe artifact* of the reverberant 8-mic mono sum, NOT a misalignment. The tail invariant is definitive.) |
| NaN/inf in audio | 0/120 |
| Silent mic channels (DG) | 0/120 (all 8 slots active; SFZ stereo handled by F0-T4e) |
| CC#4 hi-hat head | now **continuous** (31/40 samples) after the jitter fix this session |

## 1. Findings — ranked

### F1 · [HIGH] `pos_weight=1000` cap spams the 4 rare channels → dilutes the headline
The flat-28 split created 4 channels that are **near-empty in the single ShittyKit val**:
`crash` **7** onsets total (115 samples), `ride_bell` 28, `snare_sidestick` 40, `aux` 98.
The density-derived `pos_weight` hits the **cap 1000** on all four. Effect: the loss weights
their FN so hard the model **fires them everywhere** — calibrated FP: `snare_sidestick` **7569**,
`aux` **5030**, `ride_bell` **4001** (vs 1–10 TP). Because the model *predicts* them, those
channels score **F=0** (not NaN-skipped) and **drag the per-sample mean**:

> per-sample mean F (per-sample tuned, lookahead-naive probe): **5 channels-with-signal 0.066 vs all-9 0.047** → the 4 rare channels pull the mean down **~40 %**.

So a large part of the "production-flat" headline is **dilution + spam**, not model failure.
**Lever (local, no kits):** lower the `POS_WEIGHT_CAP` (1000 is too aggressive for ~0-density
channels) and/or skip near-empty channels in the loss. Directly un-dilutes the headline AND
cuts the FP flood. *Strongest local lever.*

### F2 · [HIGH] Predict-everywhere persists — poor fixed-threshold calibration
Even at calibrated thresholds, precision is **0.04–0.11 on every channel** (kick 0.038,
snare_head 0.105, hihat 0.113, tom 0.071, ride_bow 0.056) — the model over-fires ~4–10×.
This is the gap between trainer-tuned **0.257** (per-sample optimal threshold) and production
**0.1455** (fixed threshold): the model's onset confidence is poorly calibrated (F0-T4f's
"under-confident on TPs", 6/8 buses prefer T<1). Kick — the loudest, clearest transient —
has the *worst* precision (0.038) and recall 0.215, a symptom of the global over-firing
(alignment ruled out in §0). **Lever:** loss/calibration work targeting confidence (Ridnik
gave +9.4 % but didn't close it; may be partly structural to the sparse single-kit regime).

### F3 · [MEDIUM] Audio clipping — 21 % of samples peak > 1.0
21 % of Gold samples have `peak |audio| > 1.0` (max **1.436**), up from the 8 % the
2026-05-28 audit flagged. Violates the F0-T2a `(0,1]` contract **silently** — `gold_writer`
checks NaN/silent-zero but **not peak**. FP16 stores it without hard-clip and P1 per-channel
z-norm largely neutralises the model impact, but: (a) it's a silent contract violation;
(b) the multi-mic assembly/render lacks headroom. **Lever:** enforce peak headroom in render
or a `gold_writer` peak check. Low model impact locally; **matters at F2-T1 scale**.

### F4 · [MODERATE] `edge_skip_frames=0` — 67 % of the training loss is on RF-warmup frames
Train crop = 1536 frames, causal RF = 1024 → only **33 % (512 frames) of each crop has full
receptive field**, yet the loss penalises all 1536 (`edge_skip_frames=0` in F0-T4e and F0-T19).
F0-T4c *documented* this and added the `edge_skip` knob ("atteso +20-40 %") but it was **never
activated**. Empirically the F0-T19 model's edge over-firing is **mild** (36 % of predicted
onsets in the warmup zone vs 33 % of true) → likely a modest gain, but it's free and cleans
the signal. **Lever:** `--loss-edge-skip-frames 1024` (and/or a longer crop for more valid
frames).

### F5 · [MEASUREMENT] mean-of-9 is the wrong headline for a single-kit val
With 4 of 9 channels near-empty in ShittyKit, the mean-of-9 understates real performance on
learnable channels (see F1). **Lever:** report F on channels-with-support (≥ N onsets) as the
primary mini-L3 metric; keep mean-of-9 as secondary. Measures real progress, not dilution.

## 2. Honest conclusion

The mini-L3 single-kit-val **mean-of-9 headline (~0.15) cannot jump on a magic single fix** —
4/9 channels have almost no examples in ShittyKit, and no local pipeline change teaches a
channel with 7 onsets. **But the CEO's intuition holds:** a real local gain is available, and
it is **not** in adding kits — it is in **(F1) stopping the rare-channel spam (pos_weight cap)
which both un-dilutes the headline ~40 % and cuts the FP flood**, plus **(F5) measuring the
channels-with-support**, plus the cleanliness fixes **(F3 clipping, F4 edge-skip)**. The
deeper predict-everywhere/calibration ceiling **(F2)** is partly structural to the sparse
single-kit regime and fully lifts only at **L4/E-GMD** (multi-kit, far less OOD).

**Recommended local sequence (no extra kits, $0 Azure):** F1 (pos_weight cap) + F5 (metric)
first — they directly move/clarify the headline; then F4 (edge-skip) + F3 (clipping headroom)
as cheap cleanliness; re-run mini-L3 to quantify. F2 is the residual hard problem for L4.
