---
id: LIN-DT-SCHED-001
title: Scheduling Doctrine — OP-NEUROTRIGGER
type: doctrine
status: ACTIVE
phase: cross-cutting
domain: Operations / Project Governance
version: 1.1.0
updated: 2026-05-20
tags: [scheduling, doctrine, governance, arbitrage]
related: [LIN-DT-MSCHED-001, LIN-DT-CHKLST-001]
supersedes: []
---

# SCHEDULING DOCTRINE — OP-NEUROTRIGGER

> Dottrina di sequenziamento del lavoro esecutivo. Definisce **come si decide l'ordine
> delle azioni** quando criteri legittimi e concorrenti tirano in direzioni opposte.
> L'istanza operativa (date, task, tracking) vive in `MASTER_SCHEDULING.md`.

## 1. Scopo

La `MASTER_CHECKLIST.md` registra *cosa* è deciso (Design Lock). Questo documento
definisce le **regole di arbitraggio** che trasformano le decisioni in una sequenza
esecutiva. `MASTER_SCHEDULING.md` ne è l'applicazione concreta e tracciabile.

## 2. Principio Cardine — Gate-Driven, con Un Solo Muro Duro

Lo scheduling è governato da **gate** (condizioni), non da date. Eccezione unica e
sovraordinata: il **credito Azure $200 ha una scadenza dura** (clock di 30 giorni dalla
creazione account). Questo è l'unico vincolo di calendario reale del progetto e va
**back-pianificato** a ritroso dalla scadenza.

Primitive dello scheduling:
- **Fase (F0–F5):** raggruppamento di task con la stessa condizione di abilitazione.
- **Priorità (P1>P2>P3):** rango di esecuzione *all'interno* di una fase.
- **Relazione bloccante (⛔/→):** `⛔` = bloccato da; `→` = sblocca/alimenta.
- **Gate (L1–L4):** livelli di maturità (MASTER_CHECKLIST §6).

## 3. I Sette Criteri Concorrenti

Ogni criterio è legittimo. Non sono allineati: ognuno, isolato, produrrebbe un ordine
diverso. La dottrina li arbitra.

| ID | Criterio | Spinge verso… |
| :-- | :-- | :-- |
| **A** | **Critical Path to Gate** — priorità a ciò che sblocca L2→L3→L4. | "Avvia subito la pipeline pesante." |
| **B** | **Qualità del Consumo** — non spendere credito su lavoro non validato. | "Spendi solo su lavoro provato." |
| **C** | **Fail-Fast / Risk Retirement** (ERM-007) — ritira presto il rischio #1 (la TCN apprende?). | "Prototipa l'architettura il prima possibile, in locale." |
| **D** | **Lead Time Esterno** — le conferme di licenza dipendono da terzi. | "Avvia subito ciò che non controlli." |
| **E** | **Reversibilità** — impegni irreversibili (acquisto HDD €120). | "Rimanda l'irreversibile all'ultimo momento responsabile." |
| **F** | **Local-First / Zero-Cost** — massimizza il lavoro fattibile su Mac M5 a €0. | "Esaurisci il locale prima del cloud." |
| **G** | **Credit Expiry Mandate** — il credito $200 non speso entro 30 giorni è **perso**. | "Consuma il 100% del credito in modo utile, entro la scadenza." |

## 4. Matrice dei Conflitti

| | conflitto | natura |
| :-- | :-- | :-- |
| **G vs B** | strutturale | G impone "consuma tutto"; B impone "non sprecare". Risoluzione: vedi §5, Lente 3 — si consuma tutto, ma prima sul lavoro a basso rischio. |
| **G vs E/F** | forte | G dà una scadenza dura; E/F vorrebbero rallentare. G prevale: F0 va back-pianificato per non far slittare F2 oltre il muro. |
| **A vs B** | medio | A vuole avviare la pipeline; B vuole prima la validazione. Risolto dal gating L2/L3 differenziato (§5). |
| **C vs G** | tempo | C (validazione in locale) consuma giorni che G (scadenza) rende scarsi. È il conflitto centrale: lo gestiscono i Checkpoint (§6). |
| **D** | nessuno | D va sempre in parallelo, in F0. Ritardarlo costa e basta. |

Lettura: con la scadenza, **G è il criterio dominante**. Non "se" spendere il credito,
ma "come spenderlo tutto, utilmente, nel tempo dato".

## 5. Regola di Arbitraggio — Tre Lenti

Applicate **in ordine**.

**Lente 1 — Eleggibilità (filtro).** Un task è eseguibile solo se tutte le sue
dipendenze bloccanti (`⛔`) sono soddisfatte. Altrimenti è *parcheggiato*.

**Lente 2 — Costo d'Inazione (escalation).** Tra i task eleggibili, quelli con lead time
esterno (**D**) o che ritirano un rischio fatale (**C**) salgono in testa: vanno avviati
*in parallelo*, subito.

**Lente 3 — Sequenza di Consumo del Credito (gate differenziato).** Il credito si
consuma per intero (**G**), ma in ordine di rischio crescente:
- **Spend a basso rischio — RENDER:** la generazione del dataset (Sfizz/DrumGizmo su
  Azure) è gated solo da **L2** (recipe corrette). Il dataset renderizzato è un asset
  permanente, valido per *qualsiasi* architettura → si può spendere appena L2 è passato.
- **Spend a rischio — TRAINING:** il training su A100 è gated da **L3** (architettura
  validata in locale), perché dipende dall'architettura specifica.
- **Regola:** autorizza prima lo spend RENDER; autorizza lo spend TRAINING solo quando
  L3 è validato. Se L3 slitta, il credito si consuma comunque sul render (asset sicuro)
  e su Tier 2/3 (vedi `MASTER_SCHEDULING.md` §4) — **mai lasciarlo scadere**.

Ordinamento residuo: tra i task superstiti, ordina per **Critical Path (A)**.

## 6. Checkpoint di Consumo (meccanismo Anti-Scadenza)

Poiché il conflitto C-vs-G non è risolvibile a priori (non si sa quanto durerà la
validazione), si introducono **checkpoint** lungo la finestra del credito. A ogni
checkpoint si valuta *in quale scenario siamo* (GREEN/YELLOW/RED) e si ri-decide come
desplegare il credito residuo. Date e regole concrete: `MASTER_SCHEDULING.md` §3–§4.

Principio: un checkpoint non è un report, è un **bivio decisionale**. Se a un checkpoint
lo scenario non è GREEN, si scende sulla scala di deployment (§4 del Master Scheduling)
verso uno spend a rischio inferiore, in modo che il credito venga comunque consumato.

## 7. Output — Modello a Fasi

| Fase | Gate d'ingresso | Contenuto | Criteri dominanti |
| :-- | :-- | :-- | :-- |
| **F0 — Fondazione Locale (€0)** | post-L1 (fase corrente) | Trigger licenze; batch_generator + recipes; Gate **L2** e **L3** in locale. | D, F, C |
| **F1 — Provisioning Azure** | L2 superato | Resource Group, Blob LRS, SAS, alert spesa; dvc remote. | A, E |
| **F2 — Burn Compute** | F1 completa | Render Gold (gate L2) + augmentation/Demucs + training A100 (gate L3) → **L4**. | G, A, B |
| **F3 — Consolidamento** | scadenza credito o L4 | Acquisto HDD 2 TB; push Gold + teardown Azure. | E |
| **F4 — Sviluppo Plugin** | L4 superato | Implementazione C++/JUCE del plugin (codice da 0%). | A |
| **F5 — Release v1.0** | plugin completo + QA | Build Early-Access $99, conforme agli standard interni. | A |

## 8. Procedura d'Uso

1. A ogni sessione, identificare la fase aperta e consultare il tracking board in
   `MASTER_SCHEDULING.md` §7.
2. Eseguire i task in ordine di priorità, rispettando i `⛔`.
3. Un task con criterio **D** si avvia sempre per primo, in parallelo.
4. Una fase si chiude — e la successiva si apre — solo alla verifica **Ocular Proof**
   del gate d'uscita (log reale — POL-AI-001 §2).
5. A ogni checkpoint del credito, eseguire il bivio decisionale (§6) e aggiornare lo
   scenario in `MASTER_SCHEDULING.md`.

---
*Decision Lock 2026-05-20 (v1.1.0). v1.0.0 → v1.1.0: introdotto il criterio G
(Credit Expiry Mandate) e il vincolo duro della scadenza Azure; Lente 3 ridefinita da
"Guardiano del Credito" a "Sequenza di Consumo"; aggiunto il meccanismo dei Checkpoint.*
