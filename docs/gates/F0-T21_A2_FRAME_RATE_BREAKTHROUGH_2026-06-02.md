---
title: "F0-T21 A1+A2 — frame-rate root cause: the 86Hz breakthrough"
tags: [F0-T21, frame-rate, breakthrough, generalization, 86hz, azure-gate]
status: DONE
---

# F0-T21 A1+A2 — the frame-rate root cause (86Hz breakthrough)

STRP-001 candidate A, eseguito su branch `exp/f0t21-a2-86hz`. Risolve la domanda
aperta dalla sfida del CEO («0.16 è random»). Tutto $0 Azure, locale.

## A1 — loss (escluso come radice, ma diagnostico chiave)
Weighted-BCE moderata (γ=0, fp_ratio=1, pos_weight cap 8) a 344Hz, N=640 convergenza:
- val F **0.094** (vs afl 0.080, +18%) — la loss aiuta poco.
- **Smoking gun:** train_loss 0.15 (fitta la loss) ma train F **0.057** — la loss si
  minimizza **predicendo quasi-silenzio** (onset <6% dei frame a 344Hz). Il problema non
  è la loss: è la **sparsità degli onset** → frame rate.

## A2 — frame rate 344Hz → 86Hz (la radice)
Topologia ri-derivata coerente a 86Hz (stride 4×4×4×8=512, trunk RF ~255f≈3s, lookahead
9f≈100ms, R_target 86.13, **smear 3ms→11.6ms = ~1 frame**). A 86Hz la densità onset
~3× → **pos_weight moderato** (kick 33/snare 22/hihat 17 vs 130/88/112 a 344Hz). N=640,
bce, convergenza:

| modello (stesso dataset, stessa loss bce) | val F | note |
| :-- | --: | :-- |
| 344Hz | 0.094 | sotto-confident |
| **86Hz** | **0.157** | **+67% vs 344, +96% vs floor afl 0.080** |
| train F (86Hz) | ~0.10 | ≈ val → **nessun overfitting** |

**Il frame rate ERA la radice.** A 344Hz gli onset sono troppo sparsi → la loss è
dominata dalla classe-zero → il modello impara a spalmare (sotto-confident) e **non può
imparare**, mascherando ogni altra leva. A 86Hz (densità+pos_weight moderati) la rete
**impara e generalizza** (train≈val, nessun gap di overfitting).

## Implicazione strategica (positiva)
1. **Primo lever che muove il floor sostanzialmente** (+96%); tutto il resto era ±10%
   di rumore attorno a 0.08.
2. **Il modello ora generalizza** (train≈val) ed è **data-limited**, non più
   memorizzazione-bound. → **più dati ORA dovrebbero aiutare** → la scala torna
   credibile → **Azure F2-T3 giustificato con la ricetta a 86Hz.**
3. Allinea alla ricetta ADT provata (~100Hz). Il microtiming sub-frame resta nella testa
   dedicata.

## Gate / prossimi passi
- ⏳ **Conferma scala-a-86Hz** (in corso): scaling-curve N=160/320 vs 640 a 86Hz. Se val
  F sale con N → conferma data-limited → Azure.
- Candidati residui per ulteriore lift: B (log-mel multi-res), C (CRNN causale).
- Adozione: il branch `exp/f0t21-a2-86hz` va merge-ato con amendment a `F0-T4a` (frame
  rate/stride/trunk/smear) + DOSSIER §6 + re-gen del Gold a 86Hz per F2-T1.

## B + C — front-end / decoder candidates @86Hz (2026-06-03)
Stesso dataset (N=640 GMD-v1 single-kit), stessa loss bce, 300ep fp32 MPS, C=64.
Unica variabile = il front-end / decoder.

| candidato | val F | verdetto |
| :-- | --: | :-- |
| A2 raw (strided encoder) | 0.157 | baseline 86Hz |
| **B log-mel singola** (n_fft 512) | **0.174** | **+11% — vince** |
| B log-mel multi-res (1024/2048/4096 ≈ 23/46/92ms) | 0.166 | NIENTE lift vs singola (anzi −0.008) |
| C CRNN (GRU causale post-trunk) | 0.086 | FAIL — la causalità annulla il beneficio RNN |

**Conclusione candidati B/C:** la log-mel **singola** è il miglior front-end (allineato alla
ricetta ADT). La multi-risoluzione — pur essendo la ricetta ADT *piena* — non aggiunge nulla a
questa scala; il CRNN causale fallisce (un RNN unidirezionale senza look-back perde il vantaggio
sequenziale, e il real-time vieta il bidirezionale). I tre front-end raw/multi-res/single
(0.157/0.166/0.174) restano dentro la **banda di rumore ~0.16-0.17** già diagnosticata: il
*frame rate* (A2) resta l'unica leva che ha mosso davvero il floor. **Tuning locale del
front-end saturo.** Ricetta vincente: **86Hz + log-mel singola + weighted-BCE = 0.174**.

## Scaling-curve @86Hz — conferma del gate (2026-06-03)
Ricetta vincente (single log-mel + bce, C=64, 300ep), val ShittyKit, sottoinsiemi del
pool 640 (4 kit DG GMD-v1) — **nessun nuovo render, zero rischio disco**:

| N (train grooves) | val F |
| --: | --: |
| 160 | 0.158 |
| 320 | **0.174** |
| 640 | 0.174 |

**Sale 160→320 (+0.016) poi si appiattisce.** Il conteggio dei grooves **satura presto**
(~0.174 a N=320) su un pool a **bassa diversità di kit** (4 kit DG, 1 kit val). Lettura
strategica: a 86Hz il modello generalizza e migliora con i dati, ma il lever che conta non
è il *numero di grooves* bensì la **diversità timbrica/di kit**. Il piano Azure F2-T1
(1.5 TB, ~roster completo + franken-kit aug = massima diversità) resta quindi giustificato,
ma il razionale è **diversità**, non semplice scala di conteggio. Il floor locale ~0.17 è
un artefatto del val a kit singolo estremamente OOD (ShittyKit) — il gate reale resta
**L4 / E-GMD** (~30 kit, molto meno OOD).

**Decisione aperta (CEO):** adottare la ricetta 86Hz + log-mel singola + weighted-BCE
(merge `exp/f0t21-a2-86hz` + amendment F0-T4a frame-rate/stride/smear + re-gen Gold 86Hz
per F2-T1) e procedere allo scale Azure puntando sulla diversità di kit — vs. ulteriori
leve locali (tutte ormai in banda di rumore).

## File toccati (branch, da ratificare per il merge)
`model.py` (strides/trunk), `data.py` (stride/RF/lookahead), `metrics.py`/`recipe.py`/
`gold_writer.py` (R_TARGET 86.13), `target_builder.py` (smear 11.6ms), `reporter.py`
(stride frame-rate-aware), `build_scaling_dataset.py` (target rate). 0 errori nuovi
ruff/mypy.
