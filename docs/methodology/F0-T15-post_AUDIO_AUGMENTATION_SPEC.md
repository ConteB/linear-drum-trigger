---
id: LIN-DT-SPEC-F0T15POST
title: F0-T15-post — Audio Augmentation Spec (post-rendering) + agnosticità d'ingresso — STRP-001
type: spec
status: STRP-001-IN-REVIEW
phase: F0
domain: Data Engineering / Neural Robustness
version: 0.1.0
updated: 2026-05-23
tags: [augmentation, audio, post-render, input-agnostic, STRP-001, F0-T15-post]
related: [LIN-DT-DOSSIER-001, LIN-DT-SPEC-F0T2a, LIN-DT-SPEC-F0T4a, LIN-DT-SPEC-F0T15PRE, LIN-DT-AUGAUDIT-001]
supersedes: []
---

# 🎚️ F0-T15-post — Audio Augmentation Spec (Post-Rendering) + Agnosticità d'Ingresso

> **Status: STRP-001 IN REVIEW.** Documento pre-Decision Lock — applica le
> 6 fasi del Mandato Operativo (CLAUDE.md), arriva a un Executive Briefing
> formale con N raccomandazioni numerate da ratificare; la fase 6 (Docs
> Update) sarà applicata a valle del Decision Lock CEO. Implementazione
> rinviata a [F0-T16-post](../../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks).

## 0. Sintesi esecutiva (1 paragrafo)

Il DOSSIER §3.2–§3.4 prescrive un piano di **audio augmentation post-render**
costruito attorno a un solo input — *batteria tracciata e mixata in studio
professionale* — articolato su tre livelli (Stem Isolate 30 % · Studio
Mutilation 40 % · Acoustic Environment + Saboteurs 30 %). Una revisione del
CEO (2026-05-22 / 23) ha isolato **due famiglie di gap** non coperte: (a)
assi reali ortogonali allo studio — codec lossy, hum/noise floor, gating,
master limiting, mix-balance randomization, click bleed, mono collapse, DC
offset; (b) **agnosticità d'ingresso** — oggi parziale (zero-fill sui conteggi
{1, 2, 4, 8}) ma non robusta a permutazione di canali né a conteggi non
canonici {3, 5, 6, 7}. Le scelte chiave da chiudere sono **8 numeriche** + **2
strutturali** + **3 regole guardia**: range delle voci nuove, ordine di
composizione delle pipeline di augmentation, scelta tra mix-balance
*label-aware* vs *proxy*, abilitazione di permutazione canali, range dei
conteggi variabili, e tre invarianti che impediscono all'augmentation di
corrompere il ground truth (no time-stretch · masking-bound · attenuation-bound).
Costo Azure stimato per le voci approvate: incremento +**$3–$8** sul render
(applicato on-the-fly al posto di un secondo rendering) + **$0** lato CPU di
augmentation in F2-T2 (resta in finestra di crediti).

---

## 1. Competitor & Market Analysis

Letteratura ADT recente — fonti pubbliche, audit del 2026-05-23.

| Sistema | M (kit) | Pipeline di audio augmentation | Mix-balance | Codec? | Hum/noise? | Note |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| **E-GMD / Magenta** (Callender 2020) | 43 | shuffled mixup audio + IR convolution (RIR diversity) | implicito (M-div) | ❌ | shuffled noise mixup | open dataset di reference |
| **ADT-CNN** (Jacques & Roebel 2019) | n.d. | **noise remixing** (drum-noise A on drum-track B) + **attack remixing** (sostituzione del primo 30 ms del transiente) + transposition envelope | ❌ | ❌ | sì (custom) | papers IEEE ICASSP |
| **ADT synthetic-to-real** (Stein 2024) | 512 preset | composition layering (bass + other instruments via Slakh-like) + convolution reverb + parametric noise injection | ❌ | ❌ | parametric | benchmark SOTA aperto |
| **Vogl/JKU drum transcription** | dataset MIREX | MUSAN noise mixing + reverb + EQ | ❌ | ❌ | sì (MUSAN) | toolkit accademico |
| **DCASE / SED** (sound event) | n.a. | SpecAugment + audio mixup + RIR + codec (MP3 round-trip) + noise diversity | ❌ | ✅ | ✅ | best practice di settore |
| **OP-NeuroTrigger** (questo progetto) | **10** | **3 livelli §3.2-§3.4 + 8 voci nuove (questa spec)** | **da chiudere** | da chiudere | da chiudere | `M=10` vincolo Self-Evident Commercial License (F0-T1b) |

**Lettura strategica.** I sistemi ADT puri non fanno **codec augmentation**,
**hum** o **mix-balance randomization** — perché il loro target d'uso è il
benchmark accademico (audio "pulito" di provenienza nota). Il letteratura
**DCASE** (sound event detection in-the-wild) sì — è il caso più vicino al
nostro mercato target (utente con input arbitrario), e quel pattern è
ricco di codec MP3 round-trip + noise diversity + RIR. Il nostro `M=10` rende
**ancora più critico** il pattern DCASE, perché non possiamo recuperare
diversità via varietà timbrica di kit reali. La mix-balance randomization
è **non standard nella letteratura ADT** ma è una richiesta esplicita del
CEO (backlog §3, asse "mix-balance") fondata sul fatto che il plugin in
produzione riceve mix qualunque — è una decisione di **prodotto**, non di
allineamento accademico.

---

## 2. Open-Source Codebase Analysis

| Library | API | Licenza | Determinismo | Adatto qui |
| :-- | :-- | :-- | :-- | :-- |
| **`pedalboard`** (Spotify) | plugin-based (Reverb, Compressor, Distortion, Bitcrush, MP3Compressor, Limiter, Gain, HighShelf, LowShelf, PeakFilter…) | GPL-3 | ✅ (seed esplicito) | ✅ **base**, già nel DOSSIER §3.4 per IR conv |
| `audiomentations` | pipeline declarativa (`AddGaussianNoise`, `AddBackgroundNoise`, `Mp3Compression`, `RoomSimulator`, `ApplyImpulseResponse`, `Gain`) | MIT | ✅ | ✅ candidato — API più dichiarativa di pedalboard, copre il 90% delle voci |
| `torch-audiomentations` | come sopra, su GPU | MIT | ✅ | ⚠️ — GPU richiede VM A100 (F2-T3); per F2-T2 CPU resta `audiomentations` |
| `pyloudnorm` (Steinmetz) | LUFS metering + normalization | MIT | ✅ | ✅ per il master limiting / loudness war scenarios |
| `pyrubberband` | time-stretch + pitch-shift via rubberband CLI | ISC | ✅ | ⚠️ **escluso** — time-stretch viola la regola §2.1 del backlog (sposta ground truth) |
| `demucs` (Facebook Research) | source separation via Hybrid Transformer | MIT | ✅ | ✅ — solo per Stem Isolate §3.2 (Demucs AI-Isolation, F2-T2 GPU) |
| `librosa` (Brian McFee et al.) | DSP generalista (resample, effects, …) | ISC | ✅ | ✅ utility — calcolo RMS / SNR per la regola §3 (label-aware) |
| `pesq` / `pystoi` | perceptual metrics | MIT | ✅ | non necessari (gate è F-measure, F0-T17) |

**Pattern stabili osservati:**

- **Pipeline composta deterministica.** `audiomentations.Compose([...])` con
  `seed=...` esplicito → output bit-identico per stesso seed
  ([`ENGINEERING_STANDARDS §1`](../../04_INTELLIGENCE/ENGINEERING_STANDARDS.md#determinism)).
- **Ordine di composizione:** *clean signal → mutilation di stem (EQ, comp,
  saturation) → mix bus (limiting, sidechain) → ambience (IR convolution,
  noise injection) → delivery (codec, sample-rate quantize)*. Ordine
  fisico-coerente: codec è l'ultima cosa che subisce un file prima di
  arrivare all'utente.
- **Seed derivato:** stesso pattern di F0-T15-pre — `seed = sha256(master ‖
  source_audio_id ‖ variant_idx)[:8]` (idempotenza per replay).
- **GPU vs CPU:** convoluzioni IR su CPU sono dominanti in costo;
  `audiomentations.ApplyImpulseResponse` usa `scipy.signal.fftconvolve` →
  ~0.5 ×–1 × real-time per IR ≤ 4 s @ 44.1 kHz su single thread → ~150 ms
  per sample di 10 s. **Demucs** invece deve girare su GPU (≥ 8 × più veloce
  che CPU su VM equivalente).

**Decisione tooling:** combinare `audiomentations` (voci §3.3–§3.4 +
backlog) + `pedalboard` (limiting/IR specifici dove `audiomentations` è
più povero) + `demucs` solo per Stem Isolate. Zero nuove dipendenze esotiche;
`pedalboard` GPL-3 è OK perché il pacchetto data-engineering non viene
distribuito col plugin (separazione GPL/EULA garantita dal repo layout).

---

## 3. UX/UI Impact

**Diretto:** nessuno — F0-T15-post è una decisione di pipeline dati
offline; nessuna superficie UI nel plugin v1.0 EA.

**Indiretto — promessa di prodotto.** L'**agnosticità d'ingresso** (§7
backlog) è una promessa che il plugin processi *qualunque* combinazione di
canali in qualunque ordine. Se concessa nel training, **rimuove il bisogno
di una "Channel Mapping UI"** (F4 risparmia una superficie complessa: niente
drag-and-drop di sorgenti, niente "auto-detect kick"). Se non concessa,
l'utente deve mappare a mano N canali sugli 8 slot canonici di
[`F0-T4a §4`](F0-T4a_TCN_TOPOLOGY_SPEC.md#input-agnostic-slots) — friction sull'onboarding (`Laboratory Precision` doctrine
penalizza la friction). **Voce alto valore di prodotto.**

---

## 4. Tech Implementation Matrix

### 4.1 Voci di augmentation — scelte e raccomandazioni

| Asse | Opzione A (DOSSIER §3 letterale) | Opzione B (proposta) | Opzione C (skip) | Raccomandazione |
| :-- | :-- | :-- | :-- | :-- |
| **Codec lossy** | non presente | **MP3 64/128/192 kbps · Opus 32/64/96 kbps · AAC 96 kbps** (uniforme uno qualsiasi), round-trip → decodifica → drop side-information | nessuno | **B** — copertura DCASE-standard; costo ~50 ms/sample |
| **Hum di rete** | non presente | **iniettare 50 Hz + 100/150 Hz** (armoniche 2-3) a SNR `[20, 40] dB`, prob 30 % | non presente | **B** — universale in registrazioni reali |
| **Noise floor stazionario** | "Foley/FSD50K" §3.4 (impulsivo) | aggiungere **hiss broadband bianco** a SNR `[25, 50] dB`, prob 50 % | come §3.4 | **B** — il "Foley" non copre il rumore *stazionario* |
| **Noise gating** | non presente | **gate forward** (threshold `[-40, -55] dB`, attack 1 ms, release 50 ms) post-comp; prob 25 % | nessuno | **B** — Ubiquo nei mix reali |
| **Master limiting / loudness war** | non presente | `pedalboard.Limiter` (threshold `[-3, -8] dB`, release 50 ms) o pyloudnorm a `-7 LUFS` integrated; prob 30 % | nessuno | **B** — produzione moderna ne abusa |
| **Mix-balance randomization** ⚠️ | non presente | **vettore di guadagno per-canale** `[g_0, …, g_7]`, `g_i ~ U(−18, +6) dB`, prob 100 % — **con vincolo §5.3** | nessuno | **B con vincolo** — alto valore, vincolo critico |
| **Click bleed (metronomo)** | non presente | iniettare **click periodico** (banda 2 kHz, pulse 5 ms, ogni quarto a BPM=tempo) a SNR `[20, 30] dB`, prob 15 % | nessuno | **B** — saboteur perfetto, costo zero |
| **Mono collapse** | non presente | mean L+R sul multi-mic prima dell'input-agnostic projection; prob 10 % | nessuno | **B** — caso d'uso reale comune |
| **DC offset** | non presente | aggiungere offset costante `~U(-0.02, +0.02)` al segnale; prob 20 % | nessuno | **B** — costo zero, scenario reale |
| **Delay/echo + gated reverb '80s** | "Acoustic Environment" §3.4 (IR di ambienti reali) | **algoritmico** (`pedalboard.Reverb` ratio 0.4, room_size 0.8, damping 0.5) + slap-back 80–120 ms; prob 15 % | come §3.4 | **B** — letteratura non lo copre ma è realistico |
| **Sidechain pumping** | non presente | LFO sul gain del bus principale ancorato al BPM (1 ciclo per beat); prob 10 % | nessuno | **B** — produzione moderna/EDM |
| **Lo-fi / wow & flutter** | non presente | bitcrush + saturation + roll-off HF (10 kHz LPF) + LFO sul pitch ±0.5 % | non includere | **C — escluso da v1.0** — il wow & flutter sposta il *timing*, conflitto con la doctrine "precision-first" |
| **Cattura amatoriale composita** | non presente | combo: codec + bandlimiting + AGC + IR di stanza piccola | non includere ora | **C — rinviato a v1.x** — combinazione di scenari, troppo distribuita per il primo training |

### 4.2 Pipeline composition — ordine fisico LOCKED

Stadio | Operazione | Library | Note
:--|:--|:--|:--
**1. Stem Isolate** | Demucs AI-Isolation (30 %) | `demucs` (GPU) | F2-T2 GPU
**2. Studio Mutilation (per-stem)** | clipping · saturation · phase flip · EQ HPF/LPF · compressione 4:1–10:1 · pitch ±3 st | `audiomentations` + `pedalboard` | invariato §3.3
**3. Mix balance randomization** | `[g_0..g_7]` ~ U(−18, +6) dB con vincolo §5.3 | custom | **NUOVO** §4.1
**4. Acoustic Environment** | IR convolution (OpenAIR) + algoritmico (Reverb + slap-back '80) | `pedalboard` | esteso §3.4
**5. Master bus** | limiting + sidechain pumping | `pedalboard.Limiter` + LFO | **NUOVO** §4.1
**6. Saboteurs additivi** | percussion sintetiche + voce + foley + **click bleed** | `audiomentations.AddBackgroundNoise` | esteso §3.4
**7. Noise additivo** | hiss + hum 50 Hz | `audiomentations.AddGaussianNoise` + custom hum | **NUOVO** §4.1
**8. Channel collapse** | mono mix con prob 10 % | mean L+R | **NUOVO** §4.1
**9. DC offset** | +U(-0.02, +0.02) | shift costante | **NUOVO** §4.1
**10. Delivery** | codec MP3/Opus/AAC | `audiomentations.Mp3Compression` | **NUOVO** §4.1
**11. Gating** | gate threshold (-40, -55) dB | `pedalboard.NoiseGate` | **NUOVO** §4.1 (FUORI ordine fisico: opera *prima* del codec per simulare il workflow reale del mixer)

> **Nota d'ordine:** il *gating* va in posizione 11 ma intervieneposizionalmente *dopo* §2 (stem comp) e *prima* di §4 (ambience) nei mix reali — `audiomentations.Compose` esegue gli step in ordine lineare. Il vincolo "gating prima di ambience" si modella con un parametro `gate_position_in_chain` ∈ {pre_ambience, post_ambience} con prob 50/50.

### 4.3 Mix-balance randomization — vincolo §5.3 (CRITICO)

Backlog §5 regola 3: **l'attenuazione non può rendere inudibile
un'etichetta**. Due forme:

| Forma | Cosa misura | Costo | Robustezza |
| :-- | :-- | :-- | :-- |
| **Rigorosa (label-aware)** | per ogni onset del bus `b`, picco del transiente nel canale più forte **dopo** il guadagno ≥ SNR `S_min` sopra il noise floor effettivo | per-sample, richiede analisi del target e del rendering | massima — garantisce zero etichette inascoltabili |
| **Proxy (economica)** | limite inferiore fisso al **rapporto tra i guadagni dei canali**: `g_max - g_min ≤ G_spread_max` dB | per-sample, costante | discreta — non garantisce zero etichette inascoltabili al 100 % ma riduce drasticamente il rischio in pratica |

| Asse | Opzione A (rigorosa) | Opzione B (proxy) | Opzione C (skip vincolo) | Raccomandazione |
| :-- | :-- | :-- | :-- | :-- |
| **Forma del vincolo** | per-onset SNR ≥ `S_min` dopo guadagno | `g_spread ≤ G_max` dB | nessun vincolo | **B** — proxy a `G_max = 18 dB` |

**Rationale Opzione B:**

- Per dare un margine di robustezza, la randomizzazione dei guadagni
  resta in `U(-18, +6) dB` — `g_spread_max = 24 dB`. Cap a **18 dB** ribilancia.
- Costo zero: nessuna analisi per-onset, nessun loop di rejection sampling.
- Caso peggiore garantito: il canale più debole resta a `-18 + 6 = -12 dB`
  rispetto al picco di guadagno → ancora sopra la soglia di rilevabilità
  per qualsiasi onset con SNR locale ≥ 30 dB (il caso patologico è quando
  un canale single-mic è il *solo* a contenere un onset *e* viene scelto
  con `g = -18 dB`).
- **Mitigazione del caso patologico:** la mix-balance randomization
  **NON si applica** ai bus single-mic — se la `mic_config` è `mono` o
  `solo_stereo`, il vettore di guadagno è collassato a un singolo guadagno
  globale (no per-canale). Solo `glyn_johns` e `multitrack_full`
  beneficiano della randomizzazione.

Forma rigorosa è disponibile come opzione futura (v1.1 / sweep
iperparametri): post-L4, dopo aver visto il primo modello sull'Holdout
E-GMD, si valuta se la proxy sta lasciando passare scenari problematici.

### 4.4 Agnosticità d'ingresso — permutazione canali + conteggi variabili

Backlog §7 — la cura sul lato training. Sintesi:

| Asse | Opzione A (status quo) | Opzione B (proposto) | Opzione C (aggressivo) | Raccomandazione |
| :-- | :-- | :-- | :-- | :-- |
| **Conteggi attivi in training** | {1, 2, 4, 8} (status DOSSIER §2.1) | **{1, 2, 3, 4, 5, 6, 7, 8}** — sostegno uniforme | sub-set casuale di slot a ogni batch (k variabile per esempio in `U(1, 8)`) | **B** — copre i casi reali (`5` = 2 mic kick + snare + 2 OH, `7` = drum kit senza ride mic) |
| **Permutazione dei canali** | identità (slot fissi) | **shuffle uniforme** di tutti i conteggi {2..8} | shuffle solo dei "non-canonici" {3,5,6,7} | **B** — la k=1 della Input-Agnostic Projection deve diventare ordine-invariante |
| **Drop-out di canali** | non presente | "channel masking": prob 20 % di azzerare 1 canale random a parità di conteggio (simula "uno dei microfoni è morto") | prob 50 % | **B** — il modello deve gestire i mic che si rompono |
| **Probabilità relative di conteggio** | n.a. (solo canonici) | `{1: 10 %, 2: 15 %, 3: 5 %, 4: 20 %, 5: 5 %, 6: 5 %, 7: 5 %, 8: 35 %}` — `8` (multitrack_full) resta dominante perché è il caso "ideale" | uniforme 1/8 | **B** — pesi sbilanciati sul caso più realistico |

**Conseguenza per F0-T4a §4.** Lo schema "slot 0 = kick, slot 1 = snare, ..."
diventa puramente **convenzionale per il preprocessing** ma **non più
appreso dalla rete**: l'amendment a `F0-T4a §4` (a valle del Decision Lock)
sostituisce la riga "Etichetta canonica" con "Porta d'ingresso 0..7
(semantica appresa)".

### 4.5 Regole guardia — invarianti dell'augmentation

Le tre regole §5 del backlog vanno *fissate esplicitamente* nello spec
(non più solo come prosa):

| ID | Regola | Forma operativa |
| :-- | :-- | :-- |
| **R1** | **No time-stretch.** Il time-stretch sposta la ground truth → vietato | `pyrubberband` non in dipendenza; `audiomentations.TimeStretch` non in pipeline |
| **R2** | **Masking-bound (additivo).** Lo "Stealth Mix" non può rendere inudibile una ghost note senza rimuoverne il target | per ogni saboteur additivo, SNR locale del bus mascherato ≥ `M_min = 10 dB` (proxy: ratio di mix ≤ 0.4) |
| **R3** | **Attenuation-bound (sottrattivo).** Mix-balance randomization vincolata a `g_spread ≤ 18 dB`; *zero randomizzazione* su `mic_config` ∈ {mono, solo_stereo} (vedi §4.3) | come §4.3 |

### 4.6 Seed policy + DNA-Trace

Coerente con F0-T15-pre:

- Seed derivato `seed = sha256(master_seed ‖ source_gold_key ‖ aug_variant_idx)[:8]`
- `numpy.random.default_rng(seed)` per ogni voce della pipeline
- **DNA-Trace estesa** — barcode 7→8 segmenti: aggiungere segmento
  `A{aug_variant_idx:02d}` dopo `J{jitter_idx:02d}` (esempio:
  `GMD042-V1T1-J01-A03-DGZ-R2-C1H0-SLK102`); registrare in `dna.json` il
  blocco `augmentation_audio` con il dict dei parametri applicati
  (codec, hum_freq, gate_threshold, mix_balance_vector, ecc.)

### 4.7 Cardinalità della recipe matrix

| Voce | Cardinalità |
| :-- | :-- |
| `M` (kit) | 10 (F0-T1b) |
| MIDI sorgenti (GMD subset) | ~4000 |
| `k_jitter + 1` (F0-T15-pre) | 3 (k=2 + baseline) |
| Engine (Sfizz / DrumGizmo) | 2 |
| **Pre-augmentation cardinality** | ~4000 × 3 × 2 = ~24 000 sample |
| `k_audio_aug` (questa spec) | da scegliere |

| Asse | A (`k = 1`) | B (`k = 3`) | C (`k = 5`) | Raccomandazione |
| :-- | :-- | :-- | :-- | :-- |
| **Varianti audio aug per sample pre-aug** | baseline only | baseline + 2 aug | baseline + 4 aug | **B** — ×3 sample = 72 000 totali; cardinalità training comparabile con SOTA `M=43` × ~1700 = 73 000 |

### 4.8 Costo e timing

| Voce | F2-T1 (render) | F2-T2 (augmentation+demucs) | Note |
| :-- | :-- | :-- | :-- |
| `k_audio_aug = 1` (baseline) | $3.5 | $1.5 (CPU 5 min + GPU Demucs 30 min) | minimum |
| `k_audio_aug = 3` (raccomandato) | $3.5 | $5–$8 (CPU 30 min + GPU Demucs 30 min) | sweet spot |
| `k_audio_aug = 5` | $3.5 | $9–$13 | troppo |

Tutti i costi sono **proiezioni Spot** dell'allocazione §5 — il render F2-T1
non si moltiplica (l'augmentation gira **dopo** il render, sul Gold già su
Blob). Il delta sopra è la voce F2-T2 stimata. **`k = 3`** mantiene
margine del **~$30** dall'allocazione totale.

---

## 5. Executive Briefing — Raccomandazioni numerate

> Le 8 raccomandazioni richiedono un Decision Lock CEO esplicito.
> Numerate per accettazione (✅) / rifiuto (❌) / modifica puntuale.

### B1. Voci nuove di audio augmentation

**Approvare l'aggiunta delle 9 voci di §4.1 nella pipeline (codec, hum,
hiss, gating, master limiting, mix-balance, click bleed, mono collapse,
DC offset).** Includere ordine di composizione §4.2 (11 stadi).
Escludere lo-fi/wow&flutter (priorità v1.x) e cattura amatoriale composita
(priorità v1.x).

### B2. Mix-balance randomization — forma del vincolo

Adottare **Opzione B (proxy)**: `g_spread ≤ 18 dB` + `mic_config ∈
{mono, solo_stereo}` esente. **Niente forma rigorosa label-aware** per
v1.0 (rinviata a v1.1 se i dati post-L4 lo richiedono).

### B3. Agnosticità d'ingresso

Adottare **Opzione B (§4.4)**: conteggi {1..8} con probabilità
sbilanciata su 8, **permutazione canali shuffle uniforme**, **channel
masking 20 %**. Conseguenza: **amendment a F0-T4a §4** — gli slot
diventano "porte d'ingresso", la semantica fissa viene tolta.

### B4. Regole guardia esplicite

Approvare le 3 regole **R1, R2, R3** di §4.5 come invarianti vincolanti
dell'augmentation. Modifica del DOSSIER §3.6 (gap) → §3.7 nuova sezione
"Regole guardia".

### B5. Tooling

`audiomentations` (MIT) + `pedalboard` (GPL-3) + `demucs` (MIT) — tre
dipendenze pinnate in `requirements.txt` (versioni TBD a F0-T16-post).
Niente `pyrubberband`, niente `torch-audiomentations`.

### B6. DNA-Trace estesa 7→8 segmenti

Barcode passa da 7 (post F0-T15-pre) a 8 segmenti — aggiungere `A{idx:02d}`
dopo `J`. Modifica al codec di [`F0-T2a §3.7`](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#dna-trace-format) (`dna_trace.py`) in
F0-T16-post.

### B7. Cardinalità `k_audio_aug`

`k = 3` (baseline + 2 augmented) → **72 000 sample di training**, in
linea col SOTA `M=43`. Sweep di `k=5` rinviato a Tier 2/3 se il saldo
Azure lo consente.

### B8. Storage budget

Per `k = 3` → **dataset finale ~4.5 TB** (1.5 TB Gold raw × 3 varianti
audio). Riallineato all'allocazione §5: storage Cool LRS, ~$60–$90/mese
post-burn. Teardown post-F2 e migrazione asset-core (~30 GB) sull'SSD CEO
come da F3.

---

## 6. Decision Lock & Docs Update (placeholder)

> A valle del Decision Lock CEO:
>
> 1. Aggiornare `status: STRP-001-IN-REVIEW` → `LOCKED`, incrementare
>    `version` a `1.0.0`.
> 2. **DOSSIER §3** → aggiungere §3.6.1 "Voci F0-T15-post" + §3.7 "Regole
>    guardia" (R1/R2/R3); marcare §3.6 (audit backlog) come `SUPERSEDED`.
> 3. **F0-T2a §3.7** → estendere il codec DNA-Trace a 8 segmenti.
> 4. **F0-T4a §4** → amendment "slot → porte d'ingresso (semantica appresa)";
>    bump versione a 1.1.0.
> 5. **AUGMENTATION_AUDIT_BACKLOG.md** → `status: SUPERSEDED` (sia l'asse
>    audio sia l'agnosticità d'ingresso chiusi).
> 6. **MASTER_SCHEDULING §7** → F0-T15-post da `☐` → `☑`; sbloccare
>    F0-T16-post; tracciare costi F2-T2 stimati nella §5.
>
> Il sotto-task implementativo (F0-T16-post) consuma direttamente questo
> documento come spec.

---

*STRP-001 in review — pronto per Executive Briefing al CEO.
Implementazione locale (F0-T16-post) e impatto Azure (F2-T2) gated dal Decision Lock.*
