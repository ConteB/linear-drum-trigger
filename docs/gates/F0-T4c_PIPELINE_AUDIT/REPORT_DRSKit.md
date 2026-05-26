# Pipeline Ocular Audit — DRSKit
**Date:** 2026-05-26  **Samples:** 2
**Checkpoint:** mini_l3_tcn_c64_B_allfixes.pt

| Stage | Status | PNG | Notes |
|:--|:--:|:--|:--|
| S1 MIDI vs midimap | **WARN** | [`S1_midi_vs_midimap_DRSKit.png`](./S1_midi_vs_midimap_DRSKit.png) | sample MINI_L3000-V0T0-J00-DGZ-R0-L1-NONE: 74 ok / 0 render-only / 1 phantom / 0 ignored; sample MINI_L3057-V0T0-J00-DGZ-R0-L1-NONE: 39 ok / 0 render-only / 0 phantom / 0 ignored; midimap notes count: 38 (+2 more) |
| S2 Render audio | **PASS** | [`S2_render_audio_DRSKit.png`](./S2_render_audio_DRSKit.png) | all slots non-silent, peak within (1e-4, 0.99] |
| S3 Bleed cross-mic | **PASS** | [`S3_bleed_matrix_DRSKit.png`](./S3_bleed_matrix_DRSKit.png) | no identical channel pairs (off-diag < 1.0 everywhere) |
| S4 Tail std | **PASS** | [`S4_tail_std_DRSKit.png`](./S4_tail_std_DRSKit.png) | all samples: Δ < 10 ms (tail standardization OK) |
| S5 Target vs MIDI | **WARN** | [`S5_target_vs_midi_DRSKit.png`](./S5_target_vs_midi_DRSKit.png) | MINI_L3057-V0T0-J00-DGZ-R0-L1-NONE: 3 MIDI onsets without target (≤5, acceptable) |
| S6 DNA integrity | **PASS** | — | all 2 samples: sha256 + shape + finiteness OK |
| S7 Crop policy | **PASS** | [`S7_crop_policy_DRSKit.png`](./S7_crop_policy_DRSKit.png) | lookahead shift = 0.1016s (correctly applied; target crop_frames=1536) |
| S8 Preprocess P1+P2 | **PASS** | [`S8_preprocess_DRSKit.png`](./S8_preprocess_DRSKit.png) | all 8 audio channels post-P1 std in [0.05, 5.0]; onset_env channel present |
| S9 Forward pass | **PASS** | [`S9_forward_pass_DRSKit.png`](./S9_forward_pass_DRSKit.png) | pred (blue) vs target (red) overlay per-bus; thr 0.1 dashed grey |

## Detailed notes

### S1 MIDI vs midimap — WARN
- sample MINI_L3000-V0T0-J00-DGZ-R0-L1-NONE: 74 ok / 0 render-only / 1 phantom / 0 ignored
- sample MINI_L3057-V0T0-J00-DGZ-R0-L1-NONE: 39 ok / 0 render-only / 0 phantom / 0 ignored
- midimap notes count: 38
- project_mapped notes count: 21
- TOTAL phantom onsets in audited samples: 1

### S2 Render audio — PASS
- all slots non-silent, peak within (1e-4, 0.99]

### S3 Bleed cross-mic — PASS
- no identical channel pairs (off-diag < 1.0 everywhere)

### S4 Tail std — PASS
- all samples: Δ < 10 ms (tail standardization OK)

### S5 Target vs MIDI — WARN
- MINI_L3057-V0T0-J00-DGZ-R0-L1-NONE: 3 MIDI onsets without target (≤5, acceptable)

### S6 DNA integrity — PASS
- all 2 samples: sha256 + shape + finiteness OK

### S7 Crop policy — PASS
- lookahead shift = 0.1016s (correctly applied; target crop_frames=1536)

### S8 Preprocess P1+P2 — PASS
- all 8 audio channels post-P1 std in [0.05, 5.0]; onset_env channel present

### S9 Forward pass — PASS
- pred (blue) vs target (red) overlay per-bus; thr 0.1 dashed grey
