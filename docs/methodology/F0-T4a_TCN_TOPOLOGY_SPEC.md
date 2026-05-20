---
id: LIN-DT-SPEC-F0T4a
title: F0-T4a — Spec Topologia TCN Concreta
type: spec
status: LOCKED
phase: F0
domain: AI / Neural Engineering
version: 1.0.0
updated: 2026-05-20
tags: [tcn, topology, neural, F0-T4a]
related: [LIN-DT-SPEC-F0T2a, LIN-DT-DOSSIER-001, LIN-DT-CHKLST-001]
supersedes: []
---

# 🧠 F0-T4a — SPEC DI DETTAGLIO: TOPOLOGIA TCN CONCRETA
**Status:** LOCKED — Decision Lock 2026-05-20 (Executive Briefing F0-T4a)
**Riferimenti:** [`DOSSIER_TECNICO.md`](DOSSIER_TECNICO.md) §[2.2](DOSSIER_TECNICO.md#midi-output)/[2.3](DOSSIER_TECNICO.md#cymbals)/[6.1](DOSSIER_TECNICO.md#tcn)/[6.2](DOSSIER_TECNICO.md#loss) · [`MASTER_CHECKLIST.md` §1](../../MASTER_CHECKLIST.md#ai-neural) ·
[`F0-T2a` §3](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract) · [`MASTER_SCHEDULING.md` §6](../../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks) F0-T4a

> Questo documento traduce il Design Lock concettuale "Strided-Context TCN" in una **spec
> di rete implementabile**: numero di layer, kernel, dilatazioni, receptive field, shape
> dei tensori e teste d'uscita. È vincolante per `F0-T4b` (mini-prototipo + round-trip
> RTNeural). I valori marcati *baseline* sono iperparametri che `F0-T4b` può tarare sul
> mini-batch; la **struttura** della rete è invece bloccata.

---

## 0. Sintesi della decisione

| Voce | Decisione bloccata |
| :-- | :-- |
| `R_target` (frame-rate target) | **44100 / 128 = 344.53125 Hz** — ratifica del provvisorio [F0-T2a §3.4](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#r-target) |
| Famiglia architetturale | Strided encoder + **dilated causal TCN trunk** (1 solo grafo RTNeural) |
| Realizzazione del look-ahead | TCN causale + **ritardo d'ingresso = PDC** (~100 ms) |
| NN-Repeat / Sentinella-Scalpello a 2 rate | **Abbandonato** (vedi §6 — incoerenza sanata) |
| Teste d'uscita | onset[8] · velocity[8] · microtiming[8] · hihat_opening[1] → `flat-25` |

<a id="design-lock-fix"></a>
## 1. Incoerenza del Design Lock concettuale — sanata

[`DOSSIER §6.1`](DOSSIER_TECNICO.md#tcn) descriveva il "Comb-Filter Hack" come *Sentinella* `stride=4` (analisi a
"~11 kHz") + *Scalpello* `stride=1` ("massima risoluzione") fusi via **Nearest-Neighbor
Repeat**. Due problemi rilevati traducendo il concetto in spec:

1. **Numeri incoerenti col target.** Lo "Scalpello a massima risoluzione (44.1 kHz)"
   implicherebbe un'uscita a 44.1 kHz, non a `R_target ≈ 344 Hz`. La cifra "~11 kHz" è un
   artefatto **pre-R_target** (il documento concettuale precede [F0-T2a §3.4](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#r-target)).
2. **L'NN-Repeat lavora contro il suo scopo.** Il Comb-Filter Hack nasce *per* la
   compatibilità RTNeural; ma RTNeural non espone un layer di upsampling → l'NN-Repeat
   richiederebbe un'operazione custom in C++ e lo split del modello in due grafi RTNeural,
   reintroducendo il "codice inferenziale custom" che la doctrine voleva azzerare.

**Risoluzione (Decision Lock):** si conserva il *principio* Strided-Context — receptive
field grande a basso costo CPU, 100% RTNeural-nativo — e se ne corregge il *meccanismo*:
lo **strided encoder** porta l'audio raw sul frame-grid del target; il **trunk dilatato
causale** fornisce il receptive field grande tramite dilatazioni (non stride + upsampling).
Un solo grafo RTNeural, nessuna op custom → de-risca il round-trip del Gate L3.

<a id="r-target-ratifica"></a>
## 2. `R_target` — ratifica

`R_target` = **44100 / 128 = 344.53125 Hz** · periodo frame = **2.902 ms**.

- Coerente con il **Gaussian smear ±3 ms** ([`DOSSIER §6.2`](DOSSIER_TECNICO.md#loss)): un onset "sfocato" copre
  ~1 frame per lato.
- Margine anti-collisione: un frame contiene **un solo onset per bus**; a 2.9 ms i flam
  e i blast-beat del modulo Machine-Gun ([`DOSSIER §3`](DOSSIER_TECNICO.md#data-doctrine) / [`§10.1`](DOSSIER_TECNICO.md#training-set)) non collassano nello
  stesso frame, cosa che accadrebbe al frame-rate ADT standard di 100 Hz (10 ms).
- Stride totale **128 = 2⁷** → encoder pulito a sole conv strided.
- La **sample-accuracy** resta disaccoppiata da `R_target` (canale microtiming,
  [F0-T2a §3.4](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#r-target)): `R_target` definisce la griglia, non la precisione finale.

→ `output.target_frame_rate_hz` in [F0-T2a §3.4](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#r-target) passa da *provvisorio* a **ratificato**.

## 3. Topologia concreta

```
Input  [B, n_mic, n_sample]   ·   sample_rate 44100 Hz   ·   FP16 (dataset) → FP32 (training/inferenza)
  │
① Input-Agnostic Projection
      Conv1D kernel=1, stride=1,  in=8 → out=C
      I mic assenti sono zero-fill sugli 8 slot canonici (§4). Grafo statico (requisito RTNeural).
  │
② Strided Encoder Stem    44100 Hz → 344.53 Hz   (stride totale 128)
      4× Conv1D kernel=8, stride=[4, 4, 4, 2]   (Π stride = 128),  C → C,  attivazione ReLU
      Receptive field encoder ≈ 596 sample ≈ 13.5 ms
  │
③ Dilated Causal TCN Trunk    @ 344.53 Hz
      8 blocchi residui; ogni blocco = [Conv1D k=3 dilatata → ReLU → Conv1D k=3 dilatata → ReLU] + skip residuo
      dilatazioni per blocco: [1, 2, 4, 8, 16, 32, 64, 128]
      conv CAUSALI (past-only) — RTNeural le streamma stateful e Zero-Allocation
      Receptive field causale ≈ 511 frame ≈ 1.48 s di contesto passato
  │
④ Teste d'uscita    @ 344.53 Hz    (4× Conv1D kernel=1)
      onset       : C → 8   attivazione sigmoid   ∈ [0,1]
      velocity    : C → 8   attivazione sigmoid   ∈ [0,1]
      microtiming : C → 8   attivazione tanh      ∈ [-1,1]
      hihat_open  : C → 1   attivazione sigmoid   ∈ [0,1]
  │
Output   [n_frame, 8, 3]  +  [n_frame, 1]   ≡   layout `flat-25` di F0-T2a §3.3
```

- **Larghezza feature `C` = 32** *(baseline)* — tarabile da F0-T4b su Mac M5/MPS.
- Conteggio parametri stimato ≈ **80–100 k** (baseline `C=32`) — adatto a mini-batch su
  MPS e a runtime CPU Zero-Allocation.
- `n_frame = ceil(n_sample / 128)` — coerente con `n_frame = ceil(duration_s × R_target)`
  di [F0-T2a §3.4](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#r-target).

### 3.1 Allineamento col contratto dati F0-T2a
Le 4 teste si concatenano esattamente nel layout `flat-25` ([`F0-T2a §3.3`](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#target-tensor)): per il bus
`b ∈ [0,7]` colonna `3b`=onset, `3b+1`=velocity, `3b+2`=microtiming; colonna `24`=hihat
opening. Il data-loader fa già il reshape `cols 0:24 → [n_frame,8,3]` e `col 24 →
[n_frame]`: il modello produce direttamente i tensori nello stesso ordine.

## 4. Input agnostico — 8 slot canonici

Il modello ha **larghezza d'ingresso fissa = 8** (requisito di grafo statico RTNeural).
Le configurazioni microfoniche di [F0-T2a §2.3](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#mic-config) sono mappate su 8 slot canonici; gli slot
non usati sono **zero-fill**:

| Slot | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Etichetta canonica | kick | snare_top | snare_bot | tom | floor | oh_L | oh_R | room |
| `mono` | mix→0 | — | — | — | — | — | — | — |
| `solo_stereo` | — | — | — | — | — | mix_L→5 | mix_R→6 | — |
| `glyn_johns` | kick | snare→1 | — | — | — | oh_L | oh_R | — |
| `multitrack_full` | kick | snare_top | snare_bot | tom | floor | oh_L | oh_R | room |

L'**Input-Agnostic Projection** (Conv1D k=1) impara a estrarre la "verità" indipendentemente
dalla densità informativa ([`DOSSIER §2.1`](DOSSIER_TECNICO.md#input-agnostic)). L'assegnazione dei mic reali agli slot in fase
di plugin (UI) è materia di **F4**; qui si fissa solo il contratto del tensore.

## 5. Non-causalità / Look-ahead / PDC

- Il trunk è **causale**: nessun receptive field futuro intrinseco.
- Il **look-ahead ~100 ms** ([`DOSSIER §2.3`](DOSSIER_TECNICO.md#cymbals), [`MASTER_CHECKLIST §3`](../../MASTER_CHECKLIST.md#dsp) PDC) è realizzato come
  **ritardo d'ingresso pari al PDC**: l'intero plugin gira ~100 ms indietro, quindi la
  rete al frame `t` dispone dell'audio fino a `t + ~100 ms`. È la **stessa delay-line**
  del Chronos Engine già bloccato — nessuna superficie nuova.
- **Budget look-ahead:** ≤ 100 ms (≤ 4410 sample @ 44.1 kHz ≈ 34 frame @ 344.53 Hz).
- `latency_samples` **esatto** misurato da F0-T4b e scritto nell'header del Model Artifact
  (`F0-T8`); target di progetto = 4410 sample (100 ms), badge UI "MODE: MIXING GRADE ONLY".

## 6. Loss & Ground Truth

| Testa | Loss | Note |
| :-- | :-- | :-- |
| onset | **Asymmetric Focal Loss** | falso-positivo pesato **3×** la nota mancata ([`DOSSIER §6.2`](DOSSIER_TECNICO.md#loss)); target Gaussian-smeared σ ↔ ±3 ms |
| velocity | **L1 mascherata** | supervisione solo sui frame con onset attivo nel ground truth |
| microtiming | **L1 mascherata** | idem — solo sui frame con onset |
| hihat_opening | **L1 / MSE densa** | su ogni frame ([`DOSSIER §2.2`](DOSSIER_TECNICO.md#midi-output)) |

Loss totale = somma pesata; i **pesi inter-testa** sono iperparametri di F0-T4b.

<a id="l3-threshold"></a>
## 7. Soglia numerica Gate L3 — "metriche di onset significativamente non casuali"

Criterio di superamento del Gate L3 (parte metrica; la parte round-trip RTNeural è in
F0-T4b). Misurato sul **mini-holdout** del mini-batch Gold (F0-T2e):

| Metrica | Soglia | Scopo |
| :-- | :-- | :-- |
| Onset **F-measure** (finestra ±20 ms, media per-bus) | **≥ 0.80** | la rete apprende |
| F-measure su label **temporalmente shuffate** (controllo negativo) | **< 0.10** | il gap prova la non-casualità |
| **Timing-MAE** degli onset matchati | **< 5 ms** | il microtiming è informativo |
| **MAE** testa hihat_opening | **< 0.15** | la regressione continua apprende |

> ⚠️ Soglie di **de-risking architetturale**, non claim di prodotto. Nessun claim pubblico
> di accuratezza prima del Gate L4 (mandato permanente). Su un mini-batch è atteso un
> certo overfitting: l'obiettivo di L3 è escludere il "non apprende" e certificare
> l'esportabilità, non misurare l'accuratezza Studio-Grade.

## 8. Esportabilità RTNeural — note per F0-T4b

- `Conv1D` (kernel-1, strided, dilatato) e le attivazioni ReLU/sigmoid/tanh sono
  **nativi RTNeural** → encoder, trunk e teste sono esportabili.
- ⚠️ **Da verificare in F0-T4b (round-trip):** la gestione delle **skip-connection
  residue** del trunk (RTNeural privilegia grafi sequenziali). Se il parser RTNeural non
  assorbe il ramo residuo, F0-T4b valuta (a) la realizzazione del residuo come parte
  della topologia esportata, oppure (b) un blocco TCN senza skip esplicita. Decisione a
  valle dello smoke-test C++ — è esattamente il rischio che il Gate L3 esiste per
  intercettare *prima* del burn del credito.
- Le teste d'uscita multiple: F0-T4b verifica se esportarle come un'unica `Conv1D` C→25
  con attivazioni per-colonna oppure come 4 sotto-modelli.

## 9. Open items delegati a F0-T4b

1. Taratura di `C` (baseline 32) e dei pesi inter-testa della loss.
2. Lunghezza della finestra di training (crop fisso, baseline ~2¹⁸ sample ≈ 5.9 s).
3. Misura del `latency_samples` esatto e scrittura nell'header del Model Artifact.
4. Verifica del round-trip RTNeural (skip residue, teste multiple) — Gate L3.

---

## 10. Decision Lock (2026-05-20)
Approvato dal CEO (Executive Briefing F0-T4a, STRP-001):
1. ✅ `R_target` **ratificato** a 44100/128 ≈ 344.53 Hz.
2. ✅ Trunk **dilated causale**; abbandono del Sentinella/Scalpello a 2 rate + NN-Repeat
   (incoerenza §1 sanata).
3. ✅ Topologia 4-stadi (Input-Agnostic Projection → Strided Encoder → Dilated Causal TCN
   → 4 teste) bloccata; iperparametri *baseline* tarabili da F0-T4b.
4. ✅ Look-ahead realizzato come ritardo d'ingresso = PDC ~100 ms.
5. ✅ Loss e soglia numerica Gate L3 bloccate.

---
*Spec F0-T4a — STRP-001. **LOCKED 2026-05-20.** Vincolante per F0-T4b. Sblocca, con F0-T3,
il mini-prototipo TCN e il round-trip RTNeural (Gate L3).*
