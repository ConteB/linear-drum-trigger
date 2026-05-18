# DOSSIER TECNICO: DRUM-TRIGGER DATA PIPELINE
**ID:** LIN-DT-DOC-001
**Status:** DRAFT (Restored)
**Division:** Linear

## 1. Visione del Sistema
Il progetto Drum-Trigger mira a creare un sistema di rilevamento onset per batteria ad altissima precisione (60 FPS / < 1ms latency) utilizzando un dataset generato sinteticamente ma indistinguibile dalla realtà.

## 2. Architettura Augmenting a 3 Layer (CEO Mandate)
Per garantire la massima robustezza del modello, la pipeline di generazione dati segue un approccio di varianza progressiva:

### Layer 1: MIDI Humanizing
- **Obiettivo:** Simulare la variabilità di un'esecuzione umana partendo da pattern quantizzati o reali.
- **Tecnica:** 
    - **Delta Posizione:** Micro-spostamenti temporali casuali dei messaggi Note_On.
    - **Delta Velocity:** Variazioni randomiche dell'intensità del colpo per evitare la staticità timbrica.

### Layer 2: Multi-Kit Exhaustive Coverage
- **Obiettivo:** Coprire l'intero spettro timbrico disponibile nelle librerie.
- **Tecnica:** Rendering sistematico utilizzando tutti i pezzi disponibili in ogni SoundFont. Se un kit offre 3 Kick e 2 Snare, la pipeline deve generare varianti che esplorino tutte le combinazioni o selezioni sistematicamente ogni pezzo per massimizzare la diversità dei campioni di training.

### Layer 3: Stochastic Noise Injection
- **Obiettivo:** Addestrare il modello a operare in ambienti rumorosi e variabili.
- **Tecnica:** Applicazione di rumore bianco o rosa con ampiezza (RMS) scelta casualmente entro un range definito. Questo aumenta drasticamente la varianza del segnale audio finale senza alterare la Ground Truth.

## 3. Vincoli Linear (Hard Constraints)
- **Frequenza di Campionamento:** 44100 Hz (fissa).
- **Bit Depth:** 24-bit (internal) / 32-bit float (numpy).
- **No Dynamic Allocation:** Obbligatorio per i thread audio (Mandato DIV-LIN-001).

## 4. Pipeline Operativa
1. **MIDI Ingest:** Caricamento pattern da `data/raw_dataset/egmd/`.
2. **Synthesis Orchestration:** `BatchGenerator` applica i Layer 1 e 2.
3. **Audio Processing:** `AugmentationEngine` applica il Layer 3.
4. **GT Extraction:** `UGTGenerator` estrae gli onset temporali precisi per il training.
