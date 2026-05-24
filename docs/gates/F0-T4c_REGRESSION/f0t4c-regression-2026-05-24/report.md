# F0-T4c regression test — self-overfit

**Decision Lock:** CEO 2026-05-24 — B1+B2+B3+B6a+B6b ratified.
**Spec:** `docs/methodology/F0-T4c_DATA_PIPELINE_FIXES_SPEC.md`
**Run:** `f0t4c-regression-2026-05-24` · device=mps · 600 epochs · 51.1 s wall

## Pass conditions

- F_max ≥ 0.80 · **PASS** — got `0.958` on `LOCAL_RND124-V3T1-J02-DGZ-R0-L1-NONE`
- F_crash_a ≥ 0.30 · **PASS** — got `1.000` (max over 3 crash-bearing sample)
- timing_mae ≤ 5 ms on best-F · **PASS** — got `0.64 ms`

## Overall: **PASS ✅**

## Per-sample F-measure

| key | crash_a? | F_mean | F_crash_a | timing_mae_ms |
| :-- | :--: | --: | --: | --: |
| `LOCAL_RND124-V3T1-J02-DGZ-R0-L1-NONE` | ✓ | 0.958 | 1.000 | 0.64 |
| `LOCAL_RND124-V0T0-J00-DGZ-R0-L1-NONE` | ✓ | 0.957 | 1.000 | 0.41 |
| `LOCAL_RND124-V3T1-J01-DGZ-R0-L1-NONE` | ✓ | 0.943 | 1.000 | 0.32 |
| `LOCAL_RND092-V0T0-J00-DGZ-R0-L1-NONE` |  | 0.927 | nan | 1.32 |
| `LOCAL_RND092-V3T1-J02-DGZ-R0-L1-NONE` |  | 0.925 | nan | 0.44 |
| `LOCAL_RND093-V3T1-J02-DGZ-R0-L1-NONE` |  | 0.924 | nan | 0.93 |
| `LOCAL_RND092-V3T1-J01-DGZ-R0-L1-NONE` |  | 0.892 | nan | 1.54 |
| `LOCAL_RND093-V3T1-J01-DGZ-R0-L1-NONE` |  | 0.865 | nan | 0.41 |
| `LOCAL_RND093-V0T0-J00-DGZ-R0-L1-NONE` |  | 0.863 | nan | 0.54 |
| `LOCAL_RND094-V3T1-J02-DGZ-R0-L1-NONE` |  | 0.766 | nan | 0.68 |
| `LOCAL_RND094-V3T1-J01-DGZ-R0-L1-NONE` |  | 0.503 | nan | 0.34 |
| `LOCAL_RND094-V0T0-J00-DGZ-R0-L1-NONE` |  | 0.500 | nan | 0.54 |
| `LOCAL_RND003-V3T1-J02-DGZ-R0-L1-NONE` |  | 0.043 | nan | 16.35 |
| `LOCAL_RND003-V3T1-J01-DGZ-R0-L1-NONE` |  | 0.043 | nan | 17.41 |
| `LOCAL_RND003-V0T0-J00-DGZ-R0-L1-NONE` |  | 0.042 | nan | 17.11 |
| `LOCAL_RND045-V3T1-J01-DGZ-R0-L1-NONE` |  | 0.032 | nan | 15.96 |
| `LOCAL_RND045-V3T1-J02-DGZ-R0-L1-NONE` |  | 0.030 | nan | 17.00 |
| `LOCAL_RND045-V0T0-J00-DGZ-R0-L1-NONE` |  | 0.029 | nan | 16.25 |
