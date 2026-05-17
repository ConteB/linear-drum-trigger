# DOSSIER TECNICO: Linear AI Drum Trigger (002_LIN)

## 1. VISIONE DEL PRODOTTO
Un plugin VST3/AU progettato per il trigger intelligente di batterie a partire da stem complessi separati tramite AI. A differenza dei trigger tradizionali, utilizza un motore di classificazione neurale per distinguere eventi percussivi timbricamente simili (es. Snare vs Clap) in contesti rumorosi o ricchi di artefatti.

## 2. REQUISITI TECNICI (Revisione AI-First)
- **Motore di Rilevamento**: Classificatore basato su 1D-CNN operante su feature spettrali (MFCC, Spectral Flux).
- **Precisione**: Sample-accurate triggering con allineamento temporale compensato via PDC.
- **Robustezza**: Addestramento su dataset "Wild" (campioni reali, sporchi, eterogenei) per garantire il funzionamento su qualsiasi sorgente.
- **Memory Management**: Zero Allocation nel thread di processo per l'inferenza ML (Mandato DIV-LIN-001).

## 3. COMPONENTI CHIAVE
- **Pre-Processor**: FFT-based windowing per l'estrazione delle feature.
- **Inference Engine**: Modello CNN ultraleggero integrato in C++.
- **User Interface**: Visualizzatore "Visual DNA" che mappa cromaticamente le classi rilevate sullo spettrogramma.
- **MIDI Engine**: Generazione di eventi MIDI polifonici (multiple note contemporanee da un singolo stem).
