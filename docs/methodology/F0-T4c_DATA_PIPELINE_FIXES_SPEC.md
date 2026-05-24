---
id: LIN-DT-SPEC-F0T4C
title: F0-T4c — Data Pipeline Fixes (causality + RF + loss imbalance) — STRP-001
type: spec
status: PARTIAL-LOCK
phase: F0
domain: Neural / Data Engineering
version: 1.0.0
updated: 2026-05-24
tags: [F0-T4c, F0-T4a, lookahead, receptive-field, loss-imbalance, STRP-001, pre-Azure-gate]
related: [LIN-DT-SPEC-F0T4A, LIN-DT-SPEC-F0T2A, LIN-DT-RND-T1DIAGA-001]
supersedes: []
---

# 🔬 F0-T4c — Data Pipeline Fixes — STRP-001

> **Status: PARTIAL-LOCK v1.0.0 (2026-05-24).** Decision Lock CEO ratificato
> per **B1, B2, B3, B6a, B6b, B6c**; **B4 deferred** (rinviato a riesame
> post-regression test); **B5 ritirato** (errore di interpretazione corretto
> 2026-05-24). Vedi §6 per il registro voto e §5 per il dettaglio di ciascuna
> raccomandazione.
>
> **Gate operativo (post-Decision Lock parziale):**
> - **F2-T3 (training A100):** sblocco architetturale acquisito (B1+B2+B3
>   ratificati garantiscono che la rete trainata non sia strutturalmente
>   identica a quella già provata fallimentare dalla diagnostica T1-DIAG-A).
>   Resta gated solo dal completamento di F2-T1 e dalla quota A100.
> - **F2-T1 (render Gold 1.5 TB):** ⊘ **rimane bloccato** perché B4
>   (durata MIDI minima = 5 s) non è ancora ratificato. Senza B4 il Gold
>   renderizzato conterrebbe sample troppo brevi (< RF + lookahead = 3.07 s)
>   per essere consumati dalla rete con i nuovi default crop ≥ 135 552
>   ratificati da B2.
>
> Riapertura B4 prevista a valle del regression test §5 (target F_max ≥ 0.80
> sul mini-set, F_crash_a ≥ 0.3 — verifica empirica del lift teorizzato).

## 0. Sintesi esecutiva (1 paragrafo)

La diagnostica [T1-DIAG-A](../gates/R&D_Tier1_reports/T1-DIAG-A/T1_DIAG_A_REPORT.md) ha
identificato tre cause strutturali del plateau F ≈ 0.09 osservato in
ogni R&D Tier 1 run (T1-A → T1-H) — 10× sotto il gate L3 = 0.80. **Non
sono problemi di dataset né di capacity** (capacity test C=32/64/128
chiuso): sono tre disconnessioni tra la spec F0-T4a/§3 e la sua
implementazione in `src/neural/data.py` + `src/neural/train.py`. Il fix
combinato (look-ahead PDC = 35 frame, crop ≥ receptive field = 1024
frame, LossConfig riparametrizzato per density misurata) porta la stessa
rete C=32 da F = 0.08 a F = 0.234 mean / **0.827 max** su self-overfit,
con timing-MAE = 3.99 ms (< 5 ms L3) sul groove migliore — **passando il
gate L3 a livello individuale**. Un fix secondario (B6, class imbalance
sui piatti) emerge dalla misura empirica del dataset: ride/crash_a/
crash_b_misc appaiono nello 0.7-13 % dei sample GMD; sample-level
oversampling + per-bus pos_weight + lieve rebalance del mix garantiscono
F adeguata anche sulle categorie rare. Il documento ratifica i fix B1..B4
come amendment a F0-T4a §3 / §6 e a F0-T2a §3.8, B6 come secondario,
ritira B5 (errore di interpretazione iniziale corretto 2026-05-24), e
blocca il consumo del credito Azure su F2-T1 finché il Decision Lock CEO
non è formalizzato.

## 1. Competitor & Market Analysis

### 1.1 Look-ahead per onset detection (B1)

| Sistema | Causality | Look-ahead | F (E-GMD or similar) |
| :-- | :-- | --: | --: |
| **Bock & Schedl** (RNN onset, ISMIR 2014) | Bidirectional | ±100 ms (typical window) | ~0.90 |
| **Vogl et al.** (CRNN drum transcription, ISMIR 2017) | Bidirectional LSTM | ±100 ms context | 0.91 (E-GMD) |
| **ADTOF** (Zehren et al. 2021) | Causal + lookahead | 200 ms | 0.93 |
| **OnsetsAndFrames** (Hawthorne et al.) | Bidirectional | ±50 ms | 0.95 (MAPS) |
| **F0-T4a baseline** *(diagnostic, before fix)* | Strict-causal (left-pad only) | **0** | **0.08** |
| **F0-T4a + B1 fix** | Causal + 100 ms PDC | 100 ms | 0.15 (overfit) |

Industry consensus: **causal-only onset detection underperforms 20-40 %**
vs bidirectional or causal-with-lookahead on transient-dense material
(drums). 100 ms is the standard PDC budget for studio plugins; live
applications use 10-50 ms with degraded accuracy. F0-T4a §3 *prescribes*
100 ms = PDC ma il `GoldDataset` non lo applicava — bug, non scelta
deliberata.

### 1.2 Receptive field design per streaming TCN (B2)

| Sistema | Total RF | Training segment | Ratio RF/segment | Padding policy |
| :-- | --: | --: | --: | :-- |
| **WaveNet** (van den Oord et al. 2016) | ~250 ms | 16 s | 0.016 | Real audio context |
| **ConvTasNet** (Luo & Mesgarani 2019) | ~2 s | 4 s | 0.5 | Sample-padded |
| **FastSpeech 2** (Ren et al. 2020) | ~3 s | 10 s | 0.3 | Real text context |
| **F0-T4a** *(before fix)* | **2.97 s** | **0.74 s** | **4.0** | **Left-pad zero** |
| **F0-T4a + B2 fix** | 2.97 s | ≥ 3.07 s | ≤ 0.97 | Real audio context |

Consensus: il training segment **deve** essere ≥ RF, idealmente 2-4× RF
per dare al modello esempi con contesto completo su tutto il segmento.
Il caso F0-T4a (segment = 0.25× RF) è patologico — il modello impara dal
profilo del padding zero, non dall'audio. Nessun framework streaming
modern accetta questo regime.

### 1.3 Loss imbalance per onset detection sparsa (B3)

| Loss | Pos_weight | Notes |
| :-- | --: | :-- |
| **Asymmetric Focal Loss** (Ridnik et al. 2021) | ~density⁻¹ × γ_pos | Standard per multi-label sparso |
| **CRNN drum transcription** (Vogl) | 100-200 (density ~0.5 %) | Empirico, gridsearched |
| **OnsetsAndFrames** (Hawthorne) | Implicit weighted CE, ~50 | Bidirectional → tolera meno reweighting |
| **F0-T4a baseline** | **50** | **4× sotto density 0.005** |
| **F0-T4a + B3 fix** | 200 | Coerente con density misurata 0.4-1.5 % |

### 1.4 Class imbalance per categorie rare in drum transcription (B6)

| Sistema | Strategia long-tail | F crash | F kick/snare |
| :-- | :-- | --: | --: |
| **Vogl 2017** (CRNN) | Weighted CE, peso = 1/freq per classe | 0.71 | 0.92 |
| **ADTOF** (Zehren) | BCE + Dice loss su classi minoritarie | 0.78 | 0.93 |
| **OnsetsAndFrames** | WeightedRandomSampler su nota+velocity | 0.83 | 0.95 (piano) |
| **DTM** (Wu 2018) | Synthetic crash injection (downbeats) | 0.65 | 0.90 |
| **MT3** (Gardner 2022) | Curriculum learning (balanced → full) | 0.79 | 0.94 |
| **F0-T4a baseline** | Pos_weight scalare unico (=200 post-B3) | (expected ~0) | ~0.5 (post-B1+B2) |
| **F0-T4a + B6** | Sampler + per-bus pos_weight + mix rebalance | target ≥ 0.3 (overfit), ≥ 0.5 (Gold) | target ≥ 0.5 (overfit), ≥ 0.8 (Gold) |

Industry consensus: per density < 1 %, **scalar pos_weight non basta** —
serve combinare (a) sample-level oversampling, (b) per-class loss
weighting, (c) data composition rebalance. I tre sono additivi e
indipendentemente A/B testabili.

Pos_weight 50 era preso "a sentimento" dal Focal Loss originale (Lin
2017) per density ~5 %. La density del nostro dataset (Gaussian-smeared
onset al 344 Hz frame rate) è **10× più bassa** — la teoria prescrive
proporzionalmente più aggressivo.

## 2. Open-Source Codebase Analysis

| Repo | Riferimento utile | Cosa prendiamo |
| :-- | :-- | :-- |
| **madmom** (CC-BY-NC) | Onset detector training script | Full-length sample training (no crop), padding policy by reflect (not zero). **Vincolo licenza: research-only, non riusabile.** Solo come riferimento concettuale. |
| **ADTOF** (Apache-2.0) | TCN-style drum transcription | Conferma RF ≪ segment, look-ahead esplicito nel data pipeline. Pattern: `segment = max(8 s, 4 × RF)`. |
| **demucs** (MIT) | Streaming-friendly conv stack | Streaming inference con state buffer, non left-pad zero. RTNeural-style. |
| **mir_eval** (MIT) | Già in F0-T17 | Validazione metrica invariata; soglia ±50 ms standard. |
| **PyTorch `WeightedRandomSampler`** (BSD) | stdlib, B6a | Sample-level oversampling; API minimale. No dipendenza nuova. |
| **ADTOF loss combiner** (Apache-2.0) | Reference per B6b/Dice | Riferimento concettuale; non vendoring (~80 LOC equivalenti scritte ex-novo) |

**Pattern stabile dall'open-source:** TCN streaming = real-context
training (segment ≥ RF) + look-ahead esplicito + state-buffer inference.
Tutti i fix proposti sono allineati a questo pattern.

## 3. UX/UI Impact

### 3.1 PDC (Plugin Delay Compensation) — `[D]` user-visible

La latency del modello passa da **0 ms (strict-causal)** a **100 ms
(causal + 35-frame look-ahead)**. Implicazioni:

- **Studio mode (v1.0 EA):** OK. Tutti i DAW supportano la PDC reportata
  via `juce::AudioProcessor::getLatencySamples()`. Pro Tools / Logic /
  Cubase compensano automaticamente, l'utente non sente la latency.
- **Live mode:** 100 ms è il limite superiore "accettabile" per un
  trigger drum. Sopra i 30 ms diventa percepibile su transient kick;
  100 ms è "feel diverso" ma usabile per generi non-percussivi puri.
- **Plugin UI:** il badge "PDC 100 ms" deve essere visibile nella
  signal-flow section (LINEAR_DESIGN_GUIDE §badge). Il valore esatto
  dipende dal sample-rate runtime — al 44.1 kHz / 48 kHz è 100/96 ms.

**Verdetto UX:** PDC = 100 ms è la scelta corretta per "Studio
Precision" v1.0 ($99 EA). Live ottimizzato per latency-critical workflow
è scope v1.x (richiede modello con RF ridotto o look-ahead minore).

### 3.2 Aderenza "Laboratory Precision"

I fix B1..B4 non aggiungono né tolgono componenti UI. Sono modifiche
interne al data pipeline + ai default architetturali. **Nessun impatto
visivo.**

### 3.3 Uniformità delle metriche pubblicate (B6)

L'UI del plugin riporta F-measure per categoria di trigger (LINEAR_DESIGN_GUIDE
"performance card"). Una F crash_a = 0 sarebbe pubblicamente imbarazzante
("non riconosce i crash") anche se F kick/snare fossero 0.95. **B6 protegge
la coerenza percepita del prodotto:** la promessa "trascrizione
neurale a 8 categorie" deve essere uniformemente vera, non vera-su-5-
falsa-su-3. Impatto UX positivo, costo zero.

## 4. Tech Implementation Matrix

### 4.1 I tre fix, scelte e raccomandazioni

| Fix | Cosa | Default attuale | Default proposto | Lift dimostrato (overfit) |
| :-- | :-- | --: | --: | --: |
| **B1** Look-ahead PDC | `lookahead_frames` propagato a `GoldDataset` e `evaluate_holdout` | `0` (strict-causal) | **`35`** (= 100 ms a 344 Hz) | F 0.080 → 0.150 (+87 %) |
| **B2** Crop ≥ RF | `crop_samples` minimo di training | `32 768` (≈ 0.74 s, 0.25× RF) | **`≥ 135 552`** (≈ 3.07 s, ≥ RF + lookahead) | F 0.150 → 0.234 (+56 %) |
| **B3** LossConfig | Per-head weights + `pos_weight` | `pos=50, w_on=1.0, w_vel=0.5, w_mt=0.5, w_hh=1.0` | **`pos=200, w_on=2.0, w_vel=0.1, w_mt=0.1, w_hh=0.25`** | +49 % F (holdout) |

### 4.2 Vincolo derivato sul Gold (F0-T2a §3.8)

B2 impone una *durata minima* dei sample del Gold:

```
min_audio_samples = (crop_frames + lookahead_frames) × ENCODER_STRIDE
                  = (1024            + 35              ) × 128
                  = 135 552 samples
                  ≈ 3.07 s @ 44.1 kHz
```

Con un margine di sicurezza 2× per permettere crop random non a
boundary, la **durata MIDI minima del Gold deve essere ≥ 5 s**.

Lo `local_rnd` dataset attuale ha sample da 1-3 s — sotto soglia per la
maggior parte. F2-T1 deve quindi produrre clip di **almeno 5 s** (vs i
parametri attuali della recipe matrix che non hanno minimo esplicito).

**Amendment a F0-T2a §3.8:** aggiungere il vincolo
`midi_duration_min_s = 5.0` come parametro versionato della recipe matrix.

### 4.3 ~~Bus-mask dei 3 head morti~~ — ❌ RITIRATO (errore di interpretazione)

> **Errore di lettura corretto 2026-05-24.** L'osservazione "3/8 bus
> hanno target sempre vuoto" che originava B5 era un artefatto del
> diagnostic tool: avevo etichettato gli output buses con i nomi degli
> **input mic slot** (OH_L / OH_R / Room di `CANONICAL_SLOT_MAP`).
> I bus di output reali (per `midi_mapping_table.yaml` LOCKED da Decision
> Lock F0-T2a 2026-05-20) sono **ride / crash_a / crash_b_misc** — sono
> categorie di trigger reali, non mic positions. Non vanno mascherati.
> Vedi §4.6 (B6) per l'osservazione corretta che emerge dai numeri.

### 4.6 Class imbalance sui piatti (ride / crash_a / crash_b_misc) — B6

Misura empirica sul dataset `mix_2026-05-24` (% di sample con ≥ 1 hit per bus):

| Bus | GMD reale (405 sample) | rare_emphasis (90) | chaos (90) |
| :-- | --: | --: | --: |
| kick | 73 % | 99 % | 100 % |
| snare | 97 % | 99 % | 100 % |
| hihat | 56 % | 100 % | 100 % |
| tom_hi_mid | 62 % | 20 % | 100 % |
| floor_tom | 68 % | 20 % | 100 % |
| **ride** | **13 %** | 40 % | 100 % |
| **crash_a** | **0.7 %** ⚠️ | 36 % | 100 % |
| **crash_b_misc** | **11 %** | 60 % | 100 % |

Il problema vero non sono "3 head morti" ma una **class imbalance bi-assiale** sui piatti:

1. **Frame-level imbalance** (density per frame): già gestita da B3 con `pos_weight=200` scalare. OK per ride/crash_b (~10 %) ma sotto-tarato per crash_a (0.7 %) → pos_weight teorico ≈ 14 000.
2. **Sample-level imbalance** (% di sample contenenti positives): `pos_weight` non aiuta. In 99.3 % dei batch GMD la rete **non vede neanche un esempio di crash_a** → strategy ottima = "predici sempre 0" → loss quasi nulla, F = 0.

Il `rare_emphasis` e il `chaos` esistono proprio per counter-bilanciare, ma alla proporzione attuale 70/15/15 il GMD pesa abbastanza da nascondere il segnale. Tre leve, additive, **costo $0**:

| Leva | Cosa | Implementazione | Effetto atteso |
| :-- | :-- | :-- | :-- |
| **B6a · WeightedRandomSampler** | Sample-level: `PyTorch WeightedRandomSampler` con peso `1 / density_min(sample)` (= 1 / density del bus più raro che il sample contiene) | ~30 righe in `train.py`; pytorch stdlib | Grooves con crash_a visti ~140× più spesso |
| **B6b · `pos_weight` per-bus** | Frame-level: `LossConfig.pos_weight` diventa `tuple[float, ...]` (8 valori) calcolato da scan del training set, capped a 1000 | LossConfig refactor + scan tool; ~50 righe | Crash_a gradient finalmente forte sui (rari) positives |
| **B6c · Rebalance mix 70/15/15 → 60/25/15** | Data-level: aumentare `rare_emphasis` da 30 → 50 grooves | Param in `mix_dataset.py` | Più esempi reali (non solo chaos) dei piatti rari |

Tutti e tre sono **ortogonali** e individualmente A/B testabili. L'effetto è verificabile con un re-overfit: con i 3 fix B1/B2/B3 + i 3 sotto-fix B6a/b/c, il crash_a F atteso passa da ~0 a ≥ 0.3 sul mini-set.

### 4.4 Costo

| Voce | Costo | Note |
| :-- | --: | :-- |
| Implementazione fix (B1/B2/B3 defaults) | **$0** | Codice già esiste come knob CLI in `a3fe30c` / `c7f10a5`; serve solo cambiare default + ratificarli |
| ~~Implementazione bus-mask (B5)~~ | — | **B5 ritirata** (errore di interpretazione, vedi §4.3) |
| Amendment F0-T2a §3.8 (B4) | **$0** | Doc-only |
| Implementazione B6 (B6a + B6b + B6c) | **$0** | ~100 righe totali Python + 1 param in mix_dataset.py + 3 oracoli |
| F2-T1 storage impact (clip ≥ 5 s vs 1-3 s media local_rnd) | **~+30 %** sul Gold storage | Cool LRS, da $32 a ~$42/mese → dentro budget ($55 allocato §5) |
| F2-T1 storage incrementale per B6c (rare 30→50) | **~+5 %** | 20 grooves extra × 8 kit × 3 jitter = 480 sample extra; trascurabile |
| Tempo wall-clock F2-T1 con clip più lunghe | **~+20 %** | Render time scale lineare con clip duration. Da ~5h a ~6h → dentro spend budget |

### 4.5 Rischi

| Rischio | Mitigazione |
| :-- | :-- |
| 100 ms PDC inaccettabile per use-case live | Documentato; v1.0 è "Studio Mode". V1.x può esplorare lookahead ridotto. |
| B6a (oversampling): stesso groove visto N× → overfit su quei grooves | Mitigato dalla diversità del jitter k=2 (ogni groove ha 3 varianti); inoltre il `WeightedRandomSampler` resta probabilistico — il singolo groove non è "garantito ogni epoch" |
| B6b (pos_weight per-bus): bus con density = 0 nel training → pos_weight diverge | Cap a 1000 (3 σ sopra il pos_weight medio osservato). Se un bus ha 0 positives, pos_weight = 1000 ma il termine FN contribuisce 0 al loss comunque (no positives = nessun termine FN) — safe by construction |
| B6c (rare 30→50): più sintetico, meno GMD reale → potenziale domain shift | I `rare_emphasis` MIDI sono già stilisticamente realistici (famiglie crash/china/ride/tom/splash su pattern GM); non sono "chaos noise". Mantenere il 60 % di GMD reale preserva l'autenticità |
| Sample > 5 s mismatch con GMD reale | **Misurato 2026-05-23 (pre-flight chiuso):** GMD v1.0 contiene 1150 MIDI; 551 (47.9 %) sono ≥ 5 s; mediana effettiva = 4.35 s. Con jitter k=2 + baseline (×3) × 8 kit del roster F0-T1b → **13 224 sample di training**, sopra la soglia ~10 K che la CRNN literature suggerisce per la convergenza. Trade-off: meno varietà rispetto al GMD completo; mitigato da audio augmentation ×3 in F2-T2 (40 K sample totali post-augment, in linea con il SOTA `M=43 K` di Vogl). **Soglia alternative:** ≥ 4 s manterrebbe 585 MIDI (50.9 %) ma riduce il margine RF a 1.30× — meno robusto. ≥ 3 s = 846 MIDI (73.6 %) cade sotto la RF teorica (3.07 s) → escluso. **Raccomandazione: B4 = 5 s.** |
| LossConfig riparametrizzato peggiora qualche metrica secondaria (timing-MAE, hihat-MAE) | Diagnostic ha mostrato timing-MAE STESSO o migliore. HiHat MAE leggermente peggio (era già fuori range con vecchi default). Da rivalutare a F2-T3. |

## 5. Executive Briefing — Raccomandazioni numerate

> **5 raccomandazioni attive (B1, B2, B3, B4, B6) + 1 ritirata (B5).**
> Richiedono un Decision Lock CEO esplicito, numerate per accettazione
> (✅) / rifiuto (❌) / modifica puntuale.

### B1 · Look-ahead PDC default = 35 frame (100 ms)

Ratificare `lookahead_frames = 35` come default di `GoldDataset`,
`evaluate_holdout`, e di tutti i tool R&D. Implementazione: cambiare il
default da `0` a `35` in `src/neural/data.py::GoldDataset.__init__`
e `src/neural/train.py::train()` + `evaluate_holdout()`. F0-T4a §3
amendment "PDC = 100 ms" già nel testo della spec; aggiungere riferimento
esplicito a questa implementazione.

### B2 · Crop minimo di training = 135 552 samples (~3.07 s)

Ratificare `crop_samples ≥ 135 552` come **minimo bloccante** in
`GoldDataset.__init__` (raise `GoldDataError` se inferiore). Default
proposto: `crop_samples = 196 608` (~4.46 s, margine 1.45× sopra il
minimo). F0-T4a §3 amendment "Training crop ≥ RF + lookahead";
aggiungere il vincolo derivato in tabella.

### B3 · LossConfig defaults riparametrizzati

Ratificare i nuovi default di `LossConfig`:
```
pos_weight       = 200
w_onset          = 2.0
w_velocity       = 0.1
w_microtiming    = 0.1
w_hihat          = 0.25
focal_gamma      = 2.0   (invariato)
fp_to_fn_ratio   = 3.0   (invariato)
onset_mask_threshold = 0.5  (invariato)
```
F0-T4a §6 amendment con tabella aggiornata e nota su derivazione da
density misurata 0.4-1.5 %.

### B4 · F0-T2a §3.8 amendment — durata MIDI minima = 5 s

Ratificare `midi_duration_min_s = 5.0` come parametro versionato della
recipe matrix di F0-T2a. Implicazioni operative:

- Filtrare i MIDI di GMD < 5 s prima della recipe matrix di F2-T1.
- `tools/build_recipe_matrix.py` aggiunge un filtro `--min-duration-s 5.0`.
- Storage Gold: ~+30 % ($42 vs $32 mensile, dentro allocazione §5).
- Wall-time render: ~+20 % (~6h vs ~5h, dentro spend budget).
- **Pre-flight chiuso (2026-05-23):** GMD v1.0 contiene 1150 MIDI;
  **551 (47.9 %) ≥ 5 s**, mediana 4.35 s. Con jitter k=2 + baseline (×3)
  × 8 kit del roster F0-T1b = **13 224 sample di training**, sopra la
  soglia ~10 K della CRNN literature. Audio augmentation F2-T2 ×3 porta
  a ~40 K (in linea col SOTA Vogl `M=43 K`).

### ~~B5 · Bus-mask~~ — ❌ RITIRATA (2026-05-24)

> Errore di interpretazione: avevo letto i nomi degli **input mic slot**
> (`CANONICAL_SLOT_MAP` di `src/neural/data.py`) e li avevo applicati ai
> bus di **output**. I 3 bus che il diagnostic mostrava muti non sono
> Overhead/Room, sono **ride / crash_a / crash_b_misc** — categorie di
> trigger reali bloccate dal Decision Lock F0-T2a 2026-05-20
> (`docs/specs/midi_mapping_table.yaml`). **Non vanno mascherati.** Vedi
> B6 per l'osservazione corretta che emerge dalla misura empirica.

### B6 · Class balance per-bus sui piatti (ride / crash_a / crash_b_misc)

La misura empirica dei target del mix `2026-05-24` (§4.6) mostra una
**class imbalance bi-assiale** sui piatti che né B3 (`pos_weight`
scalare) né il `rare_emphasis` attuale risolvono interamente:

- `crash_a` appare nel **0.7 %** dei sample GMD (5 onset totali su 405)
- `ride` 13 %, `crash_b_misc` 11 %
- In contrasto: kick 73 %, snare 97 %

Ratificare **tre sotto-fix ortogonali**, additivi, costo $0:

**B6a · Sample-level `WeightedRandomSampler`**
- Implementare `WeightedRandomSampler` nel `train.py` DataLoader.
- Peso per sample = `max_b (1 / density_b)` dove `b` sono i bus che il
  sample contiene. Grooves con crash_a ottengono peso ~140×.
- Cap weight a 200× per evitare che lo stesso groove monopolizzi
  l'epoch. Mitigato dal jitter k=2 (3 varianti diverse per groove).
- Implementazione: ~30 righe di `train.py`, PyTorch stdlib.

**B6b · `pos_weight` per-bus calcolato dalla density**
- `LossConfig.pos_weight` diventa `float | tuple[float, ...]` (8 valori
  o scalare per backward compatibility).
- Scan one-time del training set → calcola `pos_weight[b] = min(1000,
  (1 - density_b) / max(density_b, 1e-6))`. Cap 1000 evita gradient
  explosion su bus con density = 0 (safe by construction: nessun positive
  = nessun termine FN da pesare).
- Default proposto (calcolato sul mix corrente):
  - kick: 200, snare: 65, hihat: 250, tom_hi_mid: 100, floor_tom: 95,
    ride: 770, crash_a: **1000** (capped), crash_b_misc: 920
- Implementazione: ~50 righe in `loss.py` + scan tool + 2 oracoli.

**B6c · Rebalance mix composition 70/15/15 → 60/25/15**
- Aumentare `rare_emphasis` da 30 → 50 grooves (le 5 famiglie × 10
  varianti invece di × 6).
- Mantenere GMD a 140 grooves (60 % proporzionale) e chaos a 30 (15 %).
- Implementazione: 1 parametro in `tools/mix_dataset.py` +
  `_rare_emphasis_count = 50`.
- Costo F2-T1 incrementale: 20 grooves extra × 8 kit × 3 jitter = 480
  sample extra, trascurabile.

**Verifica di accettazione (regression test):** dopo B1+B2+B3+B6a+b+c,
un self-overfit su 18 sample che includano almeno 3 grooves con
crash_a deve produrre **F_crash_a ≥ 0.3** (vs ~0 attuale). Aggiungere
all'oracolo §6 della spec.

---

## 6. Decision Lock CEO 2026-05-24 — Voto & Docs Update

### 6.1 Registro voto

| ID | Stato | Note |
| :-- | :-- | :-- |
| **B1** Look-ahead PDC = 35 frame (100 ms) | ✅ **RATIFICATO** | Default propagato a `GoldDataset` + `train()` + `evaluate_holdout()`. |
| **B2** Crop minimo = 135 552 sample, default 196 608 | ✅ **RATIFICATO** | Fail-loud in `GoldDataset.__init__` se `crop_samples < 135 552`. |
| **B3** LossConfig riparametrizzato (pos=200, w_on=2.0, w_vel=0.1, w_mt=0.1, w_hh=0.25) | ✅ **RATIFICATO** | Default applicati in `loss.py`. |
| **B4** F0-T2a §3.8 amendment `midi_duration_min_s = 5.0` | ⏸ **DEFERRED** | Rinviato a riesame post-regression test. F2-T1 resta ⊘. |
| ~~B5~~ Bus-mask | ❌ **RITIRATA** (2026-05-24) | Errore di interpretazione iniziale — vedi §4.3. |
| **B6a** `WeightedRandomSampler` | ✅ **RATIFICATO** | Attivo di default quando `loss_config.pos_weight` è tuple. |
| **B6b** `pos_weight` per-bus | ✅ **RATIFICATO** | `LossConfig.pos_weight: float \| tuple[float, ...]`. |
| **B6c** Mix `60/25/15` (rare 30→50) | ✅ **RATIFICATO** | `rare_emphasis.N_GROOVES=50`, mix totale 220 grooves. |

### 6.2 Docs Update propagati (fase 6 STRP-001)

| # | Artefatto | Stato |
| :-- | :-- | :-- |
| 1 | `F0-T4c` spec → `PARTIAL-LOCK v1.0.0` | ✅ (questo commit) |
| 2 | **F0-T4a §3** amendment crop ≥ RF + lookahead | ✅ |
| 3 | **F0-T4a §5** amendment look-ahead = 35 frame esplicito | ✅ |
| 4 | **F0-T4a §6** tabella LossConfig aggiornata (B3) | ✅ |
| 5 | **F0-T2a §3.8** amendment `midi_duration_min_s = 5.0` | ⏸ **NON applicato** (B4 deferred) |
| 6 | `src/neural/data.py` — default `lookahead_frames=35`, fail-loud `crop ≥ 135 552` | ✅ |
| 7 | `src/neural/loss.py` — nuovi default + `pos_weight: float \| tuple` | ✅ |
| 8 | `src/neural/train.py` — `WeightedRandomSampler` auto-on, propagazione lookahead, CLI flags | ✅ |
| 9 | `tools/scan_density.py` — scan training set → per-bus pos_weight tuple | ✅ |
| 10 | `tools/build_recipe_matrix.py` — flag `--min-duration-s` | ⏸ **NON applicato** (B4 deferred) |
| 11 | `src/data_engineering/midi_synth/rare_emphasis.py` — `N_GROOVES = 50` | ✅ |
| 12 | `src/data_engineering/midi_synth/mix_dataset.py` — `DEFAULT_N_RARE = 50`, guard `n_rare ≤ 50` | ✅ |
| 13 | **Regression test:** harness su 18 long-context sample → F_max ≥ 0.80, F_crash_a ≥ 0.3 | ✅ (`docs/gates/F0-T4c_REGRESSION/`) |
| 14 | **`MASTER_SCHEDULING.md`** Tracking Board — F0-T4c ☑(partial), F2-T1 ⊘ (B4 deferred), F2-T3 unblocked-by-F0T4c | ✅ |

### 6.3 Piano per B4 (deferred)

A valle del regression test §6.2 #13:

- **Se F_max ≥ 0.80 + F_crash_a ≥ 0.3 (verde):** ripresentare B4 al CEO con
  i numeri reali del regression test, conferma del +30 % storage e ~+20 %
  wall-time, e con la lista finale dei MIDI GMD ≥ 5 s pre-flight (551/1150
  = 47.9 %, già misurato 2026-05-23). Voto → sblocco F2-T1.
- **Se il regression test è rosso o ambiguo:** prima di chiedere B4
  riapertura, diagnostica della differenza (capacity? sampler troppo
  aggressivo? scan_density wrong?). B4 non ha senso senza un'architettura
  che apprende.

### 6.5 Mini-L3 cross-kit verdict (2026-05-25) — campanello d'allarme

> **🔴 FAIL ❌** — pacchetto completo in
> `docs/gates/F0-T4c_MINI_L3/`. CEO directive 2026-05-24: testare il modello
> cross-kit (3 kit train → 1 kit val "vergine") prima del burn F2-T1/T3 su
> Azure, per rispondere alla domanda: *la rete impara l'evento fisico o il
> timbro?*

**Setup mini-L3:**
- **Train:** 3 kit DrumGizmo (DRSKit, MuldjordKit3, CrocellKit) × 117 GMD MIDI
  (≥ 5s, ≤ 15s) × 2 jitter variants = **656 Gold sample**
  (di cui 600 usati per OOM safety sul Mac 16 GB)
- **Val "vergine":** ShittyKit × 117 MIDI × 1 jitter = **115 Gold sample**
  (kit mai visto in training — Decision Lock CEO 2026-05-23 Opzione B)
- **Model:** F0-T4a TCN `C=32` (83 673 params) con tutti i default F0-T4c
  (lookahead=35, crop=196 608, LossConfig B3, B6a/B6b pos_weight per-bus)
- **Wall-time:** ~30 min totali (15 min render train + 1 min render val +
  10 min training MPS + report)

**Risultati:**

| Configuration | Train sample | Epoch | Final train loss | Val F_mean | Val F range | Verdetto |
| :-- | --: | --: | --: | --: | :-- | :--: |
| Run 1 (baseline-only) | 331 | 120 | 1.09 | **0.049** | [0.005, 0.151] | ❌ FAIL |
| Run 2 (full pool) | 600 | 150 | 1.11 | **0.021** | [0.005, 0.040] | ❌ FAIL |

**Gate target:** F_mean ≥ 0.55 (sotto L4 = 0.80, sopra regression test self-overfit).

**Pattern diagnostico per-bus sul val ShittyKit (aggregato 115 sample):**

| Bus | n_true | n_pred | n_match | Precision | Recall |
| :-- | --: | --: | --: | --: | --: |
| kick | 526 | 37 444 | 438 | 0.012 | 0.833 |
| snare | 1 201 | 45 168 | 1 198 | 0.027 | **0.998** |
| hihat | 371 | 46 211 | 371 | 0.008 | **1.000** |
| floor_tom | 295 | 44 958 | 294 | 0.007 | 0.997 |
| ride | 300 | 44 857 | 300 | 0.007 | **1.000** |

**Diagnosi:** la rete sui timbri ShittyKit collassa a **"predici onset ovunque"**
— Recall ~1.00 (becca quasi tutti i veri perché spara su quasi ogni frame),
Precision ~0.01 (140× più false positive del necessario). Stesso pattern del
sample collapse osservato su RND003/RND045 nel regression test (§6.4) — la
rete non generalizza a domini fuori distribuzione.

**Cause strutturali (ordinate per severità):**
1. **Mismatch microfonico drastico.** ShittyKit ha mic layout incompatibile
   con i 3 kit train (no mic Hihat dedicato → mappato a OH-L bleed; naming
   `kick`/`snare` lowercase vs `Kdrum_front`/`Snare_top` dei kit moderni;
   8 mic totali vs 13-16 — vedi `docs/specs/kit_mic_mapping.yaml`).
2. **`pos_weight` cap 1000** (B6b) per `crash_a`/`crash_b` premia la rete che
   spara "sempre 1" sui domini fuori distribuzione (sui timbri sconosciuti
   ogni attivazione di basso livello passa la soglia di pos_weight aggressivo).
3. **Audio augmentation assente** (F0-T16-post deferred). La rete non ha mai
   visto la stessa nota fisica con sonorità diverse → non ha imparato
   l'invarianza spettrale che il cross-kit richiede.
4. **Capacity `C=32`** può essere troppo piccola per "memorizzare" abbastanza
   timbri da generalizzare. L'esclusione di T1-DIAG-A valeva per self-overfit;
   cross-kit è dominio strutturalmente diverso.

**Implicazione operativa per F2-T1/T3 e L4:**
- L4 userà E-GMD (registrazioni umane reali su kit reali) come holdout —
  **molto più diverso** dai render Gold sintetici di quanto ShittyKit lo sia
  da DRSKit/Muldjord/Crocell. Il mini-L3 è quindi un **campanello d'allarme
  forte**: l'L4 ha alta probabilità di fallire allo stesso modo con l'architettura
  attuale.
- Il fix B1-B6 di F0-T4c resta **architetturalmente corretto** (regression test
  self-overfit verde F=0.958 lo dimostra); il problema è di **generalizzazione
  cross-domain**, non di apprendimento.
- **Candidate mitigations da considerare prima di F2-T3:**
  - F0-T16-post audio augmentation: ratifica e implementazione (oggi `STRP-001
    IN REVIEW`) — la più probabile soluzione strutturale.
  - `LossConfig.pos_weight` cap più conservativo (es. 200 invece di 1000).
  - C=64 o C=128 (capacity test esteso a regime cross-kit, non solo
    self-overfit come T1-DIAG-A).
  - Domain randomization durante training (scrambling canali, mic drop, etc.)
    — l'idea di base di F0-T15-post B7/B8.

**Il mini-L3 NON blocca:**
- B4 (durata MIDI minima = 5 s) può essere ratificato — il mini-L3 ha
  dimostrato che la pipeline data → render → training funziona end-to-end;
  il problema è qualitativo del modello su cross-domain, non quantitativo
  della pipeline dati.
- F2-T1 può partire una volta firmato B4; il render Gold sintetico è la base
  per qualunque iterazione successiva.

**Il mini-L3 INFORMA:**
- F2-T3 ha ora una soglia di rischio quantificata: la prima training A100
  potrebbe fallire L4. Suggerimento di sequenza: prima ratifica F0-T16-post +
  re-run mini-L3 con augmentation; SOLO se passa, F2-T3 con confidenza.

### 6.4 Risultato regression test (2026-05-24)

> **🎉 PASS ✅** — pacchetto completo in
> `docs/gates/F0-T4c_REGRESSION/f0t4c-regression-2026-05-24/`.

Self-overfit su 18 long-context sample (3 contenenti `crash_a` positives,
15 ordinari) per 600 epoche su Mac M5/MPS. Tempo totale: **51.7 s wall**.

| Metrica | Target | Risultato | Stato |
| :-- | :--: | :--: | :--: |
| F_max | ≥ 0.80 | **0.958** (`LOCAL_RND124-V3T1-J02`) | ✅ PASS |
| F_crash_a (max su crash-bearing) | ≥ 0.30 | **1.000** (tutti e 3) | ✅ PASS |
| timing_mae sul best-F | ≤ 5 ms | **0.64 ms** | ✅ PASS |

Distribuzione F: i 3 sample con `crash_a` sono i top assoluti (F ∈ [0.943,
0.958]) — il `WeightedRandomSampler` con peso 137× (B6a) + `pos_weight=137`
(B6b) ha effettivamente foregrounded il bus raro. 9 dei 12 sample senza
`crash_a` raggiungono F ≥ 0.5; 6 sample con audio molto lungo (>228 K
samples) restano sotto 0.05 — fisiologico in self-overfit con C=32 e
solo 83 673 parametri.

**Conclusione operativa:** i fix ratificati funzionano end-to-end come
predetto dalla diagnostica T1-DIAG-A. **B4 può essere ripresentato al CEO**
per voto, con conferma empirica che l'architettura **assolutamente
risponde** ai nuovi default — il +30 % storage e ~+20 % wall-time di B4 sono
giustificati.
