# SESSION HANDOVER - 2026-05-20 (rev. post avvio Fase F0)
**Task Attivo:** AVVIO FASE F0 — COMPLETATO il blocco compliance + contratto dati
**Stato:** Fase esecutiva **F0 attiva**. Chiusi F0-T1, F0-T1b, F0-T1c, F0-T2a.

## STATO DELLA COMMESSA

### Chiuso in questa sessione
- **Pre-Flight SOP-010 + Gate Zero** — `TASK_BLUEPRINT.md` rigenerato per lo startup F0.
- **Dottrina compliance "Self-Evident Commercial License"** (Decision Lock CEO,
  `DATA_PROVENANCE_LOG.md` §1.1): si usano **solo** asset la cui licenza pubblicata
  concede di per sé l'uso commerciale (CC0/CC-BY). Zero corrispondenza con i creatori,
  zero divulgazione del progetto.
- **F0-T1 · Compliance licenze** ☑ — risolta per pura lettura delle licenze: ENST-Drums
  (research-only), MedleyDB (CC-BY-NC), SM Drums (nessuna licenza formale) → **esclusi**.
  Outreach annullato.
- **F0-T1b · Roster kit** ☑ — survey: roster di **11 voci CC0/CC-BY** (6 kit DrumGizmo
  CC-BY-4.0 multi-mic, 3 Karoryfer CC0, Frankensnare, Salamander, VSCO-2 CE), in
  `DATA_PROVENANCE_LOG.md` §2.A. Risolve il rischio di generalization gap timbrico.
- **F0-T1c · Validation Protocol ridisegnato** ☑ — Holdout reale = **E-GMD** (CC-BY 4.0),
  Stealth-Mix = **Slakh2100** (CC-BY 4.0), Ocular Proof invariato. Piano B (registrazioni
  proprietarie) scartato dal CEO.
- **F0-T2a · Recipe + contratto dati (STRP-001 snello)** ☑ — Decision Lock 5/5: recipe
  YAML; `target.f16` layout `flat-25` `[n_frame,25]`; `R_target` parametrico (provv.
  344.5 Hz, ratifica a F0-T4a); velocity normalizzata [0,1]; articolazioni intra-bus
  collassate in v1.0. Spec: `docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`;
  Mapping Table: `docs/specs/midi_mapping_table.yaml`.

### Documenti prodotti / aggiornati
- Nuovi: `docs/compliance/F0-T1_LICENSE_VERIFICATION.md`, `F0-T1b_KIT_ROSTER_SURVEY.md`,
  `F0-T1c_HOLDOUT_SURVEY.md`, `docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`,
  `docs/specs/midi_mapping_table.yaml`.
- Aggiornati: `DATA_PROVENANCE_LOG.md`, `DOSSIER_TECNICO.md`, `MASTER_CHECKLIST.md`,
  `MASTER_SCHEDULING.md`, `REGISTRO_AVANZAMENTO.md`, `PIPELINE_STATUS.json`,
  `TASK_BLUEPRINT.md`, `Diario_Presidenza_OpenPhase.md`.

### In corso / non avviato
- Nessuna esecuzione di codice avviata. F0-T2b/c/d e F0-T4a sono **☐ TODO**.

## OBIETTIVO IMMEDIATO (prossima sessione)
Due track tecnici, eseguibili in parallelo:
1. **F0-T4a — Topologia TCN concreta (STRP-001).** Lavoro d'analisi/decisione (orchestratore).
   Fissa numero layer, kernel, dilatazioni, receptive field, e ratifica `R_target`
   (frame-rate del target — lasciato parametrico da F0-T2a). Nessun blocco.
2. **F0-T2b/c/d — codice pipeline** (render Sfizz, integrazione DrumGizmo, writer
   Gold-tensor). Sono task **di codice** → per i Mandati POL-AI-001 §3 vanno eseguiti via
   **delega a sub-agenti**. Sbloccati da F0-T2a.

## CONTESTO CONGELATO (vitale)
- **VINCOLO DURO:** credito Azure $200 scade **2026-06-19**. Primo checkpoint **CP-1 il
  2026-05-30**. L2/L3 sono locali (€0).
- **Dottrina compliance §1.1 attiva:** nessun asset entra senza licenza pubblicata
  commercial-clear. Niente email ai creatori, niente divulgazione.
- **Contratto dati F0-T2a LOCKED:** WebDataset, terna `audio.f16`/`target.f16`/`dna.json`,
  target `flat-25`, microtiming disaccoppia la sample-accuracy dal frame-rate.
- **Validation Protocol:** E-GMD + Slakh2100 + Ocular Proof. ⚠️ E-GMD è registrato su
  Roland TD-17 → i claim L4 non coprono il bleed acustico reale con metrica numerica.
- Branch di lavoro **`develop`**; `main` solo per release stabile.
- **Commit dei documenti di sessione: da autorizzare** — non ancora eseguito.

## MANDATI PERMANENTI
- Nessun claim di accuratezza numerico pubblico prima del Gate L4.
- Zero-Allocation nel thread audio (RTNeural float32 CPU-only a runtime).
- STRP-001 obbligatorio per ogni decisione tecnica/architetturale aperta.
- Orchestratore non scrive codice: delega a sub-agenti (POL-AI-001 §3).
- Tracking Board (`MASTER_SCHEDULING.md` §7) aggiornato a ogni sessione e checkpoint.
