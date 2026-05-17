# SCHEDULING OPERATIVO: 002_LIN_SPRINT_01 (HARDENED)
**ID Sprint:** SPRINT-2026-05-A
**Status:** 🟢 OPEN (Audit Patched)
**Obiettivo:** Data Engineering & Modello L-AEC (M2)
**Riferimenti:** SOP-014, DCM-002, AUDIT-SCHEDULING-M2 (RESOLVED)

## 1. STRUTTURA SPRINT (WBS HARDENED)

| ID Task | Categoria | Descrizione Dettagliata | Gate SOP-014 | Persona | Agente AI |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TSK-M2-00** | OPS | **Env Freeze & Setup**: Creazione container Docker/Conda con versioni fisse (PyTorch 2.x, CUDA 12.x). | L1 | Engineer | **Pro** (Setup ambiente complesso) |
| **TSK-M2-01.1** | OPS/SCIENCE | **Multi-Source Scraper**: Implementazione `yt-dlp` per AudioSet e Freesound API con gestione TB storage. | L1, L2 | Generalist | **Pro** (Ingegnerizzazione dati) |
| **TSK-M2-01.2** | OPS | **Emergency Fallback Dataset**: Preparazione e pulizia dataset offline (es. IDMT-SMT) come backup immediato. | L1 | Generalist | **Base** (Data cleaning) |
| **TSK-M2-01.3** | SCIENCE | **Wild-Selection Logic**: Filtraggio campioni e auto-labeling via feature extraction. | L3 | Physics Expert | **Pro** (Logica ML/Signal Proc.) |
| **TSK-M2-02.1** | SCIENCE | **DSP Artifact Engine**: Sviluppo algoritmi di degrado (Aliasing, Phase-jitter, AI-artifacts). | L3 | Physics Expert | **Pro** (Algoritmi DSP) |
| **TSK-M2-02.2** | SCIENCE | **Batch Augmenter**: Generazione massiva dataset (100k+ varianti). | L2 | Generalist | **Base** (Automazione batch) |
| **TSK-M2-03.1** | CODING | **Model Skeleton**: Architettura 1D-CNN (Conv1D, BatchNorm, ReLU). | L1 | Engineer | **Pro** (Design Rete Neurale) |
| **TSK-M2-03.2** | SCIENCE | **Loss Function Tuning**: Cross-Entropy pesata per gestione classi rare. | L3 | Physics Expert | **Pro** (Matematica/Ottimizzazione) |
| **TSK-M2-03.3** | SCIENCE/CODE| **Stage 1 Training**: Addestramento su Pseudo-Random Stem Synthesis con Gate L3. | L2, L3 | Generalist | **Base** (Run & Monitor training) |
| **TSK-M2-03.4** | SCIENCE | **Real-World Fine-Tuning**: Adattamento su stem organici (MedleyDB) e pattern complessi. | L2, L3 | Generalist | **Pro** (Fine-tuning critico) |
| **TSK-M2-04.1** | GOVERNANCE | **Confusion Matrix & Edge-Case Audit**: Analisi formale falsi positivi (SOP-004). | SOP-004 | Gianpiero | **Base** (Analisi e Reportistica) |
| **TSK-M2-04.2** | SCIENCE | **Bit-Exactness Validation**: Verifica equivalenza Python vs C++ (DCM-002). | DCM-002 | Physics Expert | **Pro** (Cross-language debugging) |
| **TSK-M2-05.1** | CODING | **Static Weight Quantization**: Ottimizzazione cache L1/L2 (float16). | L1 | Engineer | **Pro** (Low-level optimization) |
| **TSK-M2-05.2** | CODING | **C++ Header Generator**: Export Zero-Allocation (DIV-LIN-001). | L4 | Engineer | **Pro** (Astrazioni C++ critiche) |

## 2. PUNTI DI CONTROLLO CRITICI (CEO GATES)
1. **Gate Infrastructure (Dopo 00):** Verifica che l'ambiente sia riproducibile al 100%.
2. **Gate Sourcing (Dopo 01.2):** Conferma disponibilità dataset (Online o Fallback).
3. **Gate Physics (Dopo 03.3):** Verifica che il modello non "allucini" transienti inesistenti.

## 3. TASK LOCK & AUTORIZZAZIONE
- [x] Vulnerabilità AUDIT-SCHEDULING-M2 patchate.
- [x] **Autorizzazione CEO per Avvio SPRINT-2026-05-A (HARDENED).** (Autorizzato via prompt 2026-05-17)
