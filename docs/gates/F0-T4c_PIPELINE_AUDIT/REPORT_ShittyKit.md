# Pipeline Ocular Audit — ShittyKit
**Date:** 2026-05-26  **Samples:** 2
**Checkpoint:** mini_l3_tcn_c64_B_allfixes.pt

| Stage | Status | PNG | Notes |
|:--|:--:|:--|:--|
| S1 MIDI vs midimap | **WARN** | [`S1_midi_vs_midimap_ShittyKit.png`](./S1_midi_vs_midimap_ShittyKit.png) | sample MINI_L3000-V0T0-J00-DGZ-R0-L1-NONE: 74 ok / 0 render-only / 1 phantom / 0 ignored; sample MINI_L3028-V0T0-J00-DGZ-R0-L1-NONE: 61 ok / 0 render-only / 1 phantom / 21 ignored; midimap notes count: 18 (+2 more) |
| S2 Render audio | **PASS** | [`S2_render_audio_ShittyKit.png`](./S2_render_audio_ShittyKit.png) | all slots non-silent, peak within (1e-4, 0.99] |
| S3 Bleed cross-mic | **WARN** | [`S3_bleed_matrix_ShittyKit.png`](./S3_bleed_matrix_ShittyKit.png) | MINI_L3000-V0T0-J00-DGZ-R0-L1-NONE: ch 2 (hihat) ≡ ch 5 (OH_L) — identical signals!; MINI_L3028-V0T0-J00-DGZ-R0-L1-NONE: ch 2 (hihat) ≡ ch 5 (OH_L) — identical signals! |
| S4 Tail std | **PASS** | [`S4_tail_std_ShittyKit.png`](./S4_tail_std_ShittyKit.png) | all samples: Δ < 10 ms (tail standardization OK) |
| S5 Target vs MIDI | **PASS** | [`S5_target_vs_midi_ShittyKit.png`](./S5_target_vs_midi_ShittyKit.png) | all MIDI onsets match target ±3 frames |
| S6 DNA integrity | **PASS** | — | all 2 samples: sha256 + shape + finiteness OK |
| S7 Crop policy | **PASS** | [`S7_crop_policy_ShittyKit.png`](./S7_crop_policy_ShittyKit.png) | lookahead shift = 0.1016s (correctly applied; target crop_frames=1536) |
| S8 Preprocess P1+P2 | **WARN** | [`S8_preprocess_ShittyKit.png`](./S8_preprocess_ShittyKit.png) | MINI_L3000-V0T0-J00-DGZ-R0-L1-NONE: ch 0 (kick) std=0.042 (expect ~1 post z-score) |
| S9 Forward pass | **PASS** | [`S9_forward_pass_ShittyKit.png`](./S9_forward_pass_ShittyKit.png) | pred (blue) vs target (red) overlay per-bus; thr 0.1 dashed grey |

## Detailed notes

### S1 MIDI vs midimap — WARN
- sample MINI_L3000-V0T0-J00-DGZ-R0-L1-NONE: 74 ok / 0 render-only / 1 phantom / 0 ignored
- sample MINI_L3028-V0T0-J00-DGZ-R0-L1-NONE: 61 ok / 0 render-only / 1 phantom / 21 ignored
- midimap notes count: 18
- project_mapped notes count: 21
- TOTAL phantom onsets in audited samples: 2

### S2 Render audio — PASS
- all slots non-silent, peak within (1e-4, 0.99]

### S3 Bleed cross-mic — WARN
- MINI_L3000-V0T0-J00-DGZ-R0-L1-NONE: ch 2 (hihat) ≡ ch 5 (OH_L) — identical signals!
- MINI_L3028-V0T0-J00-DGZ-R0-L1-NONE: ch 2 (hihat) ≡ ch 5 (OH_L) — identical signals!

### S4 Tail std — PASS
- all samples: Δ < 10 ms (tail standardization OK)

### S5 Target vs MIDI — PASS
- all MIDI onsets match target ±3 frames

### S6 DNA integrity — PASS
- all 2 samples: sha256 + shape + finiteness OK

### S7 Crop policy — PASS
- lookahead shift = 0.1016s (correctly applied; target crop_frames=1536)

### S8 Preprocess P1+P2 — WARN
- MINI_L3000-V0T0-J00-DGZ-R0-L1-NONE: ch 0 (kick) std=0.042 (expect ~1 post z-score)

### S9 Forward pass — PASS
- pred (blue) vs target (red) overlay per-bus; thr 0.1 dashed grey
