---
id: LIN-DT-CHKLST-001
title: Master Checklist — OP-NEUROTRIGGER Launchpad
type: checklist
status: ACTIVE
phase: cross-cutting
domain: Product / Design Lock
version: 1.0.0
updated: 2026-05-20
tags: [checklist, design-lock, governance, gates]
related: [LIN-DT-MSCHED-001, LIN-DT-SCHED-001, LIN-DT-DOSSIER-001]
supersedes: []
---

# 🎯 MASTER CHECKLIST (OP-NEUROTRIGGER LAUNCHPAD)
**Data ultima revisione:** 20 Maggio 2026
**Status:** PRE-PRODUZIONE DOCUMENTALE — DESIGN ALIGNMENT
Questa è la checklist operativa globale che copre tutti i domini necessari al lancio del prodotto, definita dopo l'astrazione concettuale.

> ### 📌 LEGENDA DI STATO (LETTURA OBBLIGATORIA)
> Il progetto è in **PRE-PRODUZIONE DOCUMENTALE**: nessun codice di produzione è stato scritto. Gli script presenti in `src/` sono prototipi-test usa e getta, **non vincolanti** e destinati alla riscrittura.
> - `[x]` = **DESIGN LOCK** — decisione di design/architettura approvata e blindata via STRP-001. **NON** significa "implementato".
> - `[ ]` = **DA TRATTARE** — decisione di design ancora aperta.
> - **Stato implementazione codice:** 0% (l'avvio dello sviluppo è subordinato al completamento documentale — Gate L1).
> Tracciamento implementazione: `SPRINT_BOARD.md` e `04_INTELLIGENCE/REGISTRO_AVANZAMENTO.md`.

> ### 🛑 PROTOCOLLO DI RISOLUZIONE TASK (STRP-001)
> Ogni punto marcato "DA TRATTARE" deve essere processato attraverso questa pipeline in 6 fasi:
> 1. **Competitor & Market Analysis:** Studio soluzioni industria per problematiche analoghe.
> 2. **Open-Source Codebase Analysis:** Ricerca e analisi di progetti open-source (es. GitHub) per studiare pattern implementativi stabili e collaudati.
> 3. **UX/UI Impact:** Progettazione esperienza utente (es. "Laboratory Precision").
> 4. **C++ / Tech Implementation Matrix:** Valutazione tecnica (Complessità, Aderenza Mandati Linear, Rischi).
> 5. **Executive Briefing:** Presentazione di un resoconto finale dettagliato al CEO per la scelta e l'approvazione.
> 6. **Decision, Blueprint Lock & Docs Update:** A valle dell'approvazione, aggiornare sistematicamente la `MASTER_CHECKLIST.md` e i documenti tecnici/UI correlati (es. `DOSSIER_TECNICO.md`).

## 1. 🧠 AI & NEURAL ENGINEERING (PyTorch Core)
- [x] **Topologia:** Strided-Context TCN (compatibilità RTNeural). **Spec concreta LOCKED (2026-05-20, F0-T4a)** — Input-Agnostic Projection → Strided Encoder Stem (stride totale 128) → Dilated Causal TCN Trunk → 4 teste (onset/velocity/microtiming/hihat-opening). `R_target` ratificato a `44100/128 ≈ 344.53 Hz`; look-ahead ~100 ms realizzato come ritardo d'ingresso = PDC. Dettaglio: `docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md`.
- [x] **Parametri:** Training mixed-precision (master FP32 + FP16), tensori del dataset storati in FP16, inferenza C++ in `float32` (RTNeural). Non-Causale, Look-ahead ~100ms. Output: matrice 8 target (piano-roll differenziabile).
- [x] **Training Strategy:** Asymmetric Focal Loss (Zero Falsi Positivi) + Gaussian Target Smearing (±3ms).
- [x] **Training Logistics:** Prototipazione locale su Mac M5 (MPS) per mini-batch. Addestramento "Gold" Finale su **Azure A100 Spot** per processare 1.5TB — incluso nel credito Azure $200 (non sono necessari servizi GPU cloud aggiuntivi a pagamento).
- [x] **Validation Protocol** *(ridisegnato 2026-05-20, F0-T1c):* Holdout reale = **E-GMD** (CC-BY 4.0, performance umane reali) · test Stealth-Mix = **Slakh2100** (CC-BY 4.0) · **Ocular Proof**. Sostituisce ENST-Drums e MedleyDB, esclusi per la dottrina compliance "Self-Evident Commercial License" (`DATA_PROVENANCE_LOG.md` §1.1). Dettaglio e limiti: `docs/compliance/F0-T1c_HOLDOUT_SURVEY.md`.

## 2. 🗄️ DATA INFRASTRUCTURE & DATA ENGINEERING
- [x] **Infrastruttura & Size:** Azure Blob (LRS) + DVC. Target Definitivo: **1.5 Terabyte (450 ore)**. Pianificazione basata sul **credito Azure di $200** (budget-driven, non time-driven); piano di spesa per task in `STRATEGIC_INFRASTRUCTURE_AUDIT.md` §7.1. Archivio permanente post-Azure: HDD fisico 2 TB (~€100–150). Formato del layer Gold: **WebDataset** tar-shard (`DOSSIER_TECNICO` §9.2).
- [x] **Sovereignty:** Protocollo Escape Hatch (Dual Remote + Backup tar.zst in chiaro). `ONBOARDING_HUMAN.md` completato.
- [x] **Pipeline Rendering (Python):** Motore ufficiale **Sfizz** (librerie SFZ multi-layer) + **DrumGizmo** (CLI, kit multi-microfono per il bleed reale). FluidSynth/SF2 scartato: i SoundFont non espongono tracce multi-mic e non possono generare il bleed, moat primario del prodotto.
- [x] **Data Mutilation & Saboteurs:** Approvato modulo "Studio Mutilation". Approvata iniezione "Transient Saboteurs" (Sintetici via Sfizz + Dataset Esterni).
- [x] **Machine-Gun Chaos:** Implementazione generazione stocastica di MIDI impossibili (Blast beats, multi-hits) per prevenire l'overfitting ritmico.
- [x] **Acoustic Reverb:** Implementazione Convoluzione via `pedalboard` usando IRs (OpenAIR).
- [x] **Augmentation & Lineage:** MIDI Jittering (Pre-render) e Protocollo DNA-Trace approvati.
- [x] **[STRP-001] Contratto Dati & Output MIDI:** Risolto (Executive Briefing 2026-05-20). Formato Gold tensor + packaging WebDataset; **MIDI Mapping Table** `GM↔8-bus` bidirezionale; Hi-Hat con testa di apertura **continua** e uscita selezionabile **CC-continuo / Note-discrete**. Artefatto modello: blob pesi cifrato + header metadati, export PyTorch→RTNeural. Esportabilità RTNeural certificata dal Gate L3. Dettaglio in `04_INTELLIGENCE/MASTER_SCHEDULING.md` §6 (F0-T2a, F0-T4b, F0-T8). **Spec di dettaglio F0-T2a LOCKED (2026-05-20)** — recipe YAML, layout byte FP16 `flat-25`, DNA-Trace: `docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`; MIDI Mapping Table versionata in `docs/specs/midi_mapping_table.yaml`.

## 3. 🖥️ SOFTWARE ENGINEERING & DSP (C++ / JUCE)
- [x] **Framework Inference:** RTNeural (Scelto per via del trucco Strided-Context compatibile).
- [x] **Vincoli:** Zero-Allocation nel thread audio, latenza compensata (PDC).
- [x] **[STRP-001] Testing & QA (trasversale):** Risolto (Executive Briefing 2026-05-20).
  Adottata `04_INTELLIGENCE/TESTING_DOCTRINE.md` — tassonomia a 4 layer (unit, property-based,
  fuzz, AI-Adversarial QA) + Layer-S statico; **mutation testing** come gate anti-pigrizia
  (kill-rate critici ≥ 90 %, core ≥ 85 %; il conteggio test e la coverage non sono target).
  Core DSP C++/GUI: `pluginval` ≥ 8 + test Zero-Allocation dinamico (coarse, dettaglio F4).
  Pattern AI-Adversarial QA in `SUB_AGENT_GOVERNANCE.md` §6. Nuovi task F0-T9a/b
  (`MASTER_SCHEDULING.md`); l'harness F0-T9b è **gate test-first di F0-T2b/c/d**.
- [x] **Formati di Distribuzione:** v1.0 = **VST3 + AU**. AAX (Pro Tools) rinviato post-v1.0: richiede firma PACE, incompatibile con la filosofia anti-DRM (`DOSSIER_TECNICO.md` §11).
- [x] **[STRP-001] PDC & Latenza:** Risolto. Scenario A (Honest Approach). La latenza di 100ms è fissa (setLatencySamples). UX gestita trasformando il vincolo in una feature: Badge UI "MODE: MIXING GRADE ONLY". Nessuna modalità live imperfetta.
- [x] **[STRP-001] Logica di Routing MIDI:** Risolto. Implementata architettura **Chronos Engine** (Midi Delay-Line circolare). Il plugin garantisce un output **Sample-Accurate** compensando i 100ms di PDC. Il timing è deterministico e privo di jitter indipendentemente dalla dimensione del buffer DAW.
- [ ] **DA TRATTARE (v1.x/v2.0 - C++ / Drag & Drop):** Implementazione tecnica del "Ghost File System" per l'esportazione asincrona. Architettura Chronos già predisposta per il mirroring su disco.
- [x] **[STRP-001] Sistema di Licensing:** Risolto. Adottato modello "Soft-DRM" (stile Valhalla DSP) per rispettare l'UX dell'utente. Implementazione 100% offline tramite `juce::RSAKey` e `Keyfile`. Crittografia asimmetrica per bloccare i KeyGen. Sicurezza anti-patching garantita dal pattern "Poisoned DSP" (variabili di sblocco intrecciate nella logica di Look-ahead invece di semplici booleani). L'UI mostrerà `REGISTERED TO: [NOME]`.

## 4. 🎨 PRODUCT DESIGN & UI/UX
- [x] **Brand & Aesthetic:** "Laboratory Precision", Alluminio/Fumé, Monocromatico (Vector-style).
- [x] **[STRP-001] DA TRATTARE (UX):** Gestione visiva dell'incertezza AI risolta tramite Architettura "Split-Focus". Master Matrix (8 LED Confidence Meters) + Detail Oscilloscope (Ghost Markers e Solid Hits rispetto alla soglia). Blueprint bloccato in `UX_BLUEPRINT_STRP-001.md`.
- [x] **[STRP-001] DA TRATTARE (UX):** Prototipazione UI (Wireframes vettoriali). Risolto con Estetica "Hybrid Studio-Bench" (Noce/CRT/Metallo). Proporzioni 4:3. Mockup v09 bloccato. Guida di stile creata in `LINEAR_DESIGN_GUIDE.md`.

## 5. 💼 BUSINESS, MARKETING & GOVERNANCE
- [x] **Posizionamento & Prezzo:** Ultra-High-End, Premium Tier. **Prezzo ufficiale: $149 USD**; **Early-Access $99 USD** per la fase di validazione di mercato. Il budget interno di progetto resta espresso in EUR.
- [x] **Rischi & Budget:** Budget €500, Azure coperto, Leakage chiavi mitigato.
- [x] **[STRP-001] Go-to-Market:** Risolto. Definita strategia **"Ocular Proof"** basata sulla "Impossible Triad" (Extreme Bleed, Dynamic Ghosting, Machine-Gun Chaos). Documentato in `04_INTELLIGENCE/MARKETING_OCULAR_PROOF.md`.
- [x] **[STRP-001] Governance:** Risolto. Implementato Protocollo **LINEAR-SHIELD** in `04_INTELLIGENCE/SUB_AGENT_GOVERNANCE.md`. Definiti i Trigger di Delega e i Verification Gates per i sub-agenti (DSP/UI).
- [x] **[STRP-001] Ops:** Risolto. Adottata **Zero-PII Log Policy** (Protocollo ANONYMOUS-TRACE). Nessun dato sensibile, percorso utente o identificativo reale viene mai loggato o trasmesso. Diagnostica basata esclusivamente su Hash hardware e codici errore (Enums).

## 6. 🚦 VALIDATION GATES (DEFINIZIONE CANONICA L1–L4)
Livelli di maturità progressivi citati in `SPRINT_BOARD.md`, `PIPELINE_STATUS.json` e nei documenti marketing. Definizione unica e vincolante:
- **L1 — Design Lock:** Documentazione organica completa e internamente coerente. *(Gate corrente — pre-produzione documentale.)*
- **L2 — Pipeline Dati Validata:** `batch_generator` produce un mini-dataset Gold corretto end-to-end (demo batch superato).
- **L3 — Prototipo Neurale:** TCN addestrata su mini-batch (Mac M5 / MPS) con metriche di onset significativamente non casuali **e** topologia esportabile in RTNeural (round-trip JSON + smoke-test C++ + match numerico — ridefinizione STRP-001 D4). Soglia numerica delle metriche di onset bloccata in `docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md` §7 (F-measure ≥ 0.80 @ ±20 ms, controllo negativo < 0.10).
- **L4 — Studio-Grade Validation:** Il modello "Gold" supera l'Holdout reale (ENST-Drums) e l'Ocular Proof. È il gate che **sblocca i claim di accuratezza pubblici** e la modalità "Full Mix".

## 7. 🗓️ EXECUTION SCHEDULING LAYER
Le sezioni §1–§5 registrano *cosa* è deciso (Design Lock). Questa sezione è la **mappa di fase**; il dettaglio dei task, le date e il tracking vivono in `04_INTELLIGENCE/MASTER_SCHEDULING.md`, governato da `04_INTELLIGENCE/SCHEDULING_DOCTRINE.md` (7 criteri concorrenti + arbitraggio).

> **Vincolo duro:** il credito Azure $200 scade il **2026-06-19** (clock 30 gg attivo). Le fasi F0–F2 sono back-pianificate da quella data. Mandato: il credito va consumato **interamente e utilmente** prima della scadenza.

| Fase | Gate d'ingresso | Contenuto | Spend |
| :-- | :-- | :-- | :-- |
| **F0** Fondazione Locale | post-L1 *(corrente)* | Compliance licenze; batch_generator + recipes; Gate **L2** e **L3** in locale. | €0 |
| **F1** Provisioning Azure | L2 superato | Resource Group, Blob LRS, SAS, alert spesa; dvc remote. | minimo |
| **F2** Burn Compute | F1 completa | Render Gold 1.5 TB (gate L2) + augmentation/Demucs + training A100 (gate L3) → **L4**. | $200 |
| **F3** Consolidamento | scadenza credito o L4 | Acquisto HDD 2 TB (€120); push Gold + teardown Azure. | €120 |
| **F4** Sviluppo Plugin C++/JUCE | L4 superato | Implementazione plugin (codice da 0%). | — |
| **F5** Release v1.0 EA | plugin + QA | Build Early-Access $99 (target ~2026-10-20). | — |

> ⚠️ **Correzione del SESSION_HANDOVER:** la priorità "Setup Azure = PRIORITÀ 1, sblocca L2" è superata. L2 e L3 sono mini-batch **locali** (§1, §6): non richiedono Azure. Il render Azure è gated da L2; il training da L3 (vedi `MASTER_SCHEDULING.md` §4).

➡️ **Esecuzione, task detate e Tracking Board:** `04_INTELLIGENCE/MASTER_SCHEDULING.md`.

---
*Ogni punto "DA TRATTARE" è un blocco esecutivo per le prossime sessioni.*
*Le decisioni di Design Lock derivano dal protocollo STRP-001 (6 fasi). Le risoluzioni dell'audit del 2026-05-20 sono tracciate in `04_INTELLIGENCE/AUDIT_RESOLUTION_LOG.md`.*
*L'ordine di esecuzione (§7) è governato da `04_INTELLIGENCE/SCHEDULING_DOCTRINE.md`; il piano operativo e il tracking sono in `04_INTELLIGENCE/MASTER_SCHEDULING.md` (Decision Lock 2026-05-20).*
