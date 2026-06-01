---
title: "F0-T20d — Scaling-curve (does F rise with data?) + the local-experiment ceiling"
tags: [F0-T20d, scaling, mini-l3, diagnostic, azure-decision]
status: DONE
---

# F0-T20d — Scaling-curve + the local-experiment ceiling

Ultimo esperimento della diagnostica «perché sempre 0.16» (sfida CEO 2026-05-31):
**la quantità di dati è la leva?** Costruita l'infrastruttura per scalare oltre il
muro RAM e misurata la curva F-vs-N. Tutto $0 Azure, locale.

## Infrastruttura costruita (commit di accompagnamento)
- `LazyGoldDataset` (`src/neural/data.py`): streaming da disco per-batch → toglie il
  cap RAM ~600 sample. `--lazy` nel trainer.
- `tools/build_scaling_dataset.py`: render N grooves GMD v1 distinti, single-kit
  (rotazione 4 kit DG), canonical F0-T18/T19. **Hardening disco/RAM**: trim grooves a
  6 s (i grooves GMD full-performance rendevano 85 MB e OOM-avano OrbStack), pre-check
  lunghezza senza render, hard-stop disco < 6 GB.
- Dataset: **640 train** (160 × 4 kit) + **43 val held-out IN-distribution** (stessi
  kit, grooves disgiunti → isola la scala dal muro OOD ShittyKit). 2.6 GB.

## Risultato (val F trainer-tuned, in-distribution, 100 epoche lazy)

| N train | val F |
| --: | --: |
| 160 | 0.063 |
| 320 | 0.079 |
| 640 | 0.070 |

**F NON sale con N** — 160→320 su un filo, 320→640 scende. Piatta a ~0.07.

## Interpretazione ONESTA (due confound seri)
1. **Under-training.** Il `longopt` (F0-T20c) ha mostrato che fittare ~500 grooves
   richiede **400+ epoche** (loss da 2.4 → 1.3 lentamente). A **100 epoche** tutti e
   tre i punti sono **sotto-allenati** → la curva piatta-bassa potrebbe essere
   l'under-training che domina, mascherando qualsiasi effetto di scala. Un test
   scala-a-convergenza (400+ ep × 3) costerebbe ore e resterebbe cappato a 640.
2. **Dilution canali rari.** Il GMD single-kit ha sidestick/ride_bell/crash quasi
   assenti (pos_weight al cap 1000) → F≈0 su quei canali → diluisce la media-su-9.
   Confond la metrica assoluta (ma non il trend, val costante).

→ La scaling-curve locale è **inconcludente** su "la scala aiuta": né la conferma né
la smentisce, per via dell'under-training a 100 ep e del cap a 640 sample.

## Il tetto degli esperimenti locali (sintesi di tutta la saga)
Tutto testato **con esperimenti** sul mini-L3, partendo dalla sfida del CEO:

| Leva | Esito |
| :-- | :-- |
| cross-kit / OOD | ❌ train ≈ val (nessun gap) |
| bug eval / pipeline | ❌ self-overfit 30 grooves → **F 0.68** |
| augmentation / count-masking | ❌ no-aug = 0.17 |
| capacità (C=128, 4×) | ❌ 0.17 |
| ottimizzazione (1200 ep) | ❌ loss asintota ~1.2 → F 0.18 |
| front-end mel | ❌ 0.137 (peggio) |
| **scala dati (160→640)** | ❌ piatta ~0.07 *(ma under-trained, inconcludente)* |

**Ciò che è DIMOSTRATO:**
- L'architettura **sa localizzare** (overfit 30 → 0.68; round-trip RTNeural L3 ok).
- **Nessuna leva locale rompe il floor** entro la scala raggiungibile in locale.
- La trascrizione di batteria **è imparabile a vera scala** (StemGMD/LarsNet: ~10 kit,
  1224 h, migliaia di grooves) — ma a scala 100-1000× quella locale.

**Ciò che NON è dimostrabile in locale:** che *questo* modello, a vera scala, superi il
floor. Il mini-L3 (centinaia di sample, training lento su MPS) non raggiunge il regime
in cui l'ADT funziona, e portarlo lì localmente è impraticabile (RAM/disco/tempo/dati).

## La decisione (risk choice del CEO)
Non possiamo *provare localmente* che i $200 funzioneranno. I fatti:
- **Pro Azure:** architettura validata in principio (overfit) + la letteratura dice
  che l'ADT funziona a scala (è *esattamente* il regime di F2-T3: ~100k+ sample, GPU
  vera, training lungo). Il render Gold è asset permanente comunque.
- **Contro Azure:** nessuna prova locale che il floor si rompa; rischio che la scala
  non basti e i $200 vadano in un modello che resta a F bassa.

È una scelta di rischio, ora esplicita e informata — non più "fede" né "rumore".
Opzioni residue a $0 prima di decidere: (a) scala-a-convergenza locale (400 ep × N,
ore, cap 640); (b) accettare il tetto locale e decidere su Azure.
