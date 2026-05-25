# Listening Test ShittyKit — Findings

**Data:** 2026-05-25 (sessione post C=64 mixed-5kit FAIL)
**Origine:** Decision Lock CEO 2026-05-25 — discriminare "OOD strutturale" vs "pathology specifica" su ShittyKit val pool dopo che la pipeline diagnostica del mini-L3 ha saturato a val F = 0.099.

**Checkpoint:** `artifacts/mini_l3_tcn_p1p2_c64_mixed5kit.pt`
**Tool:** `tools/listening_test_shittykit.py`
**Output dir:** `docs/gates/F0-T4c_MINI_L3/listening_test_shittykit_2026-05-25/`

---

## TL;DR

**Il problema NON è cross-kit OOD. È un problema di calibrazione globale + collapse "predict-everywhere" sui bus non-kick.**

| Metric | ShittyKit val (vergine) | DRSKit train (in-dist) | Ratio |
|---|:--:|:--:|:--:|
| F_overall (threshold=0.1) | **0.056** | **0.057** | **1.02×** |
| Kick F per-bus | 0.111 | 0.080 | 0.72× |
| Snare F per-bus | 0.104 | 0.114 | 1.10× |
| Hihat F per-bus | 0.050 | 0.079 | 1.58× |

ShittyKit val è in linea con DRSKit train — la rete fa **lo stesso lavoro su entrambi gli split**.

## Reframing del verdetto

Le precedenti diagnosi attribuivano il floor 0.10 al "distribution shift kit→kit". Il listening test smentisce:

- **Non c'è cross-kit gap.** Il modello produce lo stesso F-overall sui kit train (DRSKit, in-distribution) e sul kit val "vergine" (ShittyKit).
- Le precedenti val F (0.066, 0.093, 0.099) erano **F dopo `tune_threshold`** che cerca il threshold ottimale per il val pool. Con threshold fissa 0.1 (default di produzione) il F crolla a 0.056.
- Il modello impara la struttura ma la sua **scala di confidence è troppo bassa** per il peak-picking default → l'apparente "lift cross-kit" da 0.049 → 0.099 era artefatto del tune.

## Cosa ha realmente imparato

| Bus | F-mean | FP/FN ratio (ShittyKit val) | Diagnosi |
|---|:--:|:--:|---|
| **kick** | 0.111 | **1.10** (bilanciato) | ✅ La rete discrimina correttamente — onset kick forte, transitorio riconoscibile |
| snare | 0.104 | 32.90 | 🔴 Predict-everywhere — confidence diffusa, mare di FP |
| hihat | 0.050 | 32.70 | 🔴 Predict-everywhere |
| tom_hi_mid | 0.012 | 2.49 | 🟡 Marginale (bus raro nel training) |
| floor | 0.028 | 32.92 | 🔴 Predict-everywhere |
| ride | 0.019 | 30.14 | 🔴 Predict-everywhere |
| crash_a | 0.000 | 23.00 | 🔴 Zero precision, qualche FP |
| crash_b_misc | 0.061 | 10.23 | 🟡 Borderline |

**Pattern:** la rete distingue il kick (bilanciato 1.10) ma "spara" predizioni a bassa confidence ovunque sugli altri bus → peak-picking con threshold 0.1 trova mare di FP, F crolla.

## Causa probabile

Il `LossConfig` corrente ha:
- `pos_weight` per-bus altissimo (cap a 1000 per `crash_a`/`crash_b_misc`, ratificato in F0-T4c B6b)
- `focal_gamma = 2` (default F0-T4a §6.2)
- `fp_to_fn_ratio` non punisce abbastanza i FP

La BCE bilanciata con `pos_weight=1000` spinge la rete a "non lasciare FN", anche al costo di micro-FP a tappeto. Risultato: i logit sono leggermente positivi sui frame off-onset → cross-entropy bassa → train loss converge a 0.36, ma la **scala di confidence è collassata sotto la soglia di peak-picking**.

## Mitigations (in ordine di priorità)

1. **Loss redesign:**
   - `pos_weight` cap conservativo (50-100, non 1000)
   - `focal_gamma 4` (punisce di più i FP soft)
   - `fp_to_fn_ratio > 1` per bus rari
2. **Peak-picking config:**
   - `min_distance` adattivo per bus
   - Threshold dinamico (percentile-based, es. top-N onset per sec)
3. **Calibrazione post-training:**
   - Temperature scaling per bus sul val pool
4. **Architecture:** F0-T4a C=32/64 ratificato — NON cambiare (la rete impara la struttura)

## Sblocco strategico

- F0-T4a (arch), F0-T4c (data fix), F0-T4d (P1+P2), F0-T16-post (aug pipeline) restano ratificati
- Il fix grad-clip resta acquisito (validato ep 110+ nei run 14:00 / 15:00 / 16:00)
- **B4 (durata MIDI ≥ 5 s) può essere ratificato** — l'architettura non è il problema, è la loss config
- **F2-T1 può essere sbloccato** — render Gold + augment + train con loss redesign
- **Burn Azure ($50-80) ha senso solo dopo loss redesign + listening test rifatto sul nuovo checkpoint**

## File generati

- `per_bus_summary.json` — aggregate stats per bus su 115 ShittyKit val + 30 DRSKit train
- `per_bus_comparison.png` — bar chart F per-bus + FP/FN ratio (predict-everywhere indicator)
- `waveform_comparison.png` — snare/hihat waveform + spettrogramma di 1 ShittyKit (worst) + 1 DRSKit
- `LISTENING_TEST_FINDINGS.md` — questo documento
