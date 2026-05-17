# PROTOCOLLO TRAINING WILD: Strategia di Sourcing e Sintesi Dataset

**ID Documento:** PTW-001
**Persona Responsabile:** Physics and Mathematics Expert / Generalist
**Status:** DRAFT (Hardened & Certified)

## 1. OBIETTIVO
Definire il sourcing e la sintesi dei dati per l'addestramento del modello L-AEC, garantendo robustezza su stem "sporchi" e precisione su pattern reali.

## 2. FONTI E ACQUISIZIONE (IL "DOVE" E IL "COME")
- **Fonti**: AudioSet (Google), Freesound.org, IDMT-SMT-Drums.
- **Surgical Streaming**: Estrazione via `yt-dlp | ffmpeg` per salvare solo i segmenti necessari (max 1s). Vietato il salvataggio di file raw lunghi.

## 3. STRATEGIA DI TRAINING A DUE STADI

### Stage 1: Robustezza (Pseudo-Random Stem Synthesis)
- Mixaggio real-time di colpi isolati con jitter temporale e artefatti di fase.
- Scopo: Insegnare all'AI a "vedere" attraverso il rumore e le sovrapposizioni.

### Stage 2: Precisione (Real-World Fine-Tuning)
- Addestramento su stem di batteria reali (MedleyDB/MixingSecrets).
- Scopo: Adattamento ai pattern ritmici complessi e alla dinamica organica delle canzoni.

## 4. VINCOLI DI STORAGE & OTTIMIZZAZIONE (ERM-008)

### A. Hard Limit: 50 GB
Il dataset fisico non deve mai superare la quota di 50 GB. 

### B. Logiche di Virtual Sourcing
1.  **Lazy Augmentation**: Le tecniche di mixing adversarial non generano nuovi file su disco, ma avvengono in RAM tramite il `DataLoader`.
2.  **Binary Container**: Aggregazione dei campioni in un database binario compresso (HDF5/Zarr) per minimizzare l'overhead del file system.

## 5. SEGREGAZIONE DEI DATI (GVM-003)

### A. Training Set (80%)
Dati per l'addestramento dei pesi (Sintetici + Porzione Reale).

### B. Test Set (10%)
Validazione interna e Early Stopping (stesse fonti del Training, campioni unici).

### C. Blind Validation Set (10% - Sacro)
Dati totalmente estranei (canzoni di dataset differenti).
- **Vincolo**: Vietato l'uso per tuning iperparametri.
- **Scopo**: Prova Oculare finale su sorgenti ignote.
