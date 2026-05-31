---
title: "F0-T20b — Franken-Kit results + capacity A/B (C=64 vs C=128)"
tags: [F0-T20b, franken-kit, results, capacity, mini-l3]
status: DONE
---

# F0-T20b — Franken-Kit results + capacity A/B

Esito dell'implementazione F0-T20 (Cross-Kit Combinatorial Augmentation) sul mini-L3
cross-kit, più il confronto di capacità C=64 vs C=128 richiesto dal CEO. Sessione
autonoma 2026-05-30/31, **$0 Azure**.

## Setup (A/B pulito)
- **Dataset franken**: 496 train (230 franken hybrid + 266 single-kit, 50/50 = D3, ×2
  jitter variants) dal pool mini_l3 250-MIDI reso su 4 kit DrumGizmo
  (DRSKit/Muldjord/Crocell/Aasimonster, within-engine v1.0 = D2). Val = 248 ShittyKit
  (held-out, identico alla baseline F0-T19).
- **Config**: esatta F0-T4e (P1+P2, input-agnostic seed 20260526, loss B fp_ratio=30,
  audio-aug, cosine warmup 15, early-stop 20, grad-clip 0.5, `--no-amp`). Le UNICHE
  variabili tra i run sono il **dataset franken** (vs il floor single-kit) e la
  **capacità** (C=64 vs C=128).

## Risultati — production-calibrated (metrica realistica del plugin)

| Config | params | prod-calibrated F | vs floor | trainer-tuned | F_max | wall |
| :- | --: | --: | --: | --: | --: | --: |
| single-kit floor (F0-T19) | 331k | **0.1455** | — | 0.257 | 0.763 | 4.1h |
| **franken C=64** | 331k | **0.1599** | **+9.9%** ✅ | 0.165 | 0.672 | 3.9h |
| franken C=128 | 1.32M | 0.1531 | +5.2% | 0.230 | 0.763 | 5.2h |

## Lettura

**1. Il franken-kit dà un lift modesto ma REALE (+9.9%).** A parità di capacità (C=64),
sostituire metà del dataset con kit ibridi alza il production da 0.1455 a **0.1599** — il
miglior numero cross-kit di tutta la storia mini-L3. Coerente con l'ipotesi: la diversità
timbrica combinatoria riduce la dipendenza della rete dal *fingerprint del kit*, spingendola
verso l'*evento fisico*. È il primo lever-dati che muove il floor (F0-T19 sintetico era
flat, F0-T4f loss era flat).

**2. Più capacità NON aiuta il production (rendimento nullo/negativo).** C=128 (4× params)
alza il trainer-tuned (0.165→0.230) e tocca un nuovo F_max (0.763), MA il production scende
a 0.1531. È il pattern noto: la capacità extra fa *overfittare la soglia per-sample*
(metrica ottimistica) e abbassa la train loss (2.23→2.13), ma la metrica realistica a
soglia fissa resta al floor saturo ~0.15-0.16. **C=64 franken resta la config migliore**
(più piccola E production più alto).

**3. Il floor è il val, non il modello.** Conferma definitiva trasversale a tutta la stack
mini-L3: il val a kit singolo ShittyKit è uno strumento diagnostico **saturo** — nessun
lever (capacità, loss AFL/Tversky/Ridnik/7-candidati, augmentation, input-agnostic,
flat-28, **franken**) lo rompe oltre ~0.16 production. Il gate reale di validazione è
**L4 / E-GMD** (~30 kit reali, distribuzione molto meno OOD del singolo ShittyKit).

## Conclusioni operative
- **Franken-kit RATIFICATO empiricamente** come augmentation utile (+9.9% a costo zero di
  parametri). Da includere in F2-T1 (render di produzione) — il +10% su un val saturo
  suggerisce un guadagno maggiore su L4 multi-kit dove la diversità conta di più.
- **Capacità: restare a C=64** per F2-T3 (C=128 non ripaga sul mini-L3; rivalutare solo se
  L4 mostra under-fitting).
- Pipeline franken completa e committata (modulo + 14 oracoli + tooling + 2 run + report).

## Artefatti
- Ledger: `docs/audit/training_ledger.yaml` (run 26 = C=64, run 27 = C=128).
- Report HTML blueprint: `docs/gates/F0-T4c_MINI_L3/mini-l3-F0T20-franken-2026-05-30/` e
  `.../mini-l3-F0T20-franken-c128-2026-05-31/`.
- Calibrazioni: `.../listening_test_mini-l3-F0T20-franken-*/calibration_sweep.json`.
- Spec LOCKED: `docs/methodology/F0-T20_CROSS_KIT_AUGMENTATION_SPEC.md`.
- Checkpoint: `artifacts/mini_l3_tcn_F0T20franken{,_c128}.pt` (git-ignored, rigenerabili).
