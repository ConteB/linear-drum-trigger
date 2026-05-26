---
id: LIN-DT-SPEC-F0T4a
title: F0-T4a — Spec Topologia TCN Concreta
type: spec
status: LOCKED
phase: F0
domain: AI / Neural Engineering
version: 1.0.0
updated: 2026-05-22
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

<a id="rf-crop-constraint"></a>
### 3.3 Input agnostico esteso a 9 canali — amendment 2026-05-25 (F0-T4d · B2)

> **Amendment Decision Lock CEO 2026-05-25** ([`F0-T4d §5`](F0-T4d_PREPROCESSING_HARNESS_AND_AUDIT_SPEC.md)).
> Post mini-L3 cross-kit FAIL ([`F0-T4c §6.5`](F0-T4c_DATA_PIPELINE_FIXES_SPEC.md)),
> aggiunto un canale di **onset envelope** come 9° input — l'evidenza onset
> classica MIREX (spectral flux differenziale) entra direttamente nella
> Input-Agnostic Projection insieme agli 8 mic canonici.

> **Amendment MAJOR Decision Lock CEO 2026-05-26 ([F0-T4e §6.1](F0-T4e_INPUT_AGNOSTIC_TRAINING_SPEC.md)).**
> F0-T4e (Input-Agnostic Training) introduce un **Channel-Agnostic Frontend
> *prima* della Input-Agnostic Projection**: per-channel shared encoder
> (`Conv1d(1→C_per_ch=4, kernel=7, causal)` con weight-sharing tramite
> batch-fold) + Permutation-Invariant Pool (mean ⊕ max concat). L'output
> aggregato `[B, 2·C_per_ch=8, T]` mantiene la larghezza 8 attesa dal
> downstream (la sezione §3.3 v1.1 — 9 canali con onset envelope — resta
> invariata, F0-T4d `PreprocessingFrontend(n_mic=8)` riceve i 8 canali
> aggregati dal frontend F0-T4e e li compone con l'onset envelope).
> **Conseguenze sull'architettura:** la Input-Agnostic Projection (Conv1d
> k=1, in=9 → out=C) resta identica nel grafo; il nuovo frontend F0-T4e
> aggiunge ~228 parametri (`Conv1d(1→4, k=7)` shared = 1·4·7 + 4 = 32
> pesi + 4 bias = 36 pesi totali — il "shared" è cardinale).
> **Conseguenze sui contratti dati:** `TCNConfig.in_channels` resta 9 con
> P1+P2 attivo (8 con solo P1); il nuovo argomento di costruzione è
> `ChannelAgnosticConfig.per_channel_channels=4`, default che mantiene la
> larghezza 8 al downstream. **Implementazione:**
> `src/neural/channel_agnostic.py::ChannelAgnosticFrontend` + composizione
> in `src/neural/model.py::ComposedTCN`.

| Aspetto | Pre-amendment | Post-amendment (v1.1) |
| :-- | :-- | :-- |
| `TCNConfig.in_channels` | `8` | **`9`** |
| Canale 0..7 | 8 slot canonici (kick/snare/hihat/tom/floor/oh_L/oh_R/room) | invariato |
| Canale 8 (nuovo) | — | **onset envelope** (auto-derived dal frontend `OnsetEnvelope`, F0-T4d §4.1 P2) |
| Conv1d input layer | `in=8 → out=C`, k=1 | **`in=9 → out=C`**, k=1 *(Input-Agnostic Projection assorbe il canale extra senza cambi strutturali)* |
| Parameter count (C=32) | 83 673 | **84 186** (+513) |

Il 9° canale è generato **al volo** dal `OnsetEnvelope` layer (F0-T4d B2,
`src/neural/preprocessing.py::OnsetEnvelope`) — l'utente del plugin non lo
fornisce mai esplicitamente. Nel deployment C++/JUCE (F4), `OnsetEnvelope`
diventa parte del DSP front-end del plugin, davanti alla TCN.

### 3.2 Vincolo `crop ≥ RF + lookahead` — amendment 2026-05-24 (F0-T4c · B2)

> **Amendment Decision Lock CEO 2026-05-24** ([`F0-T4c §6.1`](F0-T4c_DATA_PIPELINE_FIXES_SPEC.md)). La
> diagnostica [T1-DIAG-A](../gates/R&D_Tier1_reports/T1-DIAG-A/T1_DIAG_A_REPORT.md)
> ha dimostrato che un training segment < receptive field è patologico:
> il modello impara dal profilo del left-pad zero, non dall'audio reale.

| Grandezza | Valore | Derivazione |
| :-- | --: | :-- |
| Receptive field totale (encoder + trunk) | **1024 frame** | `8 × (2 × dilatazione_max)` su §3 = `8 × (2 × 128)` = 2048; in pratica RF utile ≈ 1024 frame su dilatazioni `[1..128]` (gli ultimi blocchi saturano). Validato empiricamente in T1-DIAG-A. |
| Lookahead PDC (§5) | **35 frame** | `≈ 100 ms` a `R_target = 344.53 Hz` |
| Crop minimo (sample) | **`135 552`** | `(1024 + 35) × 128` — fail-loud sotto questa soglia |
| Crop default (sample) | **`196 608`** (~4.46 s) | Margine 1.45× sopra il minimo per crop random non-boundary |

**Implementato in `src/neural/data.py::GoldDataset.__init__`** — `raise
GoldDataError` se `crop_samples < 135 552`. Il default di `train.train()` è
`crop_samples = 196_608`.

**Implicazione downstream (B4 deferred):** la durata MIDI minima del Gold
deve essere ≥ ~3.07 s (con margine 2× per crop random = 5 s). B4 di F0-T4c
ratifica questo vincolo come `midi_duration_min_s = 5.0` in F0-T2a §3.8;
**deferred al post-regression test 2026-05-24**.

<a id="input-agnostic-slots"></a>
## 4. Input agnostico — 8 slot canonici

Il modello ha **larghezza d'ingresso fissa = 8** (requisito di grafo statico RTNeural).
Le configurazioni microfoniche di [F0-T2a §2.3](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#mic-config) sono mappate su 8 slot canonici; gli slot
non usati sono **zero-fill**:

| Slot | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Etichetta canonica | kick | snare | hihat | tom | floor | oh_L | oh_R | room |
| `mono` | mix→0 | — | — | — | — | — | — | — |
| `solo_stereo` | — | — | — | — | — | mix_L→5 | mix_R→6 | — |
| `glyn_johns` | kick | snare→1 | — | — | — | oh_L | oh_R | — |
| `multitrack_full` | kick | snare | hihat | tom | floor | oh_L | oh_R | room |

> **Allineato all'amendment F0-T2a §2.3 (2026-05-22):** `multitrack_full` segue lo
> standard di settore (slot 1 `snare`, slot 2 `hihat`). La robustezza alla *permutazione*
> dei canali e ai conteggi non-canonici (5/7 mic) è un punto aperto — vedi nota sotto.

L'**Input-Agnostic Projection** (Conv1D k=1) impara a estrarre la "verità" indipendentemente
dalla densità informativa ([`DOSSIER §2.1`](DOSSIER_TECNICO.md#input-agnostic)). L'assegnazione dei mic reali agli slot in fase
di plugin (UI) è materia di **F4**; qui si fissa solo il contratto del tensore.

### 4.1 Amendment 2026-05-25 (F0-T15-post · B3) — slot → "porte d'ingresso"

> **Amendment Decision Lock CEO 2026-05-25** ([`F0-T15-post §6.1`](F0-T15-post_AUDIO_AUGMENTATION_SPEC.md)).
> Conseguenza dei findings mini-L3 cross-kit ([F0-T4c §6.5](F0-T4c_DATA_PIPELINE_FIXES_SPEC.md)):
> la rete impara la *semantica* dei singoli slot (kick=0, snare=1, ...)
> e fallisce quando l'ordine dei mic cambia (es. ShittyKit ha mic layout
> diverso). La cura ratificata da F0-T15-post B3 è **insegnare l'agnosticità
> sull'ordine direttamente al training**:

> **Amendment MAJOR Decision Lock CEO 2026-05-26 ([F0-T4e §6.1](F0-T4e_INPUT_AGNOSTIC_TRAINING_SPEC.md)).**
> L'amendment 4.1 (v1.1) chiedeva la *cura per augmentation*. F0-T4e
> aggiunge la **cura architettonica complementare**: il `ChannelAgnosticFrontend`
> rende l'agnosticità una **proprietà matematicamente provata**
> (permutation-invariance via mean⊕max pool sui per-channel encoded
> features), non solo empirica. La sezione §4 "8 slot canonici" passa da
> **parziale** (zero-fill per slot inattivi, semantica appresa a posteriori
> dall'augmentation) a **completa** (l'architettura **non può** distinguere
> l'ordine dei canali — non è un'opzione di training, è una proprietà
> dell'output del frontend). Conseguenza pratica: durante l'inferenza nel
> plugin v1.0 EA, l'utente può collegare 1-8 canali in qualsiasi ordine
> senza alcun preset di routing; il modello produce lo stesso output.
> **Status §4 v1.2:** input-agnosticity = architettonica (F0-T4e) +
> augmentation (F0-T15-post B3 + F0-T4e channel_agnostic_aug).

| Aspetto | Pre-amendment (v1.0) | Post-amendment (v1.1) |
| :-- | :-- | :-- |
| Semantica degli slot 0..7 | **fissa** (kick/snare/hihat/...) | **convenzionale per il preprocessing**, **appresa dalla rete** |
| Etichetta della tabella §4 | "Etichetta canonica" | "Porta d'ingresso 0..7 (semantica appresa)" |
| Conteggi mic in training | {1, 2, 4, 8} (canonici) | **{1..8} con probabilità sbilanciata su 8** |
| Permutazione canali | identità | **shuffle uniforme** in training |
| Channel masking | non presente | **20 % prob** di azzerare 1 canale random in training |
| Implementazione | hardcoded canonical | `src/data_engineering/audio_augment/channel_masking.py` (F0-T16-post) |

**Cosa cambia praticamente:**
- La tabella mic_config (mono/solo_stereo/glyn_johns/multitrack_full) resta valida come
  **convention della pipeline dati** (F0-T2a) ma non vincola più il modello a interpretare
  "slot 0 = kick" — durante training, lo stesso sample può essere shufflato (kick → slot 5,
  hihat → slot 2) e la rete deve produrre lo stesso output.
- A inferenza nel plugin (F4): l'utente assegna i suoi mic ai 9 slot (8 mic + 1 onset
  envelope) tramite UI. La rete è agnostica all'ordine.
- Conseguenza: **eliminata** la fragilità "se il kit ha mic layout diverso, la rete crolla"
  — è esattamente la diagnosi del mini-L3 P1+P2 (ShittyKit cross-kit).

<a id="pdc"></a>
## 5. Non-causalità / Look-ahead / PDC

- Il trunk è **causale**: nessun receptive field futuro intrinseco.
- Il **look-ahead ~100 ms** ([`DOSSIER §2.3`](DOSSIER_TECNICO.md#cymbals), [`MASTER_CHECKLIST §3`](../../MASTER_CHECKLIST.md#dsp) PDC) è realizzato come
  **ritardo d'ingresso pari al PDC**: l'intero plugin gira ~100 ms indietro, quindi la
  rete al frame `t` dispone dell'audio fino a `t + ~100 ms`. È la **stessa delay-line**
  del Chronos Engine già bloccato — nessuna superficie nuova.
- **Budget look-ahead:** ≤ 100 ms (≤ 4410 sample @ 44.1 kHz ≈ 34 frame @ 344.53 Hz).
- `latency_samples` **esatto** misurato da F0-T4b e scritto nell'header del
  [Model Artifact (`F0-T8`)](F0-T8_MODEL_ARTIFACT_SPEC.md#header-json); target di
  progetto = 4410 sample (100 ms), badge UI "MODE: MIXING GRADE ONLY".

### 5.1 Default operativo — amendment 2026-05-24 (F0-T4c · B1)

> **Amendment Decision Lock CEO 2026-05-24** ([`F0-T4c §6.1`](F0-T4c_DATA_PIPELINE_FIXES_SPEC.md)). La
> diagnostica [T1-DIAG-A](../gates/R&D_Tier1_reports/T1-DIAG-A/T1_DIAG_A_REPORT.md)
> ha rivelato che `GoldDataset` propagava `lookahead_frames = 0`
> (strict-causal) ignorando il PDC di 100 ms qui prescritto.

| Parametro | Valore default ratificato |
| :-- | --: |
| `GoldDataset.lookahead_frames` (default) | **`35`** (= `ceil(0.100 × 344.53)`) |
| `train.train(lookahead_frames=...)` (default) | **`35`** |
| `evaluate_holdout(lookahead_frames=...)` (default) | **`35`** |

Implementato in `src/neural/data.py` + `src/neural/train.py`. CLI
`python -m neural.train --lookahead-frames N` consente override per
A/B sperimentali.

## 6. Loss & Ground Truth

| Testa | Loss | Note |
| :-- | :-- | :-- |
| onset | **Asymmetric Focal Loss** | falso-positivo pesato **3×** la nota mancata ([`DOSSIER §6.2`](DOSSIER_TECNICO.md#loss)); target Gaussian-smeared σ ↔ ±3 ms |
| velocity | **L1 mascherata** | supervisione solo sui frame con onset attivo nel ground truth |
| microtiming | **L1 mascherata** | idem — solo sui frame con onset |
| hihat_opening | **L1 / MSE densa** | su ogni frame ([`DOSSIER §2.2`](DOSSIER_TECNICO.md#midi-output)) |

Loss totale = somma pesata; i **pesi inter-testa** sono iperparametri di F0-T4b.

### 6.1 LossConfig — amendment 2026-05-24 (F0-T4c · B3 + B6b)

> **Amendment Decision Lock CEO 2026-05-24** ([`F0-T4c §6.1`](F0-T4c_DATA_PIPELINE_FIXES_SPEC.md)). I
> default originari (`pos_weight=50, w_on=1.0, w_vel=0.5, w_mt=0.5,
> w_hh=1.0`) erano calibrati per density ~5 % (Lin 2017 baseline);
> la density misurata sul Gold mix è 0.4-1.5 % → 10× più sparso → la
> teoria prescrive `pos_weight ≈ 200`. La diagnostica T1-DIAG-A ha
> confermato lift +49 % F (holdout) col nuovo set.

| Parametro | Default ratificato | Note |
| :-- | --: | :-- |
| `pos_weight` | **`200`** (scalare) o **tuple per-bus** (B6b) | Quando tuple di 8 valori, il sampler B6a si attiva automaticamente |
| `w_onset` | **`2.0`** | Era 1.0; raddoppiato perché onset è il segnale primario |
| `w_velocity` | **`0.1`** | Era 0.5; ridotto — velocity contribuisce poco alla F-measure di onset |
| `w_microtiming` | **`0.1`** | Era 0.5; ridotto — idem |
| `w_hihat` | **`0.25`** | Era 1.0; ridotto — HH dense L1 dominava il gradient nel regime sparso |
| `focal_gamma` | `2.0` *(invariato)* | Lin 2017 baseline |
| `fp_to_fn_ratio` | `3.0` *(invariato)* | Doctrine F0-T4a §6 / DOSSIER §6.2 |
| `onset_mask_threshold` | `0.5` *(invariato)* | — |

**B6b · `pos_weight` per-bus** (class imbalance bi-assiale sui piatti). Quando
`pos_weight` è una tupla di 8 valori (uno per bus), il termine FN
dell'Asymmetric Focal viene pesato per-bus, e il `WeightedRandomSampler` di
B6a si attiva automaticamente nel `DataLoader`. Tool: `tools/scan_density.py`
calcola la tupla dal training set (cap `1000`, safe by construction su bus
con density = 0).

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
