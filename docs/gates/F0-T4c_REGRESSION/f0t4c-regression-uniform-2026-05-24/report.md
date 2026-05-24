# F0-T4c regression test — self-overfit

**Decision Lock:** CEO 2026-05-24 — B1+B2+B3+B6a+B6b ratified.
**Spec:** `docs/methodology/F0-T4c_DATA_PIPELINE_FIXES_SPEC.md`
**Run:** `f0t4c-regression-uniform-2026-05-24` · device=mps · 600 epochs · 51.1 s wall

## Pass conditions

- F_max ≥ 0.80 · **PASS** — got `0.958` on `LOCAL_RND124-V3T1-J02-DGZ-R0-L1-NONE`
- F_crash_a ≥ 0.30 · **PASS** — got `1.000` (max over 3 crash-bearing sample)
- timing_mae ≤ 5 ms on best-F · **PASS** — got `0.64 ms`

## Overall: **PASS ✅**

## Per-sample F-measure

| key | crash_a? | F_mean | F_crash_a | timing_mae_ms |
| :-- | :--: | --: | --: | --: |
| `LOCAL_RND124-V3T1-J02-DGZ-R0-L1-NONE` | ✓ | 0.958 | 1.000 | 0.64 |
| `LOCAL_RND124-V0T0-J00-DGZ-R0-L1-NONE` | ✓ | 0.957 | 1.000 | 0.83 |
| `LOCAL_RND124-V3T1-J01-DGZ-R0-L1-NONE` | ✓ | 0.943 | 1.000 | 0.32 |
| `LOCAL_RND093-V3T1-J02-DGZ-R0-L1-NONE` |  | 0.924 | nan | 1.04 |
| `LOCAL_RND093-V3T1-J01-DGZ-R0-L1-NONE` |  | 0.865 | nan | 1.04 |
| `LOCAL_RND093-V0T0-J00-DGZ-R0-L1-NONE` |  | 0.863 | nan | 0.64 |
| `LOCAL_RND092-V0T0-J00-DGZ-R0-L1-NONE` |  | 0.857 | nan | 0.32 |
| `LOCAL_RND092-V3T1-J02-DGZ-R0-L1-NONE` |  | 0.833 | nan | 0.68 |
| `LOCAL_RND092-V3T1-J01-DGZ-R0-L1-NONE` |  | 0.778 | nan | 0.22 |
| `LOCAL_RND094-V3T1-J02-DGZ-R0-L1-NONE` |  | 0.766 | nan | 1.02 |
| `LOCAL_RND094-V3T1-J01-DGZ-R0-L1-NONE` |  | 0.503 | nan | 1.02 |
| `LOCAL_RND094-V0T0-J00-DGZ-R0-L1-NONE` |  | 0.492 | nan | 1.45 |
| `LOCAL_RND003-V3T1-J02-DGZ-R0-L1-NONE` |  | 0.052 | nan | 14.80 |
| `LOCAL_RND003-V3T1-J01-DGZ-R0-L1-NONE` |  | 0.051 | nan | 14.90 |
| `LOCAL_RND003-V0T0-J00-DGZ-R0-L1-NONE` |  | 0.050 | nan | 15.51 |
| `LOCAL_RND045-V3T1-J01-DGZ-R0-L1-NONE` |  | 0.038 | nan | 17.55 |
| `LOCAL_RND045-V3T1-J02-DGZ-R0-L1-NONE` |  | 0.036 | nan | 16.17 |
| `LOCAL_RND045-V0T0-J00-DGZ-R0-L1-NONE` |  | 0.034 | nan | 16.83 |
