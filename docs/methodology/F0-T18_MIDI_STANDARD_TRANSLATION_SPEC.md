---
title: "F0-T18 — MIDI Standard Translation Layer (STRP-001)"
id: LIN-DT-F0T18
status: LOCKED_v1.0.0
locked: true
locked_at: 2026-05-28
authors: [Strategic Advisor (Gianpiero Scappelloni)]
date: 2026-05-28
supersedes: []
related:
  - F0-T2a §1.1 (recipe midi_source — amendment: campo `standard`)
  - F0-T2a §3.3 (flat-25 target — invariato, consuma il MIDI canonico)
  - PIPELINE_AUDIT_2026-05-28 (origine: hihat edge GM 22/26 droppato)
  - midi_mapping_table.yaml (canonical-GM → bus, invariato)
  - midi_source_standards.yaml (NUOVO SSoT: source-note → articolazione canonica)
---

# F0-T18 · MIDI Standard Translation Layer — STRP-001 (LOCKED v1.0.0)

> **Status:** LOCKED v1.0.0 — Decision Lock CEO 2026-05-28. Origine: Pipeline
> Audit 2026-05-28 (MAJOR-1: hihat edge GM 22/26 droppato = 10 % degli onset).
> Direttiva CEO: «è imperativo una volta per tutte avere coerenza nelle
> traduzioni tra i vari standard, e pipeline coerenti, senza drop silenziosi».

## 0 · Inquadramento

**Il problema ricorrente.** Le sorgenti di eventi drum usano **standard di
numerazione MIDI diversi** per le stesse articolazioni fisiche. La nostra unica
sorgente MIDI reale (Magenta GMD) usa **Roland TD-11**; la `midi_mapping_table.yaml`
e i nostri assunti usano **General MIDI**; ogni kit DrumGizmo/SFZ ha la **propria**
tabella note→strumento. Le tre traduzioni erano **scollegate** → ognuna droppava
note diverse, in silenzio. Bug ricorrenti della stessa radice: Plan A (midimap
fantasma), e ora il MAJOR-1 dell'audit (hihat edge 22/26 = 10 % degli onset, 34 %
di tutto l'hihat, persi).

**Il principio cardine (Decision Lock CEO).** Ogni nota di una sorgente è *o*
mappata a un'articolazione canonica *o* elencata esplicitamente come ignorata
con motivo. **Tutto ciò che non è in nessuno dei due → errore forte.** Mai più
drop silenziosi.

## 1 · Competitor & Market

Il "drum mapping hell" (Roland TD vs GM vs Addictive vs SD3) è noto nell'industria.
Soluzione standard: **vocabolario canonico intermedio** + tabelle per-standard.
Magenta `groove` ha una `DRUM_MAP` che collassa Roland TD-11 → 9 classi; SD3 /
EZdrummer hanno preset di mapping interni per ogni e-kit.

## 2 · Open-Source Codebase Analysis

Magenta `groove.drums_encoder` (DRUM_MAP Roland→classi) è il riferimento diretto
per le righe `roland_td11`. `mido`/`pretty_midi` solo I/O. Pattern confermato:
canonical intermediate + per-source translation + registro esplicito degli scarti.

## 3 · UX/UI Impact

Nessuno (interno alla pipeline dati). Doc-only: amendment F0-T2a §1.1 (campo
`standard`), riferimento nel DOSSIER.

## 4 · Architettura (Tech Implementation Matrix)

### 4.1 · Single Source of Truth — `docs/specs/midi_source_standards.yaml`

- **`articulations`**: vocabolario canonico (15 articolazioni). Ognuna proietta
  su `render_gm` (nota GM che i midimap/SFZ conoscono) + `bus` (1-based, allineato
  a `midi_mapping_table.yaml`) + opzionale `hihat_opening`.
- **`standards`**: per ogni standard sorgente (`gm_standard`, `roland_td11`),
  mappa `nota-sorgente → articolazione`.
- **`ignored`**: registro esplicito di note scartate con motivo (oggi vuoto —
  copertura piena sulla GMD).

### 4.2 · Modulo `src/data_engineering/gold/midi_canonical.py`

`canonicalize_midi(midi, standard, out)` rimappa ogni note_on/note_off alla
`render_gm` dell'articolazione (es. TD-11 `22→42`, `26→46`, `58→43`); timing e
velocity preservati verbatim; note `ignored` droppate col loro delta-time
riassorbito; **note né mappate né ignorate → `CanonicalizationError`**.

### 4.3 · Integrazione `orchestrate.build_gold_sample`

Quando `recipe.midi_source.standard` è valorizzato, la canonicalizzazione gira
**una volta, prima dello split**: il MIDI canonico alimenta `last_onset`, render
**e** `build_target`. Le tre viste non possono più divergere — coerenza per
costruzione. `standard = None` = passthrough (sorgenti GM-native / sintetiche).

### 4.4 · Coherence Validator `tools/audit_midi_coherence.py` (gate pre-render)

Per ogni `(standard × kit)`:
- **Standard coverage** (vs corpus): nota corpus né mappata né ignorata → **BLOCKER**.
- **Render coverage**: `render_gm` di un'articolazione assente dal midimap del kit
  → **WARN** (rischio phantom-target).
- **Bus coverage**: invariante SSoT, ri-asserito.

Exit non-zero su BLOCKER (gate); `--strict` rende non-zero anche i WARN.

### 4.5 · Esito sulla GMD (1150 file, 446k onset)

| | Prima | Dopo |
| :-- | --: | --: |
| Onset droppati silenziosamente | 45 103 (10,1 %) | **0** |
| Hihat closed (file funk di prova) | 232 | **506** (+118 %) |
| BLOCKER del validator (roland_td11) | n/a | **0** |
| WARN del validator | n/a | 4 (china/splash/crash_2 su DRSKit/ShittyKit — limitazioni fisiche del kit, esplicite) |

## 5 · Executive Briefing — ratifiche

- **D1** Design completo (SSoT + canonicalizzazione + fail-loud + validator gate). ✅
- **D2** Fail-loud sui drop silenziosi (principio cardine). ✅
- **D3** Coherence validator come gate pre-render (obbligatorio prima di F2-T1). ✅

## 6 · Docs Update (Fase 6)

- `F0-T2a §1.1` — campo `standard` opzionale in `midi_source`.
- `DOSSIER §6.2` / §4 — nota sul layer di traduzione (puntatore a questo spec).
- `MASTER_SCHEDULING.md` — bullet 2026-05-28.
- **Oracoli §6.3**: 12 unit `test_midi_canonical` (SSoT load/validate, headline
  remap, fail-loud, determinismo, timing-preserve, coerenza inter-SSoT).

## 7 · Note operative

- **`ignored` vuoto oggi** = copertura piena sulla GMD. Una nuova sorgente
  (e-GMD TD-17, altri dataset) si aggiunge come nuovo blocco `standards.<nome>`;
  il validator forza a coprire ogni nota o a registrarla in `ignored`.
- **WARN china/splash/crash_2**: ShittyKit ha 1 solo crash fisico, DRSKit non ha
  china. Sono limitazioni del kit, non bug di mapping; il validator le rende
  esplicite. Volume basso (<0,5 % degli onset). Resa futura: routing kit-aware o
  esclusione mirata — fuori scope v1.0.

## 8 · Costo & Timeline

- Implementazione locale: completata in sessione. **$0 Azure.**
- Re-render mini-L3 + misura lift hihat: il gate empirico (task F0-T18 follow-up).
- **Sblocca F2-T1 in sicurezza**: il render full-scale ora canonicalizza → niente
  hihat sventrato a scala 1000×.

---

*Spec LOCKED v1.0.0 — 2026-05-28.*
