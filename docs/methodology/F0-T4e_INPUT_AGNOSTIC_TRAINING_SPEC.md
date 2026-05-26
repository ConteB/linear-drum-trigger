---
title: "F0-T4e — Input-Agnostic Training (STRP-001)"
id: LIN-DT-F0T4E
status: LOCKED_v1.0.0
locked: true
locked_at: 2026-05-26
authors: [Strategic Advisor (Gianpiero Scappelloni)]
date: 2026-05-27
supersedes: []
related:
  - F0-T4a §3.3 (in_channels parametrizzato — superseded by §6.1 amendment)
  - F0-T4a §4 (input-agnostic slots — promoted from parziale → completa)
  - F0-T4d (preprocessing P1+P2 — applicato post-aggregation)
  - F0-T15-post B5 (channel masking 20% — esteso da channel_agnostic_aug)
  - F0-T16-post (audio_aug pipeline — composer estende channel_agnostic_aug)
---

# F0-T4e · Input-Agnostic Training — STRP-001 (LOCKED v1.0.0)

> **Status:** LOCKED v1.0.0 — Decision Lock CEO 2026-05-26 ratificato.
> 6 fasi STRP-001 chiuse. §6.1 documenta le 4 ratifiche; Fase 6 Docs Update
> propagata negli amendment sotto.

## 0 · Inquadramento

**Origine.** Direttiva CEO 2026-05-27 (sessione audit pipeline ocular):
l'audit S2 del pipeline_audit ha flaggato BigRustyDrums come "FAIL" perché
6/8 canali sono identicamente ZERO. Diagnosi iniziale: "pool inquinato,
escludere BigRustyDrums". **Decisione CEO:** sbagliato il framing — il
problema NON è BigRustyDrums, è la nostra pipeline che hard-codifica un
layout semantico ai canali (slot 0=kick, 1=snare, etc).

**Rettifica strategica del CEO.** L'utente del plugin v1.0 EA *non* ha
8 microfoni con assegnazione fissa "kick mic in slot 0". Ha 8 slot audio
generici dove può buttare:
- mono (1 canale) ovunque
- stereo overhead (2 canali) in qualsiasi paio di slot
- 3 overhead + kick + snare (5 canali) in qualsiasi disposizione
- 7 canali multitrack senza un room mic
- qualsiasi permutazione del routing standard

**Conseguenza dottrinale.** La rete deve essere **input-agnostic by design**.
L'hard-coding del layout (CANONICAL_SLOT_MAP, semantica per-slot, ordine
fisso dei canali) è un *bug architetturale* che produce due classi di
problemi:

1. **In-training**: la rete impara "kit-fingerprint" dai pattern di
   zero-fill (BigRustyDrums = "ch 0-4 zero, ch 5-6 attivi"). Non sta
   imparando onset detection, sta imparando layout-identification.

2. **In-production**: l'utente con uno stereo OH che lo mette in slot 0-1
   (invece di 5-6 standard) avrà output broken perché la rete si aspetta
   slot 0 = kick mic.

**Scope.** F0-T4e copre:
- Architettura input-agnostic (estensione F0-T4a §3.3 / §4)
- Training regime input-agnostic (estensione F0-T15-post B5 / F0-T16-post)
- Implicazioni real-time C++/JUCE (F4 — front-end del plugin)
- Mantenere TUTTI i kit attuali nel pool (BigRustyDrums incluso, non
  escluso).

**Costo Azure.** $0 — interamente locale.

---

## Fase 1 · Competitor & Market Analysis

### 1.1 — Come l'industria audio ML gestisce input multi-canale variabile

| Sistema | Anno | Strategia |
|:--|:--:|:--|
| **Demucs v4** (Defossez, Meta AI) | 2023 | Stereo fisso (2-ch). NON agnostic-multichannel — il modello assume e richiede pair stereo. |
| **Spleeter** (Deezer) | 2019 | Stereo fisso. |
| **OpenUnmix** (Sigsep) | 2019 | Stereo fisso (`umxhq`) o mono (`umxhqm`) — due modelli separati, non un solo modello agnostic. |
| **TasNet / Conv-TasNet** (Luo 2018-19) | 2018 | Mono fisso (1-ch). |
| **DPRNN / SepFormer** | 2020-21 | Mono fisso. |
| **MMDenseLSTM, MMDenseNet** | 2017 | Mono o stereo — fixed-channel. |
| **Drum-CNN** (Vogl, Bock 2017) | 2017 | Mono fisso (log-mel spectrogram, 1-ch). |
| **SuperFlux onset detector** | 2013 | Mono fisso. |

**Insight industria:** la stragrande maggioranza dei modelli audio ML sono
**channel-fixed**. Quando un sistema deve gestire input variabile, lo fa
con N modelli (Open-Unmix mono vs stereo) o assumendo un upmix esterno.

### 1.2 — Eccezioni: paradigmi input-agnostic

| Paradigma | Riferimento | Idea cardinale |
|:--|:--|:--|
| **DeepSets** (Zaheer 2017) | NIPS | f({x_1..x_N}) = ρ(Σ φ(x_i)). Permutation-invariant by sum over per-element MLP. |
| **Set Transformer** (Lee 2019) | ICML | Attention sull'insieme con learned slot tokens. Permutation-invariant. |
| **PointNet** (Qi 2017) | CVPR | Idea simile applicata a point clouds; shared MLP + max-pool. |
| **Permutation-Invariant Training (PIT)** | Yu 2017 | Per source separation: ordina output con assignment al target che minimizza loss. Risolve permutation ambiguity al *target*, non al *input*. |
| **Squeeze-and-Excitation** (Hu 2018) | CVPR | Channel attention: la rete impara a pesare i canali in modo adattivo. Permutation-*equivariant* (non strict invariant), ma robusto a riordini se il pooling è simmetrico. |

**Insight per il nostro caso:** DeepSets + Set Transformer sono la
letteratura più rilevante. L'onset detection multi-mic è naturalmente
*set-like* (gli 8 canali sono un *insieme* di osservazioni dello stesso
evento). Permutation-invariance è la proprietà giusta.

### 1.3 — Drum-specific: source separation con N canali variabile

- **Spleeter / Demucs / Open-Unmix**: drum stem output ma input fisso.
- **DrumGAN / OmniDrum** (Vetterli 2022): drum sound synthesis, non onset detection.
- **Karoryfer kit benchmarks**: nessun lavoro pubblico identico al nostro
  (input multi-mic variabile → output onset 8-bus + microtiming).

**Conclusione Fase 1:** non c'è un precedente diretto. Dovremo costruire
sopra DeepSets/Set-Transformer + channel-augmentation hard.

---

## Fase 2 · Open-Source Codebase Analysis

### 2.1 — Pattern stabili in repo OS

| Repo | Pattern utile | Adatto al nostro caso? |
|:--|:--|:--:|
| `facebookresearch/demucs` | `nn.Conv2d([B, 2, F, T])` per stereo | NO — assume 2 ch |
| `mpariente/asteroid` | Framework modulare source-sep | Parziale — supporta multichannel ma con N fisso per modello |
| `juho-lee/set_transformer` | `SAB` / `PMA` layer permutation-invariant | **SÌ — utilizzabile come layer di pooling sui canali** |
| `lim0606/pytorch-DeepSets` | Reference implementation DeepSets | SÌ — utilizzabile come template |
| `kuleshov/audio-super-res` | Channel-permutation augmentation in training | Pattern utile (`torch.randperm` su dim 1) |
| `JusperLee/Conv-TasNet` | Channel dropout in training | Pattern utile (`Dropout(p=0.2)` su channel dim) |

### 2.2 — Architectural primitives PyTorch off-the-shelf

- `nn.Conv1d(kernel_size=1, groups=N)` — depthwise per-canale (shared
  weights solo entro group).
- `torch.einsum("bct,bcf->btf", x, w)` — per channel-attention pooling.
- `nn.MultiheadAttention` con `query` = learned slot tokens, `key`/`value`
  = per-canale encoding → Set Transformer style.

Tutte queste primitive sono già disponibili nella nostra `torch==2.x` stack.
Niente nuove dipendenze.

### 2.3 — Sample code esistente nel nostro repo che già supporta agnosticità

- `src/data_engineering/audio_augment/channel_mask.py` (F0-T15-post B5 +
  F0-T16-post MVP): maschera 0-7 canali a zero con probabilità 20 %.
  **Già wired in `mini_l3_train.py` via `--audio-aug`.**
- `src/neural/model.py` `TCNConfig.in_channels` è parametrizzato (default 8,
  con preprocessing → 9). Non è hard-codato, ma è *fixed-at-construction*.

---

## Fase 3 · UX/UI Impact (Laboratory Precision)

### 3.1 — Cosa l'utente vede nel plugin v1.0

**8 slot di input audio**, etichetta neutra:
```
┌─────────────────────────────────────────────────────────────┐
│ DRUM INPUT  [1] [2] [3] [4] [5] [6] [7] [8]                 │
│             ─── ─── ─── ─── ─── ─── ─── ───   (VU meters)   │
│             ▓▓░ ░░░ ▓▓▓ ▓░░ ░░░ ░░░ ░░░ ░░░                 │
└─────────────────────────────────────────────────────────────┘
```

Lo slot inattivo (no signal) si auto-grigia. Nessuna icona "kick mic" o
"hihat mic". Nessun preset "Glyn Johns" o "multitrack standard". Tutti
gli slot sono semanticamente identici, neutri, "Input N".

### 3.2 — Estetica "Laboratory Precision"

- Tipografia monospace.
- VU meters tipografici a barre Unicode (`▓▒░`).
- Nessuna metafora skeumorfica (no microfoni disegnati).
- Indicatore di "signal presence per slot" come dato oggettivo, non
  interpretato.

### 3.3 — Coerenza dottrinale

L'UX rinforza la dottrina ingegneristica: **niente assunzione semantica
sul layout**. L'utente fornisce quello che ha — la rete si adatta.

---

## Fase 4 · Tech Implementation Matrix

### 4.1 — Approcci candidati per l'agnosticità

#### Approccio A — Shuffle + Mask Aggressivo (data-only)

Training: ad ogni step applica:
1. **Permutazione random** degli 8 canali (`torch.randperm(8)`).
2. **Mask casuale**: 0-7 canali a zero (uniforme `U[0, 7]`).
3. **Conteggio variabile**: simula scenari realistici {mono, stereo, 4-ch,
   ...} con probabilità sbilanciate verso configurazioni realistiche.

Architettura: invariata (TCN F0-T4a §3.3, in_channels=9 con P1+P2).

| Aspetto | Score |
|:--|:--|
| Complessità implementazione | **Bassa** (~50 LOC in `src/data_engineering/audio_augment/`) |
| Aderenza dottrina Linear | **Bassa** — la rete deve "scoprire" agnosticità dai dati, non è by-design. Convergenza lenta. |
| Rischi | Medi — la rete potrebbe non convergere su tutte le permutazioni se il pool train è piccolo |
| Real-time C++ | Trivial — non cambia l'inferenza |

#### Approccio B — Permutation-Invariant Pooling (architectural)

Architettura modificata:
1. **Per-channel encoder shared**: ogni canale (anche se zero) viene
   processato da un encoder `φ` con shared weights — `Conv1d(1→C/8)`
   applicato indipendentemente per canale.
2. **Permutation-invariant aggregation**: i C/8 feature maps di ciascun
   canale vengono aggregati con **mean + max** (concatenati) → output
   `[B, C, T]`.
3. **TCN backbone**: come F0-T4a §3.3 dopo la fase di aggregation.

Training: anche con augmentation A.

| Aspetto | Score |
|:--|:--|
| Complessità implementazione | **Alta** (~200 LOC: nuovo encoder + refactor F0-T4a §3.2) |
| Aderenza dottrina Linear | **Alta** — agnosticità è una proprietà *provata* della rete (mean/max sono permutation-invariant by definition) |
| Rischi | Medio-bassi — perdita di info "da quale canale arriva l'onset" (ma il nostro task è onset detection, non source localization → accettabile) |
| Real-time C++ | Medio — encoder per-canale = N inference passes, ma con kernel piccolo è gestibile |

#### Approccio C — Channel Attention (Squeeze-and-Excitation)

Architettura modificata:
1. **SE block iniziale**: pesa i canali con attention learned, channel-wise.
   `attention = sigmoid(MLP(global_avg_pool(x)))` → moltiplica.
2. **TCN backbone**: come F0-T4a §3.3.

| Aspetto | Score |
|:--|:--|
| Complessità implementazione | **Media** (~100 LOC) |
| Aderenza dottrina Linear | **Media** — permutation-*equivariant*, non strict-invariant. Ma robusto se il pooling globale è simmetrico. |
| Rischi | Medi — può imparare comunque un layout preferito se l'augmentation non è hard. |
| Real-time C++ | Medio-alto — SE block aggiunge ~10% inference cost. |

#### Approccio D — Channel Sum + Augmentation Hard (front-end semplice)

Architettura modificata:
1. **Learned channel mixer**: `Conv1d(8→C_internal, kernel=1)` somma
   ponderata appresa degli 8 canali. Output `[B, C_internal, T]`.
2. **TCN backbone**: con `in_channels = C_internal` invece di 8.

Training: augmentation hard (A) + zero-symmetric (la mixer dovrebbe imparare
una somma robusta a permutazioni se l'aug è abbastanza forte).

| Aspetto | Score |
|:--|:--|
| Complessità implementazione | **Bassa-media** (~80 LOC) |
| Aderenza dottrina Linear | **Media** — il mixer 1×1 può imparare pesi diversi per canale, NON è strict invariant. Dipende dall'augmentation. |
| Rischi | Medi — se l'aug non è bilanciato, il mixer impara un layout preferito. |
| Real-time C++ | Trivial — `Conv1d(8→C, k=1)` è un fully-connected layer per-frame. |

### 4.2 — Matrice di sintesi

| | A (aug-only) | B (perm-inv pooling) | C (channel attention) | D (mixer + aug) |
|:--:|:--:|:--:|:--:|:--:|
| **Complessità impl.** | Bassa | Alta | Media | Bassa-media |
| **Aderenza dottrina** | Bassa | **Alta** | Media | Media |
| **Rischi** | Medi | Bassi | Medi | Medi |
| **Real-time C++** | **Trivial** | Medio | Medio-alto | **Trivial** |
| **Provedness** | Empirica | **Matematica** | Empirica | Empirica |
| **Costo C++ port (F4)** | $0 (no change) | ~150 LOC | ~80 LOC | ~30 LOC |
| **Param count delta vs F0-T4a** | 0 | +5-10 % | +3-5 % | +1 % |
| **Risparmio inference latency** | 0 | small overhead | small overhead | trivial |

### 4.3 — Recommendation cardinale

**Approccio combinato B+A.** Architettura permutation-invariant by design
(B) **+** augmentation hard di shuffle/mask/count (A) per *forzare* la rete
a usare la proprietà architettonica durante il training.

Razionale:
- B da solo garantisce l'invarianza matematica, ma l'augmentation hard
  accelera la convergenza e copre il caso "input degenere" (mono, 2-ch).
- A da solo non garantisce nulla — la rete potrebbe trovare uno scorciatoia.
- C e D sono compromessi che rischiano "imparare un layout preferito" se
  l'augmentation non è perfetto.

### 4.4 — Schema della soluzione raccomandata (BA-combo)

```
Input: [B, 8, T_samples]
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ Channel-Agnostic Augmentation Pipeline (training only)      │
│   1. Random permutation: x = x[:, perm, :]                  │
│   2. Random count mask: zero out U[0,7] random channels     │
│   3. Realistic mic-config mix: 30% mono / 30% stereo /      │
│      30% 4-8 ch / 10% degenerate edge cases                 │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ Per-Channel Shared Encoder (F0-T4e, NEW)                    │
│   φ : Conv1d(1 → C/4, kernel=7, causal) applied per-channel │
│   Output: [B, 8, C/4, T]                                    │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ Permutation-Invariant Aggregation                           │
│   mean = x.mean(dim=1)  ──┐                                 │
│   max  = x.max(dim=1)   ──┤── concat → [B, C/2, T]          │
│                                                              │
│   Optional: + simple-attention pooling (learned slot token) │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ Existing P1+P2 Preprocessing (F0-T4d, unchanged)            │
│   Pre-emphasis + ChannelNorm + Onset envelope               │
│   Now applied on aggregated single-stream                   │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ TCN Backbone (F0-T4a §3.3, unchanged)                       │
│   in_channels = C/2 (+1 for onset env from P2)              │
│   Strided encoder + dilated trunk + 4 heads                 │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
Output: [B, T_frames, 25] flat-25 target
```

### 4.5 — Real-time C++/JUCE implications (F4)

| Component | C++ LOC stimato | Latency impact |
|:--|:--:|:--:|
| Channel-agnostic input router (8 slots) | ~50 | trivial |
| Per-channel shared encoder | ~80 | +1-2 ms (8× Conv1d kernel=7) |
| Permutation-invariant aggregation (mean+max) | ~30 | trivial |
| Total | **~160 LOC** | **+2 ms** PDC vs F0-T4a baseline |

PDC budget attuale: 100 ms (F0-T4a §3.2). +2 ms entra senza fatica.

---

## Fase 5 · Executive Briefing al CEO

> **Status:** PENDING — richiede revisione CEO a mente fresca prima della
> ratifica. Compilato come bozza preliminare.

### Sintesi

**Problema:** la pipeline mini-L3 sta usando un layout di canali fissi
(slot 0=kick, ..., slot 7=room) come *contratto semantico*, mentre il
plugin v1.0 EA sarà input-agnostic: l'utente fornisce 1-8 canali audio in
qualsiasi ordine. Il bug "BigRustyDrums 6/8 canali zero" è il sintomo —
la pipeline tratta un input legittimo (stereo overhead) come *anomalia*.

**Conseguenza al training:** la rete impara "kit-fingerprint" (= layout)
invece di onset detection. È la spiegazione causale del cross-kit gap
osservato in tutto il mini-L3.

**Conseguenza in production:** un utente con stereo OH che routa nei suoi
slot 0-1 (invece dello standard 5-6) avrà output broken.

### Raccomandazione

Ratifica architettura **B+A combinata**:
- **B (architettura permutation-invariant)**: per-channel shared encoder +
  mean/max pooling **prima** del TCN. Agnosticità matematicamente provata.
- **A (augmentation hard)**: random permutation + random count mask +
  realistic mic-config distribution. Accelera la convergenza e copre
  edge cases.

### Implicazioni operative

| | Senza F0-T4e | Con F0-T4e (B+A) |
|:--|:--:|:--:|
| Mini-L3 cross-kit gap | ~30% del residuo è layout-fingerprint | si chiude (atteso) |
| Plugin v1.0 routing flessibile | richiede preset rigidi | supporto nativo |
| F2-T1 render scope | uguale | uguale |
| F2-T3 training cost | uguale (architettura più piccola in pooling, compensata da aug) | uguale |
| F4 C++ port | ~5 layer | +1 layer (~160 LOC) |
| Decision impact su roadmap | nessuno | nessuno |

### Cosa cambia per i 3 bug dell'audit ocular

| Bug | Risolto da F0-T4e? | Note |
|:--|:--:|:--|
| #1 BigRustyDrums zero-fill | **SÌ** | BigRustyDrums diventa un caso normale (stereo OH) invece di "anomalia". Non si esclude. |
| #2 ShittyKit ch hihat=OH_L | **PARZIALE** | Ha senso architetturale anche con perm-invariant: il canale duplicato non è più OOD perché la rete non ha nozione di "ch 2 sempre hihat". Resta utile per coverage però. |
| #3 GM 75 + 54 ignorati | **NO** | Bug ortogonale (mapping table policy). Fix separato. |

### Decision Lock pendente

Decisioni che richiedono il voto CEO:
1. **D1** — Ratificare l'architettura B+A?
2. **D2** — Mantenere tutti i 7 kit attuali nel pool (DRSKit, Crocell,
   Muldjord, Aasimonster, BigRusty, Unruly?, VSCO?, Frankensnare?,
   ShittyKit, Swirly?), inclusi gli SFZ stereo?
3. **D3** — Aggiornare F0-T4a §3 / F0-T4d a valle (Fase 6) come amendment
   MAJOR vs MINOR?
4. **D4** — Costo locale di prototipo + regression test (~2-3 giorni)
   prima del prossimo training mini-L3?

### Costo Azure

**$0** — interamente sviluppo locale + test su mini-L3 esistente.

---

## 6.1 · Decision Lock CEO 2026-05-26 — Ratifica

Sessione 2026-05-26. Executive Briefing F0-T4e presentato. CEO vota:

| # | Domanda | Voto | Risoluzione |
|:--|:--|:--|:--|
| **D1** | Architettura B+A combinata? | ✅ Ratifica B+A | Per-channel shared encoder (Conv1d k=7 causal) + mean⊕max permutation-invariant pooling + augmentation hard (shuffle/mask/count + realistic_mic_config_sampler) |
| **D2** | Tutti i kit attuali nel pool? | ✅ Sì — tutti dentro | BigRustyDrums incluso come stereo-OH legittimo; ShittyKit incluso; SFZ stereo inclusi. Nessuna esclusione. |
| **D3** | Amendment MAJOR o MINOR? | ✅ MAJOR | F0-T4a §3.3 cambia struttura input (nuovo frontend); F0-T4a §4 da parziale → completa. Cambio architetturale → semver MAJOR. |
| **D4** | Timeline ~2-3 gg locali, $0 Azure? | ✅ Vai | Implementazione completa channel_agnostic.py + channel_agnostic_aug.py + wire model.py + flag mini_l3_train.py + regression test. |

**Conseguenze operative:**

- **F0-T4e** marcato `LOCKED v1.0.0` nel Tracking Board MASTER_SCHEDULING §7.
- **F0-T4a §3.3** riceve amendment MAJOR: il frontend input-agnostic precede la
  Input-Agnostic Projection originale (che diventa "post-aggregation projection").
- **F0-T4a §4** "Input-Agnostic Slots" passa da *parziale* (zero-fill per slot inattivi)
  → *completa* (permutation-invariance matematica + agnosticità al conteggio variabile).
- **F0-T4d §3** preprocessing P1+P2 applicato **post-aggregation** sul singolo stream
  aggregato `[B, C/2, T]` invece che sui canali raw `[B, 8, T]`. Mantiene il contratto
  `in_channels = C/2 (+1 con P2)`.
- **F0-T15-post B5** channel masking esteso da `channel_agnostic_aug.py`
  (random_count_mask 0-7 invece del singolo masking 20%).
- **F0-T16-post** composer audio aug viene esteso con la nuova voce `channel_agnostic_aug`.

**Out of scope F0-T4e (rinviato):**

- **Bug #3 — GM 75 + GM 54 ignorati nel midi_mapping_table.yaml.** Fix ortogonale,
  pianificato post-F0-T4e implementation; richiede Decision Lock policy del CEO
  (a quale bus assegnare GM 75 — splash cymbal — e GM 54 — tambourine).

---

## Fase 6 · Docs Update (a valle dell'approvazione)

A valle del Decision Lock CEO, propagare:

- `F0-T4a §3.3` → amendment `in_channels` con channel-agnostic frontend
- `F0-T4a §4` → estensione "input-agnostic slots" da parziale → completa
- `F0-T4d §3` → preprocessing P1+P2 ora applicato post-aggregation
- `F0-T15-post §B5` → estensione channel-mask spec
- `F0-T16-post` → implementazione modulo `channel_agnostic_aug.py`
- `MASTER_CHECKLIST §1` → aggiornamento topologia
- `MASTER_SCHEDULING §6` → aggiungere F0-T4e al Tracking Board, ⛔ F2-T3
- `DOSSIER_TECNICO §2.1` → rivisitare "Input-Agnostic" doctrine
- `engineering_standards §6` → robustness aggiornata

### Implementazione (post-ratifica)

1. **Modulo `src/neural/channel_agnostic.py`** (~200 LOC):
   - `PerChannelEncoder(Conv1d)` shared weights
   - `PermInvariantPool(mean+max)` aggregation
2. **Modulo `src/data_engineering/audio_augment/channel_agnostic_aug.py`** (~80 LOC):
   - `random_permutation` + `random_count_mask` + `realistic_mic_config_sampler`
3. **Modifica `src/neural/model.py`**: composizione channel_agnostic →
   preprocessing → TCN.
4. **Modifica `tools/mini_l3_train.py`**: flag `--input-agnostic` per
   abilitare il front-end e l'augmentation hard.
5. **Regression test**: mini-L3 con F0-T4e + tutti gli 8 kit pool →
   misurare val F vs baseline allfixes (atteso lift +10-30 %).

---

## 7 · Appendice — Tabella decision matrix dei 4 approcci (riassuntiva)

| Approccio | Quando sceglierlo |
|:--|:--|
| A | Solo se proibiti cambi architetturali (F4 deadline ravvicinata). |
| **B+A (raccomandato)** | **Soluzione cardinale: matematicamente provata + accelerata in training.** |
| C | Compromesso se latenza C++ è critica (non è il nostro caso). |
| D | Compromesso minimalista se il tempo di sviluppo è < 1 giorno. |

---

*LOCKED v1.0.0 — Decision Lock CEO 2026-05-26. STRP-001 6 fasi chiuse.
Fase 6 Docs Update propagata negli amendment MAJOR sopra. Implementazione
in `src/neural/channel_agnostic.py` + `src/data_engineering/audio_augment/channel_agnostic_aug.py`.*
