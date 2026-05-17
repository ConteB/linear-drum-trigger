# SPECIFICA ALGORITMICA: DCM-001 (Linear Drum Trigger)

**Persona Responsabile:** Physics and Mathematics Expert
**Standard di Riferimento:** DCM-002 (Bit-Exactness), DIV-LIN-001 (Zero Allocation)

## 1. OBIETTIVO MATEMATICO
Identificare con precisione di campionamento (sample-accurate) l'inizio di un transiente percussivo. 

**Nota sulla Sincronizzazione (Mandato CEO 2026-05-17):** 
Sebbene la detection sia istantanea, il triggering MIDI deve essere ritardato di un valore fisso pari alla finestra dell'Inference Engine (1024 campioni). Questo ritardo deve essere dichiarato alla DAW tramite PDC. 
Un buffer circolare di 1024 campioni deve mantenere il segnale audio allineato alla finestra di classificazione.

## 2. CATENA DSP (Signal Flow)

### A. Pre-Filtering (Rumble Removal)
- **Tipo**: High-Pass Filter (IIR) - Butterworth 2nd Order.
- **Frequenza di Taglio ($f_c$):** Parametrica (Default 200Hz).
- **Equazione alle differenze**:
  $y[n] = b_0 x[n] + b_1 x[n-1] + b_2 x[n-2] - a_1 y[n-1] - a_2 y[n-2]$
- **Nota**: I coefficienti devono essere pre-calcolati al cambio di sample rate.

### B. Envelope Follower (RMS/Peak Hybrid)
- **Rettificazione**: $x_{rect}[n] = |x[n]|$
- **Smoothing**: Filtro passa-basso a polo singolo per l'inviluppo.
  $E[n] = (1 - \alpha) \cdot |x[n]| + \alpha \cdot E[n-1]$
  dove $\alpha = e^{-1/(f_s \cdot \tau)}$.

### C. Detection Logic (Derivative Analysis)
- **Derivata**: $\Delta E[n] = E[n] - E[n-1]$
- **Soglia Adattiva ($T_{adapt}$)**:
  $T_{adapt}[n] = T_{base} + \sigma \cdot \text{NoiseFloor}[n]$
- **Trigger Condition**:
  `IF (ΔE[n] > T_{adapt}[n]) AND (HoldOff_Counter == 0) -> TRIGGER_ON`

## 3. VINCOLI IMPLEMENTATIVI (LINEAR MANDATES)
- **Memory**: Tutte le variabili di stato ($x[n-1], y[n-1], E[n-1]$) devono essere allocate in una struttura `struct LinearTriggerState` inizializzata all'avvio.
- **Branching**: Ridurre al minimo i salti condizionali nel loop audio per ottimizzare l'esecuzione su architetture moderne.

## 4. VALIDAZIONE DIMENSIONALE
- **Ingresso**: Ampiezza Normalizzata ([-1.0, 1.0]).
- **Uscita**: MIDI Velocity (0-127), derivata dall'ampiezza di picco del transiente nei primi 2ms.
