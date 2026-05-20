# 🗺️ PROJECT ROADMAP: OP-NEUROTRIGGER
**Versione:** 1.0 (OP-X Edition)
**Status:** ACTIVE (LEAN-GUERRILLA MODE)
**Hardware Benchmark:** Mac Air M5 13"

## 🚩 MILESTONE DI BUSINESS & GOVERNANCE
- **M-B1: Lean Market Validation** - Definizione Brand OP-NeuroTrigger e Strategia €500. [COMPLETATO]
- **M-B2: Build-in-Public Launch** - Prima demo pubblica del motore di trascrizione piatti.
- **M-B3: Release V1.0** - Lancio "Davide vs Golia" sul mercato Pro-Audio.
## ⚙️ MILESTONE TECNICHE (SINGLE-DEVELOPER FOCUS)
### FASE 0: INFRASTRUCTURE ZERO (Current)
- **M-T0.1: Azure Cloud Setup** - Configurazione Blob Storage e permessi IAM.
- **M-T0.2: DVC Integration** - Inizializzazione del Data Version Control con puntamento a Azure.

### FASE 1: DATA DOCTRINE & INFRASTRUCTURE
- **M-T1.1: Bronze Layer (Acquisition)** - Download GMD, SM Drums, DrumGizmo e Noise Stems. Inizializzazione DVC su Azure Blob.
- **M-T1.2: Silver Layer (Rendering)** - Implementazione del renderer (**Sfizz + DrumGizmo CLI**) per estrazione Clean Stems e "Studio Mutilations". Setup `ugt_generator.py` per i Target MIDI.
- **M-T1.3: Gold Layer (Augmentation)** - Implementazione `augmentation_engine.py` (Bleed, Reverb, Transient Saboteurs). Esportazione 1.5TB (450 ore) tensori 16-bit.

### FASE 2: NEURAL RESEARCH
- **M-T2.1: Prototype Training (Locale)** - Addestramento mini-batch iterativo su Mac M5 (MPS) per validazione architettura.
- **M-T2.2: Final Brain Training (Cloud)** - "Cottura" del dataset Gold da 1.5TB su GPU Cloud (RunPod A100) per la convergenza definitiva. Budget: **€100 allocati, ~€25-40 spesa attesa** (vedi `STRATEGIC_INFRASTRUCTURE_AUDIT.md` §7).
- **M-T2.3: Benchmarking** - Verifica accuratezza su dataset di test reale (non sintetico).

### FASE 3: PRODUCT ENGINEERING
- **M-T3.1: C++ Core Development** - Porting del modello in RTNeural (Zero Allocation).
- **M-T3.2: UI/UX Framework** - Implementazione Linear Aesthetic 60 FPS.

### FASE 4: VALIDAZIONE & RELEASE
- **M-T4.1: Hard Audit (SOP-004)** - Stress test di stabilità e bit-exactness.
- **M-T4.2: Final Delivery** - Packaging **VST3 + AU** (v1.0; AAX escluso — incompatibile con la filosofia anti-DRM, vedi `DOSSIER_TECNICO.md` §11).

---
*Firmato: Gianpiero Scappelloni*
