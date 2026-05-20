# TASK BLUEPRINT: STRP-001 (UX Incertezza AI & UI Layout)
**Score ERM-005:** BASSO RISCHIO (Nessuna dipendenza esterna, implementazione puramente grafica in JUCE/C++).
**Checklist TOP-002:** Approvazione architettura visiva (Split-Focus).

## 1. Analisi Competitor & Pattern (Fase 1-2)
- **Standard Industry:** Strumenti complessi (FabFilter Pro-MB, iZotope) usano pattern "Master-Detail" (o Split-Focus). Una vista globale per il routing/status e una vista dettagliata (Microscopio) per l'editing del singolo nodo.
- **Gestione Incertezza AI:** I dati probabilistici (0.0 - 1.0) nei tool audio non vengono quasi mai mostrati crudi (es. testualmente "55%"). Vengono mappati su opacità (Alpha) o altezza vettoriale rispetto a una soglia.

## 2. Architettura UX "Split-Focus" (Fase 3-4)

L'interfaccia (Main Component) di OP-NeuroTrigger è divisa in due macro-Aree.

### A. THE GLOBAL MATRIX (Area Master / Routing / Status)
*Posizione:* Barra laterale sinistra (occupa ~30% della larghezza) o Rack Inferiore.
*Funzione:* Monitoraggio continuo degli 8 canali in output dal motore PyTorch (RTNeural).
*Componenti UI Standard (JUCE):*
1. **Channel Strips (x8):** Otto moduli identici, uno per target (KICK, SNR, T1, T2, HH, RD, CR, SP).
2. **Neural Confidence Meter (Il "Vu-Meter" dell'AI):** 
   - Non è un meter audio. Mostra l'output raw (0.0 - 1.0) della rete neurale per quel canale (quanto la rete "crede" ci sia un colpo in questo istante).
   - *Comportamento visivo:* Balistico, reattivo, a LED (Vertical Ladder).
3. **Threshold Slider (Il "Tagliola"):** 
   - Un cursore orizzontale o fader sottile affiancato al meter. 
   - Se l'output neurale (il LED) supera la linea del cursore, il colpo è validato.
4. **Trigger Fired Indicator:** Un LED circolare in basso che fa un "flash" bianco puro (con decadimento rapido) solo se il colpo viene validato e il MIDI viene generato (o il suono triggerato).
5. **Selection Radio Button:** Un selettore invisibile (l'intero modulo è cliccabile) che imposta il canale attivo per l'area "Microscopio". Solo un canale alla volta è selezionato.

*UX dell'Incertezza (Livello Macro):* L'utente vede "l'indecisione" della rete guardando il Meter pulsare sotto la linea di Threshold.

### B. THE PRECISION OSCILLOSCOPE (Area Detail / Microscopio)
*Posizione:* Area Centrale/Destra (occupa ~70% della larghezza).
*Funzione:* Analisi chirurgica nel dominio del tempo del canale selezionato nella Global Matrix.
*Componenti UI Standard (JUCE):*
1. **Waveform Background:** Disegno (Path) riempito (Fill) del segnale audio originale in ingresso (Grigio scuro). Serve come riferimento temporale.
2. **Threshold Line (Overlay):** Una linea orizzontale che riflette il valore della Threshold del canale selezionato.
3. **Ghost Markers & Solid Hits (Rappresentazione Vettoriale dell'Incertezza):**
   - Invece di disegnare la curva probabilistica continua (che confonderebbe la vista dell'audio), l'algoritmo UI cerca i *picchi locali* (local maxima) nell'output neurale, anche quelli sotto la Threshold.
   - Per ogni picco trovato:
     - Se **Valore > Threshold:** Disegna una linea verticale intera (Bianco ottico) = **Colpo Validato**.
     - Se **Valore < Threshold (ma vicino):** Disegna una linea tratteggiata o sfumata (Alpha proporzionale al valore) = **Ghost Marker (Incertezza)**.
4. **Scrolling Playhead:** Linea verticale che indica l'istante attuale ("Ora") rispetto al buffer visivo.

*UX dell'Incertezza (Livello Micro):* L'utente vede i Ghost Markers sui colpi leggeri (es. ghost notes sul rullante). Per catturarli, gli basta abbassare la Threshold Line: visivamente vedrà i marcatori tratteggiati "solidificarsi" in colpi reali.

## 3. Conformità Linear (JUCE/C++)
- **Performance:** Entrambe le viste (Meter balistici e Oscilloscopio a linee vettoriali semplici) sono triviali per il rasterizer di JUCE. Garantito il rispetto del target 60FPS.
- **Estetica:** L'assenza di gradienti colorati (solo Bianco/Fumé/Grigio) e l'uso di primitive (Linee, Rettangoli) rispetta il mandato "Laboratory Precision".

## 4. Executive Briefing & Decision Lock (Fasi 5-6 di STRP-001)
- **Fase 5 — Executive Briefing:** architettura "Split-Focus" presentata al CEO e approvata (sessione 2026-05-20).
- **Fase 6 — Decision, Blueprint Lock & Docs Update:** blueprint bloccato. Documenti aggiornati a valle: `MASTER_CHECKLIST.md` §4 e `LINEAR_DESIGN_GUIDE.md`. Mockup di riferimento: `Wireframes/mockups_v26_industrial_masterpiece.html`.