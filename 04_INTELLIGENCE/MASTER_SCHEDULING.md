---
id: LIN-DT-MSCHED-001
title: Master Scheduling — OP-NEUROTRIGGER
type: scheduling
status: ACTIVE
phase: cross-cutting
domain: Operations / Project Execution
version: 1.0.0
updated: 2026-05-22
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

**Mapping documentale.** Ogni task aperto espone il campo **`📚 Letture`** — i documenti
(con ancora stabile) da leggere *prima* di iniziarlo. Nessun agente esegue un task in
stato di ignoranza normativa; i link sono verificati in continuo dal gate `lychee`
([`DOC_LINKING_STANDARD`](DOC_LINKING_STANDARD.md)). Vincolante per ogni task nuovo.

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
| **F3** Consolidamento | post 06-19 | Asset core su SSD 1 TB CEO | nessuna fretta · €0 storage |
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
  dataset, che resta su Azure Blob fino al teardown F2 (poi: asset-only sull'SSD CEO).

## 5. Allocazione Budget Indicativa ($200)

| Voce | Stima | Note |
| :-- | :-- | :-- |
| Storage Blob LRS 1.5 TB (~1 mese) | ~$30 | |
| Render compute (CPU VM, Sfizz/DrumGizmo) | ~$55 | spend a basso rischio |
| Augmentation + Demucs (GPU) | ~$25 | |
| Training A100 Spot | ~$80 | spend a rischio (gate L3) |
| Buffer / egress | ~$10 | |

Soglie di monitoraggio (il CEO controlla il saldo): **$100** → valutazione · **$40** →
stop compute + `dvc fetch` selettivo degli asset sull'SSD CEO · **$10** → chiudi tutto.

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
- *📚 Letture:* [`F0-T2a §2 — render engine`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#render-engine) · [`midi_mapping_table.yaml`](../docs/specs/midi_mapping_table.yaml) · [`DOSSIER §3.2`](../docs/methodology/DOSSIER_TECNICO.md#aug-l1) · [`TESTING_DOCTRINE §6`](TESTING_DOCTRINE.md#f0-test-plan) · [`ENGINEERING_STANDARDS §6`](ENGINEERING_STANDARDS.md#execution-robustness).
- *Azioni:* riscrivere `MidiRenderer` per pilotare **Sfizz** via CLI (librerie SFZ
  multi-layer) al posto di FluidSynth.
- *DoD:* render di prova SFZ multi-layer corretto (log).
- ⛔ F0-T2a, F0-T9b *(harness test-first — Testing Doctrine)* — entrambi ☑, sbloccato.
- ☑ **FATTO (2026-05-22):** chiuso in tre passi. (1) **Parser recipe**
  (`src/data_engineering/gold/recipe.py`) — schema F0-T2a §1.1, strict fail-loud
  (`RecipeError`, mai stato parziale); 11 oracoli del contratto da `xfail` a verde;
  `PyYAML==6.0.3` aggiunto a `requirements.txt`. (2) **Provisioning** (2026-05-22):
  `sfizz_render` 1.2.3 (prebuilt ufficiale) + kit SFZ Karoryfer **Frankensnare** (CC0,
  roster F0-T1b) vendorizzati in `vendor/` (`ENGINEERING_STANDARDS §4`; manifest
  `vendor/README.md`, binari git-ignored). (3) **Adapter `SfizzRenderer`**
  (`src/data_engineering/gold/render.py`) sul CLI reale `sfizz_render` — fail-loud,
  watchdog di timeout esplicito + sanity-check anti «Silent Zero»
  (`ENGINEERING_STANDARDS §6`); `ruff` + `mypy --strict` puliti. **Oracoli §6.3** verdi:
  15 unit Layer-1 (binary-free, fake-binary per ogni failure mode) + 4 acceptance reali
  (`tests/acceptance/test_sfizz_render.py`: render deterministico, `sr=44100`, stereo
  stem, ampiezza in `[-1,1]`); i 2 scaffold `skip` Sfizz rimossi dal harness. Ocular
  Proof — render reale Frankensnare: `sr=44100 ch=2 frames=164864 peak=0.1071`,
  non-silent. Suite F0: **43 passed, 4 skipped, 39 xfailed, 0 failed**.

**F0-T2c · Integrazione DrumGizmo · `[F]` `P1`**
- *📚 Letture:* [`F0-T2a §2.4 — mic config`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#mic-config) · [`DOSSIER §3.2`](../docs/methodology/DOSSIER_TECNICO.md#aug-l1) · [`TESTING_DOCTRINE §6`](TESTING_DOCTRINE.md#f0-test-plan) · [`ENGINEERING_STANDARDS §6`](ENGINEERING_STANDARDS.md#execution-robustness).
- *Azioni:* integrare **DrumGizmo** via CLI; kit multi-microfono per il bleed reale.
- *DoD:* render multi-mic con bleed presente e verificabile (log).
- ⛔ F0-T2a, F0-T9b *(harness test-first — Testing Doctrine)* — entrambi ☑.
- ☑ **FATTO (2026-05-22):** chiuso in quattro passi. (1) **Provisioning** — DrumGizmo 0.9.20
  via apt nella VM OrbStack `ubuntu` (nessun prebuilt macOS → si gira su Linux, parità
  con Azure F2) + kit **DRSKit 2.1** (CC-BY-4.0, 13 mic, roster F0-T1b) vendorizzato in
  `vendor/drumgizmo/DRSKit/`; manifest `vendor/README.md`. (2) **Adapter
  `DrumGizmoRenderer`** in `render.py` sul CLI reale (`drumgizmo -i midifile -o wavfile`)
  — assembla i WAV per-canale `out{Canale}-{idx}.wav` in un WAV multi-mic unico;
  fail-loud + watchdog + sanity-check Silent Zero / NaN / canali ragged (`ENGINEERING_STANDARDS §6`);
  `ruff` + `mypy --strict` puliti. (3) **Standardizzazione 13→8** (Decision Lock CEO
  2026-05-22): `multitrack_full` riallineato allo **standard di settore** (Superior
  Drummer 3 / EZdrummer / Steven Slate / GetGood Drums) — scambio `snare_bot`→`hihat`,
  `F0-T2a §2.3` emendato (v1.1.0). L'adapter **seleziona** i 13 mic DRSKit sugli 8
  canonici (`DRSKIT_MULTITRACK8` — un microfono reale per slot, mai sommati); la modalità
  engine-faithful a 13 canali è conservata per una futura linea *NeuroTrigger Pro*.
  Risolve la tensione `n_mic > 8` vs contratto F0-T2a §3.2. (4) **Oracoli §6.3** verdi:
  20 unit Layer-1 (binary-free, fake-binary per ogni failure mode) + 4 acceptance reali
  (`tests/acceptance/test_drumgizmo_render.py`: `sr=44100`, render standardizzato a **8**
  canali, modalità faithful a 13, **bleed falsificabile**). **Rettifica TESTING_DOCTRINE
  §6.3** (Decision Lock CEO): la metrica di bleed passa da cross-correlazione grezza →
  **correlazione di inviluppo** (RMS a finestre, polarity-free) — il probe DRSKit ha
  dimostrato che la Pearson grezza dà falsi negativi (Snare↔OH −0.55 grezza vs **+0.93**
  inviluppo). Suite F0: **153 passed, 0 failed**; 4 acceptance DrumGizmo verdi dentro
  OrbStack. Ocular Proof — render reale DRSKit standardizzato: 8 WAV, 44100 Hz,
  non-silent, bleed snare→OH ≈ 0.93.

**F0-T2d · Writer Gold-tensor + DNA-Trace · `[F]` `P1`**
- *📚 Letture:* [`F0-T2a §3 — contratto dati`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract) · [`F0-T2a — DNA-Trace`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#dna-trace-format) · [`DOSSIER §9.2`](../docs/methodology/DOSSIER_TECNICO.md#medallion) · [`TESTING_DOCTRINE §6`](TESTING_DOCTRINE.md#f0-test-plan) · [`ENGINEERING_STANDARDS §1`](ENGINEERING_STANDARDS.md#determinism).
- *Azioni:* implementare il writer del Gold tensor (FP16 multi-mic + matrice 8-target)
  e il generatore DNA-Trace, secondo la spec bloccata in F0-T2a.
- *DoD:* un tensore Gold scritto su disco; integrità FP16 e DNA-Trace verificate.
- ⛔ F0-T2a, F0-T9b *(harness test-first — Testing Doctrine)* — entrambi ☑.
- ☑ **FATTO (2026-05-22):** `dna_trace.py` (codec barcode biiettivo + `build/validate
  dna.json`, integrità sha256/non-finite §3.7) e `gold_writer.py` (layout `flat-25`,
  scrittura `audio/target.f16` little-endian + `dna.json`, fail-loud su non-finite /
  silent-zero / larghezza errata) implementati sul contratto F0-T2a §3–§4; `ruff` +
  `mypy --strict` puliti. I 39 oracoli `xfail` del harness portati a verde, marker
  rimossi, meta-test auto-smontante aggiornato. **Suite F0: 130 passed, 0 failed.**
  **Gate mutation** (`mutmut`, TESTING_DOCTRINE §3) sbloccato: gira su Linux/OrbStack
  (`tools/run_mutation.sh` — `fork` di mutmut va in segfault su macOS con le librerie
  native); mutazione dei literal-stringa disattivata per policy (`TESTING_DOCTRINE §3.1`,
  Decision Lock CEO 2026-05-22). Esito: 680 mutanti, 0 segfault; moduli critici 533
  uccisi / 86 sopravvissuti, tutti **equivalenti** nelle classi A/B/C del registro §3.1
  → **kill-rate comportamentale 100 %** (gate ≥ 90 % superato).

**F0-T2e · Mini-batch end-to-end · `[F]` `P1`**
- *📚 Letture:* [`F0-T2a §3 — contratto dati`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract) · [`DOSSIER §9.2`](../docs/methodology/DOSSIER_TECNICO.md#medallion) · [`ENGINEERING_STANDARDS §6`](ENGINEERING_STANDARDS.md#execution-robustness).
- *Azioni:* orchestrare la pipeline (recipe → Sfizz/DrumGizmo → writer Gold tensor) e
  generare un mini-batch (~10–20 scenari).
- *DoD:* log stdout che mostra N campioni Gold generati senza errori.
- ⛔ F0-T2c, F0-T2b, F0-T2d — tutti ☑, **sbloccato**. → F0-T3.
- ☑ **FATTO (2026-05-22):** chiuso in tre passi. (1) **`target_builder.py`** — l'anello
  mancante: traduttore MIDI → matrice di trascrizione `flat-25` (onset Gaussian-smeared
  ±3 ms, velocity normalizzata, microtiming sub-frame, testa Hi-Hat continua step-held),
  mapping GM→8-bus dalla `midi_mapping_table.yaml` versionata; fail-loud su MIDI
  malformato / durata non valida / groove senza note mappate. Implementa il contratto
  F0-T2a §3.3 — già LOCKED, nessuna nuova decisione di design. (2) **`orchestrate.py`** —
  la cucitura della pipeline: `recipe → render (Sfizz/DrumGizmo) → audio.f16 + target.f16
  → dna.json → write_gold_sample`, con derivazione deterministica del barcode a 6
  segmenti e verifica `validate_dna_json` del campione scritto; fail-loud, nessun
  campione parziale. (3) **Mini-batch** — 12 grooves sintetici multi-bus (`mido`,
  deterministici — il GMD reale è Bronze, provisioning F1/F2) + 12 recipe in
  `recipes/mini_batch/`; `tools/gen_mini_batch_fixtures.py` (generatore) e
  `tools/run_mini_batch.py` (runner con log stdout). `ruff` + `mypy --strict` puliti.
  **Split di piattaforma** (come F0-T2b/c): `sfizz_render` è un build macOS, `drumgizmo`
  è nativo Linux → il runner gira in due passi nativi (`--engine`). **Ocular Proof:**
  6 Sfizz su macOS + 6 DrumGizmo in OrbStack = **12 campioni Gold, 0 errori**; campione
  DrumGizmo reale — audio `[8×445296]`, target `[3479×25]` multi-bus, testa HH 0→1,
  **bleed snare→OH 0.874**. **Oracoli §6.3** verdi: 37 test (18 unit target-builder +
  13 unit orchestrate + 6 acceptance smoke/conteggio). Suite F0: macOS **189 passed,
  7 skipped, 12 xfailed, 0 failed**; acceptance OrbStack **8 passed**. Sblocca **F0-T3
  (Gate L2)**.

**F0-T3 · Gate L2 (validazione recipe) · `[C]` `P1`**
- *📚 Letture:* [`F0-T2a §3 — contratto dati`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract) · [`DOSSIER §4 — matrice MIDI`](../docs/methodology/DOSSIER_TECNICO.md#midi-matrix) · [`MASTER_CHECKLIST §6 — Gate`](../MASTER_CHECKLIST.md#gates) · [`ENGINEERING_STANDARDS §6`](ENGINEERING_STANDARDS.md#execution-robustness).
- *Obiettivo:* validare che il mini-dataset è corretto.
- *Azioni:* ispezione manuale di ≥2 campioni (waveform multi-mic coerente, bleed
  presente, piano-roll 8-target allineato ±3 ms — schema [`DOSSIER_TECNICO` §4](../docs/methodology/DOSSIER_TECNICO.md#midi-matrix));
  verifica integrità FP16; check DNA-Trace lineage ([`DOSSIER_TECNICO` §3.5](../docs/methodology/DOSSIER_TECNICO.md#dna-trace)).
- *DoD:* **Ocular Proof** — checklist L2 firmata nel `REGISTRO_AVANZAMENTO.md`.
- ⛔ F0-T2e. **Sblocca lo spend RENDER (F1 + F2-T1).**
- ☑ **FATTO (2026-05-23):** Decision Lock CEO. Ocular Proof su 2 campioni
  rappresentativi del mini-batch F0-T2e (1 Sfizz `GMD001` + 1 DrumGizmo `GMD000`),
  pacchetto in `docs/gates/L2_OCULAR_PROOF/L2_INSPECTION_2026-05-23.md` —
  waveform multi-mic, target piano-roll con MIDI ground-truth, integrity FP16,
  DNA-Trace lineage, matrice di bleed envelope-RMS. **Verifiche tutte verdi:**
  allineamento target↔MIDI ±3 ms 65/65 onsets (drift max 2.90 ms); 0 NaN/inf,
  peak audio ∈ (0,1]; DNA-Trace shape & sha256 match; bleed DrumGizmo +0.99
  off-diag (F0-T2c falsificabile). Tooling: `tools/l2_ocular_proof.py`. Evidenza
  accessoria — calibrazione throughput `tools/calibrate_render.py`:
  Sfizz 0.03× / DrumGizmo 0.12× render-factor, ~5.6 MB/s single-thread →
  1.5 TB ≈ ~5 h @ 16 vCPU, ~$3.5 stimati (allocazione §5 = $55, headroom
  enorme per Tier 2/3). **Sblocca F1-T1 e F2-T1.**

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
- *📚 Letture:* [`F0-T4a — spec TCN + soglia L3`](../docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md#l3-threshold) · [`DOSSIER §6.1 — TCN`](../docs/methodology/DOSSIER_TECNICO.md#tcn) · [`DOSSIER §6.2 — loss`](../docs/methodology/DOSSIER_TECNICO.md#loss) · [`MASTER_CHECKLIST §6 — Gate`](../MASTER_CHECKLIST.md#gates) · [`ENGINEERING_STANDARDS §2 — bit-exactness`](ENGINEERING_STANDARDS.md#bit-exactness) · [`§5 — validazione statistica`](ENGINEERING_STANDARDS.md#statistical-validation).
- *Obiettivo:* provare che la TCN apprende **e** che è esportabile nel motore di
  inferenza del plugin.
- *Azioni:* implementare la TCN secondo la spec di F0-T4a; training sul mini-batch Gold
  (F0-T2e) su Mac M5/MPS, mixed-precision; misurare le metriche di onset; esportare i
  pesi in **RTNeural JSON**, caricarli in uno smoke-test **C++ RTNeural** e verificare
  il **match numerico** con l'output PyTorch entro tolleranza.
- *DoD (Gate L3 ridefinito):* (a) metriche di onset oltre la soglia di F0-T4a su
  mini-holdout; (b) round-trip RTNeural verificato. Ocular Proof — log.
- ⛔ F0-T3, F0-T4a. **Sblocca lo spend TRAINING (F2-T3).**
- ☑ **FATTO (2026-05-23) — Gate L3 SUPERATO (opzione A) — Decision Lock CEO.**
  **Round-trip RTNeural-equivalente PASS:** PyTorch ↔ NumPy `max|Δ|=1.49e-06`,
  PyTorch ↔ C++17 `max|Δ|=1.19e-07` ≈ epsilon fp32. Op-set verificato: Conv1D
  causale strided/dilated + ReLU/sigmoid/tanh + add elementwise; **opzione (a)
  di F0-T4a §8 ratificata** (residuo come arco esportato, add fuori dal grafo
  sequenziale RTNeural). Soglia F≥0.80 sull'holdout non raggiunta (F=0.18) ma
  *statisticamente irrilevante* su 10 grooves anche se superata — la barra
  metrica significativa si misura al **Gate L4** sull'Holdout reale E-GMD.
  Pacchetto APPROVED in `docs/gates/L3_OCULAR_PROOF/L3_INSPECTION_2026-05-23.md`.
  Tooling rieseguibile: `tools/run_round_trip.py` (orchestratore three-way) +
  `tools/l3_ocular_proof.py` (per-bus report). Topologia: 83 673 parametri,
  baseline `C=32`, training ~50 s su Mac M5 / MPS. **Sblocca F2-T3** (gated
  ora solo da F2-T1).

**F0-T5 · DVC + struttura Medallion + sharding WebDataset · `[F]` `P2`**
- *📚 Letture:* [`DOSSIER §9.2 — Medallion`](../docs/methodology/DOSSIER_TECNICO.md#medallion) · [`F0-T2a §3 — contratto dati`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract) · [`F0-T2a §3.8 — tail std`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#tail-standardization).
- *Azioni:* `dvc init` nel repo; definire la struttura **Medallion** Bronze/Silver/Gold
  ([`DOSSIER_TECNICO` §9.2](../docs/methodology/DOSSIER_TECNICO.md#medallion)) e la strategia di **sharding WebDataset** del layer Gold
  (shard ~1 GB tracciati da DVC, non micro-file); senza remote.
- *DoD:* `dvc status` pulito, struttura committata.
- ☑ **FATTO (2026-05-23):** chiuso in due passi. (1) `dvc init` ☑ in concomitanza con
  F1-T2 (era prerequisito tecnico per `dvc remote add`); scaffold `.dvc/` tracked in
  repo. (2) **Strategia di sharding** chiusa con Decision Lock CEO — spec in
  `docs/methodology/F0-T5_GOLD_SHARDING_SPEC.md`. Sintesi: pack-on-fill con pre-shuffle
  della recipe matrix, shard target **1 GB esatto** (`gold-{split}-{index:06d}.tar`),
  tar non compressi, DVC per directory (`data/gold/{train,val}`), `manifest.json` per
  split con `sha256`/seed/total bytes, atomicità via `.tmp` + rename, branch
  `*-augmented` parallelo per F2-T2. Calibrazione su mini-batch L2 reale:
  ~250 campioni/shard, ~1500 shard totali a 1.5 TB. Modulo `shard_writer.py` da
  implementare come **sotto-task di F2-T1 prep** (mai sul clock Azure). **Decision
  Lock parallelo** (osservazione CEO 2026-05-23 su rischio engine-shortcut via
  durata/tail): (A) **pairing forzato MIDI×Engine** in recipe matrix F2-T1 +
  (C) **tail standardization** `tail_s = 0.5 s` uniforme — amendment a F0-T2a §3.8
  (v1.2.0). Chiude il canale di shortcut durata↔engine alla radice.

**F0-T6 · `audit_dsp_rigor.py` (predisposizione) · `[C]` `P2`**
- *📚 Letture:* [`MASTER_CHECKLIST §3 — DSP`](../MASTER_CHECKLIST.md#dsp) · [`ENGINEERING_STANDARDS §3 — codifica`](ENGINEERING_STANDARDS.md#coding-standards) · [`TESTING_DOCTRINE §5 — test DSP`](TESTING_DOCTRINE.md#dsp-tests).
- *Nota di fase:* in F0 non esiste codice C++ (parte in F4). Qui si **predispone** solo
  lo strumento; il **gate operativo** si applica in F4 su ogni commit del core DSP.
- *Azioni:* implementare lo script che fa grep dei pattern proibiti nel thread audio
  (`new`, `malloc`, resizing `std::vector`, manipolazione stringhe) — gate manuale.
- *DoD:* lo script gira su un file di prova ed emette un report.

**F0-T7 · Track parallelo opzionale (non bloccante) · `[F]` `P3`**
- *📚 Letture:* [`LINEAR_DESIGN_GUIDE`](UX_UI/LINEAR_DESIGN_GUIDE.md) · [`UX_BLUEPRINT`](UX_UI/UX_BLUEPRINT_STRP-001.md) · [`ENGINEERING_STANDARDS §3 — codifica`](ENGINEERING_STANDARDS.md#coding-standards).
- Classi JUCE custom (Edgewise Meter, Nixie Display, Bakelite Knobs PBR) + mapping
  parametri DSP (Sensitivity, Discrim, Dynamics) ai controlli Master.

**F0-T8 · Model Artifact — spec di export & trasporto · `[C]` `P3`**
- *📚 Letture:* [`F0-T4a — spec TCN`](../docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md) · [`DOSSIER §11 — licensing`](../docs/methodology/DOSSIER_TECNICO.md#licensing) · [`ENGINEERING_STANDARDS §2 — bit-exactness`](ENGINEERING_STANDARDS.md#bit-exactness).
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
- *📚 Letture:* [`TESTING_DOCTRINE §6 — piano test F0`](TESTING_DOCTRINE.md#f0-test-plan) · [`F0-T2a §3 — contratto dati`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract) · [`ENGINEERING_STANDARDS §3 — codifica`](ENGINEERING_STANDARDS.md#coding-standards).
- *Azioni:* scaffolding `pytest`/`Hypothesis`/`mutmut`/`coverage`/`Atheris`; scrivere i
  test-oracolo derivati dal contratto F0-T2a (writer Gold-tensor, DNA-Trace, parser
  recipe, standardizzazione mic) **prima** del codice di pipeline. Dettaglio in
  [`TESTING_DOCTRINE.md` §6](TESTING_DOCTRINE.md#f0-test-plan).
- *DoD:* harness eseguibile; test-oracolo del contratto F0-T2a verdi sullo scheletro;
  gate mutation configurato. Ocular Proof — log.
- ⛔ F0-T9a. **Gate di F0-T2b/c/d** (test-first).
- ☑ **FATTO (2026-05-21):** harness `pytest`+`Hypothesis`+`mutmut`+`coverage` in
  `tests/` (config `pyproject.toml`/`setup.cfg`, toolchain pinnato in
  `requirements-dev.txt`). Pacchetto-scheletro `src/data_engineering/gold/` (interfacce
  pubbliche bloccate sul contratto F0-T2a; logica = stub `NotImplementedError`, di
  proprietà di F0-T2b/c/d). 50 test-oracolo del contratto (writer Gold-tensor, DNA-Trace,
  parser recipe, mic-std) scritti test-first; Layer 2 property (Hypothesis) + Layer 3
  fuzz; §6.3 acceptance come scaffold `skip`; harness Atheris standalone (dep opzionale).
  **Scaffold auto-smontante:** ogni oracolo è `xfail(strict, raises=NotImplementedError)`
  — verde-come-xfail ora, ma diventa `XPASS`→run rosso appena F0-T2x implementa il
  modulo, forzando la rimozione del marker (meccanismo verificato — Ocular Proof). Layer-0
  meta-test (15, verdi reali) blindano le costanti del contratto. `pytest`: **15 passed,
  6 skipped, 50 xfailed, 0 failed**. Gate mutation configurato (`setup.cfg`,
  `tools/run_mutation.sh`; kill-rate ≥ 90 % critici / ≥ 85 % core — operativo a F0-T2d).

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

**F0-T12 · Audit OpenPhase — internalizzazione standard ingegneristici · `[C]`/`[D]` `P2`**
- *Origine:* direttiva del CEO (2026-05-20) — dopo il decoupling da OP-X, l'archivio
  OpenPhase resta una fonte di conoscenza procedurale utile. Va auditato e le parti
  necessarie vanno **trasportate** nel progetto, senza ricollegarsi all'archivio.
- *Azioni:* audit dei documenti di stile + 7 famiglie OP-X (ASM/DCM/ERM/GVM/KRM/PIP/TOP);
  distinguere ciò che è universale e utile da ciò che è specifico di PySimpa o in
  conflitto con le scelte di NeuroTrigger (NeuroTrigger vincola); internalizzare le parti
  utili adattate al dominio; report di selezione.
- *DoD:* standard internalizzato e archiviato nel repo (zero dipendenze dall'archivio);
  report di cosa preso/scartato e perché.
- ☑ **FATTO (2026-05-20):** prodotto `04_INTELLIGENCE/ENGINEERING_STANDARDS.md`
  (LIN-DT-ENGSTD-001) — 5 aree internalizzate (determinismo & bit-exactness, codifica
  C++/Python, gestione dipendenze, validazione statistica del modello, robustezza
  d'esecuzione) + conventional commits. Scartati: harness OP-X, `PIPELINE_STATUS.json`,
  SHIELD, regole operative obsolete, standard PySimpa-specifici. Registro selezione nel
  §8 del documento.

**F0-T13 · De-referenziazione OP-X — chiusura del decoupling · `[F]` `P2`**
- *Origine:* l'audit F0-T12 ha rilevato che alcuni documenti vivi contenevano ancora
  riferimenti *dangling* a sigle OP-X (SOP-010, ERM-005/007, TOP-002, SOP-004/017) —
  residui non funzionali dopo il decoupling dall'archivio.
- *Azioni:* sostituire i riferimenti OP-X dangling nei documenti vivi con i puntatori
  interni equivalenti o rimuoverli; lasciare intatti i record storici (registri, diario,
  doc-fossili archiviati) che documentano correttamente lo stato passato.
- *DoD:* zero riferimenti OP-X dangling in documenti vivi; `CLAUDE.md`/`GEMINI.md` non
  impongono più il bootstrap sull'archivio.
- ☑ **FATTO (2026-05-20):** 9 file ripuliti — `CLAUDE.md` e `GEMINI.md` (rimosso il
  bootstrap mandatorio sull'archivio, sostituito con avvio interno: `docs/INDEX.md` +
  `MASTER_SCHEDULING` + `ENGINEERING_STANDARDS`); `SCHEDULING_DOCTRINE`,
  `TECHNICAL_COMPETITOR_AUDIT`, `UX_BLUEPRINT_STRP-001`, footer di
  `F0-T1`/`F0-T1b`/`F0-T1c`/`DATA_PROVENANCE_LOG`. `TASK_BLUEPRINT.md` (ARCHIVED) e i
  record storici lasciati intatti come fossili. Decoupling chiuso.

**F0-T14 · Mapping documentale dei task · `[F]` `P2`**
- *Origine:* domanda di controllo del CEO (2026-05-21) — un agente che prende in carico
  un task non aveva un riferimento strutturato ai documenti necessari per eseguirlo: i
  cross-link erano sparsi nella prosa, e i task di implementazione (F0-T2b…e) quasi nudi.
- *Azioni:* aggiungere a ogni task aperto il campo `📚 Letture` — lista ancorata dei
  documenti da leggere *prima* di iniziare; sfruttare il linking layer di F0-T10 (ancore
  stabili + link relativi + gate `lychee`); definire la regola nello schema §0.
- *DoD:* ogni task aperto di F0/F1/F2 espone il campo `Letture`; schema §0 aggiornato;
  `lychee` verde.
- ☑ **FATTO (2026-05-21):** 17 task aperti annotati (F0-T2b…T9b + F1 + F2); regola del
  campo `📚 Letture` documentata nello schema §0. È l'equivalente NeuroTrigger-nativo del
  mapping documentale OP-X (TOP-002), costruito sul linking layer del progetto invece che
  su una matrice separata soggetta a drift.

**F0-T15 · Audit augmentation & agnosticità d'ingresso (STRP-001) — `[D]` `P1`**
- *📚 Letture:* [`AUGMENTATION_AUDIT_BACKLOG`](../docs/methodology/AUGMENTATION_AUDIT_BACKLOG.md) · [`DOSSIER §3 — augmentation`](../docs/methodology/DOSSIER_TECNICO.md#aug-prerender) · [`DOSSIER §3.6 — gap`](../docs/methodology/DOSSIER_TECNICO.md#aug-gap) · [`DOSSIER §2.1 — input-agnostic`](../docs/methodology/DOSSIER_TECNICO.md#input-agnostic) · [`F0-T4a §4`](../docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md#input-agnostic-slots).
- *Origine:* due revisioni del CEO (2026-05-22), coniugate perché stessa famiglia di
  decisioni — la **varietà dei dati di training** a monte di F2. (1) La dottrina di
  augmentation del `DOSSIER §3` modella implicitamente **un solo input** (batteria
  tracciata e mixata in studio): assi scoperti — codec, noise floor / hum, cattura
  amatoriale, gating, limiting di master, lo-fi / wow & flutter, click come saboteur.
  (2) L'**agnosticità d'ingresso** è oggi solo *parziale* — agnostica al conteggio
  (1–8, zero-fill) ma **non all'assegnazione**: slot a semantica fissa, training solo
  sui conteggi {1,2,4,8} in ordine fisso. Tutto raccolto in `AUGMENTATION_AUDIT_BACKLOG.md`.
- *Decision Lock CEO 2026-05-23 — split obbligatorio pre-render / post-render.* L'audit
  originario lumpava MIDI Jittering (pre-render, §3.1) con Studio Mutilation + Inferno
  (post-render, §3.3–§3.4). Osservazione del CEO in sessione T1-prep-D: il MIDI Jittering
  per costruzione fisica **moltiplica la recipe matrix di F2-T1** (k varianti jitter ×
  MIDI × engine) — se F2-T1 parte senza, si ri-renderizza (doctrine §1.1, "use-it-or-
  lose-it" viola). Split in due sotto-task con gate distinti.

**F0-T15-pre · Audit MIDI augmentation (Time/Velocity/Component) — `[D]` `P1`**
- *📚 Letture:* [`DOSSIER §3.1 — MIDI Jittering`](../docs/methodology/DOSSIER_TECNICO.md#aug-prerender) · [`AUGMENTATION_AUDIT_BACKLOG`](../docs/methodology/AUGMENTATION_AUDIT_BACKLOG.md) · [`F0-T2a §3 — contratto dati`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract) · [`F0-T5 — sharding`](../docs/methodology/F0-T5_GOLD_SHARDING_SPEC.md).
- *Obiettivo:* arbitrare le voci di augmentation **pre-render** (Time Jittering, Velocity
  Jittering / Ghost Note Masking / Global Gain Shift, Component Dropping) e fissare:
  (i) range numerici per ogni voce; (ii) `k` jitter-variants per MIDI sorgente; (iii)
  seed policy + deterministic ordering; (iv) impatto sulla recipe matrix di T1-prep-A
  (pairing forzato MIDI × Engine × jitter-variant); (v) effetto su `manifest.json`
  (F0-T5 §5.5) e DNA-Trace lineage (F0-T2a §3.7).
- *Azioni:* applicare STRP-001 (6 fasi + Executive Briefing); produrre
  `docs/methodology/F0-T15-pre_MIDI_AUGMENTATION_SPEC.md`.
- *DoD:* Executive Briefing approvato (Decision Lock); spec archiviata; `DOSSIER §3.1`
  aggiornato con i parametri ratificati; recipe matrix di T1-prep-A riproiettata.
- *Costo Azure:* **$0** (gira sul Mac M5, MIDI è leggero).
- ⛔ — *nessuno*. **Sblocca F0-T16-pre, gate di F2-T1.**

**F0-T15-post · Audit audio augmentation (Studio Mutilation + Inferno + agnosticità) — `[D]` `P2`**
- *📚 Letture:* [`DOSSIER §3.2–§3.4 — augmentation audio`](../docs/methodology/DOSSIER_TECNICO.md#aug-l1) · [`DOSSIER §3.6 — gap`](../docs/methodology/DOSSIER_TECNICO.md#aug-gap) · [`AUGMENTATION_AUDIT_BACKLOG`](../docs/methodology/AUGMENTATION_AUDIT_BACKLOG.md) · [`DOSSIER §2.1 — input-agnostic`](../docs/methodology/DOSSIER_TECNICO.md#input-agnostic) · [`F0-T4a §4`](../docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md#input-agnostic-slots).
- *Obiettivo:* arbitrare le voci di augmentation **post-render** (Stem Isolate &
  Micro-Bleed, Studio Mutilation, Acoustic Environment, Transient Saboteurs) + le
  voci scoperte del backlog (codec, hum, gating, limiting, lo-fi, click bleed,
  randomizzazione mix-balance) + **agnosticità d'ingresso** (permutazione canali,
  conteggi variabili {1…8}).
- *Azioni:* applicare STRP-001; Executive Briefing al CEO; amendment a `F0-T4a §4`
  (semantica fissa per-slot → "porte" d'ingresso); `AUGMENTATION_AUDIT_BACKLOG.md`
  → `status: SUPERSEDED`.
- *DoD:* Executive Briefing approvato; `DOSSIER §3.2–§3.4` aggiornato.
- ⛔ — *nessuno*. **Sblocca F0-T16-post, gate di F2-T2.**

**F0-T17 · Statistical Test Plan — Data Audit + Evaluation Suite (STRP-001) · `[C]`/`[F]` `P1`**
- *📚 Letture:* [`ENGINEERING_STANDARDS §5 — validazione statistica`](ENGINEERING_STANDARDS.md#statistical-validation) · [`DOSSIER §10 — Validation Protocol`](../docs/methodology/DOSSIER_TECNICO.md#validation) · [`F0-T4a — soglia L3`](../docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md#l3-threshold) · [`F0-T2a §3.8 — tail std`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#tail-standardization).
- *Origine:* osservazione del CEO (2026-05-23, sessione T1-prep) — `ENGINEERING_STANDARDS §5`
  fissa i *principi* della validazione statistica ma non c'è una **spec operativa** dei
  test specifici da girare sul Gold prima del training A100 (~$80/run). Mancano: (a) data
  audit pre-training (class imbalance, distribuzione velocity/tempo/durata, articolazioni
  HH); (b) test inferenziali train↔val↔Holdout (Kolmogorov-Smirnov, chi-quadrato, OOD);
  (c) verifica numerica dei Decision Lock A+C anti-shortcut engine (durata-engine
  independence, MI(audio; engine) ≈ 0); (d) evaluation suite post-training (per-bus
  F-score, bootstrap CI, calibration, sliced metrics per velocity/tempo/kit-OOD).
- *Azioni:* applicare STRP-001; spec di dettaglio del piano statistico (test, soglie,
  tool); implementare `src/evaluation/` (data_audit + evaluation_suite); harness L1/L2.
- *DoD:* Executive Briefing approvato dal CEO; spec archiviata; tool girabile su
  mini-batch Gold (F0-T2e) → report JSON verde. **Gate operativo:** girato *prima* di
  F2-T3 (training A100) → da non saltare quando arriva il clock Azure.
- *Costo Azure:* **$0** — data audit gira sul Gold post F2-T1; evaluation gira a fine
  F2-T3 fuori dal training loop.
- *Sblocca/de-rischia:* F2-T3 (Gate L4 — claim pubblici falsificabili), F2-T2
  (sanity check pre-augmentation).

**F0-T16 · Pipeline di augmentation — build & test in locale**
- *Stato:* **SPLIT** in F0-T16-pre (MIDI, gate di F2-T1) + F0-T16-post (audio, gate di
  F2-T2) — Decision Lock CEO 2026-05-23 (split di F0-T15 in pre/post per simmetria).

**F0-T16-pre · MIDI augmentation pipeline — build & test in locale · `[F]` `P1`**
- *📚 Letture:* [`F0-T15-pre — spec MIDI augmentation`](../docs/methodology/F0-T15-pre_MIDI_AUGMENTATION_SPEC.md) · [`F0-T2a §3 — contratto dati`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract) · [`F0-T5 — sharding`](../docs/methodology/F0-T5_GOLD_SHARDING_SPEC.md) · [`TESTING_DOCTRINE §6`](TESTING_DOCTRINE.md#f0-test-plan) · [`ENGINEERING_STANDARDS §1 — determinismo`](ENGINEERING_STANDARDS.md#determinism).
- *Azioni:* implementare `src/data_engineering/midi_augment/` con ogni voce ratificata
  da F0-T15-pre (Time Jittering, Velocity Jittering / Ghost Note Masking / Global Gain
  Shift, Component Dropping); harness `pytest` + Hypothesis coerente con F0-T9b
  (oracoli su determinismo per-seed, range numerici, DNA-Trace lineage post-jitter,
  conservazione integrità della Mapping Table); estendere `tools/build_recipe_matrix.py`
  per emettere la matrix `MIDI × jitter-variant × engine` pre-shuffled.
- *DoD:* pipeline eseguibile in locale sui MIDI sorgente (GMD + mini-batch L2);
  oracoli §6 verdi; recipe matrix proiettata e committata; Ocular Proof — diff
  MIDI pre/post per ≥1 variante per categoria.
- *Costo Azure:* **$0** (interamente locale).
- ⛔ F0-T15-pre. **Sblocca F2-T1 — gate operativo prima di T1-prep-D.**
- ☑ **FATTO (2026-05-23):** modulo `src/data_engineering/midi_augment/` implementato
  in 4 file (`seed.py`, `jitter.py`, `recipe_matrix.py`, `__init__.py`). API pubblica:
  `apply_midi_jitter(midi, *, variant_idx, master_seed, source_midi_id)` —
  pipeline canonica time → flam → velocity → ghost → gain → component; variant 0
  = identity baseline (RNG consumato comunque per replay-invariance); `derive_jitter_seed`
  = `sha256(master ‖ id ‖ idx)[:8]`; `build_recipe_matrix_entries` =
  `|MIDI| × (k+1) × |engine|` con Fisher-Yates shuffle ancorato a `master_seed`.
  Fail-loud su MIDI malformato (orphan note_on, abs_tick negativi, file senza
  tracks). Conservazione delle durate sotto Time Jittering (note_off shifta
  della stessa quantità del note_on). Clausola groove-skeleton sotto Component
  Dropping (kick+snare mai droppati insieme nella stessa zona 2 s).
  **Oracoli §6.3 verdi:** 35 unit `seed` (determinismo, sensibilità, range,
  fail-loud) + 16 unit `jitter` (baseline identity, determinismo, time bounds,
  velocity range, ghost no-leak, gain global, skeleton, fail-loud) + 14 unit
  `recipe_matrix` (cardinalità, unicità, determinismo, baseline coverage,
  fail-loud) + 5 property Hypothesis (replay byte-identical, velocity range,
  abs_tick≥0, matrix no-drop/no-duplicate, seed derivation match) + 5
  acceptance sul mini-batch L2 (smoke, baseline identity cross-MIDI, varianti
  differiscono, range invariants, skeleton inviolato). **Suite F0: 332 passed,
  7 skipped, 0 failed** (+75 oracoli vs T1-prep-C). `ruff` + `mypy --strict`
  puliti. **Ocular Proof:** `tools/midi_augment_ocular_proof.py` genera
  PNG piano-roll a 4 pannelli (source + baseline + 2 jittered) in
  `docs/gates/F0-T16-pre_OCULAR_PROOF/` — su `groove_00`: baseline 26 eventi
  (identity), v=1 23 eventi (component dropping ~3), v=2 25 eventi. Sblocca
  **T1-prep-D (provisioning compute Azure)** — F2-T1 ora gated solo dal
  provisioning operativo.

**F0-T16-post · Audio augmentation pipeline — build & test in locale · `[F]` `P2`**
- *📚 Letture:* `F0-T15-post — spec audio augmentation` (da archiviare) · [`AUGMENTATION_AUDIT_BACKLOG`](../docs/methodology/AUGMENTATION_AUDIT_BACKLOG.md) · [`DOSSIER §3.2–§3.4`](../docs/methodology/DOSSIER_TECNICO.md#aug-l1) · [`F0-T2a §3`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract) · [`TESTING_DOCTRINE §6`](TESTING_DOCTRINE.md#f0-test-plan) · [`ENGINEERING_STANDARDS §1`](ENGINEERING_STANDARDS.md#determinism) · [`§6`](ENGINEERING_STANDARDS.md#execution-robustness).
- *Origine:* osservazione del CEO (2026-05-23) — il render aveva i sotto-task locali
  (F0-T2b/c/d/e) prima dello scale F2-T1; l'augmentation audio no: `F2-T2` mescolava
  "scrivi il codice" + "girarlo a 1.5 TB" sul clock Azure, esattamente lo spreco che
  la doctrine ($200 use-it-or-lose-it) vieta. Sub-task aperto per simmetria.
- *Azioni:* implementare `src/data_engineering/audio_augment/` con ogni voce ratificata
  da F0-T15-post — convoluzione IR (`pedalboard`, CPU), Machine-Gun Chaos, Studio
  Mutilation, Transient Saboteurs; smoke-test Demucs AI-Isolation su Mac M5 / MPS;
  harness `pytest` + Hypothesis (oracoli su determinismo, range FP16, integrità
  DNA-Trace, ENGINEERING_STANDARDS §1).
- *DoD:* pipeline eseguibile in locale sul mini-batch Gold; oracoli §6 verdi; smoke
  Demucs su MPS verde su ≥2 campioni; nessun NaN/inf e peak ∈ (0, 1] su tutti i
  campioni augmented; Ocular Proof — PNG waveform pre/post per ≥1 campione. **Costo
  Azure = $0** (interamente locale).
- ⛔ F0-T2e (mini-batch su cui testare), F0-T15-post. **Sblocca F2-T2 come *scale-only*.**

> **Gate d'uscita F0:** L2 superato (~05-28) **e** L3 superato (~06-02).

### Fase F1 — Provisioning Azure · gate d'ingresso: L2 superato

**F1-T1 · Setup Azure · `[A]` `P1`**
- *📚 Letture:* [`STRATEGIC_INFRASTRUCTURE_AUDIT §7.1`](STRATEGIC_INFRASTRUCTURE_AUDIT.md#azure-spend-plan) · [`§4 — Scala del credito`](#credit-scale).
- *Azioni:* Resource Group; Blob Container (LRS); SAS token scoped; Soft Delete + WORM
  su tier Bronze; alert di spesa a $100 e $160.
- *DoD:* portale Azure mostra risorse attive + alert configurati.
- ⛔ F0-T3.

**F1-T2 · dvc remote Azure · `[A]` `P1`**
- *📚 Letture:* [`STRATEGIC_INFRASTRUCTURE_AUDIT §7.1`](STRATEGIC_INFRASTRUCTURE_AUDIT.md#azure-spend-plan) · [`DOSSIER §9.2 — Medallion`](../docs/methodology/DOSSIER_TECNICO.md#medallion).
- *Azioni:* configurare il remote `dvc` sul Blob Container.
- *DoD:* `dvc push` di prova riuscito (log).
- ⛔ F1-T1.
- ☑ **FATTO (2026-05-23):** scaffold DVC inizializzato (`.dvc/` tracked: `config`,
  `.gitignore`, `.dvcignore`; il secret SAS-bearing **connection string** vive in
  `.dvc/config.local` gitignored, ENGINEERING_STANDARDS §6). Remote di default
  **`azure://gold/dvc`** sull'Account `stneurotrigger22`. `dvc push` di prova
  riuscito (1 file, 48 B, MD5 `649dcfcfd0cc7e52a60aff5e479f76f1`); blob
  verificato via `azure-storage-blob` SDK su `gold/dvc/files/md5/64/9dcfcf...`.
  Pacchetto in `.dvc/`; SAS valido fino al **2026-08-21** (3 mesi). Sblocca
  l'upload del Gold a F2-T1.

### Fase F2 — Burn Compute · gate d'ingresso: F1 completa

**F2-T1 · Render Gold 1.5 TB · `[G]` `P1` — spend BASSO RISCHIO (gate L2)**
- *📚 Letture:* [`F0-T2a §2 — render engine`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#render-engine) · [`F0-T2a §3.8 — tail std`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#tail-standardization) · [`F0-T5 — sharding`](../docs/methodology/F0-T5_GOLD_SHARDING_SPEC.md) · [`ENGINEERING_STANDARDS §6 — robustezza`](ENGINEERING_STANDARDS.md#execution-robustness) · [`§4 — Scala del credito`](#credit-scale).
- *Azioni:* render del dataset Gold su Azure (Sfizz/DrumGizmo, multi-mic, multi-scenario);
  upload Blob; tracciamento DVC.
- *Sotto-task di prep (locali, pre-clock-Azure):*
  - **T1-prep-A · Recipe matrix con pairing forzato MIDI×Engine × jitter-variant**
    (Decision Lock CEO 2026-05-23 — anti shortcut durata↔engine; emendata 2026-05-23
    sessione T1-prep-D per assorbire le varianti MIDI di F0-T15-pre). Ogni MIDI sorgente
    della GMD è renderizzato con tutti gli engine attivi del roster (Sfizz multi-kit +
    DrumGizmo multi-kit, F0-T1b) **e con `k` varianti jitter** definite da F0-T15-pre.
    Pre-shuffle deterministico con seed registrato in `manifest.json` (F0-T5 §5.5).
    **Partizione kit-wise train/val** (Decision Lock CEO 2026-05-23 — Opzione B,
    DOSSIER §10.2): train = 8 kit (DRSKit, CrocellKit, MuldjordKit, Aasimonster ·
    Frankensnare, Unruly Drums, Big Rusty Drums, VSCO-2 CE), val = 2 kit "vergini"
    (ShittyKit, Swirly Drums) → misura generalizzazione cross-kit, non solo
    cross-session. Holdout esterno = E-GMD (§10.3, F0-T1c).
    ⛔ F0-T15-pre, F0-T16-pre.
  - **T1-prep-B · Tail standardization** in `orchestrate.py` — implementare
    `tail_s = 0.5 s` uniforme (F0-T2a §3.8), `last_onset_s` dal target builder,
    trim/pad post-render. Supersedes la coda `_DRUMGIZMO_TAIL_S = 5.0 s` hardcoded.
    Oracoli L1: pack del tail uniforme cross-engine su mini-batch L2.
    ☑ **FATTO (2026-05-23):** `last_onset_seconds()` in `target_builder.py` (anchor
    della policy); `TAIL_S = 0.5`, `n_sample_target()` e `standardize_audio_tail()`
    in `orchestrate.py` (fail-loud, trim/pad C-contiguous, pad-zero anti-shortcut);
    `build_gold_sample` cuce la pipeline (compute `last_onset_s` → render con
    tail naturale catturato → trim/pad a `n_sample_target` → target `duration_s`
    coerente). `_DRUMGIZMO_TAIL_S` rinominato `_DRUMGIZMO_RENDER_TAIL_S` (resta
    interno al CLI DGZ, non più verità del Gold). `build_dna_json` registra
    `audio.last_onset_s` e `audio.tail_s`; `GoldSampleResult` espone entrambi.
    Oracoli L1: **20 nuovi test verdi** (6 `n_sample_target` + formula
    engine-agnostica + rifiuti negativi · 6 `standardize_audio_tail` trim/pad/exact/
    non-2D/non-positive · 5 `last_onset_seconds` · 2 `dna_trace` §3.8 + rifiuti
    negativi · 1 cross-engine identical-shape property). **Suite F0: 226 passed,
    7 skipped, 0 failed.** `ruff` + `mypy --strict` puliti sui moduli toccati.
  - **T1-prep-C · `ShardWriter` modulo** — implementazione di
    `src/data_engineering/gold/shard_writer.py` per F0-T5 §7 (pack-on-fill atomico
    1 GB, manifest, resume). Test-first.
    ☑ **FATTO (2026-05-23):** `ShardWriter` implementato — pack-on-fill su byte
    threshold (`TARGET_SHARD_BYTES = 1 << 30` esatto), tar PAX_FORMAT con header
    normalizzato (`mtime/uid/gid/mode` fissati → bit-deterministic, ENG_STD §1),
    ordine lessicografico interno (F0-T5 §5.2), atomicità via `.tmp` + `os.rename`,
    `manifest.json` per split (schema F0-T5 §5.5 — `manifest_version`, `split`,
    `recipe_matrix_seed`, `target_shard_bytes`, `tail_s`, `n_shard`, `n_sample`,
    `total_bytes`, `shards[{index, filename, n_sample, n_bytes, sha256,
    key_range}]`), resume da manifest esistente (`next_index = manifest.n_shard`),
    cleanup `.tmp` orfani all'init (split-isolated), fail-loud su key duplicate /
    dotted / triple incomplete / split-mismatch / manifest corrotto, `close()`
    idempotente. **31 oracoli verdi:** L1 unit (naming + construction + add
    validation + rotation + tar lex-order + determinismo bit-per-bit + atomicity +
    manifest schema + sha256 match + resume + edge cases) + L2 property
    (Hypothesis: determinismo cross-run su input shuffled, ogni sample appare
    esattamente in 1 shard, pack-on-fill no-drop no-duplicate). **Suite F0:
    257 passed, 0 failed.** `ruff` + `mypy --strict` puliti.
  - **T1-prep-D · Provisioning compute Azure** — VM **`Standard_D16s_v3`**
    (~$0.77/h, 16 vCPU — Decision Lock CEO 2026-05-23 sessione T1-prep-D,
    semplifica vs 2× D8s_v3 a costo equivalente), image Ubuntu 22.04 LTS
    con cloud-init che provisiona DrumGizmo (apt 0.9.20-3build3) + Sfizz
    1.2.3 (apt o source-build fallback) + 10 kit del roster F0-T1b
    (sha256-verified streams) + venv Python + DVC remote SAS + smoke
    render integrato. `dvc remote = azure` già pronto (F1-T2 ☑).
    ☑ **FATTO (2026-05-23):** pacchetto pronto per consegna CEO offline
    (stesso pattern di F1-T1):
    - `tools/build_recipe_matrix.py` — genera la recipe matrix
      `MIDI × jitter-variant × engine_kit` (kit-wise train/val split per
      DOSSIER §10.2 Opzione B); smoke test sul mini-batch verde
      (4 recipe parsabili, barcode 7-segment `J00`/`J01` distinto,
      jitter_seed sha256-derivato auditabile).
    - `tools/provision_render_vm.sh` — cloud-init script bash idempotente
      (set -euo pipefail, sha256 verification streamed, smoke render
      integrato; profilo `smoke`/`full` per validare la VM prima del
      bulk).
    - `tools/azure_kill.sh` — kill switch a 4 modalità (balance,
      deallocate, teardown, nuclear) con magic-word confirmation;
      idempotente, fail-soft, logged in `~/.neurotrigger/azure_kill.log`.
    - `docs/runbooks/F2-T1_RENDER_BURN.md` — runbook completo per il CEO
      (variabili env, comandi `az` step-by-step, smoke VM 15 min /
      $0.03 prima del burn, soglie monitoring spesa, kill switch).
    `ruff` pulito sul nuovo modulo; `mypy --strict` clean su `src/`
    (i `tools/` seguono il pattern del repo — non gated). Suite F0:
    **332 passed, 7 skipped, 0 failed** (invariato).
- *DoD:* 1.5 TB renderizzati e versionati; log di completamento; manifest verde su
  entrambi gli split.
- ⛔ F1-T1, **F0-T15-pre** *(spec MIDI augmentation)*, **F0-T16-pre** *(pipeline MIDI
  augmentation locale)*. Lo split `pre/post` di F0-T15/T16 (Decision Lock CEO 2026-05-23,
  sessione T1-prep-D) sposta il MIDI Jittering dal lato F2-T2 al lato F2-T1: il render
  consuma la recipe matrix `MIDI × jitter-variant × engine`, mai una matrix `MIDI ×
  engine` da rifare a posteriori.

**F2-T2 · Audio augmentation + Demucs — *scale-only* su Azure · `[G]` `P1`**
- *📚 Letture:* `F0-T16-post` (la pipeline d'audio augmentation è già scritta e validata
  in locale, qui si applica al dataset full-size) · [`DOSSIER §3.2 — bleed`](../docs/methodology/DOSSIER_TECNICO.md#aug-l1) · [`DOSSIER §3.4 — augmentation`](../docs/methodology/DOSSIER_TECNICO.md#aug-l3) · [`ENGINEERING_STANDARDS §1 — determinismo`](ENGINEERING_STANDARDS.md#determinism).
- *Riformulazione (2026-05-23):* il task era originariamente "augmentation Python +
  Demucs" lumpato. Due Decision Lock successivi del CEO (2026-05-23): (1) split in
  pipeline locale (F0-T16) + scale-only Azure (questo task); (2) sessione T1-prep-D —
  separazione **MIDI augmentation (pre-render, F0-T15-pre/T16-pre, gate di F2-T1)** vs
  **audio augmentation (post-render, F0-T15-post/T16-post, gate di questo task)**.
  Qui resta solo lo scale-only dell'augmentation **audio**.
- *Azioni:* applicare la pipeline di audio augmentation di F0-T16-post al dataset Gold
  completo (post F2-T1); inferenza Demucs AI-Isolation a scala su GPU Azure; upload
  Blob; tracciamento DVC.
- *DoD:* dataset aumentato versionato; nessuna nuova logica scritta su Azure (solo
  scale di codice già verde in locale).
- ⛔ F2-T1 (può procedere in streaming sul renderizzato), **F0-T16-post** (codice
  d'audio augmentation validato in locale).

**F2-T3 · Training "Gold" A100 → Gate L4 · `[G]` `P1` — spend A RISCHIO (gate L3)**
- *📚 Letture:* [`F0-T4a — spec TCN`](../docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md) · [`DOSSIER §10 — training set`](../docs/methodology/DOSSIER_TECNICO.md#training-set) · [`DOSSIER §10 — validation`](../docs/methodology/DOSSIER_TECNICO.md#validation) · [`MASTER_CHECKLIST §6 — Gate`](../MASTER_CHECKLIST.md#gates) · [`ENGINEERING_STANDARDS §5 — validazione statistica`](ENGINEERING_STANDARDS.md#statistical-validation).
- *Azioni:* training "Gold" della TCN su A100 Spot; validazione Holdout reale
  (E-GMD) + Slakh-Mix (Slakh2100) + Ocular Proof.
- *DoD:* il modello supera l'Holdout reale → **Gate L4** (sblocca i claim pubblici).
- ⛔ F2-T1 **e** F0-T4b (L3).

**F2-T4 · Credit-soak · `[G]` `P2`**
- *📚 Letture:* [`§4 — Scala del credito`](#credit-scale) · [`§3 — Checkpoint`](#checkpoints).
- *Azioni:* desplegare il credito residuo sulla scala §4 (Tier 2/3) secondo lo scenario
  fissato a CP-3.
- *DoD:* saldo credito → ~$0 consumato utilmente.

### Fasi F3–F5 — Coarse (da raffinare)

- **F3 · Consolidamento:** **SSD 1 TB del CEO** (€0 — già in casa, Decision Lock CEO
  2026-05-23 sessione T1-prep-D) come archive permanente. *Risparmio €120 vs piano
  originale (HDD 2 TB).* Strategia "asset-only, Gold riproducibile" — il volume reale
  da preservare è ~30 GB di **asset core** (recipe matrix · MIDI Bronze · kit vendor ·
  modelli trained · evaluation report · repo), non i 4.5 TB di Gold raw (derivata
  bit-deterministica della pipeline F2-T1, ricostruibile in ~14h su Azure per ~$11).
  L'SSD ha quindi:
  - **Asset core (~30 GB)** — il vero valore commerciale; sta su una chiavetta USB.
  - **Subset Gold opzionale (~200 GB)** — 1-2 shard per kit (10 GB minimo, 200 GB
    abbondante) per esperimenti locali rapidi su Mac M5 senza re-render Azure.
  - **Checkpoint di training successivi (~50-100 GB)** — sweep iperparametri post-L4.
  - **Margine libero ~700 GB+** — sicurezza.

  *Workflow operativo:* (1) durante F2-T1 il Gold è scritto su Azure Blob; (2) post-L4
  `dvc fetch` selettivo degli asset sull'SSD; (3) opzionalmente `dvc fetch` di N shard
  per backup locale; (4) teardown Azure (`az group delete`); (5) l'SSD ora contiene
  tutto il necessario per ricostruire il sistema o ri-trainare via Azure spot.
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
| F0-T2b | Render engine Sfizz | F0 | ☑ | — | — |
| F0-T2c | Integrazione DrumGizmo | F0 | ☑ | — | — |
| F0-T2d | Writer Gold-tensor + DNA-Trace | F0 | ☑ | — | — |
| F0-T2e | Mini-batch end-to-end | F0 | ☑ | — | — |
| F0-T3 | Validazione Gate L2 | F0 | ☑ | — | **L2** *(superato 2026-05-23)* |
| F0-T4a | Topologia TCN concreta (STRP-001) | F0 | ☑ | — | — |
| F0-T4b | TCN mini-prototipo + round-trip RTNeural | F0 | ☑ | F0-T3, F0-T4a | **L3** *(superato 2026-05-23 — opzione A, Decision Lock CEO)* |
| F0-T5 | DVC + struttura Medallion + sharding | F0 | ☑ | — *(spec sharding LOCKED 2026-05-23 — F0-T5_GOLD_SHARDING_SPEC.md)* | — |
| F0-T6 | audit_dsp_rigor.py (predisp.) | F0 | ☐ | — | — |
| F0-T7 | Classi JUCE (opz.) | F0 | ☐ | — | — |
| F0-T8 | Model Artifact — spec export | F0 | ☐ | — | — |
| F0-T9a | Testing & QA Doctrine (STRP-001) | F0 | ☑ | — | — |
| F0-T9b | F0 Pipeline Test Harness | F0 | ☑ | — | — |
| F0-T10 | Documentation Linking Layer (STRP-001) | F0 | ☑ | — | — |
| F0-T11 | Content-rot audit (roster F0-T1b) | F0 | ☑ | — | — |
| F0-T12 | Audit OpenPhase — standard ingegneristici | F0 | ☑ | — | — |
| F0-T13 | De-referenziazione OP-X (chiusura decoupling) | F0 | ☑ | — | — |
| F0-T14 | Mapping documentale dei task (campo Letture) | F0 | ☑ | — | — |
| F0-T15-pre | Audit MIDI augmentation (STRP-001) | F0 | ☑ | — *(2026-05-23 — spec LOCKED, Decision Lock CEO ratificato B1–B4: range Opzione B, k=2 + baseline, DNA-Trace 7-segment, storage ~$90)* | — |
| F0-T15-post | Audit audio augmentation + agnosticità (STRP-001) | F0 | ☐ | — *(non critico — pre F2-T2)* | — |
| F0-T16-pre | MIDI augmentation pipeline — build & test in locale | F0 | ☑ | — *(2026-05-23 — src/data_engineering/midi_augment/ implementato, 75 oracoli verdi, Ocular Proof in docs/gates/F0-T16-pre_OCULAR_PROOF/)* | — |
| F0-T16-post | Audio augmentation pipeline — build & test in locale | F0 | ☐ | F0-T2e, F0-T15-post | — |
| F0-T17 | Statistical Test Plan (STRP-001) | F0 | ◐ | — *(spec LOCKED 2026-05-23 — implementazione `src/evaluation/` in 2-3 sessioni; gate pre-F2-T3)* | — |
| F1-T1 | Setup Azure | F1 | ☑ | — *(2026-05-23 — CEO offline runbook)* | — |
| F1-T2 | dvc remote Azure | F1 | ☑ | — *(2026-05-23 — `dvc push` smoke verde)* | — |
| F2-T1 | Render Gold 1.5 TB ×3 (≈4.5 TB) | F2 | ☐ | — *(2026-05-23 — tutti i gate prep chiusi: T1-prep-A/B/C/D ☑ + F0-T15-pre/T16-pre ☑; F2-T1 ora gated solo dall'esecuzione CEO offline — runbook `docs/runbooks/F2-T1_RENDER_BURN.md`)* | — |
| F2-T2 | Audio augmentation + Demucs — *scale-only* | F2 | ⊘ | F2-T1, F0-T16-post | — |
| F2-T3 | Training A100 → L4 | F2 | ⊘ | F2-T1 *(F0-T4b ☑)* | **L4** |
| F2-T4 | Credit-soak | F2 | ⊘ | CP-3 | — |
| F3 | Consolidamento SSD 1 TB CEO (€0) | F3 | ⏸ | F2 | — |
| F4 | Sviluppo Plugin | F4 | ⏸ | L4 | — |
| F5 | Release v1.0 EA | F5 | ⏸ | F4 | — |

**Stato globale:** Fase attiva **F0** · ☑ F0-T1 · ☑ F0-T1b · ☑ F0-T1c · ☑ F0-T2a · ☑ F0-T4a
· ☑ F0-T9a · ☑ F0-T10 (Doc Linking Layer — standard + INDEX + gate lychee blocking, chiuso)
· ☑ F0-T11 (content-rot audit — SM Drums riallineato al roster F0-T1b)
· ☑ F0-T12 (audit OpenPhase — `ENGINEERING_STANDARDS.md` internalizzato)
· ☑ F0-T13 (de-referenziazione OP-X — decoupling dall'archivio chiuso)
· ☑ F0-T14 (mapping documentale — campo `📚 Letture` su 17 task aperti)
· ☑ F0-T9b (F0 Pipeline Test Harness — scaffold test-first auto-smontante, gate di F0-T2b/c/d)
· ☑ F0-T2b (render engine Sfizz — parser recipe + provisioning + adapter `SfizzRenderer`
sul CLI reale, watchdog + fail-loud Silent Zero, oracoli §6.3 verdi)
· ☑ F0-T2d (writer Gold-tensor + DNA-Trace — contratto F0-T2a §3–§4, suite F0 verde,
gate mutation sbloccato su Linux/OrbStack, kill-rate comportamentale 100 %)
· ☑ F0-T2c (integrazione DrumGizmo — provisioning DRSKit 13-mic + adapter
`DrumGizmoRenderer` sul CLI reale, 17 unit + 3 acceptance §6.3, bleed falsificabile via
correlazione di inviluppo, suite F0 150 passed)
· ☑ F0-T2e (mini-batch end-to-end — `target_builder.py` MIDI→`flat-25` + `orchestrate.py`
cuce la pipeline, 12 campioni Gold generati su 12 grooves sintetici, 37 oracoli §6.3,
suite F0 189 passed)
(Decision Lock 2026-05-20) · ☑ **F0-T15-pre LOCKED (2026-05-23 sessione T1-prep-D)** —
STRP-001 chiuso, Decision Lock CEO ratificato. Spec in
`docs/methodology/F0-T15-pre_MIDI_AUGMENTATION_SPEC.md`. Parametri: Time σ=2ms clip
±5ms, Velocity σ=8 + Ghost (vel≤40→×0.3..1.0) + Gain ×0.5..2.0, Component 10%/2s +
skeleton kick+snare, **k=2 + baseline = ×3 recipe matrix**, seed sha256-derivato,
DNA-Trace 7-segment. Costo Azure: +$67 (render +$7, storage +$60), dentro $200 con
margine $100. **Sblocca F0-T16-pre (gate di F2-T1).** DOSSIER §3.1 e F0-T2a §3.7
aggiornati; AUGMENTATION_AUDIT_BACKLOG segnato come *partially superseded* sull'asse MIDI.
· ☐ F0-T15-post (audit audio augmentation + agnosticità d'ingresso — aperto 2026-05-22
su due revisioni del CEO, backlog in `AUGMENTATION_AUDIT_BACKLOG.md`; non critico,
pre F2-T2/T3)
· ☑ **F0-T16-pre LOCKED (2026-05-23 sessione T1-prep-D)** — `src/data_engineering/
midi_augment/` implementato (`seed.py` + `jitter.py` + `recipe_matrix.py`), pipeline
canonica time→flam→velocity→ghost→gain→component, variant 0 identity baseline, seed
derivation `sha256(master‖id‖idx)[:8]`, recipe matrix `|MIDI| × (k+1) × |engine|`
Fisher-Yates-shuffled. Suite F0: **332 passed, 7 skipped, 0 failed** (+75 oracoli:
35 seed + 16 jitter + 14 recipe_matrix + 5 property + 5 acceptance). Ocular Proof
in `docs/gates/F0-T16-pre_OCULAR_PROOF/`. `ruff` + `mypy --strict` puliti. **Sblocca
T1-prep-D** (F2-T1 ora gated solo dal provisioning compute Azure).
· ☐ F0-T16-post (audio augmentation pipeline — build & test in locale; sblocca F2-T2)
· ☑ **F0-T3 / Gate L2 SUPERATO (2026-05-23) — Decision Lock CEO.** Ocular Proof su 2
campioni (1 Sfizz + 1 DrumGizmo): allineamento target↔MIDI **65/65 onsets entro ±3 ms**;
0 NaN/inf; DNA-Trace shape & sha256 match; **bleed multi-mic DrumGizmo +0.99 off-diag**.
Calibrazione render — Sfizz 0.03× / DrumGizmo 0.12× factor, ~5.6 MB/s single-thread →
**1.5 TB ≈ ~5 h @ 16 vCPU, ~$3.5 stimati** (vs $55 allocazione §5 → headroom enorme per
Tier 2/3). Pacchetto firmato in `docs/gates/L2_OCULAR_PROOF/L2_INSPECTION_2026-05-23.md`.
· **Sbloccato dal Gate L2:** **F1-T1** (Setup Azure — il prossimo critico) e **F2-T1**
(Render Gold 1.5 TB — gated anche da F1-T1) · **F0-T4b** (mini-prototipo TCN) ora
gated solo da F0-T4a (già ☑) · Percorso critico verso F1/L4: **F1-T1 → F1-T2 → F2-T1**
+ in parallelo locale **F0-T4b** verso L3 · Scenario credito: *da fissare a CP-1
(2026-05-30, fra 7 gg)* — con L2 in anticipo (target era ~05-28) si conferma **GREEN**
salvo sorprese su F1.
· ☑ **F0-T4b chiuso (2026-05-23) — Gate L3 SUPERATO (opzione A) — Decision Lock CEO.**
Round-trip RTNeural-equivalente PASS (PyTorch ↔ C++17 `1.19e-07` ≈ epsilon fp32),
F0-T4a §8 open item risolto. Barra metrica F≥0.80 spostata al Gate L4 (su 10
grooves del mini-batch sarebbe stata statisticamente irrilevante anche se
superata). Pacchetto APPROVED in `docs/gates/L3_OCULAR_PROOF/`. **F2-T3 ora
gated solo da F2-T1.**
· ☑ **F0-T5 chiuso (2026-05-23) — sharding WebDataset LOCKED.** Spec in
`docs/methodology/F0-T5_GOLD_SHARDING_SPEC.md`: pack-on-fill con pre-shuffle, shard
1 GB esatto, DVC per directory, manifest sha256, atomicità `.tmp`+rename, branch
`*-augmented` per F2-T2. Calibrazione su mini-batch L2: ~250 campioni/shard,
~1500 shard a 1.5 TB.
· **Decision Lock CEO 2026-05-23 — anti shortcut engine-specific durata/tail**
(osservazione CEO sul rischio di leak strutturale durata↔engine):
  - **(A) Pairing forzato MIDI×Engine** nella recipe matrix di F2-T1 — sotto-task
    `T1-prep-A`. Ogni MIDI renderizzato con tutti gli engine del roster → durata
    smette di essere proxy dell'engine.
  - **(C) Tail standardization** `tail_s = 0.5 s` uniforme — amendment F0-T2a §3.8
    (v1.2.0); sotto-task `T1-prep-B` (implementazione). Trim/pad post-render
    cross-engine. Supersedes la coda 5 s hardcoded di F0-T2e.
  Insieme chiudono il canale di shortcut alla radice.
· **Decision Lock CEO 2026-05-23 — F3 SSD-only, Gold riproducibile** (sessione
T1-prep-D, post-domanda del CEO «come trovo 15 TB di HDD»). Reframe: l'asset
preservabile non è il Gold raw (4.5 TB) ma il quartetto **modello trained + recipe
matrix + kit vendor + MIDI Bronze** (~30 GB). Il Gold è derivata bit-deterministica
(verificato dalla pipeline midi_augment + orchestrate.py), ricostruibile in ~14h su
Azure per ~$11. F3 usa l'**SSD 1 TB del CEO** (€0, già in casa) al posto del piano
HDD €120: risparmio **€120 sul budget €500** → utilizzabile per ri-render Azure
futuri o riserva imprevisti.
· **Decision Lock CEO 2026-05-23 — split MIDI augmentation pre-render vs audio
augmentation post-render** (osservazione CEO sessione T1-prep-D — il MIDI Jittering
del DOSSIER §3.1 moltiplica la recipe matrix di F2-T1, non quella di F2-T2).
  - **F0-T15** split in **F0-T15-pre** (MIDI, gate F2-T1) + **F0-T15-post** (audio,
    gate F2-T2). Stesso split per F0-T16.
  - **Recipe matrix T1-prep-A** emendata: `MIDI × jitter-variant × engine` (k variants
    decise da F0-T15-pre via STRP-001).
  - **F2-T1 ora ⊘ bloccato da F0-T15-pre + F0-T16-pre.** T1-prep-D
    (provisioning compute Azure) sospeso finché lo split non si concretizza nel codice.
  - Doctrine: il MIDI Jittering è pre-render per costruzione fisica (Time Jittering
    sposta gli onset, Ghost Note Masking cambia il timbro, Component Dropping muta
    sezioni → audio diverso). Renderizzare ora senza significherebbe ri-renderizzare
    poi (use-it-or-lose-it §1.1 viola).
Prossimo checkpoint: **CP-1 / 2026-05-30**.

---
*Decision Lock 2026-05-20. Aggiornare il Tracking Board (§7) e lo scenario credito (§4)
a ogni sessione e a ogni checkpoint. Verifica di avanzamento solo via Ocular Proof.*
