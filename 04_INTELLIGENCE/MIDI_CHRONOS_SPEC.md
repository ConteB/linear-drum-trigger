# ⏱️ CHRONOS ENGINE: MIDI TIMING SPECIFICATIONS
**ID:** LIN-DSP-CHRONOS
**Status:** DESIGN LOCKED

## 1. OBIETTIVO
Garantire che ogni messaggio MIDI emesso dal plugin sia allineato al singolo campione (Sample-Accurate) rispetto al segnale audio originale, neutralizzando il jitter introdotto dal processamento neurale e dalla dimensione del buffer DAW.

## 2. ARCHITETTURA (DELAY-LINE)
Il sistema non emette il MIDI istantaneamente dopo l'inferenza. Utilizza una **Midi Delay-Line** interna:
- **Buffer:** Circolare, pre-allocato (`juce::MidiBuffer` o array di struct pre-allocato).
- **Latenza:** Fissa a 100ms (PDC dichiarata alla DAW).
- **Modello temporale (chiarito in audit 2026-05-20):**
    1. Il plugin dichiara alla DAW una latenza fissa di 100ms (`setLatencySamples`). La DAW compensa automaticamente questo ritardo, allineando l'output del plugin alle altre tracce (PDC).
    2. Per analizzare l'istante audio `t`, l'engine neurale necessita della finestra `[t, t+100ms]` (look-ahead non-causale). Quindi, mentre la DAW fornisce l'audio fino al campione `C`, l'AI può finalizzare le decisioni solo per l'audio fino a `C − 100ms`.
    3. Ogni onset rilevato viene inserito nel Chronos Buffer col suo **timestamp audio assoluto reale** `T_onset` (la posizione esatta del transiente nel materiale originale).
    4. Ad ogni `processBlock`, il thread audio estrae dal Chronos Buffer gli eventi il cui `T_onset` cade nell'intervallo di campioni coperto dal blocco corrente e li scrive in `MidiBuffer` con l'offset-campione corretto interno al blocco.
    5. Risultato: l'evento MIDI esce ritardato di 100ms rispetto al tempo reale ma — grazie alla PDC dichiarata al punto 1 — la DAW lo riallinea in **perfetta sincronia sample-accurate** col transiente originale. **Non si applica alcun offset manuale aggiuntivo**: il ritardo della delay-line e la compensazione PDC sono lo *stesso identico meccanismo*, non due correzioni sommate.

## 3. VINCOLI LINEAR (ZERO-ALLOCATION)
- **No dynamic memory:** Il Chronos Buffer è dimensionato per gestire fino a 128 eventi simultanei (follia ritmica) senza mai riallocare.
- **Lock-Free:** L'accesso tra il thread di inferenza (se asincrono) e il thread audio deve avvenire tramite `std::atomic` o `AbstractFifo`.

## 4. UI FEEDBACK (SOLID MARKERS)
L'oscilloscopio visualizzerà linee verticali bianche ("Solid Markers") sovrapposte alla waveform audio ritardata. La posizione del marker deve coincidere graficamente con il picco del transiente audio per confermare il sync visivo all'utente.

---
*Specifiche approvate per l'implementazione C++ v1.0.*
