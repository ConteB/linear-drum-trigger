---
id: LIN-DT-LICVER-F0T1
title: F0-T1 — Verifica Licenze (Working Artifact)
type: registro
status: ACTIVE
phase: F0
domain: Legal / Compliance
version: 1.0.0
updated: 2026-05-20
tags: [compliance, licensing, F0-T1]
related: [LIN-DT-DPL-001, LIN-DT-ROSTER-F0T1b]
supersedes: []
---

# 🔍 F0-T1 — VERIFICA LICENZE (Working Artifact)
**Task:** F0-T1 Compliance licenze · **Avviato:** 2026-05-20 · **Stato:** ◐ IN CORSO
**Riferimento:** `MASTER_SCHEDULING.md` §6 F0-T1 · `DATA_PROVENANCE_LOG.md`

> ⚠️ **AGGIORNAMENTO 2026-05-20 — la sezione §3 (outreach) è SUPERATA.**
> Decision Lock del CEO: dottrina **"Self-Evident Commercial License"**
> (`DATA_PROVENANCE_LOG.md` §1.1). Si decide per pura lettura della licenza già
> pubblicata — **niente email, niente divulgazione del progetto**. Le 3 bozze di outreach
> in §3 sono **annullate**. Verdetti aggiornati: **ENST-Drums** e **MedleyDB** → esclusi
> (research-only / NonCommercial); **SM Drums** → escluso (nessuna licenza formale, sola
> dichiarazione informale). La diversità di kit è ricostruita da
> `F0-T1b_KIT_ROSTER_SURVEY.md`. La matrice §1 e le fonti §2 restano valide come
> fotografia della ricerca; §3 va letto come storico.

## 1. Matrice di Verifica

| Asset | Classe | Licenza accertata (fonte primaria) | Uso previsto | Verdetto | Azione | Decadenza |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| **SM Drums** (AUDIO-01) | A — Training | Dichiarazioni pubbliche dell'autore: *royalty-free, uso libero commerciale e non, "anyone for anything"*. **Nessun documento di licenza formale** sul sito primario. Redistributore SFZ Instruments lo classifica "Public Domain". | Render multi-layer Ludwig → audio dato in pasto al training | 🟡 **PERMISSIVO ma non formalizzato** | Conferma scritta dall'autore (bozza §3.1) | **CP-1 / 2026-05-30** |
| **ENST-Drums** (EVAL-01) | B — Eval-only | User License Agreement Télécom Paris: *"limited to research purposes, **no commercial use is possible**"*; richiede firma di un accordo prima del download. | Holdout Test Set (validazione interna a supporto di prodotto commerciale) | 🔴 **CRITICO** — la licenza vieta l'uso commerciale *tout court*; la validazione interna a supporto di un prodotto a pagamento non è chiaramente coperta | Quesito formale al licensor (bozza §3.2) + valutare Piano B | **CP-2 / 2026-06-09** |
| **MedleyDB** (EVAL-02) | B — Eval-only | CC BY-NC-SA 4.0 — *non-commercial*; gli autori chiedono di non ripubblicare il dataset. | Franken-Mix (test Stealth Mix Mode) | 🟠 **A RISCHIO** — la clausola NC rende la validazione a supporto di un prodotto commerciale una zona grigia | Quesito formale agli autori (bozza §3.3) + valutare Piano B | **CP-2 / 2026-06-09** |

**Lettura strategica:** SM Drums è quasi certamente utilizzabile — manca solo la
formalizzazione scritta, coerente con lo standard "Zero-Risk IP / Audit-Ready" del DPL.
ENST-Drums e MedleyDB sono invece **strutturalmente in tensione** con un prodotto
commerciale: anche il solo uso *evaluation-only* interno è una zona grigia sotto licenze
"research-only" / "NC". Il Piano B (registrazioni proprietarie annotate / Validation
ridotto a Franken-Mix + Ocular Proof) va considerato realistico, non eccezionale.

## 2. Dettaglio Fonti

### SM Drums (AUDIO-01)
- Autore: Scott McLean (con Tod Stillwell, Suleiman Ali). Kit Ludwig anni '60, multi-mic,
  fino a 127 layer di velocity.
- Sito primario `smmdrums.wordpress.com`: home con soli link di download, **nessun file
  di licenza formale** esposto (verificato 2026-05-20).
- Dichiarazioni riportate da fonti secondarie: "royalty free use by anyone for anything",
  "for both commercial and private use", "Creative Commons Royalty-Free".
- Redistributore `sfzinstruments.github.io` (formato SFZ — quello che useremo con Sfizz):
  licenza dichiarata **"Public Domain"**.
- ⚠️ Gap: nessuna delle fonti affronta esplicitamente il caso d'uso *"training di una rete
  neurale su audio renderizzato dai sample"*. Serve conferma scritta puntuale.

### ENST-Drums (EVAL-01)
- Distributore: ADASP Group, Télécom Paris. License agreement pubblico (PDF Télécom Paris).
- Testo accertato: uso **limitato a fini di ricerca, nessun uso commerciale possibile**;
  firma obbligatoria di un accordo prima del download; citazione obbligatoria del paper
  Gillet & Richard.

### MedleyDB (EVAL-02)
- Distributore: NYU MARL (Bittner et al.). Licenza **CC BY-NC-SA 4.0**.
- Uso gratuito solo per **ricerca non commerciale**; ridistribuzione del dataset
  scoraggiata senza consenso.

## 3. Bozze di Outreach — DA INOLTRARE A CURA DEL CEO

### 3.1 — Email a Scott McLean (SM Drums)
> **Canale:** da identificare — opzioni: form di contatto WordPress su `smmdrums.wordpress.com`,
> messaggio privato all'autore sul forum KVR Audio, o tramite Critical Vibrations.

**Oggetto:** SM Drums — written permission request (commercial ML training use)

> Hello Scott,
>
> I'm developing a commercial audio software product and would like to use the SM Drums
> library as one of the sound sources. Your published terms describe the samples as
> royalty-free for any use; to keep our legal record audit-ready I'd like a brief written
> confirmation covering our specific case:
>
> 1. We render audio from the SM Drums samples and use that rendered audio **as training
>    data for a neural network**. The original samples are never redistributed.
> 2. The resulting neural network (a transformative derivative — learned weights, not
>    audio) ships inside a **paid commercial product**.
>
> Can you confirm in writing that this use is permitted under your royalty-free terms?
> A one-line reply to this email is sufficient for our records.
>
> Thank you for making such a remarkable instrument freely available.
> — [Nome], OpenPhase / Linear Division

### 3.2 — Quesito formale al licensor ENST-Drums
> **Canale:** ADASP Group, Télécom Paris (referente del license agreement, Gaël Richard).

**Oggetto:** ENST-Drums — clarification on internal evaluation use

> Dear ADASP Group,
>
> We would like to use the ENST-Drums database **strictly as an internal hold-out
> evaluation set** — never for training, never redistributed, never embedded in any
> product. The product we are evaluating is, however, commercial.
>
> Could you confirm whether the User License Agreement permits this purely internal,
> evaluation-only use, given the "research purposes only / no commercial use" clause?
> If not, we will exclude ENST-Drums entirely.
>
> Thank you. — [Nome], OpenPhase / Linear Division

### 3.3 — Quesito formale agli autori MedleyDB
> **Canale:** NYU MARL (autori MedleyDB, contatto Justin Salamon / Rachel Bittner).

**Oggetto:** MedleyDB — internal evaluation use under CC BY-NC-SA 4.0

> Dear MedleyDB authors,
>
> We intend to use MedleyDB **only for internal evaluation** (a "Franken-Mix" robustness
> test), with no redistribution and no use as training data. The product under evaluation
> is commercial. We would like your view on whether this internal evaluation-only use is
> compatible with the NonCommercial clause of CC BY-NC-SA 4.0. If it is not, we will
> exclude MedleyDB and rely on alternative validation material.
>
> Thank you. — [Nome], OpenPhase / Linear Division

## 4. Stato DoD

- [x] Licenze identificate e verificate su fonte primaria.
- [x] Matrice di verifica prodotta.
- [x] Bozze di outreach redatte.
- [ ] **SM Drums** — conferma scritta ricevuta e archiviata nel DPL → entro **CP-1 / 2026-05-30**.
- [ ] **ENST-Drums / MedleyDB** — risposta del licensor ricevuta e archiviata → entro **CP-2 / 2026-06-09**.
- [ ] Decisione Piano B (se necessaria) registrata al checkpoint.

---
*F0-T1 working artifact — OpenPhase SOP-004.*
