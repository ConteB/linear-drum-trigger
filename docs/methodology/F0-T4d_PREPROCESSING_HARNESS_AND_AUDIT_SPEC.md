---
id: LIN-DT-SPEC-F0T4D
title: F0-T4d — Preprocessing Harness + Training Audit (STRP-001)
type: spec
status: LOCKED
phase: F0
domain: Neural / DSP / Reporting
version: 1.0.0
updated: 2026-05-25
tags: [F0-T4d, preprocessing, training-audit, P1-pre-emphasis, P2-onset-envelope, ledger, STRP-001]
related: [LIN-DT-SPEC-F0T4A, LIN-DT-SPEC-F0T4C, LIN-DT-DOSSIER-001, LIN-DT-RPTBP-001]
supersedes: []
---

> **Decision Lock CEO 2026-05-25**: tutte le 6 raccomandazioni B1..B6
> ratificate. Implementazione completa in sessione.

# 🔬 F0-T4d — Preprocessing Harness + Training Audit (STRP-001)

> **Status: STRP-001 IN REVIEW (2026-05-25).** Documento pre-Decision Lock.
> Risponde alla **direttiva CEO 2026-05-25** post mini-L3 FAIL ❌:
>
> > «vorrei capire una cosa. è possibile fare un harness al modello neurale
> > che stiamo allenando per rendergli il lavoro più facile? un po di
> > preprocessing dei dati che de-tona la batteria magari [...]
> > bisogna tener traccia degli aumenti anche lato training. bisogna fare
> > il modo che il training sia il più efficace ed efficiente possibile.
> > e bisogna assolutamente prevedere un audit su questo»
>
> Il documento copre **tre componenti complementari**: (A) un layer di
> *preprocessing audio* davanti alla TCN — P1 pre-emphasis + P2 onset
> envelope — per de-tonare/normalizzare il segnale prima della rete;
> (B) un **Training Audit Ledger** versionato che registra ogni esperimento;
> (C) un set di *training efficiency improvements* (mixed-precision sempre,
> grad accumulation, optimizer schedule, early stop).

## 0. Sintesi esecutiva (1 paragrafo)

Il mini-L3 ([F0-T4c §6.5](F0-T4c_DATA_PIPELINE_FIXES_SPEC.md)) ha mostrato
che la rete F0-T4a `C=32` collassa a "predici onset ovunque" sui timbri
fuori distribuzione (ShittyKit val: F=0.021, Recall 1.00, Precision 0.01).
Tre interventi ortogonali possono mitigare il problema; questa spec si
concentra su **un input-side preprocessing leggero** (P1+P2) che de-tona
il segnale e fornisce un'evidenza onset pre-digerita, lasciando a F0-T16-post
il lato augmentation training-side. Il preprocessing è progettato per essere
**replicabile in C++ RTNeural** (vincolo Zero-Allocation F4): nessuna STFT,
solo biquad + running statistics + un secondo stream a 344 Hz (l'onset envelope
opera già nel dominio del frame target). Parallelamente si introduce un
**Training Audit Ledger** versionato — schema YAML che traccia ogni training
run con preprocessing/aug/hyper/metrics, permettendo diff cross-run e
identificazione delle cause di lift. Il ledger è mandatorio per ogni run
futuro (gate di accettazione: nessun run senza entry).

## 1. Competitor & Market Analysis

### 1.1 Pre-emphasis nel sistema MIREX / DRUM ML

| Sistema | Preprocessing | Effetto su F (drum onset) |
| :-- | :-- | --: |
| **Bock & Schedl** (RNN onset, ISMIR 2014) | Mel spectrogram + log + delta | 0.91 baseline |
| **Bock & Schedl no-preproc** | Raw audio | 0.78 (−15 %) |
| **Vogl et al.** (CRNN drum transcription, ISMIR 2017) | Mel-filterbank 80 bands + log | 0.91 |
| **ADTOF** (Zehren et al. 2021) | Log-mel + per-channel norm | 0.93 |
| **OnsetsAndFrames** (Hawthorne et al. 2018) | Log-mel + Z-score | 0.95 (piano) |
| **madmom SpectralOnset** | Spectral flux + adaptive whitening | 0.89 |

Industria consensus: **mai audio raw direttamente**. Sempre almeno un
pre-emphasis + spectral transform + normalization. Saltare il preprocessing
costa 15-20 % di F-measure (Bock & Schedl ablation).

### 1.2 De-toning (HPSS) nel SOTA

| Sistema | HPSS pre-model | Effetto |
| :-- | :-- | :-- |
| **Wu & Lerch 2018** (DTM) | HPSS frontend | +6 % F crash |
| **MT3** (Gardner 2022) | Niente (full-mix transformer) | 0.79 crash |
| **Demucs DrumSep** (Défossez 2021) | Pretrained source separation | Stem-isolation perfetta ma 50 ms latency |

HPSS aggressivo (P3 nel nostro inventario) ha trade-off: migliora kick/snare/tom
ma **danneggia ride/crash** (i piatti sono prevalentemente tonali nelle alte
frequenze; HPSS li classifica come "harmonic" e li attenua).
**Conclusione operativa: HPSS no, spectral flux sì** — il flux preserva i
piatti perché coglie il loro *attacco transitorio*.

### 1.3 Tracking degli esperimenti — pratiche industriali

| Tool/sistema | Cosa traccia | Costo |
| :-- | :-- | :-- |
| **MLflow** | Hyper, metric, artifact | Heavy (server) |
| **Weights & Biases** | idem + plots | SaaS (~$50/mese team) |
| **TensorBoard** | Loss curves, scalar | Locale, no diff cross-run |
| **Run cards** (manuale, paper-style) | Tutto in YAML/MD versionato | Zero infra, full audit |

Per il nostro vincolo $0 Azure + privacy (zero divulgazione del progetto):
**ledger versionato in repo** è la scelta univoca. Pattern affermato in
laboratori "audit-first" (es. EleutherAI run cards, OpenReview supplementary).

## 2. Open-Source Codebase Analysis

| Repo | Riferimento utile | Cosa prendiamo |
| :-- | :-- | :-- |
| **madmom** (CC-BY-NC) | `madmom.audio.signal.SignalProcessor` — pre-emphasis 1-pole | Solo concetto (research-only license); riscritto ex-novo |
| **librosa** (ISC) | `librosa.onset.onset_strength` (spectral flux) | Reference algorithm — riscritto in PyTorch differenziabile per training |
| **torchaudio** (BSD) | `torchaudio.transforms.PreEmphasis`, `MelSpectrogram` | Differenziabile, usabile direttamente come building block |
| **ADTOF data pipeline** (Apache-2.0) | Per-channel z-score running | Pattern; ~20 LOC ex-novo |
| **PyTorch `torchaudio.functional.spectrogram`** | STFT differenziabile su GPU | API stabile (≥ 2.0) |

Tutti i building block esistono in torchaudio/PyTorch nativo. **Nessuna nuova
dipendenza richiesta** (torchaudio già presente per la TCN).

## 3. UX/UI Impact

### 3.1 Preprocessing è invisibile all'utente

Pre-emphasis + onset envelope sono **dentro il modello** dal punto di vista
del plugin C++. Lo step DSP front-end è trasparente: l'utente non vede mai
"un onset envelope" — vede solo i trigger MIDI. Zero impatto UI/UX.

### 3.2 Latency

P1 (pre-emphasis biquad) aggiunge **≤ 1 sample** di latency (1-pole HP).
P2 (onset envelope) opera al frame rate `R_target = 344 Hz`, quindi
non aggiunge latency oltre il PDC già contabilizzato (35 frame = 100 ms).

### 3.3 Badge "Laboratory Precision"

Il preprocessing rinforza il claim "Laboratory Precision" del prodotto:
non audio raw "in pasto" a un modello, ma un pre-processing DSP-grade
classico (P1) + state-of-art onset evidence (P2). Coerente con la dottrina
visiva del progetto.

## 4. Tech Implementation Matrix

### 4.1 Il preprocessing layer — P1 + P2

#### P1 · Pre-emphasis + per-channel z-score

| Componente | Operazione | Iperparametro | LOC (Python) | LOC (C++ runtime) |
| :-- | :-- | :-- | :--: | :--: |
| **Pre-emphasis** | `y[t] = x[t] − α · x[t−1]` (1-pole HP) | `α = 0.97` | ~5 | ~10 (biquad coef) |
| **Per-channel z-score** | `z = (x − μ_running) / σ_running` | EMA decay = 0.99 | ~15 | ~20 (running stats) |
| Subtotal | | | **~20** | **~30** |

Differenziabile: `torchaudio.transforms.Preemphasis` esiste già. Per il
z-score running, custom `nn.Module` con `register_buffer` per μ/σ.

#### P2 · Onset envelope concat (9° canale)

| Componente | Operazione | Iperparametro | LOC |
| :-- | :-- | :-- | :--: |
| **STFT** | `torch.stft` n_fft=2048 hop=128 | window=Hann | ~5 |
| **Magnitude → log-mel** | `MelScale(n_mels=80)` + `log1p` | sr=44100 | ~5 |
| **Differenziale temporale** | `max(0, frame[t] − frame[t−1])` | half-wave rectify | ~5 |
| **Sum across mel bands** | → 1 canale per frame | mean | ~3 |
| **Concat con audio 8-canali** | `cat([audio, envelope], dim=1)` su canale | resample envelope da 344 Hz a 44100 Hz via NN-repeat × 128 | ~10 |
| **Subtotal Python** | | | **~30** |
| **Subtotal C++ runtime** | STFT + mel + concat | ~150 |
| | | | |

**Architectural change**: `TCNModel.in_channels: 8 → 9`. La Conv1D k=1
dell'Input-Agnostic Projection (F0-T4a §3.①) assorbe il 9° canale come
banalità (la Conv1D è agnostica al numero di canali in ingresso).
**Backward compat**: gli oracoli L1 del flat-25 target restano invariati.

### 4.2 Training Audit Ledger — schema

**File:** `docs/audit/TRAINING_LEDGER.md` (Markdown + tabella + JSON-LD per entry).

**Schema entry:**
```yaml
run_id: mini-l3-crosskit-p1p2-2026-05-25
date: 2026-05-25T01:30:00Z
git_commit: 32fc9ff
status: PASS | FAIL | BASELINE | ABANDONED

# Dataset
dataset:
  pool_root: data/gold/mini_l3_train
  n_train_samples: 600
  n_val_samples: 115
  train_kits: [DRSKit, MuldjordKit3, CrocellKit]
  val_kits: [ShittyKit]   # cross-kit
  midi_source: GMD v1.0 (all-splits, 5-15s, 117 grooves)
  jitter_variants: [0, 1]   # baseline + 1 jittered

# Model
model:
  arch: F0-T4a TCN
  channels: 32
  in_channels: 9             # 8 mic + 1 onset envelope
  trunk_depth: 8
  params: 84_186             # +513 from in_channels=8→9

# Preprocessing (NEW in F0-T4d)
preprocessing:
  P1_pre_emphasis: { alpha: 0.97 }
  P1_channel_norm: { ema_decay: 0.99 }
  P2_onset_envelope: { n_fft: 2048, hop: 128, n_mels: 80 }

# Augmentation (existing)
augmentation:
  midi_pre_F0T15pre: enabled (k_variants=1)
  audio_post_F0T15post: disabled

# Loss config (F0-T4c B3+B6b)
loss:
  pos_weight: [132, 64, 200, 269, 235, 243, 1000, 1000]
  w_onset: 2.0
  w_velocity: 0.1
  w_microtiming: 0.1
  w_hihat: 0.25

# Training
training:
  epochs: 150
  batch_size: 8
  lr: 1.0e-3
  optimizer: AdamW
  sampler: WeightedRandomSampler (B6a, cap=200)
  device: mps
  wall_time_s: 563

# Metrics
metrics:
  final_train_loss: 1.11
  val_F_mean: 0.??              # TARGET ≥ 0.55
  val_F_range: [0.??, 0.??]
  val_per_bus_F:
    kick: 0.??
    snare: 0.??
    # ...

# Verdict + delta vs predecessor
verdict:
  gate: F_mean ≥ 0.55
  outcome: PASS | FAIL
  delta_vs_run: mini-l3-crosskit-fulldata-2026-05-25 → +0.??
  notes: |
    Add P1+P2 preprocessing — first run with input-side harness.
    [link to HTML report]

# Cost
cost:
  azure_usd: 0.00
  local_compute_min: 9.4
```

**Backfill mandatorio**: i 4 run già fatti (regression PASS, regression
uniform PASS, mini-L3 run 1 FAIL, mini-L3 run 2 FAIL) devono essere
ricostruiti come entry ledger storiche per dare baseline al diff cross-run.

**Tool**: `tools/training_ledger.py` (CLI):
- `add` — appende entry da config + report.json
- `list` — tabella sintetica run × verdict × F_mean
- `diff <run-a> <run-b>` — diff cross-run su tutti i campi
- `query` — filtra per status/preprocessing/data/etc.

### 4.3 Training efficiency improvements

| ID | Cosa | Lift atteso | Costo (LOC) |
| :-- | :-- | :-- | --: |
| **E1** | Mixed-precision sempre on (`autocast(fp16)`) | Già attivo; 1.5× speedup MPS | 0 (no change) |
| **E2** | `torch.compile()` sull'inferenza per evaluate_holdout | 1.5× speedup eval | ~3 |
| **E3** | Cosine LR schedule con warmup | Convergenza più stabile, meno epoch | ~10 |
| **E4** | Early stopping su patience N=20 epoch (no val improvement) | Risparmia 30-50 % epoch se converge presto | ~15 |
| **E5** | Gradient accumulation per emulare batch=32 con RAM=4 | Migliore stima del gradient | ~10 |

Subtotal E2-E5: ~40 LOC, lift atteso 30-50 % wall-time + qualche % di
robustezza convergenza.

### 4.4 Costo

| Voce | Costo |
| :-- | --: |
| Implementazione P1+P2 (~50 LOC Python) | **$0** |
| Training Audit Ledger tool (~150 LOC) | **$0** |
| Efficiency (E2-E5, ~40 LOC) | **$0** |
| Re-run mini-L3 con P1+P2 (~10 min su MPS) | **$0** |
| Backfill 4 run esistenti nel ledger | **$0** |
| C++ port (P1=~30 LOC + P2=~150 LOC) | rinviato a **F4** |

**Totale costo Azure: $0.** Sessione di sviluppo locale stimata 2-3h
(implementazione + audit + re-run + verifica).

### 4.5 Rischi

| Rischio | Mitigazione |
| :-- | :-- |
| P2 onset envelope non aiuta cross-kit | Confronto baseline pre/post nel ledger → se delta < +0.05 → ritira P2 e tenta solo P1 |
| Pre-emphasis distorce piatti (alte freq) | Test con α più conservativo (0.95) → ledger entry comparativa |
| C++ port di P2 (STFT) pesante in F4 | Fallback: P1 solo (escludi P2). Decisione a F4 quando si vede il budget runtime reale. |
| Ledger diventa "scartoffia" (entry incomplete) | Tool `training_ledger.py add` enforce schema strict; senza entry il commit fa fail |
| Esperimenti P1+P2 → ancora F < 0.55 | Diagnosi: il problema è di training-side (augmentation), non input-side. Si passa a F0-T16-post come priorità. Ledger documenta il fallimento, niente sforzo perso. |

## 5. Executive Briefing — Raccomandazioni numerate

> **6 raccomandazioni**, indipendentemente votabili (✅ accept / ❌ reject /
> ✏️ modifica). 5 di queste sono **a costo $0 e a basso rischio**; la #6
> (efficiency) è puramente performance, mai bloccante.

### B1 · Preprocessing P1 (pre-emphasis + per-channel z-score)

Implementare `src/neural/preprocessing.py::PreEmphasis(α=0.97)` +
`ChannelNorm(ema_decay=0.99)` come layer differenziabile prima del trunk
TCN. Replicabile in C++ con biquad standard. **Vincolo `in_channels=8`
preservato**.

### B2 · Preprocessing P2 (onset envelope come 9° canale)

Aggiungere un canale di spectral-flux onset envelope (`torchaudio.STFT` +
`MelScale` + half-wave-rectify diff + concat). **Cambio architetturale:
`TCNModel.in_channels: 8 → 9`** (Conv1d k=1 dell'Input-Agnostic Projection
assorbe). +513 parametri totali. Amendment F0-T4a §3/§4.

### B3 · Training Audit Ledger (mandatorio per ogni run)

Creare `docs/audit/TRAINING_LEDGER.md` come ledger versionato; tool
`tools/training_ledger.py` (add/list/diff/query). **Gate di accettazione**:
nessun training run è "valido" senza entry ledger. CI hook a F4 verifica
che ogni commit con un nuovo report HTML abbia anche un nuovo ledger entry.

### B4 · Backfill ledger con 4 run esistenti

Ricostruire le entry per: F0-T4c regression PASS, regression uniform PASS,
mini-L3 run 1 FAIL, mini-L3 run 2 FAIL. Permette al CEO di vedere subito
"che esperimenti abbiamo fatto, cosa hanno mostrato" senza scorrere git.

### B5 · Re-run mini-L3 con P1+P2

Stesso setup (3 kit train + ShittyKit val, 600 sample, 150 epoch) ma con
preprocessing P1+P2 attivo. Confronto diretto con il run senza
preprocessing: lift atteso +20-40 % F (oggi F=0.021 → target ≥ 0.04-0.07
per non bocciare P1+P2; ≥ 0.55 per passare gate mini-L3).

### B6 · Training efficiency (E1-E5)

E1 già attivo. E2 (`torch.compile` su eval), E3 (cosine LR + warmup), E4
(early stopping), E5 (grad accumulation) — implementati come opzioni del
training loop. Lift wall-time ~30-50 %. **Non bloccante**: si possono fare
in passi separati e indipendenti.

## 6. Decision Lock & Docs Update (placeholder)

A valle della ratifica:

1. `F0-T4d` spec → `LOCKED v1.0.0`
2. **Amendment F0-T4a §3** — `in_channels: 8 → 9` con descrizione del
   9° canale onset envelope
3. **Amendment F0-T4a §4** — slot 9 = "onset_envelope (auto-derived)"
4. `src/neural/preprocessing.py` (nuovo)
5. `src/neural/model.py` — `TCNConfig(in_channels=9)`, propagazione
6. `src/neural/train.py` + `tools/mini_l3_train.py` — wire preprocessing
   prima del modello, log preprocessing config nel report
7. `docs/audit/TRAINING_LEDGER.md` (nuovo) + `tools/training_ledger.py`
   (nuovo)
8. **Backfill** 4 entry storiche
9. **Re-run mini-L3 con P1+P2** + nuova entry ledger
10. `04_INTELLIGENCE/MASTER_SCHEDULING.md` Tracking Board — F0-T4d ☑

## 7. Gate operativo

- **Per F2-T1**: F0-T4d **non bloccante** (la pipeline dati è invariata).
- **Per F2-T3 (training A100)**: F0-T4d **fortemente raccomandato** prima
  del burn $50-80, perché aumenta significativamente la probabilità di
  passare L4. Se il CEO vuole partire F2-T3 senza, accetta esplicitamente
  il rischio L4 documentato in F0-T4c §6.5.
- **Per F4 (plugin C++)**: vedi §9 "C++/JUCE Port Plan" — diventa il primo
  task obbligatorio di F4 (**F4-T0 · DSP Harness Audit & Port**, vedi
  `04_INTELLIGENCE/MASTER_SCHEDULING.md` §6).

<a id="cpp-port-plan"></a>
## 9. C++/JUCE Port Plan (deliverable F4)

> **Scope di questa sezione**: documentare passo-per-passo cosa fa l'harness
> di preprocessing in PyTorch (quello che gira durante il training) e
> dimostrare che è **integralmente replicabile in JUCE C++** con i vincoli
> del progetto (Zero-Allocation thread audio, PDC ≤ 100 ms, bit-exactness
> Python↔C++). Il documento è la **base operativa** per il task
> **F4-T0 · DSP Harness Audit & Port (STRP-001)** che apre la fase F4
> dell'implementazione plugin.

### 9.1 Flusso dati end-to-end

```
Input audio raw 44.1 kHz multi-mic
        │
        │  [B, 8, T]  (8 canali microfonici)
        ▼
┌─────────────────────────────────────────────────────────┐
│  PreprocessingFrontend (src/neural/preprocessing.py)    │
│                                                         │
│  ┌───────────────┐    ┌──────────────────────────────┐  │
│  │  P1.1         │    │  P2  OnsetEnvelope           │  │
│  │  PreEmphasis  │    │  (in parallelo)              │  │
│  │  (HP filter)  │    └──────────────────────────────┘  │
│  └───────────────┘                  │                   │
│         │                           │                   │
│         │  [B, 8, T]                │  [B, 1, T]        │
│         │  (audio "pulito")         │  (onset evidence) │
│         └──────────┬────────────────┘                   │
│                    │                                    │
│                    │  concat dim=1 → [B, 9, T]          │
│                    ▼                                    │
│         ┌─────────────────────┐                         │
│         │  P1.2 ChannelNorm   │                         │
│         │  (z-score per-ch)   │                         │
│         └─────────────────────┘                         │
│                    │                                    │
└────────────────────┼────────────────────────────────────┘
                     │  [B, 9, T]  →  alla TCN
                     ▼
```

### 9.2 Step-by-step (cosa fa ogni layer e perché)

#### Step 1 — `PreEmphasis` (P1.1)

- **Cosa fa**: high-pass 1° ordine, attenua DC + sub-bass.
- **Formula**: `y[t] = x[t] − 0.97 · x[t−1]`
- **Perché**: il transient è ciò che ci interessa per l'onset detection.
  Il sustain (coda del piatto, sottofondo del basso) è rumore informativo.
  Pre-emphasis enfatizza la *novità temporale*.
- **Costo per sample**: 1 moltiplicazione + 1 sottrazione.

#### Step 2 — `OnsetEnvelope` (P2) — onset evidence classico MIREX

7 sotto-passi:

##### 2a · STFT (Short-Time Fourier Transform)
- Finestre da **2048 sample** (≈ 46 ms a 44.1 kHz), una ogni **128 sample** (≈ 3 ms).
- FFT per ogni finestra → matrice tempo × frequenza ("spettrogramma").
- **Formula**: `spec[f, t] = |FFT(audio[t−1024 : t+1024]) · Hann(2048)|`

##### 2b · Mel-band reduction
- Le 1025 frequenze FFT → **80 bande mel** (scala log-spaced sotto 4 kHz, ~lineare sopra), simile al sistema uditivo umano.
- Output: matrice 80 × tempo.

##### 2c · Compressione logaritmica
- **Formula**: `log_mel = log1p(mel)`
- Comprime la dinamica: un piatto fortissimo non oscura un kick sussurrato.

##### 2d · Spectral flux (il cuore del trick)
- **Formula**: `flux[band, t] = max(0, log_mel[band, t] − log_mel[band, t−1])`
- *Differenza temporale half-wave-rectified*: cattura solo gli **incrementi** di energia.
  Nota stazionaria → flux ≈ 0. Attacco improvviso → flux grande.

##### 2e · Somma sulle bande mel
- **Formula**: `envelope[t] = Σ_{bands} flux[band, t]`
- Un singolo scalare per frame: alto quando *qualunque* banda ha un improvviso aumento di energia.

##### 2f · Min-max normalize
- **Formula**: `envelope[t] = (envelope[t] − min) / (max − min)`
- Riscalato in `[0, 1]`. Indipendente dal volume assoluto del sample.

##### 2g · Upsample × 128 (NN-repeat)
- L'envelope è a 344 Hz (frame rate del modello). Hold-and-repeat ×128 → 44 100 Hz, stesso rate dell'audio.
- Necessario per concatenarlo come 9° canale alongside ai mic.

**Perché tutta questa fatica**: dai alla rete un canale extra che dice *"qui c'è probabilmente un onset"*. Non è una predizione del modello, è un'evidenza DSP pre-computata. La rete TCN poi raffina/correla con gli altri 8 canali audio. **Il preprocessing fa il 50% del lavoro che la rete dovrebbe fare da sola.**

#### Step 3 — `concat`
```
combined = cat([mics_pre_emphasized, onset_envelope], dim=1)
# [B, 8, T] + [B, 1, T] = [B, 9, T]
```

#### Step 4 — `ChannelNorm` (P1.2)
- Per ognuno dei 9 canali: sottrai media e dividi per std (frozen, da training).
- **Formula**: `z[c, t] = (x[c, t] − μ[c]) / √(σ²[c] + ε)`
- Tutti i 9 canali a media 0 e varianza 1 → la rete vede solo la *forma* dell'onda, non la loudness.

### 9.3 Mappatura C++/JUCE — componente per componente

| Componente | Operazione DSP | JUCE building block | LOC C++ | Latenza |
| :-- | :-- | :-- | --: | --: |
| **PreEmphasis** | `y[t] = x[t] − 0.97 · x[t−1]` | `juce::IIRFilter` 1-pole o custom | ~10 | **1 sample** |
| **STFT (2048/128)** | FFT sliding-window con Hann | `juce::dsp::FFT` + ring buffer + window | ~80 | **n_fft/2 = 1024 samples (~23 ms)** |
| **Mel-bank `[80×1025]`** | matrice precomputed, 80 dot product per frame | `float[80][1025]` const + SIMD | ~30 | 0 |
| **`log1p`** | element-wise | `std::log1pf` (intrinsic) o LUT | ~5 | 0 |
| **Flux differenziale** | `max(0, frame[t] − frame[t−1])` | array diff + max | ~10 | **1 frame (~3 ms)** |
| **Sum mel + min-max** | reduce 80 + scaling | trivial loop + running min/max | ~15 | 0 |
| **NN-repeat ×128** | hold-and-repeat | trivial | ~5 | 0 |
| **Concat 8→9 canali** | append a buffer multi-channel | `juce::AudioBuffer<float>::copyFrom` | ~10 | 0 |
| **ChannelNorm** | `(x − μ) / σ` element-wise | `float[9]` μ + `float[9]` σ const + loop SIMD | ~20 | 0 |
| **Totale** | | | **~185** | **~26 ms** |

### 9.4 Compatibilità con i vincoli del progetto

| Vincolo | Stato |
| :-- | :-- |
| **Zero-Allocation thread audio** (`audit_dsp_rigor.py`) | ✅ tutto static, pre-allocato in `prepareToPlay()` |
| **LGPL-3.0 compatibile** (JUCE) | ✅ tutto JUCE nativo, nessuna libreria di terzi |
| **PDC budget ≤ 100 ms** (F0-T4a §5) | ✅ +26 ms (23 STFT + 3 flux), entro budget |
| **Compatibilità RTNeural** | ✅ il preprocessing è *davanti* a RTNeural, non dentro. RTNeural rimane invariato (`in_channels=9` nel JSON dei pesi) |
| **Bit-exact replication** | ⚠️ STFT in float32 sì; mixed-precision FP16 no (motivo dei bug NaN della sessione P1+P2). C++ usa float32 di default → no problema |

### 9.5 Architettura nel plugin JUCE (deliverable F4)

```
┌──────────────────────────────────────────────────────────┐
│  AudioProcessor::processBlock(buffer)                    │
│                                                          │
│  1. buffer (8 mic in)                                    │
│  2. PreEmphasisProcessor.process(buffer)       ← P1.1    │
│  3. OnsetEnvelopeProcessor.process(buffer)     ← P2      │
│     └─ STFT → Mel → log1p → flux → sum → upsample        │
│  4. concat(buffer, onsetEnvelope) → 9 channels           │
│  5. ChannelNormProcessor.process(9chan_buffer) ← P1.2    │
│     └─ frozen μ/σ from training (in BinaryData)          │
│  6. RTNeuralModel.forward(9chan_buffer) → trigger MIDI   │
│  7. Chronos delay-line (PDC compensation)                │
│  8. MIDI out                                             │
└──────────────────────────────────────────────────────────┘
```

### 9.6 Asset da embeddare in `BinaryData`

| Asset | Size | Note |
| :-- | --: | :-- |
| Pesi TCN cifrati (`.opna`) | ~340 KB | spec F0-T8 esistente |
| **Mel filterbank `[80×1025]`** | ~320 KB float32 → 160 KB float16 | costante, una sola volta |
| **ChannelNorm μ, σ `[9]`** | 72 byte | float32 per canale, frozen a fine training |
| **Hann window `[2048]`** | 8 KB | costante, precomputed |
| **Totale extra harness** | **~170 KB** | trascurabile |

### 9.7 Ottimizzazioni runtime considerate

- **STFT a passo `> 1 hop`** (downsampling onset evidence) → −50 % CPU, latency invariata
- **Bandpass filterbank invece di mel** → −90 % CPU, qualità leggermente peggiore (da A/B testare in F4-T0)
- **SIMD (SSE/NEON)** → `juce::dsp::FFT` lo usa già nativamente; SIMD manuale per mel-bank dot product
- **Buffer chunking** → process audio a chunk di N campioni invece di sample-by-sample (più cache-friendly)

### 9.8 Rischi tecnici noti

| Rischio | Mitigazione |
| :-- | :-- |
| STFT FP32 in C++ ≠ STFT FP32 in PyTorch (ordering FFT, edge handling) | Round-trip bit-exactness test (max\|Δ\| ≤ 1e-5) come F0-T4b — primo step di F4-T0 |
| `juce::dsp::FFT` non garantisce determinismo cross-platform (CPU vs ARM) | Verificare su entrambi (Mac arm64 + Windows x86_64); fallback "vendored FFT" se serve |
| Hann window definition differs (periodic vs symmetric) | Documentato esplicitamente nella spec PyTorch (`periodic=True`); replicato in C++ |
| Mel-bank slaney vs HTK normalization | PyTorch usa slaney (matched in `_make_mel_filterbank`); replicato bit-exact |
| Loudness drift in ChannelNorm running stats tra train ed eval | μ, σ vanno **frozen** a fine training (`model.eval()`); in C++ caricati come `const float[]` |

### 9.9 Plan operativo F4-T0 (STRP-001)

Quando F4 parte, F4-T0 è il primo task. Le 6 fasi STRP-001 saranno:

1. **Competitor & Market Analysis**: come Superior Drummer / EZdrummer / Steven Slate fanno il DSP front-end (proprietario, non documentato — sostituiamo con benchmark MIREX moderni).
2. **Open-Source Codebase Analysis**: `juce::dsp::FFT` API, `juce::IIRFilter` API, vendor SIMD libraries (Eigen/xsimd se servono).
3. **UX/UI Impact**: nessuno diretto (DSP è invisibile); badge "PDC 100 ms" già nel design (LINEAR_DESIGN_GUIDE).
4. **Tech Implementation Matrix**: tabella per ogni layer (Python ref → C++ port → bit-exact test).
5. **Executive Briefing**: piano dettagliato, budget LOC, budget CPU%, budget memoria → ratifica CEO.
6. **Docs Update**: spec C++ del DSP front-end + amendment a F0-T4d con risultati round-trip test.

**DoD F4-T0**:
- ✅ tutti i 4 componenti (PreEmphasis, OnsetEnvelope, ChannelNorm, concat) implementati come `juce::dsp::ProcessorBase` subclass
- ✅ round-trip test Python ↔ C++ verde su 10 sample (max\|Δ\| ≤ 1e-5 sul output finale TCN)
- ✅ `audit_dsp_rigor.py` verde sui file C++ (zero allocation/lock/mutex/IO nel thread audio)
- ✅ CPU profile dimostra ≤ 5 % CPU su MacBook Air M1 a 44.1 kHz / 256 sample buffer
- ✅ Latency report misurata = 26 ms ± 1 ms (PDC budget rispettato)

---
