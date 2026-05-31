---
title: "F0-T20c — Mel-spectrogram front-end A/B + the mini-L3 floor diagnostic"
tags: [F0-T20c, mel, frontend, mini-l3, diagnostic, architecture]
status: DONE
---

# F0-T20c — Mel front-end A/B + mini-L3 floor diagnostic

Su richiesta del CEO (2026-05-31, sfida «0.16 è praticamente random»): provare un
**front-end mel-spectrogram** al posto dell'encoder strided sul raw audio, e — più in
generale — capire *perché* il mini-L3 resta inchiodato a ~0.16 con qualsiasi leva.
Tutto $0 Azure, locale.

## Implementazione (commit di accompagnamento)
- `src/neural/model.py`: `TCNConfig.frontend ∈ {"raw","mel"}`. Con `mel`, log-mel
  (`torchaudio.MelSpectrogram`, n_fft=512, n_mels=64, **hop=128 → frame rate diretto**)
  sostituisce `projection + StridedEncoder`, mantenendo **trunk + heads identici** =
  A/B pulito del solo front-end. Streamabile (look-ahead n_fft/2 ≈ 5.8 ms ≪ PDC).
- `tools/mini_l3_train.py`: flag `--frontend {raw,mel}`.
- 0 errori ruff/mypy nuovi (model.py ha 1 errore Any-return pre-esistente).

## Risultato A/B (496 train / 248 val ShittyKit, config identica, unica var = front-end)

| metrica (comparabile) | raw-audio (F0-T4a) | **mel** |
| :-- | --: | --: |
| val F trainer-tuned | 0.165 | **0.137** |
| loss plateau (300 ep, LR cost.) | ~1.31 | **~1.47** |
| train F ≈ val F | 0.16 ≈ 0.16 | 0.04 ≈ 0.03 *(thr fisso 0.3, non calibrato — conta l'uguaglianza)* |

**Il front-end mel NON aiuta — anzi è marginalmente peggiore** (loss plateau più alta,
val F più bassa). Train F ≈ val F anche col mel → non fitta nemmeno i 496.

## Il quadro diagnostico completo (tutto falsificato, testato non assunto)

Sfida del CEO ⇒ una settimana di "miglioramenti" ~0.16 era **rumore**, non progresso.
Cause escluse **una per una, con esperimenti**:

| Ipotesi | Test | Esito |
| :-- | :-- | :-- |
| Cross-kit / OOD | train F vs val F | ❌ train ≈ val ≈ 0.16 (no gap) |
| Bug eval/pipeline | self-overfit 30 grooves no-aug | ❌ **F 0.68** → pipeline sana, rete sa localizzare |
| Augmentation / count-masking | no-aug a scala piena (496) | ❌ 0.17 ≈ con-aug 0.16 |
| Capacità | C=128 (4× params) | ❌ 0.17, loss uguale |
| Ottimizzazione (epoche/LR) | 1200 ep, LR costante, no early-stop | ❌ loss asintota ~1.2, F resta 0.18 |
| **Front-end (mel)** | mel vs raw, stesso tutto | ❌ 0.137, leggermente peggio |

**Diagnosi residua (l'unica non smentita): SCALA DEI DATI.** Il modello **memorizza 30
grooves (F 0.68) ma non riesce a imparare la funzione generale da 496** (train≈val≈0.16,
loss plateau ~1.2-1.5), *indipendentemente da architettura/front-end/capacità/loss/aug/
ottimizzazione*. È il classico **interpolation threshold**: 496 sono troppi per
memorizzare, troppo pochi per generalizzare. Nessuna leva *architetturale* lo rompe
perché il limite è la **quantità di dati diversi**.

## Cosa NON sappiamo ancora (e come saperlo)
Se è davvero scala, allora **più dati → F più alta**. È l'unica leva non testata. La
prova decisiva è la **scaling-curve**: rendere un dataset locale molto più grande
(1500-4000 sample dai 1150 GMD × kit) + val held-out **in-distribution**, allenare a
scale crescenti.
- Se F sale con i dati → la scala è la leva, **F2-T3 al vero scale funzionerà → Azure
  giustificato**.
- Se F resta ~0.16 a 4000 sample → limite reale architettura/feature → **NON spendere
  Azure**, ripensare il modello.

## Note di onestà
- L'architettura **non è rotta** (overfit 30→0.68, round-trip RTNeural L3 ok). La
  trascrizione di batteria è imparabile a scala (StemGMD/LarsNet).
- Il mel *as implemented* non aiuta; un mel più ricco (più mels, log-mel normalizzato)
  *potrebbe* dare margini, ma il pattern train≈val-non-fitta-496 è identico → il collo
  non è il front-end.
- **Raccomandazione**: scaling-curve locale come gate prima di qualsiasi burn Azure.
