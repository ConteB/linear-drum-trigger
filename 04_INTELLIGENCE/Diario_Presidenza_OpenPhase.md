# DIARIO DI PRESIDENZA - DRUM-TRIGGER
**ID:** LIN-DT-DIARY

## SESSIONE: 2026-05-18 - FRESH START & RECOVERY
**Partecipanti:** CEO, Gianpiero Scappelloni (AI)

### DECISIONI STRATEGICHE
- **WIPE TOTALE:** Decisa la distruzione della cronologia Git corrotta su GitHub a causa di inquinamento da file binari e incoerenze logiche.
- **MIGRAZIONE "CLEAN SLATE":** Creato nuovo repository fresco (`drum-trigger-fresh`) con .gitignore blindato.
- **PATCH LOGICA:** Corretto il `BatchGenerator` con l'implementazione del metodo `run_scenario` mancante.
- **OP-X HARNESS:** Installato sistema di intelligence v2.1 per la governance locale dei log.

### NOTE DEL CEO
- "Voglio la pulizia. Tanto non c'è niente di interessante nel vecchio storico."
- Mandato di operare esclusivamente nel nuovo ambiente Fresh.

---

## SESSIONE: 2026-05-18 - ANALISI DI MERCATO E BUFFER STRATEGY
**Partecipanti:** CEO, Gianpiero Scappelloni (AI)

### DECISIONI TECNICHE & USABILITÀ
- **USABILITÀ DAW:** Fissato target di buffer a 512/1024 sample per garantire stabilità in sessioni di mixing complesse.
- **LATENZA (PDC):** Accettata una PDC di ~100ms per abilitare il look-ahead necessario alla precisione sui piatti.
- **BENCHMARKING:** Il plugin si posiziona nella fascia "High-End" (stile Acustica Audio/iZotope), dove il peso computazionale è giustificato dalla superiorità del risultato (Transcription accuracy).
- **CYMBALS DOCTRINE:** I piatti sono integrati come target primari. Hi-Hat gestito con CC continuo per l'apertura.
- **ECO MODE (Sotto Analisi):** Discussa l'ipotesi di attivazioni parziali della rete o modelli gerarchici per ridurre il carico, ma non ancora inclusa nella documentazione ufficiale.

### STATO DOCUMENTALE
- Aggiornato DOSSIER_TECNICO.md alla versione LIN-DT-DOC-002.

## SESSIONE: 2026-05-18 - ARCHITECTURAL SELECTION & CODING REALITY
**Partecipanti:** CEO, Gianpiero Scappelloni (AI)

### DECISIONI ARCHITETTURALI
- **TCN (Temporal Convolutional Networks):** Identificata come architettura ad alta aderenza. Motivo: stabilità industriale (Standard NAM), efficienza C++/JUCE, comportamento deterministico e gestione ottimale dei 100ms di look-ahead.
- **U-Net:** Mantenuta come opzione per scenari di separazione spettrale estrema (piatti).
- **CODING STRATEGY:** Il plugin seguirà la filosofia di NAM per l'inferenza (Zero dynamic allocation, RTNeural/Eigen integration).
- **PROIBIZIONE:** Escluse architetture puramente Transformer (AST) o State-Space (Mamba) per la versione 1.0 a causa dell'instabilità e del peso dei framework di inferenza in C++.

### STATO TECNICO
- DOSSIER_TECNICO.md aggiornato con la Sezione 6 (Architectural Candidates).

## SESSIONE: 2026-05-18 - MODULAR BRAIN & CYMBAL RESOLUTION
**Partecipanti:** CEO, Gianpiero Scappelloni (AI)

### EVOLUZIONE ARCHITETTURALE
- **MULTI-SCALE TCN:** Eletta ad architettura del prototipo. Le dilatazioni parallele risolveranno il problema dei piatti nel dominio del tempo garantendo stabilità estrema.
- **DUAL-PATH STRATEGY:** Pianificata evoluzione v2.0 con analisi spettrale dedicata per la separazione chirurgica dei piatti.
- **IDrumBrain INTERFACE:** Formalizzata l'astrazione del motore d'inferenza. Il plugin sarà un guscio modulare capace di ospitare diversi "cervelli" neurali senza modifiche al codice core.
- **NAM INHERITANCE:** Confermata la scelta di non usare framework pesanti (ONNX/TF) se non strettamente necessario, preferendo motori C++ snelli (RTNeural/Eigen) per onorare il mandato "Zero Allocation".

### STATO FINALE SESSIONE
- Repository Fresh: Sincronizzato.
- Dossier Tecnico: Versione LIN-DT-DOC-002 (Aggiornato con Modularità e Multi-Scale).
- Prossimo Goal: Generazione Dataset Sintetico Sporco (Augmentation v2).
