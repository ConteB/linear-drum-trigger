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
Il dataset di addestramento deve simulare il "Mondo Reale dello Studio":
- **Scenario "Cheap Gear":** Simulazione di preamplificatori economici, rumore elettrico e clipping.
- **Scenario "Bad Engineering":** Bleeding estremo, microfoni fuori fase, posizionamento errato.
- **Scenario "Acoustic Chaos":** Riverberi di stanze piccole e risonanti, saturazione degli overhead.

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
