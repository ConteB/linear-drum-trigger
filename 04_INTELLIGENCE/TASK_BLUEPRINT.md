# TASK BLUEPRINT (SOP-016 / ERM-005)

## IDENTIFICAZIONE TASK (TOP-002)
- **Task:** Avvio Fase F0 — esecuzione parallela **F0-T1** (Compliance licenze) + **F0-T2a** (Recipe + contratto dati, via STRP-001).
- **Categoria:** OPERATIONS / Esecuzione di Fase (Compliance legale + Spec di dettaglio).
- **Check Autorizzazione:** Task Lock ricevuto dal CEO — "avvia le attività" (2026-05-20). Coerente con l'obiettivo immediato dell'handover `SESSION_HANDOVER_REVISION.md`.
- **Documenti Mappati:** SOP-010, SOP-016, ERM-005, TOP-002, STRP-001, `MASTER_SCHEDULING.md` §6, `DATA_PROVENANCE_LOG.md`, `DOSSIER_TECNICO.md`.

## SCORING (ERM-005)
| Metrica | Valutazione | Punteggio (1-10) | Peso | Risultato Ponderato |
| :--- | :--- | :--- | :--- | :--- |
| **Impatto Business** | Alto — F0-T1 condiziona lo spend render; F0-T2a è il documento radice che sblocca F0-T2b/c/d. | 9 | 40% | 3.6 |
| **Complessità Tecnica** | Media — ricerca legale + spec di dettaglio su carta; nessun codice (arriva in F0-T2b+). | 5 | 20% | 1.0 |
| **Rischio Regressione** | Basso — nessun kernel/invariante toccato; solo documentazione e specifiche. | 2 | 30% | 0.6 |
| **Debito Documentale** | Basso — aggiorna documenti esistenti e archivia nuove spec. | 3 | 10% | 0.3 |
| **PUNTEGGIO TOTALE (S)** | | | | **5.5 (Fattibile)** |

## LIVELLO DI RISCHIO
**BASSO:** task documentale e di specifiche. Nessun Kernel/Invariante DSP toccato; nessun thread audio. Approvato per l'esecuzione senza escalation SOP-003.

## STRATEGIA
- **F0-T1** — identificare la licenza di ENST-Drums, MedleyDB, SM Drums (ricerca verificata, Ocular Proof su fonti); produrre la matrice di verifica; redigere le bozze di outreach. DoD chiuso solo con conferma scritta esterna (azione del CEO). Decadenza dura: SM Drums → CP-1 (2026-05-30); ENST/MedleyDB → CP-2 (2026-06-09).
- **F0-T2a** — applicare le 6 fasi di **STRP-001**; culmina in Executive Briefing per Decision Lock del CEO prima di passare a F0-T2b/c/d.
- **Gate Zero:** questo Blueprint autorizza scritture su documenti direzionali/registri (eccezione orchestratore POL-AI-001 §3). L'eventuale codice di F0-T2b+ resta soggetto a delega sub-agente.

## NOTE
- Incoerenza documentale rilevata: `MASTER_SCHEDULING.md` (fallback F0-T1) cita `DATA_PROVENANCE_LOG.md §39` inesistente — da correggere in docs-update.

> *Blueprint dello startup di Fase F0. Sostituisce il blueprint stale del task "Esportazione MIDI" (chiuso).*
