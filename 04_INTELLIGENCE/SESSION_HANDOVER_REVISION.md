---
id: LIN-DT-HANDOVER-001
title: Session Handover — rev. post F0-T9b / F0-T2b (parser + provisioning)
type: registro
status: ACTIVE
phase: F0
domain: Operations
version: 2.1.0
updated: 2026-05-22
tags: [handover, registro, F0]
related: [LIN-DT-MSCHED-001, LIN-DT-REGAV-001]
supersedes: []
---

# SESSION HANDOVER - 2026-05-22 (rev. post F0-T9b / F0-T2b parser + provisioning)
**Task Attivo:** Fase F0 — avviata l'esecuzione del codice di pipeline.
**Stato:** **F0 attiva.** Chiusi F0-T1/T1b/T1c/T2a/T4a/T9a/T10-T14 + **F0-T9b**.
F0-T2b **◐ in corso** (parser fatto, provisioning fatto, adapter renderer da scrivere).

## ✅ Provisioning render engine — FATTO (2026-05-22)

Il provisioning, inizialmente assegnato al CEO, è stato eseguito dall'agente su sua
richiesta. Tutto vendorizzato in `vendor/` (manifest `vendor/README.md`; binari pesanti
git-ignored — `ENGINEERING_STANDARDS §4`):

- **`sfizz_render` 1.2.3** → `vendor/sfizz/sfizz_render`. Prebuilt ufficiale sfizz,
  eseguibile autonomo x86_64 (gira sotto Rosetta 2 su Apple Silicon).
- **Kit SFZ Karoryfer Frankensnare v2.100** (CC0, roster F0-T1b) →
  `vendor/sfz/frankensnare/`. 309 file `.sfz`; snare su GM key 38.
- **Catena verificata:** render di prova → WAV 44.1 kHz non-silent (peak 0.134).

CLI reale: `sfizz_render --sfz <f> --midi <f> --wav <f> --samplerate 44100`
(opz. `-b blocksize`, `-q quality`, `--log`). *Nota:* per **F0-T2c** servirà un kit
**DrumGizmo** (engine diverso) — provisioning analogo, **non ancora fatto**.

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
- **F0-T2b renderer:** provisioning fatto; resta da scrivere l'adapter `SfizzRenderer`
  + oracoli §6.3 → chiusura DoD. **Non più bloccato.**
- **F0-T2d** (Writer Gold-tensor + DNA-Trace) — pronto a partire: pura Python, **zero
  binari**, modulo critico, 16 oracoli già nell'harness. Non gated da nulla.
- **F0-T2c** (DrumGizmo) — bloccato sul provisioning di un kit DrumGizmo (engine diverso).
- **F0-T10 (corpo, P2)** e **F0-T4b** (gated da F0-T3): invariati.

## OBIETTIVO IMMEDIATO (prossima sessione)
**F0-T2b · adapter `SfizzRenderer`** — provisioning completo, si chiude il task:
implementare l'adapter CLI Sfizz (subprocess su `vendor/sfizz/sfizz_render` + watchdog
timeout, `ENGINEERING_STANDARDS §6`), riscrivendo l'ex-`MidiRenderer`; sostituire gli
oracoli §6.3 `skip` (render deterministico per seed, sr 44100, ampiezza [-1,1]) con i
test reali; chiudere il DoD. **In parallelo/alternativa: F0-T2d** (Writer Gold-tensor +
DNA-Trace, pura Python, 16 oracoli `@awaiting("F0-T2d")` pronti) — anch'esso sulla
critical path L2.

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
