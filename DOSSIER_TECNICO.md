# DOSSIER TECNICO: Linear Drum Trigger (002_LIN)

## 1. VISIONE DEL PRODOTTO
Un trigger per batteria ad altissima precisione, ottimizzato per stem di batteria (Kick, Snare, Toms). L'obiettivo è generare trigger MIDI o impulsi audio puliti con latenza zero e rilevamento dei transienti intelligente.

## 2. REQUISITI TECNICI (Mandati Linear)
- **Classe DSP**: Linear / Zero Latency.
- **Memory Management**: Zero Allocation nel thread di processo (Mandato DIV-LIN-001).
- **Algoritmo**: Rilevamento basato su inviluppo (Peak/RMS) con soglia adattiva e filtraggio pre-trigger.
- **Stabilità**: Supporto sampling rate fino a 192kHz.

## 3. ARCHITETTURA PROPOSTA
- **Pre-Processing**: High-pass filter per eliminare rumble.
- **Detection**: Analisi della derivata del segnale per identificare l'attacco esatto.
- **Output**: MIDI Note on con velocity mappata sull'ampiezza del transiente.
