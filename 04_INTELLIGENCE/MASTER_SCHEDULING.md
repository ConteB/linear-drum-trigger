---
ID: LIN-DT-MSCHED-001
Status: ACTIVE — EXECUTION MASTER
Domain: Operations / Project Execution
Progetto: drum-trigger-fresh (OP-260518-FRESH)
Versione: 1.0.0
Data: 2026-05-20
Riferimenti: SCHEDULING_DOCTRINE.md, MASTER_CHECKLIST.md, SESSION_HANDOVER_REVISION.md
---

# MASTER SCHEDULING — OP-NEUROTRIGGER

> **Documento operativo unico.** Lega tutto coerentemente, dice esattamente cosa fare in
> ogni task, e funge da board di tracking. È governato da `SCHEDULING_DOCTRINE.md`
> (il *perché* e *come si decide*); registra l'esecuzione di ciò che `MASTER_CHECKLIST.md`
> ha deciso (il *cosa*).

## 0. Come si legge

| Documento | Ruolo |
| :-- | :-- |
| `MASTER_CHECKLIST.md` | *Cosa* è deciso (Design Lock) e i Gate L1–L4. |
| `SCHEDULING_DOCTRINE.md` | *Come si decide* l'ordine (7 criteri concorrenti + arbitraggio). |
| **`MASTER_SCHEDULING.md`** (questo) | *Cosa fare, in che ordine, con che stato.* |

Stato task: `☐` TODO · `◐` IN CORSO · `☑` FATTO · `⊘` BLOCCATO · `⏸` PARCHEGGIATO.

## 1. Vincoli Temporali

### 1.1 Vincolo DURO — Credito Azure ($200, use-it-or-lose-it)
- **Clock attivo.** Account creato; finestra di 30 giorni: **2026-05-20 → 2026-06-19**.
- **Mandato del CEO:** il credito non è "denaro regalato da ignorare". Modello mentale:
  budget = **€500 + $200**. Tra 30 giorni i $200 spariscono. Devono sparire **perché li
  abbiamo usati**, non perché sono scaduti. Obiettivo: consumare il 100% del credito
  nel modo più utile ed efficiente possibile (criterio G della doctrine).
- Conseguenza: F2 (compute) è back-pianificato a ritroso dal 2026-06-19.

### 1.2 Vincolo MORBIDO — Orizzonte v1.0
- Prima versione **pubblicabile e vendibile**: build Early-Access $99, stabile e conforme
  agli standard interni.
- Orizzonte fissato: **~5 mesi → target ~2026-10-20**. Da raffinare dopo il Gate L4
  (quando il modello Gold è validato e inizia lo sviluppo del plugin C++/JUCE).

## 2. Timeline Macro — Back-plan dalla Scadenza

| Fase | Finestra (back-plan) | Gate d'uscita | Note |
| :-- | :-- | :-- | :-- |
| **F0** Fondazione Locale (€0) | 05-20 → ~06-02 | **L2** entro ~05-28 · **L3** entro ~06-02 | sotto pressione del muro |
| **F1** Provisioning Azure | ~05-29 → ~06-01 | infra pronta | parte appena L2 è passato |
| **F2** Burn Compute | ~06-01 → 06-19 | **L4** | il muro duro |
| **F3** Consolidamento | post 06-19 | Gold su HDD | nessuna fretta |
| **F4** Sviluppo Plugin C++/JUCE | ~06-20 → ~10-10 | plugin completo | coarse, raffinato post-L4 |
| **F5** Release v1.0 EA | ~10-10 → ~10-20 | build $99 pubblicata | coarse |

**Parallelismo chiave:** appena **L2** è validato (~05-28), due track corrono in
parallelo — *Track Cloud* (F1 → F2 render, spend a basso rischio) e *Track Locale*
(prototipazione TCN → L3). Il render NON aspetta L3. Il training parte quando L3 è
pronto. Questo è ciò che protegge il consumo del credito.

## 3. Checkpoint del Credito — Bivi Decisionali

A ogni checkpoint si valuta lo **scenario** e si ri-decide il deployment del credito
residuo. Un checkpoint è un bivio, non un report.

| CP | Giorno | Data | Cosa si valuta | Decisione |
| :-- | :-- | :-- | :-- | :-- |
| **CP-1** | D10 | 2026-05-30 | L2 superato? batch_generator solido? | Confermare avvio Track Cloud. Se L2 non passato → escalation su F0-T2. |
| **CP-2** | D20 | 2026-06-09 | % render completata · stato L3 · $ spesi | Se L3 ok → autorizzare training. Altrimenti → render + Tier 2. Fissare scenario. |
| **CP-3** | D25 | 2026-06-14 | $ residui · training in corso? | Credit-soak finale: desplegare ogni dollaro residuo sulla scala §4. |

## 4. Scala di Deployment del Credito — Spendere Ogni Dollaro

Regola (doctrine §5, Lente 3): si spende per intero, in ordine di **rischio crescente**.
Il **render** è spesa a basso rischio (asset permanente, valido per qualsiasi
architettura, gated solo da L2); il **training** è spesa a rischio (gated da L3).

- **Tier 1 — Core (must-do):** render Gold 1.5 TB · augmentation + Demucs isolation ·
  un training "Gold" A100 completo → L4.
- **Tier 2 — Se restano credito/tempo:** training aggiuntivo (più epoche, sweep
  iperparametri, convergenza più lunga) · varianti extra di augmentation / Studio
  Mutilation · scenari di bleed multi-mic aggiuntivi.
- **Tier 3 — Credit-soak ("ultimo dollaro"):** seconda variante di modello / ensemble ·
  re-render ad alta fedeltà di un subset · run di validazione estese.

**Scenari (fissati ai checkpoint):**
- 🟢 **GREEN** — L2 ~05-28, L3 ~06-08: Tier 1 completo + Tier 2. Caso ideale = dataset
  massivo + training completo per la prima versione vendibile del modello.
- 🟡 **YELLOW** — L3 slitta oltre ~06-10: render completato comunque; training compresso;
  Tier 2 leggero. Modello Gold valido ma meno rifinito.
- 🔴 **RED** — L3 non raggiunto entro CP-3: il credito si consuma **interamente** sul
  render (asset permanente sicuro) + augmentation + Tier 3 lato-render. Il training si
  rimanda a un piano post-credito. **Il credito non si perde mai** — si converte in
  dataset, che resta su HDD.

## 5. Allocazione Budget Indicativa ($200)

| Voce | Stima | Note |
| :-- | :-- | :-- |
| Storage Blob LRS 1.5 TB (~1 mese) | ~$30 | |
| Render compute (CPU VM, Sfizz/DrumGizmo) | ~$55 | spend a basso rischio |
| Augmentation + Demucs (GPU) | ~$25 | |
| Training A100 Spot | ~$80 | spend a rischio (gate L3) |
| Buffer / egress | ~$10 | |

Soglie di monitoraggio (il CEO controlla il saldo): **$100** → valutazione · **$40** →
stop compute + push HDD · **$10** → chiudi tutto.

## 6. Task Detate — Esecuzione Precisa

### Fase F0 — Fondazione Locale · gate d'ingresso: post-L1 (corrente)

**F0-T1 · Compliance licenze · `[D]` `P1`**
- *Obiettivo:* conferma scritta del diritto d'uso per ENST-Drums, MedleyDB, SM Drums.
- *Azioni:* identificare la licenza di ciascun asset; confermare per ENST-Drums e
  MedleyDB lo status **Evaluation-Only** (mai training, mai redistribuzione — coerente
  con `DATA_PROVENANCE_LOG.md` §2.B); per SM Drums verificare la licenza commerciale di
  redistribuzione dell'**output renderizzato**; inviare le richieste/email dove serve.
- *DoD:* conferma scritta archiviata in `DATA_PROVENANCE_LOG.md`.
- *Avvio immediato, in parallelo* — lead time esterno.

**F0-T2 · batch_generator + render recipes · `[F]` `P1`**
- *Obiettivo:* pipeline locale che produce un mini-batch Gold corretto end-to-end.
- *Azioni:* verificare `BatchGenerator.run_scenario`; integrare Sfizz e DrumGizmo via
  CLI; definire le recipe (SFZ multi-layer; kit multi-microfono DrumGizmo per il bleed
  reale); generare un mini-batch (~10–20 scenari) di Gold tensor — waveform FP16 grezzo
  44.1 kHz multi-mic + matrice 8-target.
- *DoD:* log stdout che mostra N campioni generati senza errori.
- → F0-T3.

**F0-T3 · Gate L2 (validazione recipe) · `[C]` `P1`**
- *Obiettivo:* validare che il mini-dataset è corretto.
- *Azioni:* ispezione manuale di ≥2 campioni (waveform multi-mic coerente, bleed
  presente, piano-roll 8-target allineato ±3 ms); verifica integrità FP16; check
  DNA-Trace lineage.
- *DoD:* **Ocular Proof** — checklist L2 firmata nel `REGISTRO_AVANZAMENTO.md`.
- ⛔ F0-T2. **Sblocca lo spend RENDER (F1 + F2-T1).**

**F0-T4 · TCN mini-prototipo → Gate L3 · `[C]` `P1`**
- *Obiettivo:* provare che la TCN Strided-Context apprende.
- *Azioni:* implementare la TCN (topologia MASTER_CHECKLIST §1); training su mini-batch
  Mac M5/MPS, mixed-precision; misurare le metriche di onset.
- *DoD:* metriche di onset **significativamente non casuali** su mini-holdout (Ocular
  Proof — log delle metriche).
- ⛔ F0-T3. **Sblocca lo spend TRAINING (F2-T3).**

**F0-T5 · `dvc init` · `[F]` `P2`**
- *Azioni:* `dvc init` nel repo; struttura Bronze/Silver/Gold (senza remote).
- *DoD:* `dvc status` pulito, committato.

**F0-T6 · `audit_dsp_rigor.py` · `[C]` `P2`**
- *Azioni:* implementare lo script che fa grep dei pattern proibiti nel thread audio
  (`new`, `malloc`, resizing `std::vector`, manipolazione stringhe) — gate manuale.
- *DoD:* lo script gira ed emette un report.

**F0-T7 · Track parallelo opzionale (non bloccante) · `[F]` `P3`**
- Classi JUCE custom (Edgewise Meter, Nixie Display, Bakelite Knobs PBR) + mapping
  parametri DSP (Sensitivity, Discrim, Dynamics) ai controlli Master.

> **Gate d'uscita F0:** L2 superato (~05-28) **e** L3 superato (~06-02).

### Fase F1 — Provisioning Azure · gate d'ingresso: L2 superato

**F1-T1 · Setup Azure · `[A]` `P1`**
- *Azioni:* Resource Group; Blob Container (LRS); SAS token scoped; Soft Delete + WORM
  su tier Bronze; alert di spesa a $100 e $160.
- *DoD:* portale Azure mostra risorse attive + alert configurati.
- ⛔ F0-T3.

**F1-T2 · dvc remote Azure · `[A]` `P1`**
- *Azioni:* configurare il remote `dvc` sul Blob Container.
- *DoD:* `dvc push` di prova riuscito (log).
- ⛔ F1-T1.

### Fase F2 — Burn Compute · gate d'ingresso: F1 completa

**F2-T1 · Render Gold 1.5 TB · `[G]` `P1` — spend BASSO RISCHIO (gate L2)**
- *Azioni:* render del dataset Gold su Azure (Sfizz/DrumGizmo, multi-mic, multi-scenario);
  upload Blob; tracciamento DVC.
- *DoD:* 1.5 TB renderizzati e versionati; log di completamento.
- ⛔ F1-T1.

**F2-T2 · Augmentation + Demucs · `[G]` `P1`**
- *Azioni:* augmentation Python (convoluzione IR `pedalboard`, Machine-Gun Chaos,
  Studio Mutilation, Transient Saboteurs); Demucs AI-Isolation.
- *DoD:* dataset aumentato versionato.
- ⛔ F2-T1 (può procedere in streaming sul renderizzato).

**F2-T3 · Training "Gold" A100 → Gate L4 · `[G]` `P1` — spend A RISCHIO (gate L3)**
- *Azioni:* training "Gold" della TCN su A100 Spot; validazione Holdout reale
  (ENST-Drums) + Franken-Mix (MedleyDB) + Ocular Proof.
- *DoD:* il modello supera l'Holdout reale → **Gate L4** (sblocca i claim pubblici).
- ⛔ F2-T1 **e** F0-T4 (L3).

**F2-T4 · Credit-soak · `[G]` `P2`**
- *Azioni:* desplegare il credito residuo sulla scala §4 (Tier 2/3) secondo lo scenario
  fissato a CP-3.
- *DoD:* saldo credito → ~$0 consumato utilmente.

### Fasi F3–F5 — Coarse (da raffinare)

- **F3 · Consolidamento:** acquisto HDD fisico 2 TB (€120 — unico impegno irreversibile);
  push Gold tensor + recipes su HDD; teardown risorse Azure.
- **F4 · Sviluppo Plugin C++/JUCE:** core DSP + integrazione RTNeural; Chronos Engine
  (MIDI delay-line); UI JUCE (componenti custom, render V26); licensing Soft-DRM
  (`juce::RSAKey`, Poisoned DSP); PDC. *Sotto-fasi da dettagliare post-L4.*
- **F5 · Release v1.0 EA:** QA conforme agli standard interni; build VST3 + AU;
  pubblicazione Early-Access $99.

## 7. Tracking Board

| ID | Task | Fase | Stato | ⛔ Bloccato da | Gate |
| :-- | :-- | :-- | :-- | :-- | :-- |
| F0-T1 | Compliance licenze | F0 | ☐ | — | — |
| F0-T2 | batch_generator + recipes | F0 | ☐ | — | — |
| F0-T3 | Validazione Gate L2 | F0 | ☐ | F0-T2 | **L2** |
| F0-T4 | TCN mini-prototipo | F0 | ☐ | F0-T3 | **L3** |
| F0-T5 | dvc init | F0 | ☐ | — | — |
| F0-T6 | audit_dsp_rigor.py | F0 | ☐ | — | — |
| F0-T7 | Classi JUCE (opz.) | F0 | ☐ | — | — |
| F1-T1 | Setup Azure | F1 | ⊘ | F0-T3 | — |
| F1-T2 | dvc remote Azure | F1 | ⊘ | F1-T1 | — |
| F2-T1 | Render Gold 1.5 TB | F2 | ⊘ | F1-T1 | — |
| F2-T2 | Augmentation + Demucs | F2 | ⊘ | F2-T1 | — |
| F2-T3 | Training A100 → L4 | F2 | ⊘ | F2-T1, F0-T4 | **L4** |
| F2-T4 | Credit-soak | F2 | ⊘ | CP-3 | — |
| F3 | Consolidamento HDD | F3 | ⏸ | F2 | — |
| F4 | Sviluppo Plugin | F4 | ⏸ | L4 | — |
| F5 | Release v1.0 EA | F5 | ⏸ | F4 | — |

**Stato globale:** Fase attiva **F0** · Scenario credito: *da fissare a CP-1* ·
Prossimo checkpoint: **CP-1 / 2026-05-30**.

---
*Decision Lock 2026-05-20. Aggiornare il Tracking Board (§7) e lo scenario credito (§4)
a ogni sessione e a ogni checkpoint. Verifica di avanzamento solo via Ocular Proof.*
