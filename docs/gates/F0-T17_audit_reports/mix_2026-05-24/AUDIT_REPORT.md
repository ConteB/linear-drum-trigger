# Audit report — Mixed-dataset 70/15/15 (2026-05-24)

Source-stratified analysis of the Gold output produced by `tools/render_mix_chunked.sh` on the mix `140 GMD + 30 rare + 30 chaos`. Complements the F0-T17 standard `data_audit` (`data_audit.report.{json,png}`) with a per-source breakdown — the F0-T17 gate aggregates across the whole directory, this report disambiguates the three layers.

**Total samples:** 585

**Layer mix (post-render):**

| Source | Samples | Share |
|--------|---------|-------|
| gmd | 405 |  69.2% |
| rare | 90 |  15.4% |
| chaos | 90 |  15.4% |

## 1. Bus class imbalance per source

`5%` is the F0-T17 minority threshold. A bus below it triggers loss-reweighting in F2-T3 (informative, not blocking).

| Bus | Label | gmd % | rare % | chaos % | Global % |
|---|---|---:|---:|---:|---:|
| 0 | kick | 14.57 | 15.15 | 10.50 | 11.97 |
| 1 | snare | 44.59 | 14.33 | 13.05 | 20.70 |
| 2 | hihat |  9.69 | 37.53 | 13.27 | 15.06 |
| 3 | tom_hi_mid | 12.22 |  3.33 | 14.17 | 12.52 |
| 4 | floor_tom | 12.45 |  2.65 | 14.59 | 12.78 |
| 5 | ride |  4.90 | 14.50 | 11.79 | 10.44 |
| 6 | crash_a |  0.05 |  0.51 | 11.77 |  7.75 |
| 7 | crash_b_misc |  1.53 | 11.99 | 10.87 |  8.77 |

## 2. Onset density per source (hits/sec)

Median density tells us how *busy* the grooves are — a GMD groove typically lands 10-25 hits/s, the chaos layer should push much higher (λ × 8 buses).

| Source | n | median | p25 | p75 | min | max |
|---|---:|---:|---:|---:|---:|---:|
| gmd | 405 |   5.4 |   4.1 |   7.0 |   1.5 |  10.9 |
| rare | 90 |   5.9 |   4.9 |   6.7 |   3.9 |   8.7 |
| chaos | 90 |  44.5 |  39.1 |  50.4 |  26.3 |  62.2 |

## 3. Sample duration distribution

GMD is filtered to `duration ≤ 6 s` (OrbStack memory budget); the chaos layer samples Uniform[2, 6] s; the rare-emphasis layer emits 2-3 bar grooves at multiple BPM tiers.

| Source | n | mean | median | min | max |
|---|---:|---:|---:|---:|---:|
| gmd | 405 |  2.89 |  2.44 |  0.98 |  6.10 |
| rare | 90 |  5.65 |  5.50 |  3.72 |  8.34 |
| chaos | 90 |  4.34 |  4.23 |  2.76 |  6.20 |

## 4. Hi-Hat articulation segments per source

Each transition between closed/pedal/open counts as one segment — a high `open` count means the layer uses opens often; a low `pedal` count means the foot ostinato is absent.

| Source | closed | pedal | open |
|---|---:|---:|---:|
| gmd | 390 | 221 | 24 |
| rare | 147 | 129 | 26 |
| chaos | 644 | 604 | 571 |

## 5. Interpretation

- **Layer-B (rare emphasis) goal:** lift crash/china/ride/tom/splash above the GMD baseline. Compare bus 6-7 (`ride`, `crash_a`) and bus 7 (`crash_b_misc`, including china + splash) in the per-source table — the `rare` column should be markedly higher than `gmd`.

- **Layer-C (Machine-Gun Chaos) goal:** break grid-position shortcuts. The chaos density should be near-uniform across buses (no bus dominates) and the velocity histogram on rare buses should approach flat (Uniform[40, 120]) rather than peaked.

- **Global gate (5%):** every bus is above the F0-T17 minority threshold at the aggregate level — no loss-reweighting required for F2-T3 by data-imbalance criteria.


*See `panels.png` for the visual.*
