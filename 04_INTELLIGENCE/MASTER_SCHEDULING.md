---
id: LIN-DT-MSCHED-001
title: Master Scheduling — OP-NEUROTRIGGER
type: scheduling
status: ACTIVE
phase: cross-cutting
domain: Operations / Project Execution
version: 1.0.0
updated: 2026-05-20
tags: [scheduling, execution, governance, tracking]
related: [LIN-DT-SCHED-001, LIN-DT-CHKLST-001, LIN-DT-DOCSTD-001]
supersedes: []
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

<a id="checkpoints"></a>
## 3. Checkpoint del Credito — Bivi Decisionali

A ogni checkpoint si valuta lo **scenario** e si ri-decide il deployment del credito
residuo. Un checkpoint è un bivio, non un report.

| CP | Giorno | Data | Cosa si valuta | Decisione |
| :-- | :-- | :-- | :-- | :-- |
| **CP-1** | D10 | 2026-05-30 | L2 superato? batch_generator solido? | Confermare avvio Track Cloud. Se L2 non passato → escalation su F0-T2. |
| **CP-2** | D20 | 2026-06-09 | % render completata · stato L3 · $ spesi | Se L3 ok → autorizzare training. Altrimenti → render + Tier 2. Fissare scenario. |
| **CP-3** | D25 | 2026-06-14 | $ residui · training in corso? | Credit-soak finale: desplegare ogni dollaro residuo sulla scala §4. |

<a id="credit-scale"></a>
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

<a id="tasks"></a>
## 6. Task Detate — Esecuzione Precisa

### Fase F0 — Fondazione Locale · gate d'ingresso: post-L1 (corrente)

**F0-T1 · Compliance licenze · `[D]` `P1`**
- *Obiettivo:* conferma scritta del diritto d'uso per ENST-Drums, MedleyDB, SM Drums.
- *Azioni:* identificare la licenza di ciascun asset; confermare per ENST-Drums e
  MedleyDB lo status **Evaluation-Only** (mai training, mai redistribuzione — coerente
  con `DATA_PROVENANCE_LOG.md` §2.B); per SM Drums verificare la licenza commerciale di
  redistribuzione dell'**output renderizzato**; inviare le richieste/email dove serve.
- *DoD:* conferma scritta archiviata in `DATA_PROVENANCE_LOG.md`.
- *Fallback (criterio di decadenza):*
  - **SM Drums** (Classe A, serve al render): se nessuna conferma scritta entro
    **CP-1 / 2026-05-30**, escluderlo dalle recipe e renderizzare solo con asset
    CC-BY/CC0 (DrumGizmo, Salamander).
  - **ENST-Drums / MedleyDB** (Classe B, servono al validation L4): se i termini non
    consentono la valutazione interna a supporto di un prodotto commerciale entro
    **CP-2 / 2026-06-09**, attivare il piano B di `DATA_PROVENANCE_LOG.md` §2.B
    (registrazioni proprietarie annotate) o ridurre il Validation Protocol a
    Franken-Mix + Ocular Proof. Decisione registrata al checkpoint.
- *Avvio immediato, in parallelo* — lead time esterno.
- ✅ **AGGIORNAMENTO (2026-05-20) — dottrina "Self-Evident Commercial License":** per
  Decision Lock del CEO si usano solo asset la cui licenza pubblicata concede di per sé
  l'uso commerciale (CC0/CC-BY). **Outreach annullato** — niente email, niente
  divulgazione del progetto. Conseguenze per pura lettura della licenza: **ENST-Drums**
  (research-only) e **MedleyDB** (CC-BY-NC) → **ESCLUSI**; **SM Drums** → escluso (nessuna
  licenza formale). La diversità di kit è ricostruita da **F0-T1b**. Lo **Holdout reale**
  va ridisegnato (task a sé). Dettaglio: `docs/compliance/DATA_PROVENANCE_LOG.md` §1.1.

**F0-T1b · Survey & selezione kit — roster di training · `[D]` `P1`**
- *Origine:* osservazione del CEO (2026-05-20) — SM Drums è un solo kit; serve diversità
  timbrica per chiudere il generalization gap (train su pochi timbri → la rete impara il
  timbro, non l'evento fisico).
- *Dottrina:* "Self-Evident Commercial License" (vedi F0-T1 aggiornamento).
- *Azioni:* survey dei kit liberi; matrice licenze verificate alla fonte; proporre un
  roster-target. Esito in `docs/compliance/F0-T1b_KIT_ROSTER_SURVEY.md`.
- *DoD:* roster approvato dal CEO; `DATA_PROVENANCE_LOG.md` §2.A aggiornato.
- ☑ **FATTO (2026-05-20):** roster di 11 voci CC0/CC-BY approvato dal CEO e inserito in
  `DATA_PROVENANCE_LOG.md` §2.A. Esito in `docs/compliance/F0-T1b_KIT_ROSTER_SURVEY.md`.

**F0-T1c · Ridisegno Validation Protocol / Holdout reale · `[C]` `P1`**
- *Origine:* l'esclusione di ENST-Drums e MedleyDB (dottrina §1.1) ha rimosso lo Holdout
  reale e il Franken-Mix ([`DOSSIER_TECNICO` §10.3](../docs/methodology/DOSSIER_TECNICO.md#holdout), [`MASTER_CHECKLIST` §1](../MASTER_CHECKLIST.md#ai-neural)).
- *Azioni:* survey di fonti di registrazioni reali di batteria con ground-truth a licenza
  commerciale chiara (CC0/CC-BY); ridisegnare il Validation Protocol; se nessuna fonte
  idonea → Piano B (registrazioni proprietarie annotate). Decisione critica — tocca il
  Gate L4 e i claim pubblici di accuratezza.
- *DoD:* Validation Protocol ridisegnato e approvato dal CEO; [`DOSSIER_TECNICO` §10](../docs/methodology/DOSSIER_TECNICO.md#validation) e
  [`MASTER_CHECKLIST` §1](../MASTER_CHECKLIST.md#ai-neural) aggiornati.
- ☑ **FATTO (2026-05-20):** Decision Lock CEO. Holdout reale = E-GMD (CC-BY 4.0),
  Stealth-Mix = Slakh2100, Ocular Proof invariato. Piano B (registrazioni proprietarie)
  scartato dal CEO. Esito in `docs/compliance/F0-T1c_HOLDOUT_SURVEY.md`.

**F0-T2 · Pipeline di rendering Gold — *riscrittura* · `[F]` `P1`**
> ⚠️ **Non è una verifica.** Gli script in `src/data_engineering/`
> (`midi_renderer.py`, `batch_generator.py`) sono prototipi **FluidSynth/SF2** — motore
> **scartato** dal Design Lock ([`MASTER_CHECKLIST` §2](../MASTER_CHECKLIST.md#data-infra), [`DOSSIER_TECNICO` §3.2](../docs/methodology/DOSSIER_TECNICO.md#aug-l1)). Vanno
> riscritti, non riusati. Spacchettato in 5 sotto-task; T2a passa per **STRP-001**
> (6 fasi + Executive Briefing) prima di scrivere codice.
- *Obiettivo macro:* pipeline locale che produce un mini-batch Gold corretto end-to-end.

**F0-T2a · Recipe + contratto dati — spec di dettaglio · `[F]` `P1`**
- *Obiettivo:* bloccare recipe e contratto dati nel dettaglio implementativo.
- *Direzione già bloccata* (Executive Briefing STRP-001, 2026-05-20 — D1/D2/D2-bis):
  dataset **WebDataset** tar-shard ~1 GB (terna `audio.f16` / `target.f16` / `dna.json`
  per campione); target `[frame, 8, 3]` (onset/vel/microtiming) + testa HH continua;
  **MIDI Mapping Table** `GM↔8-bus` bidirezionale + toggle d'uscita HH (CC continuo /
  Note discrete).
- *Azioni:* dettagliare (i) schema recipe SFZ multi-layer + kit multi-mic DrumGizmo
  ([`DOSSIER_TECNICO` §3.2](../docs/methodology/DOSSIER_TECNICO.md#aug-l1)); (ii) layout esatto del Gold tensor FP16 e dello shard
  WebDataset ([`DOSSIER_TECNICO` §9.2](../docs/methodology/DOSSIER_TECNICO.md#medallion)); (iii) formato DNA-Trace ([`DOSSIER_TECNICO` §3.5](../docs/methodology/DOSSIER_TECNICO.md#dna-trace));
  (iv) la MIDI Mapping Table come artefatto versionato; survey delle articolazioni HH
  delle librerie.
- *DoD:* spec archiviata; MIDI Mapping Table committata; checklist aggiornata.
- ✅ **FATTO (2026-05-20)** — Decision Lock approvato. Spec in
  `docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`; Mapping Table versionata in
  `docs/specs/midi_mapping_table.yaml`. Sblocca F0-T2b/c/d.
- → F0-T2b, F0-T2c, F0-T2d.

**F0-T2b · Render engine Sfizz · `[F]` `P1`**
- *Azioni:* riscrivere `MidiRenderer` per pilotare **Sfizz** via CLI (librerie SFZ
  multi-layer) al posto di FluidSynth.
- *DoD:* render di prova SFZ multi-layer corretto (log).
- ⛔ F0-T2a, F0-T9b *(harness test-first — Testing Doctrine)*.

**F0-T2c · Integrazione DrumGizmo · `[F]` `P1`**
- *Azioni:* integrare **DrumGizmo** via CLI; kit multi-microfono per il bleed reale.
- *DoD:* render multi-mic con bleed presente e verificabile (log).
- ⛔ F0-T2a, F0-T9b *(harness test-first — Testing Doctrine)*.

**F0-T2d · Writer Gold-tensor + DNA-Trace · `[F]` `P1`**
- *Azioni:* implementare il writer del Gold tensor (FP16 multi-mic + matrice 8-target)
  e il generatore DNA-Trace, secondo la spec bloccata in F0-T2a.
- *DoD:* un tensore Gold scritto su disco; integrità FP16 e DNA-Trace verificate.
- ⛔ F0-T2a, F0-T9b *(harness test-first — Testing Doctrine)*.

**F0-T2e · Mini-batch end-to-end · `[F]` `P1`**
- *Azioni:* orchestrare la pipeline (recipe → Sfizz/DrumGizmo → writer Gold tensor) e
  generare un mini-batch (~10–20 scenari).
- *DoD:* log stdout che mostra N campioni Gold generati senza errori.
- ⛔ F0-T2b, F0-T2c, F0-T2d. → F0-T3.

**F0-T3 · Gate L2 (validazione recipe) · `[C]` `P1`**
- *Obiettivo:* validare che il mini-dataset è corretto.
- *Azioni:* ispezione manuale di ≥2 campioni (waveform multi-mic coerente, bleed
  presente, piano-roll 8-target allineato ±3 ms — schema [`DOSSIER_TECNICO` §4](../docs/methodology/DOSSIER_TECNICO.md#midi-matrix));
  verifica integrità FP16; check DNA-Trace lineage ([`DOSSIER_TECNICO` §3.5](../docs/methodology/DOSSIER_TECNICO.md#dna-trace)).
- *DoD:* **Ocular Proof** — checklist L2 firmata nel `REGISTRO_AVANZAMENTO.md`.
- ⛔ F0-T2e. **Sblocca lo spend RENDER (F1 + F2-T1).**

**F0-T4 · TCN mini-prototipo → Gate L3 · `[C]` `P1`**
> ⚠️ La "topologia [`MASTER_CHECKLIST` §1](../MASTER_CHECKLIST.md#ai-neural)" è un Design Lock concettuale (Strided-Context
> TCN, Comb-Filter Hack, look-ahead ~100ms), **non** una spec implementabile: mancano
> numero di layer, kernel, dilatazioni e receptive field. Spacchettato in 2 sotto-task;
> T4a passa per **STRP-001** (6 fasi + Executive Briefing) prima di scrivere codice.
> **Gate L3 ridefinito** (Executive Briefing STRP-001, D4): L3 certifica non solo che
> la rete *apprende*, ma anche che la topologia *si esporta* in RTNeural — il rischio
> architetturale più grave de-rischiato a F0, prima del burn del credito.

**F0-T4a · Topologia TCN concreta — Decision Lock (STRP-001) · `[C]` `P1`**
- *Obiettivo:* tradurre il Design Lock concettuale in una spec di rete implementabile.
- *Azioni:* applicare STRP-001; fissare numero di layer, kernel size, dilatazioni,
  receptive field (coerente col look-ahead ~100ms), shape del tensore di input e teste
  di output — matrice 8-target + testa di regressione apertura Hi-Hat
  ([`DOSSIER_TECNICO` §2.2](../docs/methodology/DOSSIER_TECNICO.md#midi-output), [§4](../docs/methodology/DOSSIER_TECNICO.md#midi-matrix)) — e la loss (Asymmetric Focal + Gaussian smearing,
  [`MASTER_CHECKLIST` §1](../MASTER_CHECKLIST.md#ai-neural), [`DOSSIER_TECNICO` §6.2](../docs/methodology/DOSSIER_TECNICO.md#loss)). Fissare la **soglia numerica** che
  qualifica le metriche di onset come "significativamente non casuali".
- *DoD:* Executive Briefing approvato dal CEO; spec e soglia archiviate.
- ☑ **FATTO (2026-05-20):** Decision Lock CEO (Executive Briefing F0-T4a, STRP-001).
  `R_target` ratificato a `44100/128 ≈ 344.53 Hz`; topologia 4-stadi (Input-Agnostic
  Projection → Strided Encoder Stem → Dilated Causal TCN Trunk → 4 teste); look-ahead
  ~100 ms come ritardo d'ingresso = PDC; abbandonato il Sentinella/Scalpello + NN-Repeat
  (incoerenza RTNeural sanata); soglia L3 fissata. Spec in
  `docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md`. Sblocca F0-T4b (con F0-T3).
- → F0-T4b.

**F0-T4b · Mini-prototipo + round-trip RTNeural · `[C]` `P1`**
- *Obiettivo:* provare che la TCN apprende **e** che è esportabile nel motore di
  inferenza del plugin.
- *Azioni:* implementare la TCN secondo la spec di F0-T4a; training sul mini-batch Gold
  (F0-T2e) su Mac M5/MPS, mixed-precision; misurare le metriche di onset; esportare i
  pesi in **RTNeural JSON**, caricarli in uno smoke-test **C++ RTNeural** e verificare
  il **match numerico** con l'output PyTorch entro tolleranza.
- *DoD (Gate L3 ridefinito):* (a) metriche di onset oltre la soglia di F0-T4a su
  mini-holdout; (b) round-trip RTNeural verificato. Ocular Proof — log.
- ⛔ F0-T3, F0-T4a. **Sblocca lo spend TRAINING (F2-T3).**

**F0-T5 · DVC + struttura Medallion · `[F]` `P2`**
- *Azioni:* `dvc init` nel repo; definire la struttura **Medallion** Bronze/Silver/Gold
  ([`DOSSIER_TECNICO` §9.2](../docs/methodology/DOSSIER_TECNICO.md#medallion)) e la strategia di **sharding WebDataset** del layer Gold
  (shard ~1 GB tracciati da DVC, non micro-file); senza remote.
- *DoD:* `dvc status` pulito, struttura committata.

**F0-T6 · `audit_dsp_rigor.py` (predisposizione) · `[C]` `P2`**
- *Nota di fase:* in F0 non esiste codice C++ (parte in F4). Qui si **predispone** solo
  lo strumento; il **gate operativo** si applica in F4 su ogni commit del core DSP.
- *Azioni:* implementare lo script che fa grep dei pattern proibiti nel thread audio
  (`new`, `malloc`, resizing `std::vector`, manipolazione stringhe) — gate manuale.
- *DoD:* lo script gira su un file di prova ed emette un report.

**F0-T7 · Track parallelo opzionale (non bloccante) · `[F]` `P3`**
- Classi JUCE custom (Edgewise Meter, Nixie Display, Bakelite Knobs PBR) + mapping
  parametri DSP (Sensitivity, Discrim, Dynamics) ai controlli Master.

**F0-T8 · Model Artifact — spec di export & trasporto · `[C]` `P3`**
- *Direzione bloccata* (Executive Briefing STRP-001, D3): pesi come **blob binario
  cifrato** embedded via JUCE `BinaryData`; header metadati `{model_id, version,
  latency_samples, n_channel, sr}` per il badge PDC; exporter PyTorch→RTNeural JSON.
- *Azioni:* dettagliare la spec dell'exporter (riuso del round-trip di F0-T4b) e dello
  schema di cifratura/header. Implementazione in **F4**.
- *DoD:* spec archiviata. Decisione di design, eseguibile in parallelo.

**F0-T9a · Testing & QA Doctrine (STRP-001) · `[C]` `P1`**
- *Origine:* osservazione del CEO (2026-05-20) — il progetto non aveva alcuna strategia
  di test oltre `audit_dsp_rigor.py` (gate statico) e l'Ocular Proof. Buco grave: il
  codice è delegato a sub-agenti e il render Azure è spesa irreversibile.
- *Azioni:* applicare STRP-001; fissare la dottrina di test trasversale — tassonomia a
  4 layer, mutation testing come gate anti-pigrizia, protocollo AI-Adversarial QA.
- *DoD:* Executive Briefing approvato dal CEO; dottrina archiviata.
- ☑ **FATTO (2026-05-20):** Decision Lock CEO. Dottrina in `04_INTELLIGENCE/TESTING_DOCTRINE.md`;
  pattern AI-Adversarial QA in [`SUB_AGENT_GOVERNANCE.md` §6](SUB_AGENT_GOVERNANCE.md#ai-adversarial-qa). Mutation kill-rate gate
  (critici ≥ 90 %, core ≥ 85 %); `pluginval` ≥ 8 per il C++ (coarse, dettaglio F4).
- → F0-T9b.

**F0-T9b · F0 Pipeline Test Harness · `[F]` `P1`**
- *Azioni:* scaffolding `pytest`/`Hypothesis`/`mutmut`/`coverage`/`Atheris`; scrivere i
  test-oracolo derivati dal contratto F0-T2a (writer Gold-tensor, DNA-Trace, parser
  recipe, standardizzazione mic) **prima** del codice di pipeline. Dettaglio in
  [`TESTING_DOCTRINE.md` §6](TESTING_DOCTRINE.md#f0-test-plan).
- *DoD:* harness eseguibile; test-oracolo del contratto F0-T2a verdi sullo scheletro;
  gate mutation configurato. Ocular Proof — log.
- ⛔ F0-T9a. **Gate di F0-T2b/c/d** (test-first).

**F0-T10 · Documentation Linking Layer (STRP-001) · `[C]`/`[F]` `P2`**
- *Origine:* osservazione del CEO (2026-05-20) — i riferimenti tra documenti erano in
  prosa e per numero di sezione, fragili: è la radice delle ~30 incoerenze dell'audit.
- *Azioni:* STRP-001; definire l'OP-NEUROTRIGGER Doc Standard (frontmatter YAML + ancore
  HTML stabili + link relativi + INDEX generato + validatore `lychee`); rollout incrementale.
- *DoD:* standard archiviato; INDEX generato; `lychee` in gate; hot-set conforme.
- ☑ **FATTO (2026-05-20):** Decision Lock CEO. Standard `DOC_LINKING_STANDARD.md` (v1.1.0);
  `gen_docs_index.py` esteso ai doc root; `lychee.toml` corretto; frontmatter su **33
  documenti** (copertura 100 %, 0 backlog); ancore stabili + cross-ref prosa→link sul
  hot-set; 3 doc-fossili (`PROJECT_ROADMAP`, `SPRINT_BOARD`, `PROJECT_MASTER_INDEX`)
  archiviati a puntatori; gate `lychee` **blocking** via pre-commit hook (`tools/pre-commit`,
  installabile con `tools/install-hooks.sh`). `lychee --offline`: 109 OK, 0 errori.

**F0-T11 · Content-rot audit — allineamento al roster F0-T1b · `[F]` `P2`**
- *Origine:* il "controllone" di F0-T10 ha isolato rot di *contenuto* (non di linking):
  **SM Drums** — kit escluso dal Decision Lock F0-T1b — era ancora citato come asset
  *attivo* in spec tecniche, in contraddizione con il roster approvato.
- *Azioni:* grep trasversale di tutte le menzioni di SM Drums; distinguere i record
  storici/compliance legittimi (da NON toccare) dalle citazioni stale come asset attivo;
  riallineare queste ultime al roster F0-T1b (DrumGizmo / Karoryfer / Salamander).
- *DoD:* zero menzioni di SM Drums come asset attivo; record storici intatti.
- ☑ **FATTO (2026-05-20):** 6 siti corretti — `DOSSIER_TECNICO` §3.2/§8/§9.2 e
  `F0-T2a` §2.1/§2.3/§5 (survey HH). I record storici (F0-T1/T1b, `DATA_PROVENANCE_LOG`,
  `AUDIT_RESOLUTION_LOG`, diario, doc-fossili) lasciati intatti — documentano
  correttamente l'esclusione.

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
  (E-GMD) + Slakh-Mix (Slakh2100) + Ocular Proof.
- *DoD:* il modello supera l'Holdout reale → **Gate L4** (sblocca i claim pubblici).
- ⛔ F2-T1 **e** F0-T4b (L3).

**F2-T4 · Credit-soak · `[G]` `P2`**
- *Azioni:* desplegare il credito residuo sulla scala §4 (Tier 2/3) secondo lo scenario
  fissato a CP-3.
- *DoD:* saldo credito → ~$0 consumato utilmente.

### Fasi F3–F5 — Coarse (da raffinare)

- **F3 · Consolidamento:** acquisto HDD fisico 2 TB (€120 — unico impegno irreversibile);
  push Gold tensor + recipes su HDD; teardown risorse Azure.
- **F4 · Sviluppo Plugin C++/JUCE:** core DSP + integrazione RTNeural; Chronos Engine
  (MIDI delay-line); UI JUCE (componenti custom, render V26); licensing Soft-DRM
  (`juce::RSAKey`, Poisoned DSP); PDC. Implementazione del **Model Artifact** (spec
  F0-T8): exporter PyTorch→RTNeural, blob pesi cifrato, header metadati.
  `audit_dsp_rigor.py` (predisposto in F0-T6) applicato come gate Zero-Allocation su
  ogni commit del core DSP. *Sotto-fasi da dettagliare post-L4.*
- **F5 · Release v1.0 EA:** QA conforme agli standard interni; build VST3 + AU;
  pubblicazione Early-Access $99.

<a id="tracking-board"></a>
## 7. Tracking Board

| ID | Task | Fase | Stato | ⛔ Bloccato da | Gate |
| :-- | :-- | :-- | :-- | :-- | :-- |
| F0-T1 | Compliance licenze | F0 | ☑ | — | — |
| F0-T1b | Survey & selezione kit (roster) | F0 | ☑ | — | — |
| F0-T1c | Ridisegno Validation Protocol/Holdout | F0 | ☑ | — | — |
| F0-T2a | Recipe + contratto dati (STRP-001) | F0 | ☑ | — | — |
| F0-T2b | Render engine Sfizz | F0 | ☐ | F0-T2a, F0-T9b | — |
| F0-T2c | Integrazione DrumGizmo | F0 | ☐ | F0-T2a, F0-T9b | — |
| F0-T2d | Writer Gold-tensor + DNA-Trace | F0 | ☐ | F0-T2a, F0-T9b | — |
| F0-T2e | Mini-batch end-to-end | F0 | ☐ | F0-T2b, F0-T2c, F0-T2d | — |
| F0-T3 | Validazione Gate L2 | F0 | ☐ | F0-T2e | **L2** |
| F0-T4a | Topologia TCN concreta (STRP-001) | F0 | ☑ | — | — |
| F0-T4b | TCN mini-prototipo + round-trip RTNeural | F0 | ☐ | F0-T3, F0-T4a | **L3** |
| F0-T5 | DVC + struttura Medallion | F0 | ☐ | — | — |
| F0-T6 | audit_dsp_rigor.py (predisp.) | F0 | ☐ | — | — |
| F0-T7 | Classi JUCE (opz.) | F0 | ☐ | — | — |
| F0-T8 | Model Artifact — spec export | F0 | ☐ | — | — |
| F0-T9a | Testing & QA Doctrine (STRP-001) | F0 | ☑ | — | — |
| F0-T9b | F0 Pipeline Test Harness | F0 | ☐ | F0-T9a | — |
| F0-T10 | Documentation Linking Layer (STRP-001) | F0 | ☑ | — | — |
| F0-T11 | Content-rot audit (roster F0-T1b) | F0 | ☑ | — | — |
| F1-T1 | Setup Azure | F1 | ⊘ | F0-T3 | — |
| F1-T2 | dvc remote Azure | F1 | ⊘ | F1-T1 | — |
| F2-T1 | Render Gold 1.5 TB | F2 | ⊘ | F1-T1 | — |
| F2-T2 | Augmentation + Demucs | F2 | ⊘ | F2-T1 | — |
| F2-T3 | Training A100 → L4 | F2 | ⊘ | F2-T1, F0-T4b | **L4** |
| F2-T4 | Credit-soak | F2 | ⊘ | CP-3 | — |
| F3 | Consolidamento HDD | F3 | ⏸ | F2 | — |
| F4 | Sviluppo Plugin | F4 | ⏸ | L4 | — |
| F5 | Release v1.0 EA | F5 | ⏸ | F4 | — |

**Stato globale:** Fase attiva **F0** · ☑ F0-T1 · ☑ F0-T1b · ☑ F0-T1c · ☑ F0-T2a · ☑ F0-T4a
· ☑ F0-T9a · ☑ F0-T10 (Doc Linking Layer — standard + INDEX + gate lychee blocking, chiuso)
· ☑ F0-T11 (content-rot audit — SM Drums riallineato al roster F0-T1b)
(Decision Lock 2026-05-20) · Sbloccati: **F0-T9b** (harness test-first, via sub-agente —
ora gate di F0-T2b/c/d) e **F0-T4b** (mini-prototipo TCN, gated anche da F0-T3) ·
Scenario credito: *da fissare a CP-1* · Prossimo checkpoint: **CP-1 / 2026-05-30**.

---
*Decision Lock 2026-05-20. Aggiornare il Tracking Board (§7) e lo scenario credito (§4)
a ogni sessione e a ogni checkpoint. Verifica di avanzamento solo via Ocular Proof.*
