# Pipeline Ocular Audit — BigRustyDrums
**Date:** 2026-05-26  **Samples:** 2
**Checkpoint:** mini_l3_tcn_c64_B_allfixes.pt

| Stage | Status | PNG | Notes |
|:--|:--:|:--|:--|
| S1 MIDI vs midimap | **FAIL** | [`S1_midi_vs_midimap_BigRustyDrums.png`](./S1_midi_vs_midimap_BigRustyDrums.png) | sample MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: 0 ok / 0 render-only / 75 phantom / 0 ignored; sample MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: 0 ok / 0 render-only / 39 phantom / 9 ignored; midimap notes count: 0 (+2 more) |
| S2 Render audio | **FAIL** | [`S2_render_audio_BigRustyDrums.png`](./S2_render_audio_BigRustyDrums.png) | MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 0 (kick) SILENT (peak<1e-4); MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 1 (snare) SILENT (peak<1e-4); MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 2 (hihat) SILENT (peak<1e-4) (+9 more) |
| S3 Bleed cross-mic | **PASS** | [`S3_bleed_matrix_BigRustyDrums.png`](./S3_bleed_matrix_BigRustyDrums.png) | no identical channel pairs (off-diag < 1.0 everywhere) |
| S4 Tail std | **PASS** | [`S4_tail_std_BigRustyDrums.png`](./S4_tail_std_BigRustyDrums.png) | all samples: Δ < 10 ms (tail standardization OK) |
| S5 Target vs MIDI | **WARN** | [`S5_target_vs_midi_BigRustyDrums.png`](./S5_target_vs_midi_BigRustyDrums.png) | MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: 4 MIDI onsets without target (≤5, acceptable) |
| S6 DNA integrity | **FAIL** | — | MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: audio shape DNA=[2, 340213] actual=[8, 340213]; MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: audio shape DNA=[2, 372351] actual=[8, 372351] |
| S7 Crop policy | **PASS** | [`S7_crop_policy_BigRustyDrums.png`](./S7_crop_policy_BigRustyDrums.png) | lookahead shift = 0.1016s (correctly applied; target crop_frames=1536) |
| S8 Preprocess P1+P2 | **WARN** | [`S8_preprocess_BigRustyDrums.png`](./S8_preprocess_BigRustyDrums.png) | MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 0 (kick) std=0.000 (expect ~1 post z-score); MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 1 (snare) std=0.000 (expect ~1 post z-score); MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 2 (hihat) std=0.000 (expect ~1 post z-score) (+9 more) |
| S9 Forward pass | **PASS** | [`S9_forward_pass_BigRustyDrums.png`](./S9_forward_pass_BigRustyDrums.png) | pred (blue) vs target (red) overlay per-bus; thr 0.1 dashed grey |

## Detailed notes

### S1 MIDI vs midimap — FAIL
- sample MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: 0 ok / 0 render-only / 75 phantom / 0 ignored
- sample MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: 0 ok / 0 render-only / 39 phantom / 9 ignored
- midimap notes count: 0
- project_mapped notes count: 21
- TOTAL phantom onsets in audited samples: 114

### S2 Render audio — FAIL
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 0 (kick) SILENT (peak<1e-4)
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 1 (snare) SILENT (peak<1e-4)
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 2 (hihat) SILENT (peak<1e-4)
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 3 (tom) SILENT (peak<1e-4)
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 4 (floor) SILENT (peak<1e-4)
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 7 (room) SILENT (peak<1e-4)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 0 (kick) SILENT (peak<1e-4)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 1 (snare) SILENT (peak<1e-4)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 2 (hihat) SILENT (peak<1e-4)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 3 (tom) SILENT (peak<1e-4)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 4 (floor) SILENT (peak<1e-4)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 7 (room) SILENT (peak<1e-4)

### S3 Bleed cross-mic — PASS
- no identical channel pairs (off-diag < 1.0 everywhere)

### S4 Tail std — PASS
- all samples: Δ < 10 ms (tail standardization OK)

### S5 Target vs MIDI — WARN
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: 4 MIDI onsets without target (≤5, acceptable)

### S6 DNA integrity — FAIL
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: audio shape DNA=[2, 340213] actual=[8, 340213]
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: audio shape DNA=[2, 372351] actual=[8, 372351]

### S7 Crop policy — PASS
- lookahead shift = 0.1016s (correctly applied; target crop_frames=1536)

### S8 Preprocess P1+P2 — WARN
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 0 (kick) std=0.000 (expect ~1 post z-score)
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 1 (snare) std=0.000 (expect ~1 post z-score)
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 2 (hihat) std=0.000 (expect ~1 post z-score)
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 3 (tom) std=0.000 (expect ~1 post z-score)
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 4 (floor) std=0.000 (expect ~1 post z-score)
- MINI_L3000-V0T0-J00-SFZ-R0-L1-NONE: ch 7 (room) std=0.000 (expect ~1 post z-score)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 0 (kick) std=0.000 (expect ~1 post z-score)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 1 (snare) std=0.000 (expect ~1 post z-score)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 2 (hihat) std=0.000 (expect ~1 post z-score)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 3 (tom) std=0.000 (expect ~1 post z-score)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 4 (floor) std=0.000 (expect ~1 post z-score)
- MINI_L3058-V3T1-J01-SFZ-R0-L1-NONE: ch 7 (room) std=0.000 (expect ~1 post z-score)

### S9 Forward pass — PASS
- pred (blue) vs target (red) overlay per-bus; thr 0.1 dashed grey
