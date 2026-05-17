# REPORT DI INTELLIGENCE: Fonti e Dataset per Automatic Drum Transcription (ADT)

**Progetto:** 002_LIN_DrumTrigger
**Data:** 17 Maggio 2026
**Obiettivo:** Consolidamento della ricerca e mappatura delle fonti dati per l'addestramento del classificatore 1D-CNN (L-AEC).

Questo documento mappa i principali dataset accademici, sintetici e community-driven disponibili per l'addestramento di modelli di Machine Learning in ambito audio.

---

## 1. STRATEGIA V2: PATTERN-AWARE SYNTHESIS (Il Cambio di Paradigma)
In seguito ad analisi architettonica, si è stabilito che **l'addestramento basato su "colpi singoli" (One-Shot) miscelati a rumore casuale è inadeguato**.
La vera musica (doppi pedali, blast beat, ghost notes) è dominata dall'interferenza di fase, dal sustain e da pattern ritmici concatenati.
*   **Azione:** Il dataset verrà processato e "dato in pasto" alla rete sotto forma di **Loop continui di 5-10 secondi**, non più come singoli segmenti isolati. Il rumore verrà mixato sopra l'intero loop, preservando l'ecologia ritmica.

---

## 2. DATASET SELEZIONATI E RUOLO ARCHITETTURALE

### A. Le "Fondamentali Pure" (Ibrido Reale + Sintetico)
L'ossatura del Training Set è un'integrazione di due dataset per massimizzare la precisione fisica (stanza) e la ricchezza di vocabolario (pattern estremi).

| Dataset | Tipologia | Peso / Ore | Contenuto e Ruolo |
| :--- | :--- | :--- | :--- |
| **ENST-Drums** | Acustico Reale | ~4.2 GB (Audio) | 3 kit reali registrati in studio. Fornisce l'acustica imperfetta, le risonanze fisiche (bleed tra i tom) e le dinamiche organiche. |
| **StemGMD** | Sintetico/Procedurale | >1200 ore | Performance MIDI umane convertite con VST HQ. Fornisce un vocabolario illimitato di ghost notes, blast beat e fill complessi senza problemi di isolamento. |

**Strategia di Armonizzazione (DatasetHarmonizer):**
I file di ENST e StemGMD verranno normalizzati a **44.1 kHz, Mono/Stereo, 16 bit** e le etichette convertite in un formato universale CSV (mappato sulle 8 classi target), livellando i volumi (LUFS) per evitare bias della rete.

### B. Il "Caos" (Rumore & Artefatti per Data Augmentation)
| Dataset | Tipologia | Peso / Ore | Contenuto e Ruolo |
| :--- | :--- | :--- | :--- |
| **AudioSet (via yt-dlp)** | Audio "In-The-Wild" | Max 5 GB | Estrazione mirata di stems "spuri" (Bassi sordi, piatti continui, rumore bianco/rosa). Mixati dinamicamente durante il training sui pattern puri per forzare l'AI a isolare i transienti. |

### C. La "Validazione Sacra" (Blind Test)
| Dataset | Tipologia | Peso / Ore | Contenuto e Ruolo |
| :--- | :--- | :--- | :--- |
| **MDB Drums** | Reale (Mix/Stems) | ~3 GB | Subset di MedleyDB (23 canzoni vere). **Non alterato, non mixato.** Usato esclusivamente al termine del training (Gate L3) per verificare la capacità dell'AI di gestire stem veri pre-processati da Spleeter/Demucs. |

---

## 3. RIPARTIZIONE DATASET (SPLIT STRATEGY)
- **Training Set:** 70% StemGMD + 30% ENST-Drums (+ Caos Dinamico).
- **Validation Set (Controllo per Epoca):** 50% StemGMD + 50% ENST-Drums.
- **Blind Test Set:** 100% MDB Drums (Nessun dato di training incluso).
