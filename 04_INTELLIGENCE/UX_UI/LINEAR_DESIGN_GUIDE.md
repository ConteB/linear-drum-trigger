# LINEAR DESIGN GUIDE: OP-NEUROTRIGGER
**Project:** Drum-Trigger (Fresh)
**Aesthetic:** "Hybrid Studio-Bench" (Lab Precision meets 70s Studio Luxury)
**Status:** LOCKED - MANDATORY COMPLIANCE

## 1. Architettura Industriale (Form Factor)
- **Ratio:** 4:3 / Squarish (Target: 950x650px).
- **Chassis:** Metallo spazzolato antracite (Brushed Metal) con fianchetti laterali in **Noce (Walnut)** da 25px.
- **Filosofia:** Lo strumento deve apparire come un apparecchio da banco di precisione "customizzato" per uno studio di registrazione d'élite.

## 2. Componenti Visivi & Specifiche UX

### A. CRT Oscilloscope (The Vision Core)
- **Display:** Simulazione tubo catodico (CRT) a fosfori verdi (`#33ff33`).
- **Rendering:** Vettoriale puro con bagliore (glow) stocastico proporzionale all'intensità del segnale.
- **Griglia:** Overlay a 30px con linee a bassa opacità (5%).
- **Ghost Markers:** Rappresentazione dell'incertezza AI tramite linee tratteggiate a intensità variabile (Alpha 0.1 - 0.5) che si solidificano al superamento della soglia.

### B. Global Matrix (The Inline Bus)
- **Layout:** 8 canali disposti in linea orizzontale.
- **Bus Strip:** Ogni canale include:
    - **Label:** Font Monospazio (Helvetica/Swiss style), bold, tracking 1.5px.
    - **Confidence Meter:** LED Ladder verticale (14px width). Feeling balistico anni '70.
    - **Threshold Line:** Riga bianca inline sovrapposta al meter (Pattern V2.2).
    - **Trigger LED:** Piccolo indicatore circolare alla base (flash bianco puro).
- **Interaction:** Selezione tramite click sullo strip. Il canale attivo viene evidenziato tramite **Active State Focus** (Pattern V2.3 - Incasso e illuminazione).

### C. Maintenance Panel (The Expert's Drawer)
- **Concept:** Barriera psicologica all'accesso dei parametri interni.
- **Esterno (Cover):** Placca in metallo fissata con 4 viti a taglio (Flat-head screws).
    - **Ownership Plate:** Serigrafia indelebile con Nome Proprietario e Watermark Licenza.
    - **Model Selector:** Area tecnica di selezione del modello neurale (SELECT: [ID]).
- **Interno (PCB Reveal):** Scheda elettronica verde scuro (`#0d120d`).
    - **Trimmers:** Viti di regolazione (Bias, Decay, Gain) per parametri avanzati.
    - **Internal Serigraphy:** Replica dei dati proprietari, versione app e build ID serigrafati direttamente sul rame della PCB.

## 3. Guida ai Materiali & Colori (Spec. Tecniche)
- **Legno:** Noce (Walnut) - Gradiente `#4d2d18` -> `#5d3d28`.
- **Metallo:** Brushed Antracite - `#242422`.
- **Fosforo:** Green CRT - `#33ff33` (Shadow glow: 8px).
- **Tipografia:** SF Mono / Helvetica Neue (Technical cuts).

## 4. Interaction Patterns
- **Threshold Drag:** La soglia si regola trascinando la linea direttamente nell'oscilloscopio o tramite il meter in basso.
- **Selection:** Un solo canale alla volta è attivo per l'analisi nel microscopio.
- **Maintenance:** Accesso tramite click sulle viti (simulazione svitamento). Non incentivare l'apertura: l'ambiente interno deve apparire tecnico e potenzialmente "pericoloso" per la taratura di fabbrica.

---
*Questa guida è la Verità di Progetto. Ogni deviazione è considerata un errore di integrità.*