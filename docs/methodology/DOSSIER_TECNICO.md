---
id: LIN-DT-DOSSIER-001
title: Dossier Tecnico — Drum-Trigger End-to-End Transcription
type: spec
status: ACTIVE
phase: cross-cutting
domain: Architecture / DSP / Neural
version: 1.0.0
updated: 2026-05-22
tags: [dossier, architecture, dsp, neural, augmentation]
related: [LIN-DT-CHKLST-001, LIN-DT-SPEC-F0T2a, LIN-DT-SPEC-F0T4a, LIN-DT-AUGAUDIT-001]
supersedes: []
---

# DOSSIER TECNICO: DRUM-TRIGGER (END-TO-END TRANSCRIPTION)
**Status:** ACTIVE - STRATEGIC PIVOT
**Division:** Linear / OpenPhase
**Target:** Mixing Engineers, Producers, Studio Post-Production.

## 1. Visione "Studio-First"
Drum-Trigger non è un semplice "gate a soglia", ma un sistema di **Intelligent Drum Transcription**. Il suo obiettivo è convertire riprese audio di batteria (da 1 a 8 canali) in un protocollo di controllo MIDI a 8 canali con precisione chirurgica, gestendo nativamente bleeding, phasing e ambienti acustici complessi.

## 2. Pilastri Architetturali (New Doctrine)

<a id="input-agnostic"></a>
### 2.1 Input Agnostico (Universal Channel Mapping)
Il sistema accetta input variabili da 1 a 8 canali. Un layer di pre-processing mappa la configurazione (es. Solo Stereo, Glyn Johns, Multitraccia completo) in un tensore standardizzato. L'IA è addestrata a estrarre la "verità" (il MIDI) indipendentemente dalla densità informativa dell'input.

> **Amendment MAJOR Decision Lock CEO 2026-05-26 ([F0-T4e §6.1](F0-T4e_INPUT_AGNOSTIC_TRAINING_SPEC.md)).** La dottrina §2.1 passa da
> *aspirazionale* a *provata*. F0-T4e (Input-Agnostic Training) introduce un
> **Channel-Agnostic Frontend permutation-invariant by design** (per-channel
> shared encoder + mean⊕max pool) prima della TCN F0-T4a. La proprietà
> *l'output è invariato per ogni permutazione dei canali di input* è
> matematicamente garantita dall'architettura, non solo imparata
> dall'augmentation. Conseguenze pratiche per il plugin v1.0 EA: nessun
> preset di routing, l'utente assegna 1-8 mic ai suoi slot in qualsiasi
> ordine senza degrado. Vincolo sull'agnosticità rispetto al *conteggio*
> dei canali (zero-fill graceful): preservato dal pool stesso (mean e max
> di un canale zero non perturbano l'aggregato). Implementazione:
> `src/neural/channel_agnostic.py` + `src/data_engineering/audio_augment/channel_agnostic_aug.py`
> + composizione in `src/neural/model.py::ComposedTCN`.

<a id="midi-output"></a>
### 2.2 End-to-End MIDI Output
L'output non è un timestamp, ma una **Matrice di Trascrizione Differenziabile (Piano Roll)** a 8 canali:
- **Kick, Snare, Hi-Hat (con stati di apertura CC), Tom H/M, Floor Tom, Ride, Crash A, Crash B/Varie.**
- Ogni evento include: Probabilità di Onset, Micro-timing (Sample-Accurate) e Velocity (0-127).

Il bus **Hi-Hat** espone, oltre alla matrice di onset, una **testa di regressione continua dedicata** che stima il grado di apertura del piatto frame-by-frame (0.0 = chiuso, 1.0 = aperto). Questo valore continuo è instradato in uscita secondo uno schema **selezionabile dall'utente**: **(a) CC continuo** (default — `CC#4`, Foot Controller; massima espressione, compatibile con Superior Drummer/EZdrummer) oppure **(b) Note discrete** (il valore continuo è quantizzato sulle articolazioni GM closed/pedal/open per la compatibilità universale). Il modello resta invariato in entrambi i casi: il toggle agisce solo sullo stadio MIDI d'uscita. La testa di apertura è addestrata con loss di regressione (L1/MSE), distinta dalla Asymmetric Focal Loss usata per gli onset (§6.2).

<a id="cymbals"></a>
### 2.3 Gestione Integrale dei Piatti (Cymbals Mastery)
A differenza dei trigger tradizionali, Drum-Trigger tratta i piatti come cittadini di serie A. L'architettura utilizza finestre di **Look-ahead (Non-causale)** per separare l'attacco della bacchetta dal "sustain wash" e identificare i colpi di piatto anche in presenza di saturazione spettrale.

### 2.4 Vincoli di Performance & Usabilità
Per garantire l'integrazione con DAW professionali e altri VST pesanti (es. Superior Drummer 3, Acustica Audio Sienna):
- **Buffer Target:** Ottimizzato per 512 / 1024 sample.
- **PDC (Plugin Delay Compensation):** Target ~100ms (Latenza algoritmica necessaria per l'analisi non-causale).
- **Inference Engine (plugin):** Processamento a blocchi (Block-processing) **CPU-only** tramite RTNeural, deterministico e Zero-Allocation. Nessuna dipendenza da GPU/Metal/DirectML a runtime: l'inferenza in tempo reale su acceleratori grafici introdurrebbe jitter e latenza non deterministici, incompatibili col thread audio. L'accelerazione hardware (MPS/CUDA) è impiegata **esclusivamente in fase di training** (§6.2).
- **Presidio di test del core DSP:** i vincoli sopra (Zero-Allocation, determinismo,
  sicurezza numerica, PDC) non sono dichiarativi — sono verificati. Layer statico
  (`audit_dsp_rigor.py`) + test dinamici (override `new`/`malloc` su `processBlock`,
  null-test di determinismo, fuzz NaN/denormali, `pluginval` ≥ 8). Dottrina completa:
  [`TESTING_DOCTRINE.md` §5](../../04_INTELLIGENCE/TESTING_DOCTRINE.md#dsp-tests) (coarse, dettaglio a F4).

<a id="data-doctrine"></a>
## 3. Dottrina di Generazione Dati (Augmentation v2 & Lineage)
Il dataset di addestramento deve simulare l'entropia del segnale reale, tracciando rigorosamente la provenienza di ogni trasformazione. **Il volume target è 1.5 Terabyte (450 ore di audio).**

<a id="aug-prerender"></a>
### 3.1 Augmentation Pre-Rendering (Il "MIDI Jittering Engine")

**Parametri operativi LOCKED** — Decision Lock CEO 2026-05-23, STRP-001 in
[`F0-T15-pre — MIDI Augmentation Spec`](F0-T15-pre_MIDI_AUGMENTATION_SPEC.md).
Prima di sintetizzare l'audio, i MIDI "perfetti" di Ground Truth subiscono una
distorsione *ricalibrata sulla GMD umana* (già imperfetta per costruzione):

| Voce | Parametro |
| :-- | :-- |
| **Time Jittering — onset shift** | gaussiano `σ = 2 ms`, clip `±5 ms` (range ricalibrato — il `±15 ms` originario eccede la tolleranza target ±3 ms di [`§4`](#midi-matrix) e il gaussian smearing di [`F0-T2a §3.3`](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract)) |
| **Flams artificiali** | 5% delle note · distanza inter-flam 15–25 ms uniforme (lookahead PDC ~100 ms ha headroom) |
| **Velocity Jittering — perturbazione** | additivo gaussiano `σ = 8`, clip `[1, 127]` |
| **Velocity Jittering — Ghost Masking** | note con `vel ≤ 40` → moltiplicate per fattore uniforme in `[0.3, 1.0]` |
| **Velocity Jittering — Global Gain Shift** | fattore uniforme in `[0.5, 2.0]` applicato all'intero groove |
| **Component Dropping** | 10% per zona temporale 2 s · **clausola groove-skeleton**: mai droppare kick+snare insieme |
| **k varianti per MIDI sorgente** | **`k = 2` jitter + 1 baseline = ×3 sulla recipe matrix** (scalable down a `k = 1` a CP-1 se il saldo Azure lo richiede) |
| **Seed policy** | `seed = sha256(master_seed ‖ source_midi_id ‖ variant_idx)[:8]` consumato via `numpy.random.default_rng` ([`ENGINEERING_STANDARDS §1 — determinismo`](../../04_INTELLIGENCE/ENGINEERING_STANDARDS.md#determinism)) |
| **Lineage** | DNA-Trace barcode esteso 6→7 segment (segmento `J{idx:02d}` — vedi [`F0-T2a §3.7`](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#dna-trace-format)) |

**Cosa NON si fa:** pitch-shifting (overlap con M-diversity timbrica), time-stretching
(sposta ground truth), pattern dropping groove-distruttivo (kick+snare insieme),
cross-MIDI mixup (riservato all'audio side, [`F0-T15-post`](../../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks)).

**Razionale strategico.** La letteratura ADT moderna (E-GMD M=43, Stein M=512)
costruisce diversità via `M` grande di kit/preset e non fa MIDI jittering. Noi siamo
vincolati a `M = 10` (roster F0-T1b — Self-Evident Commercial License): il MIDI
jittering è il sostituto razionale per iniettare il caos esecutivo che `M` grande
darebbe naturalmente.

<a id="aug-l1"></a>
### 3.2 Livello 1: Stem Isolate & Micro-Bleed (30% Dataset)
- **Baseline:** Segnale generato tramite `Sfizz` (kit SFZ del roster F0-T1b — Salamander, Karoryfer) e `DrumGizmo` via CLI (kit multi-microfono). Motore di rendering ufficiale del progetto (Decision Lock 2026-05-20); FluidSynth/SF2 scartato perché privo di tracce multi-mic.
- **Focus:** Precisione assoluta del transiente d'attacco e apprendimento del rientro microfonico reale.

### 3.3 Livello 2: The Studio Mutilation (40% Dataset)
Per simulare le azioni degli ingegneri del suono, l'audio pulito subisce alterazioni fisiche pesanti prima dell'inserimento in un mix:
- **Clipping / Saturation:** Taglio del transiente d'attacco per forzare l'IA a leggere l'inviluppo.
- **Phase Flip:** Inversione di polarità (essenziale per i microfoni Snare Bottom).
- **Extreme Compression / EQ:** Alterazione dell'attacco/rilascio e filtri HPF/LPF estremi.
- **Pitch Shifting:** Variazioni di accordatura (±3 semitoni).
- **Stealth Mix Mode (Standard):** Iniezione di Basso e Chitarre (Slakh Dataset).

<a id="aug-l3"></a>
### 3.4 Livello 3: Acoustic Environment & Transient Saboteurs (30% Dataset - Il Girone dell'Inferno)
- **Acoustic Environment (Convolution Reverb):** Processamento tramite **Riverbero a Convoluzione** (`pedalboard`) usando Impulse Responses (OpenAIR Library) liberi da copyright.
- **Stealth Mix Mode (The Transient Saboteurs):** L'augmentation usa una "Stealth Matrix Ponderata" per combattere i Falsi Positivi causati da strumenti impulsivi:
    - *Percussioni Accessorie (Generazione Sintetica Sincrona):* Non si usano sample morti. Le percussioni (Congas, Tamburelli, Shaker) vengono **sintetizzate on-the-fly tramite Sfizz** (usando librerie orchestrali CC0 come VSCO-2 CE). Questo permette di allineare i transienti percussivi *esattamente* sui colpi di rullante/cassa (Transient Clashing perfetto) e funge da R&D per future reti dedicate (es. OP-NeuroPercussion).
    - *Acoustic Strumming / Slap:* (Dataset GuitarSet).
    - *Piano Fortissimo (Staccato):* (MAESTRO Dataset).
    - *Foley / Stage Noise:* (FSD50K).
    - *Voce / Parlato (Speech Rejection):* (LibriSpeech). Iniezione di voce parlata per insegnare alla rete a non interpretare consonanti plosive e transienti vocali come colpi di batteria.
- **Focus:** L'Armatura Definitiva. Reiezione categorica dell'energia impulsiva non appartenente al core-set della batteria, risolvendo i casi limite e i mix impossibili.

<a id="dna-trace"></a>
### 3.5 Protocollo "DNA-Trace" (Data Lineage & Hashing)
Ogni tensore Gold finale (in pasto all'IA) possiede una "Carta d'Identità" per debug deterministico:
- **DNA Barcode (Nome File):** Esempio `GMD042-V0T1-DGZ-R2-C1H0-SLK102.npy` traccia: Fonte MIDI (`GMD042`), Alterazione MIDI (`V0T1`), Motore Audio (`DGZ`), Ambiente Acustico/Riverbero (`R2`), Alterazione Audio (`C1H0`) e Disturbatore (`SLK102`).
- **Libretto Sanitario (JSON):** Ogni batch o tensore critico è accompagnato da un file JSON con l'esatto quantitativo di time shift applicato, la percentuale di riverbero Wet/Dry o il ratio di mix, consentendo reverse-engineering totale.

> Lo schema formale dei campi (barcode e JSON) è **bloccato** — vedi [`F0-T2a` §4 — DNA-Trace](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#dna-trace-format) (Decision Lock 2026-05-20); ogni campione WebDataset porta il proprio `{key}.dna.json` (vedi [§9.2](#medallion)).

<a id="aug-gap"></a>
### 3.6 Audit Backlog — gap di augmentation (aperto)
La dottrina §3 modella implicitamente **un solo input**: una batteria tracciata e
mixata in studio professionale. La revisione del 2026-05-22 (osservazione del CEO) ha
isolato assi reali scoperti — artefatti di codec, noise floor / hum, cattura
amatoriale, gating, lo-fi — raccolti in [`AUGMENTATION_AUDIT_BACKLOG.md`](AUGMENTATION_AUDIT_BACKLOG.md).
L'arbitraggio valore/costo e il Decision Lock sono delegati al task
[`F0-T15`](../../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks); questo §3 va aggiornato a
valle di quella chiusura. Non sul percorso critico di F0 (l'augmentation è F2).

<a id="midi-matrix"></a>
## 4. Matrice di Output MIDI (Standard OpenPhase)
1.  **CH 1:** Kick
2.  **CH 2:** Snare (Center, Rim, Side-stick)
3.  **CH 3:** Hi-Hat (Continuous Control per apertura)
4.  **CH 4:** Tom High / Mid
5.  **CH 5:** Floor Tom
6.  **CH 6:** Ride (Bell, Bow, Edge)
7.  **CH 7:** Crash A
8.  **CH 8:** Crash B / Cymbals (China, Splash, etc.)

> **Nota di routing:** "CH 1–8" identifica 8 *bus logici di trascrizione*, non necessariamente 8 canali MIDI fisici. L'output supporta due schemi selezionabili dall'utente: **(a) Note-Mapped** — tutti i target su un singolo canale MIDI con note GM standard (compatibile con Superior Drummer e la maggioranza delle drum-VST); **(b) Multi-Channel** — un canale MIDI per bus, per routing avanzato. Default: Note-Mapped.

## 5. UI/UX Mandates (The CEO Doctrine)

### 5.1 Visual Identity: "The Industrial Rack"
L'estetica deve comunicare "Peso" e "Autorità", posizionando OP-NeuroTrigger come uno strumento hardware di fascia alta (Studio-Grade).
- **Chassis:** Texture procedurale in alluminio anodizzato "Industrial Slate" (Grigio Antracite).
- **Control Paradigms:** Manopole in metallo zigrinato per parametri temporali. Zero interazione grafica sulla timeline (Mandato 5.2).
- **Metering:** Barre a LED verticali (LED Ladders) per monitoraggio livelli e confidenza del trigger.
- **The Digital Post-it (Contextual Help):** Per mitigare la complessità del routing MIDI tra varie DAW senza rompere l'estetica hardware, l'interfaccia include un elemento "Digital Post-it" (graficamente simile a un nastro adesivo di carta opaca). Questo elemento compare obbligatoriamente al **primo avvio assoluto** del plugin, rilevando l'host DAW (es. Logic vs Cubase) e mostrando istruzioni di routing "scritte a penna" (garantendo un onboard immediato dell'utente). Il post-it riporterà un testo esplicito alla fine: *"P.S. Puoi disattivare questo avviso nelle opzioni"*.

### 5.2 The Laboratory Precision Display
Il cuore informativo è un display ad alta risoluzione incassato in vetro fumé:
- **Grafica Vettoriale:** Visualizzazione dei transienti tramite linee sottili e ultra-definite, emulando la precisione di un oscilloscopio da laboratorio (Vector-style).
- **Tipografia Technical-Sans:** Utilizzo di font puliti e senza tempo (Stile DIN/Helvetica) per una leggibilità matematica. Zero decorazioni, zero pixel-art.
- **Cromia:** Bianco Ghiaccio o Verde Fosforo su fondo Nero Assoluto.
- **Focus:** Lo schermo non deve "decorare", ma fornire un readout tecnico di precisione sulla Neural Attention e sul timing dei colpi.

### 5.3 Audio-Inspired Naming (Human Interface)
L'interfaccia deve parlare il linguaggio dell'audio engineer:
- **Sensitivity:** Soglia di probabilità per l'attivazione (AI Threshold).
- **Bleed Rejection:** Filtraggio basato sulla confidenza per eliminare i rientri.
- **Analysis Depth:** Profondità del look-ahead (Complessità dell'inferenza).
- **Dynamic Response:** Mappatura della curva di velocity.
- **Recovery:** Gestione temporale delle collisioni (Double trigger prevention).
- **PDC Indicator (Dynamic Latency):** Il plugin deve visualizzare in modo permanente (come un badge serigrafato hardware) la latenza richiesta dal modello neurale in uso. La dicitura esatta e tassativa è `LOOK-AHEAD: [X]ms (PDC SYNCED)` (dove [X] è un valore dinamico letto dai metadati del modello, es. 100ms per la TCN attuale). È **severamente vietato** l'uso di diciture come "Mixing Mode" o "High Quality", per evitare di suggerire l'esistenza di toggle di qualità abbassabile. Il plugin non ha modalità, ha solo modelli che richiedono finestre di tempo specifiche.

### 5.4 MIDI Routing & Output Workflow
Il plugin risolve il paradosso del routing MIDI offrendo un doppio paradigma di esportazione, per coprire sia il workflow di missaggio in tempo reale sia l'estrazione offline.

**Paradigma Primario: Live Mixing Playback (Direct MIDI Out)**
Essendo il plugin dotato di una latenza compensata (PDC) di 100ms, il suo scopo primario è operare attivamente durante il mix. Quando la DAW è in Play, l'engine C++ (utilizzando `MidiBuffer::addEvent`) inserisce gli eventi calcolati nel thread audio tramite il **Chronos Engine** (delay-line MIDI — specifica canonica in `04_INTELLIGENCE/MIDI_CHRONOS_SPEC.md`). La sincronia sample-accurate è garantita dall'**unico** meccanismo della PDC dichiarata (`setLatencySamples`): la DAW riallinea automaticamente il flusso MIDI alle altre tracce. **Non** si applica alcun offset manuale aggiuntivo ai timestamp — delay-line e compensazione PDC sono lo stesso meccanismo, non due correzioni sommate.

*Gestione Compatibilità OS/DAW (C++ JUCE):*
- **Formato VST3 (Cubase, Ableton, Studio One):** Il plugin è compilato come un classico "Audio FX Insert" che genera MIDI Out nativamente.
- **Formato AUv2 (Logic Pro):** Logic ospita esclusivamente Audio Unit (no VST3) e impone vincoli storici sul routing del MIDI generato da un plug-in di tipo *audio* verso tracce strumentali arbitrarie. Il plugin viene quindi compilato come **AU di tipo `kAudioUnitType_Effect`**, che riceve regolarmente l'audio della batteria sul proprio input. Poiché il routing MIDI *live* verso altre tracce non è garantito in modo nativo e affidabile su tutte le versioni di Logic, su Logic **il workflow primario raccomandato è l'export offline tramite Ghost File System** (drag & drop della clip `.mid` generata — vedi Paradigma Evolutivo). Il "Digital Post-it" rileva Logic come host e mostra esattamente questa procedura.

> ⚠️ **Nota di audit (2026-05-20):** l'ipotesi precedente — compilare come `kAudioUnitType_MIDIProcessor` ("MIDI Effect") e ricevere l'audio via Sidechain — è stata **scartata**: un AU di tipo MIDIProcessor non possiede ingressi audio, quindi il percorso era tecnicamente irrealizzabile. Conseguenza: il sottoinsieme "export sincrono su azione utente" del Ghost File System rientra nello scope **v1.0** per garantire la compatibilità Logic; l'accumulatore asincrono "Neuro-Capture" resta v1.x/v2.0.

**Paradigma Evolutivo (v1.x/v2.0): Neuro-Capture & Ghost File System (Drag & Drop)**
Per arginare le incompatibilità di routing interno di alcune DAW, l'architettura del plugin prevede fin dal Day-One la predisposizione strutturale per un sistema di estrazione asincrona (che verrà implementato in una fase successiva al lancio per snellire lo sviluppo iniziale dell'MVP):
1. **Predisposizione Zero-Allocation:** Lo stream di eventi verrà deviato anche su una coda lock-free (`AbstractFifo`) per permettere al thread grafico di accedervi senza bloccare l'audio.
2. **Ghost File Export (Target Futuro):** L'utente utilizzerà il Drag & Drop dal pannello UI. In quell'istante, nel thread grafico (Message Thread), il plugin creerà fisicamente un file `.mid` reale (Ghost File) in una cartella temporanea dell'OS (`/tmp` o `%TEMP%`).
3. **Drop (Target Futuro):** Il sistema operativo passerà alla DAW l'URI del file temporaneo, permettendo un'importazione nativa garantita al 100%. L'UI esporrà un accumulatore progressivo (`EVENTS CAPTURED: 4096`).

## 6. Neural Architectures Candidates

<a id="tcn"></a>
### 6.1 Strided-Context TCN (The "Comb-Filter" Hack)
**Status:** HIGH ADHERENCE (Primary Architecture)
**Motivazione:** Architettura "Industrial Grade" monolitica che garantisce la precisione della Multi-Risoluzione senza rompere la compatibilità con il framework di inferenza `RTNeural` in C++.

**Topologia & Matematica (Il Trucco Linear):**
> 📐 **Spec implementabile bloccata:** la topologia concreta (numero di layer, kernel,
> dilatazioni, receptive field, teste d'uscita) è definita in
> `docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md` — Decision Lock F0-T4a (STRP-001),
> 2026-05-20. I bullet seguenti ne descrivono il *principio*; per i numeri vale la spec.
- **Single Stream (44.1 kHz):** Nessun resampling reale a runtime, per evitare filtri
  anti-aliasing pesanti. L'audio raw entra a piena risoluzione.
- **Strided Encoder Stem (waveform → frame-grid):** una cascata di convoluzioni *strided*
  porta l'audio da 44.1 kHz alla griglia del target `R_target = 44100/128 ≈ 344.53 Hz`
  (stride totale 128). È qui che vive il principio "Strided-Context": il carico CPU è
  abbattuto subito, prima del trunk.
- **Dilated Causal TCN Trunk (Macro-Context):** un singolo trunk di blocchi residui con
  convoluzioni *dilatate causali* fornisce un receptive field grande (~1.5 s di contesto
  passato) a basso costo. Le dilatazioni — non lo stride + upsampling — danno il contesto:
  un solo grafo, 100% RTNeural-nativo. *(Il blocco "Sentinella/Scalpello" a 2 rate con
  `Nearest-Neighbor Repeat` è stato abbandonato a F0-T4a: introduceva un'operazione di
  upsampling non-nativa RTNeural, contraria allo scopo stesso del Comb-Filter Hack — vedi
  [`F0-T4a` §1](F0-T4a_TCN_TOPOLOGY_SPEC.md#design-lock-fix).)*
- **Latenza / Look-Ahead:** il trunk è causale; il look-ahead non-causale (~100 ms) è
  realizzato come **ritardo d'ingresso pari al PDC** (la rete gira ~100 ms indietro →
  vede il "futuro"). Coincide con la delay-line del Chronos Engine.
- **Risoluzione Dati:** Training in mixed-precision (master FP32 + FP16). I tensori del dataset Gold sono storati in **FP16** per ridurre l'impronta su disco/banda. L'inferenza C++ in RTNeural opera in **`float32`** (RTNeural è template-based su tipo floating-point): nessuna quantizzazione intera (INT8/INT16) è prevista a runtime.
- **Output:** Matrice differenziabile a 8 Canali (Piano Roll).

**Vantaggi per il Prodotto:** 
- **Compatibilità Totale:** RTNeural supporta nativamente le operazioni di `stride`, azzerando la necessità di scrivere codice inferenziale custom complesso in C++. ⚠️ **Asserzione da verificare empiricamente** (Decision Lock STRP-001 D4): l'esportabilità della topologia in RTNeural è certificata dal **Gate L3** (F0-T4b — export JSON + smoke-test C++ + match numerico), *prima* di qualsiasi spesa di compute.
- **Zero Allocation:** Piena aderenza al mandato Linear. L'assenza di resampling garantisce buffer statici in memoria.

<a id="loss"></a>
### 6.2 Neural Training Strategy (Loss & Ground Truth)
Per risolvere il catastrofico sbilanciamento delle classi (99.9% di campioni audio sono silenzi o code, 0.1% sono attacchi di transienti), l'addestramento non utilizzerà metriche standard (es. MSE), ma seguirà questo protocollo:

1. **Gaussian Target Smearing (Ground Truth):** L'engine di generazione dati (`ugt_generator.py`) non produrrà "spilli" digitali (un singolo 1 circondato da 0). Il timestamp dell'onset verrà "sfocato" creando una curva Gaussiana simmetrica di ±3ms. Questo fornisce un gradiente morbido alla rete neurale per correggere il timing durante la discesa dell'errore (backpropagation).
2. **Asymmetric Focal Loss:** Per punire aspramente i "Falsi Positivi" (l'errore più detestato in studio di registrazione), si utilizzerà una Loss asimmetrica custom in PyTorch. Ispirata alla Computer Vision, forzerà la rete a ignorare i transienti "facili" e a concentrare tutto il compute power cognitivo sui transienti mascherati dal bleeding microfonico. Il rapporto FP/FN — originariamente 3× nella dottrina F0-T4a §6 — è stato **superseded a 30×** dalla Loss Competition 2026-05-25 (Decision Lock CEO, kind="afl"). La **F0-T4f Step B** (Decision Lock CEO 2026-05-27) aggiunge un path alternativo `kind="ridnik"` (Ridnik AsymmetricLoss, Alibaba MS-COCO 2020 — γ+ e γ- separati + probability shifting sul ramo negative) per attaccare il fenomeno opposto rivelato dallo Step A calibration sweep: la **under-confidence** sui veri positivi della rete F0-T4e (6/8 bus preferiscono temperature sharpening). Spec dettagliata: [F0-T4f](F0-T4f_STEP_B_LOSS_REDESIGN_SPEC.md), [F0-T4a §6.2](F0-T4a_TCN_TOPOLOGY_SPEC.md#l3-threshold).

<a id="dual-path"></a>
### 6.3 Dual-Path Network (Spectral + Temporal)
**Status:** EVOLUTIONARY TARGET (v2.0)
- **Concept:** Sistema a due vie per la risoluzione definitiva del "Cymbal Wash".
    - **Path A (Time Domain):** TCN per il timing sample-accurate degli onset.
    - **Path B (Frequency Domain):** CNN/U-Net leggera su spettrogrammi per la classificazione timbrica e separazione dei piatti dal bleeding.
- **Fusione:** I due rami convergono in un layer di decisione finale per generare il MIDI target.

## 7. Modular Inference Engine (IDrumBrain)
Il design del plugin adotta un pattern "Strategy". Il core audio e l'UI non sanno quale rete neurale stia girando. Sfruttano un'interfaccia C++ astratta `IDrumBrain` che espone:
- `process(const float* input, int numSamples)`
- `getLatencySamples()`
Questo isola il debito tecnico e permette di aggiornare i modelli o testare nuove architetture (es. Mamba/State-Space in V2) con zero modifiche al codice VST.

## 8. Guerrilla Rendering Pipeline (Zero-Cost Infrastructure)
La pipeline di generazione dati automatizza la trasformazione di MIDI e librerie Open (DrumGizmo, Karoryfer, Salamander) in tracce di addestramento. Si basa sul rendering locale tramite Sfizz (per SFZ) e un orchestration in Python.

## 9. Data Infrastructure & Cloud Governance (Medallion Flow)
Per garantire la scalabilità e la tracciabilità "Industrial Grade", il progetto adotta:

### 9.1 Hybrid Cloud Data Lake
- **Azure Blob Storage (LRS):** Utilizzato come **storage e compute scratch durante il Data Sprint**, coperto dal credito Azure di $200. Azure non è l'archivio permanente: alla fine del credito, i Gold tensor vengono spostati su HDD fisico (2 TB, ~€100–150). Piano di spesa per task: [`STRATEGIC_INFRASTRUCTURE_AUDIT.md` §7.1](../../04_INTELLIGENCE/STRATEGIC_INFRASTRUCTURE_AUDIT.md#azure-spend-plan).
- **HDD Fisico (2 TB):** Archivio permanente post-sprint. Contiene: Gold tensor FP16 (~1.5 TB) + recipes DNA-Trace. Silver e Bronze non vengono archiviati (Silver è rigenerabile; Bronze è re-scaricabile).
- **DVC (Data Version Control):** Gestisce il puntamento ai dati dal repository Git, garantendo che ogni commit del codice sia legato a una specifica versione del dataset.

<a id="medallion"></a>
### 9.2 Medallion Flow (Livelli del Dato)
Il processamento del dato è strutturato a livelli incrementali di qualità gestiti via DVC:
- **BRONZE LAYER (Raw):** Immutabile. Dataset originali (GMD, DrumGizmo, kit SFZ Karoryfer/Salamander, Noise/Stems per Negative Sampling).
- **SILVER LAYER (Clean & Target):** Stem audio prodotti dai render engine
  `src/data_engineering/gold/render.py` (adapter Sfizz / DrumGizmo, F0-T2b/c) e Tensori
  MIDI Target (matrice di trascrizione a 8 bus, layout `flat-25`) prodotti da
  `src/data_engineering/gold/target_builder.py` (F0-T2e). *(I prototipi FluidSynth
  `midi_renderer.py` / `ugt_generator.py` sono stati scartati al Design Lock — vedi F0-T2.)*
- **GOLD LAYER (Augmented Tensors):** La terna `audio.f16` / `target.f16` / `dna.json` è
  scritta da `src/data_engineering/gold/gold_writer.py` + `dna_trace.py` (F0-T2d) e
  l'intera pipeline `recipe → render → Gold` è cucita da
  `src/data_engineering/gold/orchestrate.py` (F0-T2e). L'augmentation (Phase Chirping,
  Bleed sintetico, "Stealth Mix Mode" / Negative Sampling) è lo stadio **F2-T2** —
  `augmentation_engine.py` è ancora un prototipo da riscrivere. Tensori quantizzati a
  16-bit pronti per l'Inference Layer (TCN). **Impacchettamento:** WebDataset in tar-shard
  da ~1 GB (terna per campione), tracciati da DVC come shard — non come micro-file
  (Decision Lock STRP-001 2026-05-20, D1). Layout di byte FP16 di `audio.f16` /
  `target.f16` (`[n_mic,n_sample]` e `[n_frame,25]` flat-25) e schema dello shard:
  [`F0-T2a` §3 — contratto dati](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract).

<a id="validation"></a>
## 10. Validation & Holdout Protocol (The "Iron Gate")
Per scongiurare l'overfitting e garantire la vendibilità Studio-Grade, il dataset e il testing seguono la Dottrina del Triplo Set:

<a id="training-set"></a>
### 10.1 Training Set (80%) & The "Machine-Gun" Module
Usato esclusivamente per aggiornare i pesi della TCN.
- **Anti-Overfitting Ritmico:** Per impedire alla rete di imparare a memoria il "groove" musicale umano, il 5-10% del Training Set è generato stocasticamente. Il modulo **"Machine-Gun / Chaos"** inserisce blast-beat a 300 BPM, sovrapposizioni fisicamente impossibili (8 tamburi colpiti nello stesso frame) e note randomiche fuori griglia. Questo forza la rete a valutare l'evento acustico fisico, non il pattern musicale.

**Implementazione concreta (2026-05-23, sessione mixed-dataset R&D).** Il modulo
Machine-Gun + il counterweight "Rare-Emphasis" sono ora codice in
`src/data_engineering/midi_synth/`:

- **`chaos_generator.py`** — 30 grooves stocastici via processo di Poisson per-bus
  indipendente, `λ ∈ [2, 15] hits/sec`. Inter-arrival time esponenziale ⇒ onset
  *off-grid* per costruzione (rompe lo shortcut "posizione-su-griglia"). Velocity
  uniforme `[40, 120]` (no skew naturale). BPM `[80, 200]`, durata `[2, 6] s`. Nota GM
  scelta uniformemente dalle articolazioni del DRSKit voiced sul bus. Determinismo
  byte-deterministico per `(master_seed, index)` via `random.Random` (no NumPy dep).
- **`rare_emphasis.py`** — 30 grooves dove crash/china/ride/tom/splash sono
  sovra-rappresentati 3-5× la frequenza naturale GMD. Cinque famiglie × 6 sub-grooves
  (3 BPM × 2 bar): `crash_led`, `china_led`, `ride_led`, `tom_fill_heavy`,
  `splash_bell`. Counter-pesa lo skew della distribuzione GMD reale.
- **`mix_dataset.py`** — orchestratore 70/15/15: 140 GMD reali (sample
  deterministico da `info.csv`, filtrato a `time_signature=4-4 ∧ split=train`) +
  30 rare + 30 chaos = 200 grooves. Shuffle deterministico `master_seed=20260524`.
  Output: `bronze/gmd/mix_2026-05-24/` (gmd/, rare/, chaos/) + `manifest.json`.

Il mix viene consumato da `tools/generate_local_rnd_dataset.py --source-mix <dir>`
che riusa la pipeline jitter (F0-T15-pre/T16-pre LOCKED) e DrumGizmo+DRSKit per il
render Gold (`audio/target/dna` triple). Costo Azure: **$0** (gira su Mac M5 +
OrbStack DrumGizmo). Doctrine: anti-shortcut learning + coverage delle code rare
della distribuzione GMD.

<a id="validation-set"></a>
### 10.2 Validation Set (10%)
Usato per il monitoraggio "Early Stopping" durante il training su Azure.

**Policy di partizione kit-wise — Decision Lock CEO 2026-05-23 (Opzione B).** Il Val Gold
deve misurare la **generalizzazione cross-kit**, non solo cross-session. Il prodotto
finale vivrà sui kit del cliente, mai visti al training: il Val deve simulare lo stesso
scenario. Due kit del roster F0-T1b sono quindi tenuti **interamente fuori dal Training
Set** e formano il Val Gold; gli altri 8 vanno in training (con uno split session-wise
GMD all'interno del Train per la varietà ritmica). Insieme al **pairing forzato
MIDI×Engine** (`F0-T2a` §[3.8](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#tail-standardization))
e alla **tail standardization** (stessa sezione), la partizione kit-wise chiude il
canale di shortcut timbrico.

| Set | Kit DrumGizmo | Kit SFZ |
| :-- | :-- | :-- |
| **Train** (8 kit) | DRSKit · CrocellKit · MuldjordKit · Aasimonster | Frankensnare · Unruly Drums · Big Rusty Drums · VSCO-2 CE (accessorie) |
| **Val** (2 kit "vergini") | **ShittyKit** | **Swirly Drums** |

Razionale della scelta: ShittyKit e Swirly Drums sono timbri "fuori standard" rispetto
agli altri 8 — kit lo-fi/vintage (ShittyKit) e atmospheric/effettato (Swirly). Testano
se la rete riconosce un onset anche su un kit che non assomiglia a quelli di training.
La barra finale resta comunque l'**Holdout reale E-GMD** (§10.3) — il Val Gold è il
sensore di processo durante il training, non l'arbitro del Gate L4.

> **Statistical gate pre-F2-T3.** La consistenza distribuzionale train↔val viene
> verificata numericamente prima del training (KS test su feature continue, χ² sui
> categoriali, MIDI-leakage check). Spec dettagliata in
> [`F0-T17 — Statistical Test Plan` §3.2](F0-T17_STATISTICAL_TEST_PLAN.md#modules);
> il gate è bloccante per il lancio del training A100.

<a id="holdout"></a>
### 10.3 The Holdout Test Set (10% - La Prova del Mondo Reale)
Questo set non viene mai processato in fase di training. È l'arbitro finale della qualità del prodotto:
- **Holdout reale (E-GMD):** *(ridisegnato 2026-05-20, F0-T1c)* — E-GMD, Expanded Groove MIDI Dataset (CC-BY 4.0): 444 h di performance di batteria **umane reali**, 43 kit, con ground-truth MIDI di timing e velocity allineato ±2 ms. Sostituisce ENST-Drums (escluso — dottrina compliance §1.1 di `DATA_PROVENANCE_LOG.md`). ⚠️ Limite noto: E-GMD è registrato su modulo Roland TD-17 — performance umana vera, ma l'audio non cattura microfoni acustici in stanza né il bleed reale: i claim numerici a L4 vanno formulati di conseguenza.
- **Test Stealth-Mix (Slakh-Mix via Slakh2100):** *(ridisegnato 2026-05-20, F0-T1c)* — su Slakh2100 (CC-BY 4.0) l'IA genera un MIDI dal full-mix che deve coincidere col MIDI ottenuto (thresholding standard) dallo stem batteria isolato dello stesso brano. Sostituisce il Franken-Mix/MedleyDB (escluso — clausola NonCommercial).
- **L'Ultimo Miglio (Ocular Proof):** Il plugin pilota un suono percussivo estraneo (es. Woodblock) riprodotto in controfase sulla registrazione originale. Il test è superato solo se l'orecchio umano non percepisce "flam" (sdoppiamento temporale) sull'attacco dei transienti.

> **Evaluation Suite L4.** Le metriche numeriche del Gate L4 (per-bus F-score con
> tolerance ±25 ms, bootstrap CI 95 %, confusion matrix inter-bus, calibration curve,
> sliced metrics per velocity / tempo / kit-OOD) sono definite in
> [`F0-T17 — Statistical Test Plan` §3.4](F0-T17_STATISTICAL_TEST_PLAN.md#modules)
> con soglie pre-dichiarate (`per_bus_f_min = 0.80`, `f_macro_min = 0.85`).

<a id="licensing"></a>
## 11. Security & Licensing Architecture (Soft-DRM)
In aderenza alla filosofia OpenPhase, il plugin ripudia l'uso di DRM invasivi (iLok, Hub Apps) che degradano l'esperienza dell'utente pagante. Adotta invece un approccio **Offline Asimmetrico (Modello Valhalla DSP)**.

> **Formati & coerenza anti-DRM (Decision Lock 2026-05-20):** la v1.0 è distribuita **solo come VST3 e AU**. Il formato **AAX (Pro Tools) è escluso**: richiede la firma PACE, una forma di DRM in contrasto diretto con questa dottrina. Un eventuale supporto AAX post-v1.0 sarà trattato come eccezione esplicita e documentata.

### 11.1 Il Paradigma RSA (Ingegneria C++)
La validazione avviene in locale, al 100% offline, tramite la classe `juce::RSAKey`.
- **Server-Side (Generazione):** La piattaforma e-commerce possiede una Private Key a 2048-bit. Firma un payload contenente email e nome utente, generando un file `.license`.
- **Plugin-Side (Validazione):** Il binario C++ contiene esclusivamente la Public Key hardcodata. Decodifica la firma del file `.license` per garantirne l'autenticità. È matematicamente impossibile scrivere un "KeyGen" senza trafugare la Private Key dai server OpenPhase.

### 11.2 The "Drag & Drop" Authorization (UX)
1.  **Stato Demo:** Il plugin si avvia con le funzioni di processamento alterate. L'interfaccia "Laboratory Precision" sovrappone un pannello opaco con l'istruzione vettoriale: `[ UNREGISTERED COPY - DRAG .LICENSE FILE TO AUTHORIZE ]`.
2.  **Handshake:** L'utente trascina il file nella GUI. Il framework JUCE valida la firma e salva il file (o il suo hash) nelle cartelle utente sicure di sistema (`~/.config/OpenPhase/DrumTrigger/` su Mac o `%APPDATA%` su Win).
3.  **Deterrente Psicologico:** A validazione avvenuta, il pannello sparisce e l'interfaccia incide in modo permanente nel design (in basso a destra) la dicitura `REGISTERED TO: [NOME UTENTE]`.

### 11.3 Anti-Patching Doctrine (Distributed Logic)
I gruppi di reverse engineering non attaccheranno la crittografia RSA, ma proveranno a patchare il binario in Assembly bypassando il controllo condizionale. Per mitigare l'attacco senza implementare offuscamenti pesanti:
- **Il Divieto del Boolean Singolo:** È categoricamente vietato riassumere lo stato della licenza in un blocco del tipo `if (!isLicensed) return silence;`. Questo richiederebbe a un cracker la modifica di un singolo byte (`JMP` vs `JE`).
- **The Poisoned DSP:** Lo stato dell'autorizzazione deve restituire variabili continue intrecciate con la logica neurale. Se l'autenticazione fallisce:
    1.  L'offset del **PDC** viene sfalsato stocasticamente di ±15ms ogni *n* secondi.
    2.  La **Sensitivity Threshold** della TCN viene moltiplicata per un fattore oscillante (simulando un comportamento fallato dell'AI).
Questo approccio costringe il cracker a dover disassemblare e disinnescare molteplici layer di matematica DSP FP16, dilatando enormemente il tempo necessario al cracking senza gravare sulla CPU dell'utente onesto.

### 11.4 Customer Care & License Recovery Policy ("Email-as-Identity")
La gestione post-vendita (smarrimento del file di licenza da parte dell'utente) deve avvenire a "Frizione Zero" ed essere completamente automatizzata, senza richiedere interventi manuali o apertura di ticket.
- **Divieto di Aree Personali Custom:** Si ripudia lo sviluppo di portali utenti con login e password (bloatware web, rischi GDPR). L'indirizzo email di acquisto è l'unico identificatore valido.
- **Integrazione UI:** Sulla schermata "Laboratory Precision" bloccata, al di sotto dell'istruzione di Drag & Drop, sarà presente un hyperlink minimale (es. `Lost your Keyfile?`).
- **L'Ecosistema E-commerce:** Il click reindirizzerà a un portale gestito dal provider di pagamento (es. LemonSqueezy / Stripe Customer Portal), dove l'inserimento dell'email innesca un webhook API che forgia e invia immediatamente una nuova copia del file `.license` all'utente, H24/7.
