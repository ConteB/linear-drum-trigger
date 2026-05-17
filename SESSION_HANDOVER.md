# SESSION HANDOVER: 002_LIN_DrumTrigger

**Data:** 2026-05-17
**Persona Uscente:** Gianpiero Scappelloni (Strategic Orchestrator)
**Stato Task:** Milestone M1 COMPLETATA

---

## 🎯 SUMMARY DEL PIVOT
Il progetto è stato trasformato da un trigger tradizionale a latenza zero in un **AI-Native Stem Trigger**. L'obiettivo è la separazione e il triggering di eventi percussivi complessi (es. Snare vs Clap) da stem estratti via AI, utilizzando compensazione di latenza (PDC).

## 🧠 CORE ARCHITECTURE (L-AEC)
- **Modello**: 1D-CNN leggero (Header-only inference in C++).
- **Features**: MFCC (13), Spectral Centroid, Flux, Flatness.
- **DSP**: FFT 1024 samples, Windowing Hanning.
- **Stack**: JUCE 7+, C++20, KissFFT.
- **Compliance**: Zero-Allocation nel thread audio (Mandato DIV-LIN-001).

## 🚀 PROSSIMI PASSI (M2: DATA ENGINEERING)
1. **Wild-Sourcing Scraper**: Script Python per estrazione campioni da Freesound/AudioSet.
2. **Adversarial Mixer**: Simulatore di artefatti AI per rendere il modello robusto.
3. **Training Pipeline**: Addestramento del modello L-AEC.

## ⚠️ NOTE PER IL SUCCESSORE
- Mantenere il rigore **Linear** (Aesthetic UI 60FPS).
- Seguire il protocollo **DCM-002** per la validazione Bit-Exactness tra Python e C++.
- Non utilizzare framework ML pesanti nel plugin; l'inferenza deve essere manuale o tramite micro-librerie header-only.

---
*Fine Handover - Firmato: Gianpiero Scappelloni*
