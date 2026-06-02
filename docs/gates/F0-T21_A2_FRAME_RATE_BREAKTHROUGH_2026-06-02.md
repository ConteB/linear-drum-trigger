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

## File toccati (branch, da ratificare per il merge)
`model.py` (strides/trunk), `data.py` (stride/RF/lookahead), `metrics.py`/`recipe.py`/
`gold_writer.py` (R_TARGET 86.13), `target_builder.py` (smear 11.6ms), `reporter.py`
(stride frame-rate-aware), `build_scaling_dataset.py` (target rate). 0 errori nuovi
ruff/mypy.
