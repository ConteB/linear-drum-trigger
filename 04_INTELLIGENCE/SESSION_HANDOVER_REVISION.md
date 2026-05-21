---
id: LIN-DT-HANDOVER-001
title: Session Handover — rev. post F0-T9b / F0-T2b (parser)
type: registro
status: ACTIVE
phase: F0
domain: Operations
version: 2.0.0
updated: 2026-05-21
tags: [handover, registro, F0]
related: [LIN-DT-MSCHED-001, LIN-DT-REGAV-001]
supersedes: []
---

# SESSION HANDOVER - 2026-05-21 (rev. post F0-T9b / F0-T2b parser)
**Task Attivo:** Fase F0 — avviata l'esecuzione del codice di pipeline.
**Stato:** **F0 attiva.** Chiusi F0-T1/T1b/T1c/T2a/T4a/T9a/T10-T14 + **F0-T9b**.
F0-T2b **◐ in corso** (parser fatto, renderer bloccato).

## ⚠️ AZIONE RICHIESTA AL CEO — provisioning render engine

**F0-T2b (renderer Sfizz) è bloccato in attesa di provisioning manuale del CEO.**
Per Decision del CEO (2026-05-21) il provisioning è a sua cura. Servono due cose:

1. **Binario `sfizz_render`** — la CLI di rendering SFZ, disponibile su PATH (oppure
   comunicarne il path assoluto). Non è in Homebrew: va costruito da sorgente
   (`github.com/sfztools/sfizz`, CMake) o preso da release prebuilt. Verifica:
   `which sfizz_render`.
2. **Un kit SFZ del roster F0-T1b** — per Sfizz servono i kit in formato **SFZ**:
   **Salamander** o **Karoryfer** (CC-BY). Collocazione vendorizzata definitiva
   (`ENGINEERING_STANDARDS §4`): proposto `lib/sfz/<kit>/`. Comunicare il path del `.sfz`.

Appena binario + kit sono presenti, la prossima sessione implementa l'adapter
`SfizzRenderer` sul CLI reale e chiude il DoD di F0-T2b (render di prova multi-mic + log).
*Nota:* lo stesso provisioning, lato **DrumGizmo**, servirà per F0-T2c.

## STATO DELLA COMMESSA

### Chiuso in questa sessione
- **F0-T9b · F0 Pipeline Test Harness** ☑ — harness `pytest`+`Hypothesis`+`mutmut`+
  `coverage` in `tests/`; pacchetto-scheletro `src/data_engineering/gold/` con interfacce
  pubbliche bloccate sul contratto F0-T2a. 50 test-oracolo scritti test-first; scaffold
  **auto-smontante** (`xfail(strict, raises=NotImplementedError)` → `XPASS`/rosso quando
  il modulo è implementato). Gate mutation configurato. Dettaglio: `tests/README.md`.
- **F0-T2b · Render engine Sfizz** ◐ — **parser recipe** implementato e verificato
  (`src/data_engineering/gold/recipe.py`, schema F0-T2a §1.1, strict fail-loud). Renderer
  Sfizz **bloccato** (vedi azione CEO sopra).

### Codice / documenti prodotti
- Nuovi: `src/data_engineering/gold/` (`recipe.py` implementato; `dna_trace.py`,
  `gold_writer.py`, `mic_standardize.py` = scheletro), `tests/` (harness completo),
  `pyproject.toml`, `setup.cfg`, `requirements-dev.txt`, `tools/run_tests.sh`,
  `tools/run_mutation.sh`.
- Aggiornati: `MASTER_SCHEDULING.md` (Tracking Board), `requirements.txt` (+`PyYAML`),
  `.gitignore`.
- Committato su `develop`: `131346c` (F0-T9b), `be6617e` (F0-T2b parser). **Non pushato.**
- Verifiche: `pytest` 24 passed / 6 skipped / 39 xfailed / 0 failed · `ruff` pulito ·
  `mypy --strict` pulito.

### In corso / non avviato
- **F0-T2b renderer:** bloccato (provisioning CEO).
- **F0-T2d** (Writer Gold-tensor + DNA-Trace) — pronto a partire: pura Python, **zero
  binari**, modulo critico, 16 oracoli già nell'harness. Non gated da nulla.
- **F0-T2c** (DrumGizmo) — bloccato dallo stesso tipo di provisioning (kit DrumGizmo).
- **F0-T10 (corpo, P2)** e **F0-T4b** (gated da F0-T3): invariati.

## OBIETTIVO IMMEDIATO (prossima sessione)
**F0-T2d · Writer Gold-tensor + DNA-Trace** — è il task pronto e non bloccato, sulla
critical path verso Gate L2. Implementare `gold_writer.py` (n_frames, bus_columns, writer
FP16 + integrità §3.7) e `dna_trace.py` (barcode codec bijettivo, `dna.json`) contro gli
oracoli `@awaiting("F0-T2d")` già scritti; poi rimuovere i marker e far girare il gate
mutation (≥ 90 % critici). In parallelo, appena il CEO provisiona Sfizz → ripresa F0-T2b.

## CONTESTO CONGELATO (vitale)
- **VINCOLO DURO:** credito Azure $200 scade **2026-06-19**. Primo checkpoint **CP-1 il
  2026-05-30**. L2/L3 sono locali (€0). Scenario credito: *da fissare a CP-1*.
- **Contratto dati F0-T2a LOCKED** + **topologia F0-T4a LOCKED**: `R_target` 344.53125 Hz,
  target `flat-25` `[n_frame,25]`, microtiming disaccoppia la sample-accuracy dal frame-rate.
- **Testing Doctrine attiva:** ogni task di codice ha DoD = suite verde + mutation
  kill-rate; l'harness precede il codice (test-first). Harness F0-T9b operativo.
- **Scaffold auto-smontante:** implementare un modulo-scheletro fa diventare i suoi
  oracoli `XPASS(strict)` → run rosso, finché non si rimuove il marker `@awaiting`.
- **Doc Standard attivo:** frontmatter YAML su ogni doc nuovo; dopo modifiche al
  frontmatter rigenerare `docs/INDEX.md` (`python3 tools/gen_docs_index.py`); `lychee`
  in gate via pre-commit hook.
- **Dottrina compliance §1.1 attiva:** nessun asset senza licenza pubblicata
  commercial-clear (CC0/CC-BY).
- **Toolchain dev:** venv in `.venv/` (gitignored); dipendenze in `requirements-dev.txt`.
- Branch di lavoro **`develop`**; `master` solo per release.

## MANDATI PERMANENTI
- Nessun claim di accuratezza numerico pubblico prima del Gate L4.
- Zero-Allocation nel thread audio (RTNeural float32 CPU-only a runtime).
- STRP-001 obbligatorio per ogni decisione tecnica/architetturale aperta.
- Testing Doctrine: harness test-first; mutation testing come gate anti-pigrizia.
- Determinismo della pipeline dati: seed espliciti nel DNA-Trace (`ENGINEERING_STANDARDS §1`).
- Standard di codifica: `mypy --strict` + `ruff` puliti su ogni modulo Python (§3.1).
- Vendoring locale di binari di render e librerie SFZ/DrumGizmo (`ENGINEERING_STANDARDS §4`).
- Delega a sub-agenti come strumento di *governance del rischio*, non come divieto di
  scrittura diretta (`ENGINEERING_STANDARDS §8.2` — POL-AI-001 §3 non adottato).
- Tracking Board (`MASTER_SCHEDULING.md` §7) aggiornato a ogni sessione e checkpoint.
