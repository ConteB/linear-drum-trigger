# 🥁 DRUM-TRIGGER PROJECT INDEX
**Status:** RECOVERY MODE (Stabilized by Gianpiero)
**Owner:** Linear Division / OpenPhase

## 📖 Documentazione Strategica
- [DOSSIER_TECNICO.md](docs/methodology/DOSSIER_TECNICO.md) - Architettura e Sistema a 3 Layer.
- [PROJECT_MASTER_INDEX.md](PROJECT_MASTER_INDEX.md) - Questo file.
- [Linear Mandates](../../OpenPhase_Archive/03_OPERATIONS/Linear_Division/Linear_DSP_Mandates.md) - Vincoli tecnici Linear.

## 🛠️ Moduli Core (src/data_engineering/)
- `batch_generator.py` - Orchestratore Strategie S1, S2, S3.
- `midi_renderer.py` - Sintesi via FluidSynth.
- `augmentation_engine.py` - Layer 3 (Noise & Gain).
- `ugt_generator.py` - Ground Truth Generator.

## 📊 Dataset Status
- `data/raw_dataset/` - E-GMD, ENST, MDB.
- `data/temp/augmentation_comparison/` - Output dell'ultima sessione di validazione.

---
*Ultimo Aggiornamento: 2026-05-17 (Sessione di Recupero)*
