# Pipeline Ocular Audit — MuldjordKit
**Date:** 2026-05-26  **Samples:** 2
**Checkpoint:** mini_l3_tcn_c64_B_allfixes.pt

| Stage | Status | PNG | Notes |
|:--|:--:|:--|:--|
| S1 MIDI vs midimap | **PASS** | [`S1_midi_vs_midimap_MuldjordKit.png`](./S1_midi_vs_midimap_MuldjordKit.png) | sample MINI_L3000-V0T0-J00-DGZ-R0-L1-NONE: 75 ok / 0 render-only / 0 phantom / 0 ignored; sample MINI_L3057-V0T0-J00-DGZ-R0-L1-NONE: 39 ok / 0 render-only / 0 phantom / 0 ignored; midimap notes count: 21 (+2 more) |
| S2 Render audio | **WARN** | [`S2_render_audio_MuldjordKit.png`](./S2_render_audio_MuldjordKit.png) | MINI_L3057-V0T0-J00-DGZ-R0-L1-NONE: ch 2 (hihat) CLIPPED (peak=1.010) |
| S3 Bleed cross-mic | **PASS** | [`S3_bleed_matrix_MuldjordKit.png`](./S3_bleed_matrix_MuldjordKit.png) | no identical channel pairs (off-diag < 1.0 everywhere) |
| S4 Tail std | **PASS** | [`S4_tail_std_MuldjordKit.png`](./S4_tail_std_MuldjordKit.png) | all samples: Δ < 10 ms (tail standardization OK) |
| S5 Target vs MIDI | **WARN** | [`S5_target_vs_midi_MuldjordKit.png`](./S5_target_vs_midi_MuldjordKit.png) | MINI_L3057-V0T0-J00-DGZ-R0-L1-NONE: 3 MIDI onsets without target (≤5, acceptable) |
| S6 DNA integrity | **PASS** | — | all 2 samples: sha256 + shape + finiteness OK |
| S7 Crop policy | **PASS** | [`S7_crop_policy_MuldjordKit.png`](./S7_crop_policy_MuldjordKit.png) | lookahead shift = 0.1016s (correctly applied; target crop_frames=1536) |
| S8 Preprocess P1+P2 | **PASS** | [`S8_preprocess_MuldjordKit.png`](./S8_preprocess_MuldjordKit.png) | all 8 audio channels post-P1 std in [0.05, 5.0]; onset_env channel present |
| S9 Forward pass | **PASS** | [`S9_forward_pass_MuldjordKit.png`](./S9_forward_pass_MuldjordKit.png) | pred (blue) vs target (red) overlay per-bus; thr 0.1 dashed grey |

## Detailed notes

### S1 MIDI vs midimap — PASS
- sample MINI_L3000-V0T0-J00-DGZ-R0-L1-NONE: 75 ok / 0 render-only / 0 phantom / 0 ignored
- sample MINI_L3057-V0T0-J00-DGZ-R0-L1-NONE: 39 ok / 0 render-only / 0 phantom / 0 ignored
- midimap notes count: 21
- project_mapped notes count: 21
- TOTAL phantom onsets in audited samples: 0

### S2 Render audio — WARN
- MINI_L3057-V0T0-J00-DGZ-R0-L1-NONE: ch 2 (hihat) CLIPPED (peak=1.010)

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
