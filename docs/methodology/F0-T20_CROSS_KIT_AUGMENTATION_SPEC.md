---
title: "F0-T20 · Cross-Kit Combinatorial Augmentation (Franken-Kit) — STRP-001"
tags: [methodology, augmentation, franken-kit, cross-kit, render, F0-T20, STRP-001]
status: LOCKED
---

# F0-T20 · Cross-Kit Combinatorial Augmentation ("Franken-Kit") — STRP-001

**Origine:** osservazione del CEO (2026-05-30) — durante l'audit di readiness F2-T1
è emerso che la pipeline di augmentation **non** combina pezzi di kit diversi. Il CEO
ricorda di averne parlato; l'idea non è mai entrata in spec/codice (persa). Direttiva:
augmentation *più spinta* che assembli ogni campione come un **kit ibrido** pescando
ogni strumento (kick, snare, hihat, tom, ride, crash…) da kit **diversi** dell'intero
roster — non limitato ai rullanti di Frankensnare.

**Tesi.** È la leva mancante contro il problema cardine del progetto: la rete impara il
**timbro del kit** invece dell'**evento fisico** (il floor saturo ~0.15 del mini-L3, il
movente di F0-T4e). F0-T4e ha tolto il fingerprint dal *layout dei canali*; il
franken-kit toglie il fingerprint dal *timbro* — ogni campione una combinazione timbrica
mai vista → diversità combinatoria `N_kick × N_snare × N_hihat × …`.

> **Stato:** **LOCKED v1.0.0 — Decision Lock CEO 2026-05-30.** Fasi 1-5 compilate e
> ratificate (D1-D8 sotto). Implementazione = sotto-task `[F]` **F0-T20b**. Fase 6
> (Docs Update downstream) a valle dell'implementazione.

## Decision Lock v1.0.0 (CEO 2026-05-30)

| D | Decisione | Voto CEO |
| :- | :- | :- |
| **D1** | Approccio **A** (render per-strumento + somma 8-bus) | ✅ ratificato |
| **D2** | **Within-engine v1.0** (DG-franken + SFZ-franken separati; cross-engine → v1.1) | ✅ ratificato |
| **D3** | Composizione dataset **~50% franken + 50% single-kit** (ancore timbriche reali) | ✅ ratificato |
| **D4** | Bleed per-kit sommato accettato (room-invariance); reverb unificante opzionale | ✅ default |
| **D5** | **Entrambi**: stem ground-truth esatti per i campioni **franken** **+** Demucs Stem-Isolate sui campioni **single-kit reali** (la rete impara anche gli artefatti di separazione reali) | ✅ ratificato (variante "keep both") |
| **D6** | DNA-Trace registra la provenienza per-bus `{bus: kit}` | ✅ default |
| **D7** | Moltiplicatore render ×N autorizzato (dentro budget, cap di frazione via D3) | ✅ implicito |
| **D8** | Riammettere **Frankensnare** come sorgente-rullante nel pool franken; **VSCO2CE** resta saboteur (non kit) | ✅ default |

**Nota D5 (keep both).** Lo Stem-Isolate (F0-T15-post §3.2) non viene soppiantato ma
**sdoppiato**: i campioni franken-kit usano gli stem **esatti** del render per-strumento
(zero artefatti, abilita source-separation R&D); i campioni single-kit reali (il 50% di
D3) continuano a passare per **Demucs AI-Isolation** → la rete vede *entrambe* le
distribuzioni (isolamento perfetto E artefatti di separazione reali del campo).

---

## Fase 1 — Competitor & Market Analysis

### 1.1 Ricerca accademica (MIR / drum transcription)
La ricombinazione cross-kit di stem isolati è una tecnica **pubblicata e validata**:

- **Kit-swap augmentation** + **doubling augmentation** (media dello stesso pattern da
  kit diversi) + pitch-shift sono tecniche standard nella letteratura ADT recente.
- **StemGMD** (Mezza et al., Politecnico di Milano, *Toward Deep Drum Source
  Separation*, 2024): dataset di **stem per-strumento isolati**, sintetizzati dalla
  **Groove MIDI Dataset** con **10 kit acustici**, su un **canonical nine-piece**
  (Kick · Snare · High Tom · Low-Mid Tom · High Floor Tom · Closed HH · Open HH ·
  Crash · Ride). 1224 ore. Le mixture si ottengono **sommando i 9 stem sintetizzati**
  (principio di sovrapposizione). Costruito *esplicitamente* per le "countless data
  augmentation possibilities" che gli stem isolati abilitano.
- **LarsNet** (modello U-Net bank trained su StemGMD): valutato su **kit held-out**,
  **generalizza al timbro non visto** — prova empirica che la diversità timbrica via
  stem cross-kit produce timbre-invariance.

**Lettura strategica.** (a) La nostra tassonomia flat-28 a 9 canali **coincide** col
canonical nine-piece di StemGMD. (b) La nostra sorgente MIDI **è** la GMD. (c) Il
nostro target è proprio la timbre-invariance cross-kit. Siamo già sul binario; ci manca
solo lo step di ricombinazione.

### 1.2 Industria (drum production)
Superior Drummer 3, EZdrummer, GetGood Drums, Steven Slate Drums, addictive Drums:
tutti permettono all'utente di **costruire kit custom** mescolando strumenti da
librerie diverse (kick di una, rullante di un'altra…). Il "custom kit building" è la
**norma di settore**. Il franken-kit augmentation **simula combinatorialmente** ciò che
ogni fonico fa a mano → il modello vede la stessa varietà che incontrerà sul campo.

---

## Fase 2 — Open-Source Codebase Analysis

- **`polimi-ispl/larsnet`** (GitHub): pipeline StemGMD → sintesi **per-strumento** dalla
  GMD → **somma** in mixture (superposition preservata, 1:1 con il MIDI). Pattern
  stabile e replicato: *render isolato per strumento → ricombina*.
- **Pipeline nostra (esistente):** `orchestrate.build_gold_sample` renderizza il MIDI
  completo su **un** kit → 8-bus multi-mic + target flat-28. Il franken-kit è
  un'**estensione naturale**: split MIDI per-strumento → render ogni strumento sul kit
  assegnato → somma i render 8-bus. Riusa `_render`, `target_builder`, `gold_writer`
  invariati; cambia solo l'orchestrazione (loop per-strumento + somma).
- **Side-benefit architetturale:** rendere per-strumento produce **stem isolati esatti**
  come sottoprodotto → potrebbe **soppiantare** lo "Stem Isolate" via Demucs (F0-T15-post
  §3.2, isolamento *AI-stimato e imperfetto*) con isolamento **ground-truth perfetto, zero
  artefatti Demucs**, e abilita R&D futuro di source-separation (OP-NeuroPercussion,
  DOSSIER §3.4) — esattamente il caso d'uso di StemGMD.

---

## Fase 3 — UX/UI Impact

Nessun impatto sull'UI del plugin (è pipeline-dati). Impatti indiretti, coerenti con
l'estetica **"Laboratory Precision"**:
- **Claim di prodotto rafforzato:** "funziona su QUALSIASI kit" diventa vero *by
  construction* (la rete non ha mai visto un kit "puro" abbastanza da memorizzarlo).
- **DNA-Trace** guadagna la **provenienza per-bus** (`{bus: kit}`) → debuggabilità
  totale di quale kit ha generato quale strumento di ogni campione.

---

## Fase 4 — Tech Implementation Matrix

Linguaggio: **Python** (data pipeline; nessun C++, F4 non toccato).

### 4.1 Approcci

| | **A — Render per-strumento + somma** *(raccomandato)* | **B — Render full-kit + stem-mix per-bus** |
| :- | :- | :- |
| Metodo | split MIDI per strumento canonico → render ognuno sul kit assegnato → somma i buffer 8-bus | render il groove su K kit → per ogni bus prendi quello di un kit a caso |
| Isolamento | **esatto** (un solo strumento per render) | sporco (ogni bus full-kit porta il bleed di tutti) |
| Bleed | per-strumento naturale del suo kit (fisicamente plausibile) | **double-counting** del bleed (kick-bus di A + snare-bus di B contengono entrambi tutto) |
| Stem ground-truth | ✅ sì (supera Demucs) | ❌ no |
| Costo render | `~N_strumenti ×` per campione (N≈4-6 tipico) | `K ×` per campione |
| Allineamento | deterministico (stesso MIDI timing) | deterministico |
| Precedente | **StemGMD / LarsNet** (superposition) | nessuno |

→ **Approccio A** vince su isolamento, fedeltà del bleed, stem ground-truth e aderenza
al precedente pubblicato.

### 4.2 Aderenza ai mandati Linear
- **Determinismo (ENG §1):** l'assegnazione strumento→kit è derivata da
  `sha256(master_seed ‖ source_midi_id ‖ variant_idx ‖ bus)` → replay byte-identico,
  registrato in `manifest.json` + DNA-Trace. ✅
- **Fail-loud (ENG §6):** ogni render per-strumento è già fail-loud; somma verificata
  (no NaN/inf, peak ∈ (0,1] — chiude anche M6 dell'audit F2-T1). ✅
- **Contratto dati:** il **target flat-28 è invariato** (stesso groove MIDI → stesso
  target); cambia solo l'audio. Nessun re-design del contratto. ✅

### 4.3 Rischi e mitigazioni
| Rischio | Mitigazione |
| :- | :- |
| **Costo render ×N** su F2-T1 (1.5 TB → potenzialmente ×4-6) | (a) franken-kit su una **frazione** del dataset (es. 50%); (b) **k-varianti** limitate; (c) il budget render ha enorme headroom (audit L2: ~$3.5 su $55 allocati → anche ×6 = ~$21). Decisione D7. |
| **Room/bleed non unificato** (ogni strumento porta la stanza del suo kit → spazio acustico "impossibile") | **È una feature, non un bug:** insegna room-invariance. Per realismo opzionale, reverb unificante post-somma (già in F0-T15-post §3.4). Decisione D4. |
| **Cross-engine** (kick DG multitrack_full 8-mic + snare SFZ solo_stereo 2-mic → layout incompatibile) | v1.0 **franken WITHIN engine** (DG-franken + SFZ-franken separati); cross-engine rinviato a v1.1 (richiede normalizzazione layout). Decisione D2. |
| **Coerenza dinamica** (velocity scale diverse tra kit) | velocity normalizzata dal target builder già oggi; spot-check. |
| **Esplosione combinatoria** (troppe combo → nessun anchor di kit reale) | tenere una quota di campioni **single-kit reali** come ancore (D3). |

### 4.4 Impatto su F2-T1 (timing)
Il franken-kit **cambia come si renderizza il Gold** → idealmente **deciso prima di
F2-T1** (renderizzare ora single-kit e poi rifare = viola use-it-or-lose-it §1.1).
Sblocca anche la riconsiderazione del roster (Frankensnare/VSCO2CE: con il franken-kit,
Frankensnare torna utile come **sorgente di rullanti**; VSCO2CE resta saboteur).

---

## Fase 5 — Executive Briefing (per Decision Lock CEO)

**Raccomandazione:** adottare il **Cross-Kit Combinatorial Augmentation (Approccio A)**
come parte della pipeline di render F2-T1, su evidenza StemGMD/LarsNet + l'allineamento
nativo (GMD + 9 canali). Punti di decisione:

- **D1 — Approccio.** A (render per-strumento + somma). *Rec: A.*
- **D2 — Engine scope.** v1.0 within-engine (DG-franken + SFZ-franken); cross-engine
  v1.1. *Rec: within-engine v1.0.*
- **D3 — Composizione dataset.** Quota franken vs single-kit reale (es. 50/50, o
  k-varianti franken per groove + 1 baseline single-kit). *Rec: ~50% franken + 50%
  single-kit anchors.*
- **D4 — Room/bleed.** Accettare il bleed per-kit sommato (room-invariance) vs reverb
  unificante. *Rec: accettare; reverb unificante opzionale via pipeline esistente.*
- **D5 — Supersede Demucs Stem-Isolate?** Usare gli stem ground-truth esatti del render
  per-strumento al posto dell'isolamento Demucs AI (F0-T15-post §3.2). *Rec: sì, grande
  win (zero artefatti + abilita source-separation R&D).*
- **D6 — Provenienza.** DNA-Trace registra `{bus: kit}` per campione. *Rec: sì.*
- **D7 — Budget compute.** Autorizzare il moltiplicatore render ×N (mitigato da D3 +
  headroom budget). *Rec: sì, con cap di frazione.*
- **D8 — Roster.** Con il franken-kit, riammettere Frankensnare come sorgente-rullante;
  VSCO2CE resta saboteur (non kit). *Rec: sì.*

**Costo Azure:** $0 fino al render (sviluppo+test locale); a F2-T1 il moltiplicatore è
dentro il budget con cap di frazione.

---

## Fase 6 — Docs Update (a valle dell'approvazione)

*Pending Decision Lock.* All'approvazione: aggiornare `DOSSIER §3` (nuovo livello
augmentation), `F0-T15-post` (Demucs Stem-Isolate → render-stem esatto se D5),
`F0-T2a §3.7` (DNA-Trace provenienza per-bus), `MASTER_SCHEDULING §6/§7` (task F0-T20 +
gate F2-T1), `kit_dialect_map`/roster (D8). Implementazione = sotto-task `[F]` separato.

---
*STRP-001 — F0-T20. Fasi 1-5 compilate 2026-05-30. Attende Executive Briefing /
Decision Lock CEO prima di scrivere codice (cultura Decision-Lock).*
