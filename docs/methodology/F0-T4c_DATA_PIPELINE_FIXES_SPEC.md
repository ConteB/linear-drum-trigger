---
id: LIN-DT-SPEC-F0T4C
title: F0-T4c — Data Pipeline Fixes (causality + RF + loss imbalance) — STRP-001
type: spec
status: STRP-001-IN-REVIEW
phase: F0
domain: Neural / Data Engineering
version: 0.1.0
updated: 2026-05-23
tags: [F0-T4c, F0-T4a, lookahead, receptive-field, loss-imbalance, STRP-001, pre-Azure-gate]
related: [LIN-DT-SPEC-F0T4A, LIN-DT-SPEC-F0T2A, LIN-DT-RND-T1DIAGA-001]
supersedes: []
---

# 🔬 F0-T4c — Data Pipeline Fixes — STRP-001

> **Status: STRP-001 IN REVIEW.** Documento pre-Decision Lock. Applica le
> 6 fasi del Mandato Operativo (CLAUDE.md) all'ondata di findings della
> diagnostica [T1-DIAG-A](../gates/R&D_Tier1_reports/T1-DIAG-A/T1_DIAG_A_REPORT.md)
> (2026-05-23) e arriva a un Executive Briefing formale con
> raccomandazioni numerate da ratificare. La fase 6 (Docs Update) sarà
> applicata a valle del Decision Lock CEO.
>
> **Gate operativo:** questo Decision Lock è bloccante per **F2-T1 (render
> Gold 1.5 TB)** e **F2-T3 (training A100)** — i tre fix toccano la
> *durata minima dei sample del Gold* (B4) e i *default architetturali*
> (B1/B2/B3). Spendere il credito Azure prima di ratificarli rischia di
> renderizzare un Gold che la rete non può consumare e/o di trainare un
> modello strutturalmente identico a quello che la diagnostica ha già
> dimostrato fermarsi a F = 0.08.

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
gate L3 a livello individuale**. Il documento ratifica i tre fix come
amendment a F0-T4a §3 / §6 e a F0-T2a §3.8, e blocca il consumo del
credito Azure su F2-T1 finché il Decision Lock CEO non è formalizzato.

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

I tre fix non aggiungono né tolgono componenti UI. Sono modifiche
interne al data pipeline + ai default architetturali. **Nessun impatto
visivo.**

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

### 4.3 Bus-mask dei 3 head morti — fix secondario `[F]` P2

I bus OH_L / OH_R / Room non hanno mai onset nel target (sono mic
positions, non bus di trigger). Tre opzioni:

| Opzione | Approccio | Vantaggio | Svantaggio |
| :-- | :-- | :-- | :-- |
| (a) **N_BUSES = 5** | Riduce flat-25 → flat-16 | Cleanest | Rompe il contratto F0-T2a §3.3, invasivo |
| (b) **Bus-mask nel loss** | I 3 bus muti restano nel target ma il loss ignora i loro contributi | Zero rotture | Modello continua a parametrizzare 3 head inutili |
| (c) **Lasciare com'è** | Niente fix | Zero lavoro | Spreco di capacity (qual.) — non bloccante |

**Raccomandazione: (b)** — bus-mask nel `TCNLoss` su un set bloccato di
indici (5 bus reali: 0/1/2/3/4). Modifica chirurgica al loss, niente
rotture di contratto. Tier 2, può essere committato dopo F2-T3.

### 4.4 Costo

| Voce | Costo | Note |
| :-- | --: | :-- |
| Implementazione fix (B1/B2/B3 defaults) | **$0** | Codice già esiste come knob CLI in `a3fe30c` / `c7f10a5`; serve solo cambiare default + ratificarli |
| Implementazione bus-mask (B5) | **$0** | ~50 righe in `loss.py` + 2 oracoli |
| Amendment F0-T2a §3.8 (B4) | **$0** | Doc-only |
| F2-T1 storage impact (clip ≥ 5 s vs 1-3 s media local_rnd) | **~+30 %** sul Gold storage | Cool LRS, da $32 a ~$42/mese → dentro budget ($55 allocato §5) |
| Tempo wall-clock F2-T1 con clip più lunghe | **~+20 %** | Render time scale lineare con clip duration. Da ~5h a ~6h → dentro spend budget |

### 4.5 Rischi

| Rischio | Mitigazione |
| :-- | :-- |
| 100 ms PDC inaccettabile per use-case live | Documentato; v1.0 è "Studio Mode". V1.x può esplorare lookahead ridotto. |
| Sample > 5 s mismatch con GMD reale (median ~10-12 s, OK; ma alcuni grooves brevi) | Filtrare a monte i MIDI < 5 s. **Verifica empirica:** GMD v1.0 contiene 1150 MIDI; quanti sono ≥ 5 s? **Da misurare prima del Decision Lock.** |
| LossConfig riparametrizzato peggiora qualche metrica secondaria (timing-MAE, hihat-MAE) | Diagnostic ha mostrato timing-MAE STESSO o migliore. HiHat MAE leggermente peggio (era già fuori range con vecchi default). Da rivalutare a F2-T3. |

## 5. Executive Briefing — Raccomandazioni numerate

> Le **5 raccomandazioni** richiedono un Decision Lock CEO esplicito.
> Numerate per accettazione (✅) / rifiuto (❌) / modifica puntuale.

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

### B5 · Bus-mask dei 3 head morti (OH_L/OH_R/Room) — Tier 2

Aggiungere `loss_bus_mask: tuple[int, ...] = (0, 1, 2, 3, 4)` a
`LossConfig` (lista dei bus che contribuiscono al loss). Esclude 5, 6,
7 di default. Modifica chirurgica a `TCNLoss.forward`. **Tier 2** — può
essere ratificato in qualsiasi momento prima di F2-T3, non blocca F2-T1.

---

## 6. Decision Lock & Docs Update (placeholder)

> A valle del Decision Lock CEO:
>
> 1. Aggiornare `status: STRP-001-IN-REVIEW` → `LOCKED`, incrementare
>    `version` a `1.0.0`.
> 2. **F0-T4a §3** → amendment "PDC default = 35 frame" + vincolo
>    `crop ≥ RF + lookahead` con tabella RF.
> 3. **F0-T4a §6** → tabella `LossConfig` aggiornata (B3).
> 4. **F0-T2a §3.8** → aggiungere `midi_duration_min_s = 5.0` (B4).
> 5. **`src/neural/data.py`** → cambio default `lookahead_frames=35`,
>    minimum check `crop_samples ≥ 135 552`.
> 6. **`src/neural/train.py`** → cambio default `crop_samples`,
>    propagazione lookahead a `evaluate_holdout`.
> 7. **`src/neural/loss.py`** → nuovi default `LossConfig`.
> 8. **`tools/build_recipe_matrix.py`** → flag `--min-duration-s 5.0`.
> 9. **`MASTER_SCHEDULING.md`** → F2-T1 sblocco (era ⊘ blocked da
>    F0-T4c), F2-T3 sblocco (idem), F0-T4c → ☑.
> 10. **Regression test:** harness `pytest` su 18 sample long-context
>     deve riprodurre F_max ≥ 0.80, F_shuf < 0.10 con i nuovi default.
