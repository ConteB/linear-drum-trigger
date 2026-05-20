# SESSION HANDOVER - 2026-05-20 (rev. post-STRP-001 dominio dati)
**Task Attivo:** AUDIT DETTAGLIO F0 + STRP-001 DOMINIO DATI — COMPLETATO
**Stato:** Documentazione a Gate L1 (Design Lock). Fase esecutiva **F0 attiva** (nessun task F0 ancora avviato).

## STATO DELLA COMMESSA

### Chiuso in questa sessione
- **Audit dettaglio dei task F0.** `F0-T2` e `F0-T4` spacchettati in sotto-task azionabili
  (F0-T2a…e, F0-T4a/b) con STRP-001 schedulato *prima* del codice; fallback licenze con
  date dure su `F0-T1`; `F0-T6` ri-fasato (predisposizione, gate operativo in F4);
  cross-link al `DOSSIER_TECNICO` aggiunti. 7 task macro → **11 task azionabili**.
- **Executive Briefing STRP-001 — dominio dati. Decision Lock D1–D4 + D2-bis approvato:**
  - **D1** — dataset **WebDataset** tar-shard ~1 GB (terna `audio.f16`/`target.f16`/`dna.json`).
  - **D2** — contratto training: input `[n_mic, n_sample]` FP16 · target `[frame, 8, 3]`
    (onset/vel/microtiming) + testa HH continua. Finestra e frame-rate → fissati a F0-T4a.
  - **D2-bis** — **MIDI Mapping Table** `GM↔8-bus` bidirezionale + **toggle d'uscita HH**
    (CC continuo / Note discrete). *Il modello resta invariato — il toggle agisce solo
    sullo stadio MIDI d'uscita.*
  - **D3** — Model Artifact: pesi come **blob binario cifrato** (JUCE `BinaryData`) +
    header metadati; exporter PyTorch→RTNeural JSON.
  - **D4** — **Gate L3 ridefinito**: F0-T4b deve provare che la TCN apprende **e** fa
    round-trip in RTNeural (export JSON → smoke-test C++ → match numerico). De-risking
    del rischio architetturale più grave, anticipato a F0 (€0) prima del burn del credito.
- **Fase 6 STRP-001** — aggiornati `MASTER_SCHEDULING.md`, `DOSSIER_TECNICO.md`,
  `MASTER_CHECKLIST.md`, `REGISTRO_AVANZAMENTO.md`. Commit `da189d2`.
- **Modello branch Git** impostato: `main` = solo release stabile finale; **`develop`**
  = branch di sviluppo corrente (su GitHub). Branch topic ridondante eliminato.

### In corso / non avviato
- Nessuna esecuzione tecnica iniziata. I task della Fase F0 sono tutti **☐ TODO** nel
  Tracking Board (`MASTER_SCHEDULING.md` §7).

## OBIETTIVO IMMEDIATO (prossima sessione)
Avviare la **Fase F0**. Due task partono in parallelo:
1. **F0-T1** — Compliance licenze (ENST-Drums, MedleyDB, SM Drums). Lead time esterno:
   va lanciato per primo. Attenzione ai criteri di decadenza con date dure (SM Drums →
   CP-1; ENST/MedleyDB → CP-2).
2. **F0-T2a** — Spec di dettaglio recipe + contratto dati. La direzione è già bloccata
   dal Decision Lock D1/D2/D2-bis; resta il dettaglio implementativo + survey delle
   articolazioni HH delle librerie.

## CONTESTO CONGELATO (vitale)
- **VINCOLO DURO:** il credito Azure $200 scade **2026-06-19** (clock 30gg attivo). Va
  consumato interamente e utilmente. Primo checkpoint **CP-1 il 2026-05-30**.
- **L2 e L3 sono LOCALI** (Mac M5/MPS, €0): NON richiedono Azure. Render Azure gated da
  L2; training A100 gated da L3.
- **Gate L3 ora include il round-trip RTNeural** (D4): non basta che la rete apprenda,
  deve essere provata esportabile prima dello spend.
- **Dominio dati: Decision Lock completo.** WebDataset, contratto `[frame,8,3]`+HH,
  Mapping Table, Model Artifact cifrato. Hi-Hat = testa continua + toggle d'uscita.
- Lavorare sul branch **`develop`**; `main` solo per release stabile.
- Documenti operativi: `MASTER_SCHEDULING.md` (piano + Tracking Board §7),
  `SCHEDULING_DOCTRINE.md` (arbitraggio), `DOSSIER_TECNICO.md` (specifiche tecniche).
- Decision Lock infrastruttura (validi): Azure copre tutto il compute; render Sfizz +
  DrumGizmo; prezzo $149 / $99 EA; formati VST3 + AU; HDD 2 TB €120; budget €500.

## MANDATI PERMANENTI
- Nessun claim di accuratezza numerico pubblico prima del Gate L4.
- Zero-Allocation nel thread audio (RTNeural float32 CPU-only a runtime).
- STRP-001 obbligatorio per ogni decisione tecnica/architetturale aperta.
- Scheduling governato da `SCHEDULING_DOCTRINE.md`; Tracking Board aggiornato a ogni
  sessione e a ogni checkpoint.
