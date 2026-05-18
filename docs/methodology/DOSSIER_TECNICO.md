# DOSSIER TECNICO: DRUM-TRIGGER (END-TO-END TRANSCRIPTION)
**ID:** LIN-DT-DOC-002
**Status:** ACTIVE - STRATEGIC PIVOT
**Division:** Linear / OpenPhase
**Target:** Mixing Engineers, Producers, Studio Post-Production.

## 1. Visione "Studio-First"
Drum-Trigger non è un semplice "gate a soglia", ma un sistema di **Intelligent Drum Transcription**. Il suo obiettivo è convertire riprese audio di batteria (da 1 a 8 canali) in un protocollo di controllo MIDI a 8 canali con precisione chirurgica, gestendo nativamente bleeding, phasing e ambienti acustici complessi.

## 2. Pilastri Architetturali (New Doctrine)

### 2.1 Input Agnostico (Universal Channel Mapping)
Il sistema accetta input variabili da 1 a 8 canali. Un layer di pre-processing mappa la configurazione (es. Solo Stereo, Glyn Johns, Multitraccia completo) in un tensore standardizzato. L'IA è addestrata a estrarre la "verità" (il MIDI) indipendentemente dalla densità informativa dell'input.

### 2.2 End-to-End MIDI Output
L'output non è un timestamp, ma una **Matrice di Trascrizione Differenziabile (Piano Roll)** a 8 canali:
- **Kick, Snare, Hi-Hat (con stati di apertura CC), Tom H/M, Floor Tom, Ride, Crash A, Crash B/Varie.**
- Ogni evento include: Probabilità di Onset, Micro-timing (Sample-Accurate) e Velocity (0-127).

### 2.3 Gestione Integrale dei Piatti (Cymbals Mastery)
A differenza dei trigger tradizionali, Drum-Trigger tratta i piatti come cittadini di serie A. L'architettura utilizza finestre di **Look-ahead (Non-causale)** per separare l'attacco della bacchetta dal "sustain wash" e identificare i colpi di piatto anche in presenza di saturazione spettrale.

### 2.4 Vincoli di Performance & Usabilità
Per garantire l'integrazione con DAW professionali e altri VST pesanti (es. Superior Drummer 3, Acustica Audio Sienna):
- **Buffer Target:** Ottimizzato per 512 / 1024 sample.
- **PDC (Plugin Delay Compensation):** Target ~100ms (Latenza algoritmica necessaria per l'analisi non-causale).
- **Inference Engine:** Processamento a blocchi (Block-processing) con utilizzo di accelerazione hardware (GPU/Metal/DirectML) per minimizzare il carico sulla CPU singola.

## 3. Dottrina di Generazione Dati (Augmentation v2)
Il dataset di addestramento deve simulare l'entropia del segnale reale su tre livelli:

### 3.1 Livello 1: Stem Isolate (Target 99.9%)
- **Baseline:** Segnale pulito, augmentation standard (Pitch/Time).
- **Focus:** Precisione assoluta del transiente.

### 3.2 Livello 2: AI-Isolates & Artifacts (Target 98.0%)
- **AI-Artifact Simulator:** Inserimento di "Spectral Holes" e "Phase Chirping" tipici dei separatori neurali.
- **Focus:** Robustezza agli errori dei tool di pre-processing dell'utente.

### 3.3 Livello 3: Full Mix & Negative Sampling (Target 75-80%)
- **Stealth Mix Mode:** Iniezione di strumenti non percussivi (Chitarre, Bassi, Voci) con Gain-Scaling randomizzato.
- **Focus:** Eliminazione dei falsi positivi (Negative Sampling) e capacità di estrazione in contesti densi.

## 4. Matrice di Output MIDI (Standard OpenPhase)
1.  **CH 1:** Kick
2.  **CH 2:** Snare (Center, Rim, Side-stick)
3.  **CH 3:** Hi-Hat (Continuous Control per apertura)
4.  **CH 4:** Tom High / Mid
5.  **CH 5:** Floor Tom
6.  **CH 6:** Ride (Bell, Bow, Edge)
7.  **CH 7:** Crash A
8.  **CH 8:** Crash B / Cymbals (China, Splash, etc.)

## 5. UI/UX Mandates (The CEO Doctrine)

### 5.1 The "Time-Domain Isolation" Rule
È severamente vietato implementare strumenti di editing temporale grafico (Piano Roll, Timeline, Griglia) all'interno del plugin. Drum-Trigger è un trasduttore, non un sequencer. Qualsiasi correzione temporale di precisione deve avvenire nella DAW dell'utente tramite MIDI Export.

### 5.2 Control Paradigms
- **Frequency Domain (Modern/Graphical):** È permessa l'interazione grafica per parametri legati allo spettro (es. Intelligent Spectral Filters, Attention Masks). L'utente può visualizzare l'energia e "disegnare" filtri per guidare l'attenzione dell'IA.
- **Time Domain (Analog/Parametric):** Tutti i parametri legati al tempo devono essere controllati esclusivamente tramite manopole, switch o slider. Niente interazione diretta sull'asse temporale.

### 5.3 Audio-Inspired Naming (Human Interface)
L'interfaccia deve parlare il linguaggio dell'audio engineer:
- **Sensitivity:** Soglia di probabilità per l'attivazione (AI Threshold).
- **Bleed Rejection:** Filtraggio basato sulla confidenza per eliminare i rientri.
- **Analysis Depth:** Profondità del look-ahead (Complessità dell'inferenza).
- **Dynamic Response:** Mappatura della curva di velocity.
- **Recovery:** Gestione temporale delle collisioni (Double trigger prevention).

## 6. Neural Architectures Candidates

### 6.1 TCN (Temporal Convolutional Networks)
**Status:** HIGH ADHERENCE (Primary Candidate for Prototype)
- **Motivazione:** Architettura "Industrial Grade" ispirata alla stabilità di Neural Amp Modeler (NAM).
- **Variante Multi-Scale:** Per la gestione dei piatti, si implementerà una configurazione a dilatazioni parallele (Multi-Scale). Questo permette alla rete di catturare simultaneamente il transiente d'attacco (alta frequenza) e l'evoluzione timbrica del metallo (media frequenza).
- **Vantaggi:** 
    - **Deterministica:** Garantisce coerenza totale (DCM-001).
    - **C++ Native:** Altissima efficienza in ambiente JUCE tramite RTNeural.
    - **Zero Allocation:** Compatibile con il mandato Linear.

### 6.2 Dual-Path Network (Spectral + Temporal)
**Status:** EVOLUTIONARY TARGET (v2.0)
- **Concept:** Sistema a due vie per la risoluzione definitiva del "Cymbal Wash".
    - **Path A (Time Domain):** TCN per il timing sample-accurate degli onset.
    - **Path B (Frequency Domain):** CNN/U-Net leggera su spettrogrammi per la classificazione timbrica e separazione dei piatti dal bleeding.
- **Fusione:** I due rami convergono in un layer di decisione finale per generare il MIDI target.

## 7. Modular Inference Engine (IDrumBrain)
...

## 8. Guerrilla Rendering Pipeline (Zero-Cost Infrastructure)
Per massimizzare la varietà senza costi di licenza VST, la pipeline di generazione dati utilizza:
- **Engine:** `Sfizz` (headless) per il rendering di formati SFZ ad alta fedeltà.
- **Kits:** SM Drums (Ludwig/Vintage) e DrumGizmo (Multi-mic/Bleeding) per simulare l'acustica di studio reale.
- **Automation:** Scripting Python per il rendering asincrono dei batch, con iniezione di artefatti e strumenti negativi (Slakh2100) in tempo reale.
- **Augmentation:** Pitch-shifting algoritmico e EQ randomizzato applicati post-rendering per espandere il dataset base di un fattore 10x.
