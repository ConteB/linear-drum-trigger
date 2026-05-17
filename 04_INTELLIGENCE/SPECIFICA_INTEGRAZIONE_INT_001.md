# SPECIFICA DI INTEGRAZIONE: INT-001 (Inference Arbiter & Mapping)

**Persona Responsabile:** Senior Software Engineer / Physics Expert
**Status:** DRAFT (Audit-Driven Patch)

## 1. OBIETTIVO
Colmare il vuoto operativo tra il rilevamento del transiente (DCM) e la classificazione neurale (AEC), definendo la logica di decisione e il mapping dei parametri MIDI.

## 2. INFERENCE ARBITER (Sensor Fusion)
La logica di trigger deve operare secondo la seguente gerarchia:

### A. Condizione di Validazione
Un evento è considerato valido solo se:
1.  **DCM Trigger**: Il segnale supera la soglia adattiva $T_{adapt}$.
2.  **AEC Confidence**: La probabilità della classe predetta ($P_{class}$) è superiore alla soglia di confidenza $C_{threshold}$ (Default: 0.65).

### B. Tabella di Verità Operativa
| DCM Trigger | AEC Prob > C | Azione Risultante | Nota |
| :--- | :--- | :--- | :--- |
| SI | SI | **TRIGGER MIDI ON** | Evento confermato. |
| SI | NO | **TRIGGER MIDI ON** | Classe impostata su "UNKNOWN/PERC" (Fallback). |
| NO | SI | **NO ACTION** | Possibile falso positivo o bleed. |
| NO | NO | **NO ACTION** | Silenzio/Rumore di fondo. |

## 3. VELOCITY MAPPING (Matematica del Tocco)
La Velocity MIDI ($V_{midi}$) è calcolata partendo dal picco energetico dell'inviluppo $E[n]$ rilevato dal DCM nella finestra di attacco (primi 5ms).

### Algoritmo di Mapping:
$V_{midi} = \text{clamp}\left( 127 \cdot \left( \frac{E_{peak} - E_{floor}}{E_{ceiling} - E_{floor}} \right)^{\gamma}, 0, 127 \right)$

**Parametri:**
- $E_{peak}$: Valore massimo dell'inviluppo nel transiente.
- $E_{floor}$: Soglia di rumore (User defined).
- $E_{ceiling}$: Livello di saturazione (Default 0dBFS).
- $\gamma$: Curva di risposta dinamica (Default 1.0 - Lineare).

## 4. GESTIONE BUFFER & PDC
- **Buffer di Allineamento**: 1024 campioni.
- **Reporting**: Il plugin deve comunicare `latencySamples = 1024` all'host via API (JUCE `setLatencySamples`).
