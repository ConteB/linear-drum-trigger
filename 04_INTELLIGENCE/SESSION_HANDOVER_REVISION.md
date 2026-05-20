# SESSION HANDOVER - 2026-05-20 (rev. post F0-T4a / F0-T9a / F0-T10)
**Task Attivo:** Fase F0 — chiusi tre cicli STRP-001 (topologia TCN, Testing Doctrine, Doc Linking Layer).
**Stato:** Fase esecutiva **F0 attiva**. Chiusi F0-T1, F0-T1b, F0-T1c, F0-T2a, F0-T4a, F0-T9a · F0-T10 in corso.

## STATO DELLA COMMESSA

### Chiuso in questa sessione
- **F0-T4a · Topologia TCN concreta (STRP-001)** ☑ — Decision Lock. `R_target` ratificato
  a `44100/128 = 344.53 Hz`; topologia 4-stadi (Input-Agnostic Projection → Strided
  Encoder Stem stride-128 → Dilated Causal TCN Trunk 8 blocchi → 4 teste); look-ahead
  ~100 ms come ritardo d'ingresso = PDC; abbandonato il Sentinella/Scalpello + NN-Repeat
  (incoerenza RTNeural sanata); soglia Gate L3 fissata. Spec:
  `docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md`.
- **F0-T9a · Testing & QA Doctrine (STRP-001)** ☑ — Decision Lock. Tassonomia a 4 layer
  (unit / property-based / fuzz / AI-Adversarial QA) + Layer-S statico; mutation testing
  come gate anti-pigrizia (critici ≥ 90 %, core ≥ 85 %); conteggio test e coverage
  rifiutati come target. Dottrina: `04_INTELLIGENCE/TESTING_DOCTRINE.md`. Pattern
  AI-Adversarial QA in `SUB_AGENT_GOVERNANCE.md` §6.
- **F0-T10 · Documentation Linking Layer (STRP-001)** ◐ — Decision Lock. OP-NEUROTRIGGER
  Doc Standard: frontmatter YAML, ancore HTML stabili, link relativi, INDEX generato,
  validatore `lychee`. Standard + tooling + frontmatter su 9 doc FATTI; corpo del
  retrofit aperto (vedi sotto).

### Documenti prodotti / aggiornati
- Nuovi: `docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md`, `04_INTELLIGENCE/TESTING_DOCTRINE.md`,
  `04_INTELLIGENCE/DOC_LINKING_STANDARD.md`, `docs/INDEX.md`, `tools/gen_docs_index.py`,
  `lychee.toml`.
- Aggiornati: `DOSSIER_TECNICO.md`, `MASTER_CHECKLIST.md`, `F0-T2a_…SPEC.md`,
  `MASTER_SCHEDULING.md`, `SUB_AGENT_GOVERNANCE.md`, `SCHEDULING_DOCTRINE.md`,
  `REGISTRO_AVANZAMENTO.md`, `Diario_Presidenza_OpenPhase.md`.
- **Tutto committato e pushato** su `origin/develop` (commit `5f8bf06`, `1682e1b`).

### In corso / non avviato
- **F0-T10 (corpo, `P2`):** ancore HTML stabili + conversione dei riferimenti in
  prosa→link sul hot-set; retrofit dei **20 documenti** ancora senza frontmatter (lista
  esplicita in fondo a `docs/INDEX.md`); `lychee` da warn → blocking. Non blocca L2/L3.
- Nessuna esecuzione di codice di pipeline avviata.

## OBIETTIVO IMMEDIATO (prossima sessione)
**F0-T9b · F0 Pipeline Test Harness** — è il primo anello reale verso il Gate L2 e ora
**gate test-first di F0-T2b/c/d**. Scaffolding `pytest`/`Hypothesis`/`mutmut`/`coverage`/
`Atheris` + test-oracolo derivati dal contratto F0-T2a, scritti **prima** del codice.
Task di codice → **delega a sub-agente** (POL-AI-001 §3). Dettaglio in `TESTING_DOCTRINE.md` §6.

Poi, a valle: **F0-T2b/c/d** (codice pipeline, sub-agenti), che sbloccano F0-T2e → F0-T3 (L2).
In parallelo, non bloccante: **F0-T4b** (mini-prototipo TCN, gated anche da F0-T3) e il
corpo di **F0-T10**.

## CONTESTO CONGELATO (vitale)
- **VINCOLO DURO:** credito Azure $200 scade **2026-06-19**. Primo checkpoint **CP-1 il
  2026-05-30**. L2/L3 sono locali (€0). Scenario credito: *da fissare a CP-1*.
- **Dottrina compliance §1.1 attiva:** nessun asset senza licenza pubblicata commercial-clear.
- **Contratto dati F0-T2a LOCKED** + **topologia F0-T4a LOCKED**: `R_target` 344.53 Hz,
  target `flat-25`, microtiming disaccoppia la sample-accuracy dal frame-rate.
- **Testing Doctrine attiva:** ogni task di codice ha DoD = suite verde + mutation
  kill-rate; l'harness precede il codice (test-first).
- **Doc Standard attivo:** ogni documento nuovo nasce con frontmatter YAML; dopo modifiche
  al frontmatter, rigenerare `docs/INDEX.md` con `python3 tools/gen_docs_index.py`.
- **Validation Protocol:** E-GMD + Slakh2100 + Ocular Proof. ⚠️ E-GMD è su Roland TD-17 →
  i claim L4 non coprono il bleed acustico reale con metrica numerica.
- Branch di lavoro **`develop`** (sincronizzato con `origin`); `main` solo per release.

## MANDATI PERMANENTI
- Nessun claim di accuratezza numerico pubblico prima del Gate L4.
- Zero-Allocation nel thread audio (RTNeural float32 CPU-only a runtime).
- STRP-001 obbligatorio per ogni decisione tecnica/architetturale aperta.
- Orchestratore non scrive codice di produzione: delega a sub-agenti (POL-AI-001 §3).
- Testing Doctrine: harness test-first; mutation testing come gate anti-pigrizia.
- Doc Standard: frontmatter su ogni doc nuovo; INDEX rigenerato; `lychee` come gate.
- Tracking Board (`MASTER_SCHEDULING.md` §7) aggiornato a ogni sessione e checkpoint.
