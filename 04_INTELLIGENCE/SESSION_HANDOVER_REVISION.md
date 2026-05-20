# SESSION HANDOVER - 2026-05-20 (rev. post-sistema di scheduling)
**Task Attivo:** SISTEMA DI SCHEDULING — COMPLETATO
**Stato:** Documentazione a Gate L1 (Design Lock). Fase esecutiva **F0 attiva** (nessun task F0 ancora avviato).

## STATO DELLA COMMESSA

### Chiuso in questa sessione
- **`SCHEDULING_DOCTRINE.md` v1.1.0** — 7 criteri concorrenti + regola di arbitraggio a 3 lenti; criterio G (Credit Expiry Mandate).
- **`MASTER_SCHEDULING.md`** (LIN-DT-MSCHED-001) — documento operativo unico: timeline back-pianificata F0–F5, checkpoint credito, scala di deployment, task detate, Tracking Board (§7).
- **`MASTER_CHECKLIST.md` §7** — ridotta a mappa di fase, rinvia al Master Scheduling.
- **Sistema di scheduling-awareness in Claude Code:** `@import` in `CLAUDE.md` (L1), hook `SessionStart` (`.claude/settings.json` + `.claude/hooks/scheduling_status.py`, L2), comando `/scheduling` (`.claude/commands/scheduling.md`). Verificato (pipe-test exit 0, jq valido).

### In corso / non avviato
- Nessuna esecuzione tecnica iniziata. I task della Fase F0 (F0-T1 … F0-T7) sono tutti **☐ TODO** nel Tracking Board.

## OBIETTIVO IMMEDIATO (prossima sessione)
Avviare la **Fase F0**. Due task partono in parallelo:
1. **F0-T1** — Compliance licenze (ENST-Drums, MedleyDB, SM Drums). Criterio D (lead time esterno): va lanciato per primo.
2. **F0-T2** — `batch_generator` + render recipes Sfizz/DrumGizmo. Critical path verso il Gate L2.

Il CEO non ha ancora indicato da quale dei due far partire l'esecuzione operativa — chiederlo, oppure procedere con entrambi.

## CONTESTO CONGELATO (vitale)
- **VINCOLO DURO:** il credito Azure $200 scade **2026-06-19** (clock 30gg attivo). Va consumato interamente e utilmente — mandato del CEO. Primo checkpoint **CP-1 il 2026-05-30**.
- **L2 e L3 sono LOCALI** (Mac M5/MPS, €0): NON richiedono Azure. Il render Azure è gated da L2; il training A100 da L3. (La vecchia priorità "Azure-first" dell'handover precedente era errata — corretta.)
- Il **sistema di scheduling-awareness è live dalla prossima sessione**: l'hook `SessionStart` inietta automaticamente countdown credito e checkpoint; usare `/scheduling` per un report on-demand.
- Documenti operativi di riferimento: `04_INTELLIGENCE/MASTER_SCHEDULING.md` (piano + Tracking Board), `04_INTELLIGENCE/SCHEDULING_DOCTRINE.md` (arbitraggio).
- Decision Lock infrastruttura (sessioni precedenti, ancora validi): Azure copre tutto il compute; render engine Sfizz + DrumGizmo; prezzo $149 / $99 EA; formati VST3 + AU; HDD 2 TB €120; budget €500.

## MANDATI PERMANENTI
- Nessun claim di accuratezza numerico pubblico prima del Gate L4.
- Zero-Allocation nel thread audio (RTNeural float32 CPU-only a runtime).
- STRP-001 obbligatorio per ogni decisione tecnica/architetturale aperta.
- Scheduling governato da `SCHEDULING_DOCTRINE.md`; Tracking Board aggiornato a ogni sessione e a ogni checkpoint.
