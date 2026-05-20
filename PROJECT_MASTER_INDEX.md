# 🥁 DRUM-TRIGGER PROJECT INDEX (OP-X EDITION)
**Status:** OPERATIONAL - FRESH REPO
**Owner:** Linear Division / OpenPhase
**Harness:** OP-X v2.1

## 🏛️ GOVERNANCE & INTELLIGENCE (Local)
- [Diario di Presidenza](04_INTELLIGENCE/Diario_Presidenza_OpenPhase.md) - Cronologia decisionale.
- [Handover Revision](04_INTELLIGENCE/SESSION_HANDOVER_REVISION.md) - Stato e compiti correnti.
- [Registro Avanzamento](04_INTELLIGENCE/REGISTRO_AVANZAMENTO.md) - Milestone tecniche.
- [Pipeline Status](04_INTELLIGENCE/PIPELINE_STATUS.json) - Monitoraggio risorse.

## 📖 DOCUMENTAZIONE TECNICA
- [DOSSIER_TECNICO.md](docs/methodology/DOSSIER_TECNICO.md) - Architettura 3-Layer.
- [Linear Mandates](../../OpenPhase_Archive/03_OPERATIONS/Linear_Division/Linear_DSP_Mandates.md) - Vincoli tecnici Linear.

## 🛠️ MODULI CORE (src/data_engineering/) — SPECIFICA TARGET
> ⚠️ Pre-produzione: gli script attualmente in `src/` sono prototipi-test usa e getta, da riscrivere. Sotto è la specifica di progetto.
- `batch_generator.py` - Orchestratore Strategie S1, S2, S3.
- `midi_renderer.py` - Rendering audio via **Sfizz (SFZ) + DrumGizmo (CLI multi-mic)**.
- `augmentation_engine.py` - Gold Layer: Bleed, Convolution Reverb, Transient Saboteurs.
- `ugt_generator.py` - Universal Ground Truth Generator (Target MIDI piano-roll).

## 📋 AUDIT
- [Audit Resolution Log](04_INTELLIGENCE/AUDIT_RESOLUTION_LOG.md) - Risoluzione delle incoerenze documentali (2026-05-20).

---
*Ultimo Aggiornamento: 2026-05-20 (Audit di coerenza documentale)*
