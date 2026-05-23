---
id: LIN-DT-SPEC-F0T15PRE
title: F0-T15-pre — MIDI Augmentation Spec (Time/Velocity/Component) — STRP-001
type: spec
status: LOCKED
phase: F0
domain: Data Engineering
version: 1.0.0
updated: 2026-05-23
tags: [augmentation, midi, pre-render, STRP-001, F0-T15-pre, recipe-matrix]
related: [LIN-DT-DOSSIER-001, LIN-DT-SPEC-F0T2a, LIN-DT-SPEC-F0T5, LIN-DT-MSCHED-001]
supersedes: []
---

# 🎛️ F0-T15-pre — MIDI Augmentation Spec (Pre-Rendering)

> **Status: LOCKED — Decision Lock CEO 2026-05-23.**
> Tutte e 4 le raccomandazioni della §5 (B1 range Opzione B · B2 `k=2` + baseline ·
> B3 DNA-Trace 7-segment · B4 storage Azure ~$90) approvate. La fase 6 (Docs Update)
> è applicata a valle: [`DOSSIER §3.1`](DOSSIER_TECNICO.md#aug-prerender),
> [`F0-T2a §3.7`](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#dna-trace-format),
> [`AUGMENTATION_AUDIT_BACKLOG`](AUGMENTATION_AUDIT_BACKLOG.md). Implementazione
> in [F0-T16-pre](../../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks).

## 0. Sintesi esecutiva (1 paragrafo)

Il DOSSIER §3.1 prescrive **MIDI Jittering pre-render** (Time / Velocity / Component
Dropping) ma senza parametri operativi: range numerici, `k` varianti per MIDI sorgente,
seed policy e ordering nella recipe matrix non erano fissati. La letteratura ADT moderna
(E-GMD, Jacques & Roebel, Stein) **non fa MIDI jittering** — costruisce diversità via
`M` grande (43–512 kit/preset) + audio augmentation. Noi abbiamo `M=10` (roster F0-T1b)
→ il MIDI jittering recupera **caos esecutivo** (imperfezione di timing, ghost notes,
dropped components) — ortogonale alla diversità timbrica. Raccomandazione: implementare
le tre voci §3.1 con range **ricalibrati sulla GMD** (che è già umana), `k=2` varianti
sintetizzate + 1 baseline non jitterata, seed deterministico per riproducibilità, e
recipe matrix riproiettata a `MIDI × jitter-variant × engine`. Costo Azure: $0 nella
fase di build (locale); incremento del render budget F2-T1 da ~$3.5 a ~$10 (×3 sulla
calibrazione L2) → resta dentro $55 allocati.

## 1. Competitor & Market Analysis

| Sistema | M (kit/preset) | MIDI augmentation? | Augmentation prevalente |
| :-- | :-- | :-- | :-- |
| **E-GMD / Magenta** (Callender et al., 2020) | 43 kit | ❌ (quantization solo in ablation) | shuffled mixup audio · M-diversity timbrica |
| **ADT-CNN** (Jacques & Roebel, 2019) | n.d. | ❌ | noise remixing · attack remixing · transposition · envelope transposition |
| **ADT synthetic-to-real** (Stein et al., 2024) | 512 preset | ❌ (composizione di loop pro) | composition layering + M-diversity di preset |
| **OP-NeuroTrigger** (questo progetto) | **10 kit** | **✅ (DOSSIER §3.1)** | recipe matrix `MIDI × jitter × engine` + audio aug post-render (F0-T15-post) |

**Lettura strategica.** I sistemi SOTA con `M ≥ 43` evitano il MIDI jittering perché la
diversità di esecuzione viene a costo zero dalla varietà di sample (kit umani diversi
suonano già lo stesso MIDI in modo diverso) + dalla cattura **performativa** (E-GMD ha
human-performed velocity annotations). Noi non possiamo seguire quel pattern in modo
puro: `M=10` (vincolo Self-Evident Commercial License, F0-T1b) e i campioni dei kit SFZ
sono *deterministici* per velocity-layer — la stessa MIDI dà sempre lo stesso WAV. Il
MIDI jittering è il sostituto razionale per iniettare il caos che `M` grande darebbe
naturalmente, senza dover ricorrere a kit non liberi.

## 2. Open-Source Codebase Analysis

| Library | API | Determinismo | Adatto qui |
| :-- | :-- | :-- | :-- |
| **`mido`** (MIT) | basso livello (note_on, note_off, ticks) | ✅ esplicito | ✅ — già usato in `tools/gen_mini_batch_fixtures.py` per il mini-batch F0-T2e |
| `pretty_midi` (MIT) | medio livello (seconds + note objects) | ✅ | conversione comoda secondi↔tick, ma layer extra |
| `partitura` (Apache 2.0) | alto livello (musicologia) | ✅ | over-engineered per il nostro caso |
| `music21` (BSD) | molto alto livello (analisi) | ⚠️ | troppo pesante per data pipeline |
| `muspy` (MIT) | alto livello (toolkit ML) | ✅ | candidato, ma `mido` è già nella codebase |

**Pattern stabili osservati su GitHub:**

- **Time jittering** (es. `magenta/groove-converter`, `music-augmentation`): shift
  uniforme o gaussiano dell'onset, con clipping ai bound del tick-grid; conservazione
  della *durata* tra note_on / note_off (jitter solo l'onset, non la durata).
- **Velocity jittering**: shift additivo gaussiano, clipping `[1, 127]`; ghost
  detection via soglia (`velocity ≤ 40` → candidate ghost).
- **Component dropping**: maschera a livello di nota — un singolo pitch o pitch-class
  rimosso da una *zona temporale* (non dall'intera traccia, altrimenti si perde
  l'evento ritmico).
- **Seed policy** (in tutte le pipeline maturi): un seed master per la run + seed
  derivati `seed_i = hash(master_seed, source_midi_id, variant_idx)` → idempotenza
  bit-per-bit.

**Decisione:** usiamo `mido` (zero nuova dipendenza). Pattern di seeding via
`numpy.random.default_rng(derived_seed)` come in `shard_writer.py` (F0-T5) e
`orchestrate.py` (F0-T2e) — coerente con [`ENGINEERING_STANDARDS §1 — determinismo`](../../04_INTELLIGENCE/ENGINEERING_STANDARDS.md#determinism).

## 3. UX/UI Impact

**Non applicabile.** F0-T15-pre è una decisione di pipeline dati offline; nessun impatto
sull'UI del plugin. Conservato per completezza STRP-001.

## 4. Tech Implementation Matrix

### 4.1 Scelte di design

| Asse | Opzione A (DOSSIER §3.1 letterale) | Opzione B (ricalibrata) | Opzione C (skip) | Raccomandazione |
| :-- | :-- | :-- | :-- | :-- |
| **Time Jittering — range** | ±2 ms → ±15 ms (uniforme) | ±2 ms → **±5 ms** (gaussiano σ=2 ms, clip ±5 ms) | nessuno | **B** — GMD è già umana, ±15 ms creerebbe artifacts oltre la tolleranza del target (±3 ms gaussian smearing di F0-T2a §3.3) |
| **Flams artificiali** | 5% delle note → doppio colpo a ~10–30 ms | 5% delle note → doppio colpo a **15–25 ms** (uniforme) | nessuno | **A modificata** — distanza inter-flam fissa nel range tipico, lookahead PDC ~100 ms ha headroom |
| **Velocity Jittering** | Ghost Masking + Global Gain Shift | additivo gaussiano σ=8 + Ghost Masking (vel ≤ 40 → ×0.3..1.0) + Global Gain Shift ×0.5..2.0 | nessuno | **B esplicita** — DOSSIER vago, qui numerico |
| **Component Dropping** | 10% di componenti | **10% per zona temporale** di 2 s (uniforme); mai droppare se kick+snare da soli (groove-skeleton) | nessuno | **B con clausola** — evita di disintegrare il groove |
| **k varianti per MIDI sorgente** | non specificato | **k=2** jitter-variants + **1 baseline** = ×3 sulla matrix | k=1 | **B** — equilibrio costo/varietà |
| **Seed policy** | non specificata | `seed = sha256(master_seed ‖ source_midi_id ‖ variant_idx)[:8]` | global RNG | **B** — bit-deterministic, replay perfetto |
| **Ordering nella matrix** | non specificato | pre-shuffle deterministico globale (F0-T5 §5.5) | sequenziale | **B** — coerente con sharding |

### 4.2 Impatto sul costo render F2-T1

| Voce | Pre-emendamento | Post-emendamento (`k=2` + baseline) | Headroom §5 |
| :-- | :-- | :-- | :-- |
| Recipe matrix | `\|MIDI\| × \|engine\|` ≈ N entries | `\|MIDI\| × 3 × \|engine\|` ≈ 3N entries | — |
| Stima costo render (calibrazione L2) | ~$3.5 | **~$10.5** | $55 allocati → -$44.5 residui per Tier 2/3 |
| Tempo wall-clock (D16s_v3) | ~5 h | **~15 h** | dentro 27 gg di credito |
| Storage Gold (1.5 TB stima) | 1.5 TB | **~4.5 TB** *(scenario peggiore)* | Blob LRS — capacità ok; storage cost ~$30 → **~$90** per il mese |

⚠️ **Punto sensibile.** Il moltiplicatore `×3` sullo storage va verificato contro
l'allocazione storage di §5 ($30 base). A scenario peggiore: ~$90 storage + ~$10.5
render + audio aug + training = ancora dentro $200, ma il margine si stringe.

**Mitigazione:** `k=2` può ridursi a `k=1` (1 baseline + 1 jitter-variant) se a CP-1 il
saldo Azure lo richiede — la decisione è economica, non architetturale; lo schema
sopporta entrambi i regimi.

### 4.3 Interazione con altri Decision Lock

| Decision Lock | Interazione | Risoluzione |
| :-- | :-- | :-- |
| **T1-prep-A pairing forzato MIDI×Engine** | il MIDI jitter è *prima* dell'engine pairing → la matrix diventa `MIDI × jitter-variant × engine` (3 assi) | jitter-variants sono "MIDI logici" — l'engine pairing si applica sopra invariato |
| **T1-prep-B tail standardization (0.5 s)** | il jitter sposta l'ultimo onset → `last_onset_s` cambia per variant → `n_sample_target` ricomputato | invariato — già supportato da `last_onset_seconds()` |
| **F0-T2a §3.7 DNA-Trace lineage** | il barcode deve registrare la jitter-variant | aggiungere segmento `J{variant_idx:02d}` al barcode 6-segment → 7-segment |
| **F0-T5 sharding manifest** | `recipe_matrix_seed` deve coprire anche la jitter dimension | seed master già unico per run; jitter seed derivato (§2) |

## 5. Executive Briefing — Raccomandazione strategica al CEO

### Ratifica

1. **Implementare le 3 voci §3.1** (Time Jittering, Velocity Jittering, Component
   Dropping) con i range **Opzione B** (§4.1) — ricalibrati su GMD umana.

2. **`k = 2` varianti jitter + 1 baseline = ×3 sulla recipe matrix.** Riserva di scala:
   se a CP-1 il saldo Azure è sotto-soglia, abbattere `k` a 1.

3. **Seed policy bit-deterministica** — master seed + derivati per (source MIDI, variant
   idx) via sha256; `numpy.random.default_rng` per consumo.

4. **DNA-Trace 7-segment** (§4.3) — il segmento J permette di filtrare per variant in
   evaluation, e di rifare bit-per-bit un singolo campione.

5. **Recipe matrix `T1-prep-A` emendata** — 3 assi (`MIDI × jitter × engine`) con
   pre-shuffle deterministico (F0-T5 §5.5).

### Cosa non si fa

- **Nessun pitch-shifting o time-stretching del MIDI** — il primo cambia il timbro nel
  render (overlap con M-diversity), il secondo *sposta la ground truth* (audit backlog
  §5, regola 1). Entrambi vietati.

- **Nessuna augmentation "groove-distruttiva"** — pattern dropping che azzera kick +
  snare insieme (clausola §4.1).

- **Nessun cross-MIDI mixup** — riservato all'audio side (F0-T15-post).

### Costo

- **Build (F0-T16-pre):** $0 (locale Mac M5, MIDI è leggero).
- **Render (F2-T1):** +$7 vs baseline ($3.5 → $10.5); storage +$60 vs baseline
  ($30 → $90). Totale F2-T1 ~$100. **Dentro $200 con margine $100.**
- **Training/eval:** invariato.

### Rischi

- **R1.** Il MIDI jittering *modella* caos esecutivo che la GMD ha *già* (è human-performed).
  Mitigazione: range ridotti (Opzione B); `k=2` modesto; ablation post-L4 per misurare il
  guadagno marginale.
- **R2.** Component dropping può creare grooves "innaturali" (es. solo hi-hat senza
  kick/snare). Mitigazione: clausola groove-skeleton (§4.1) preserva kick+snare in
  almeno 1 zona temporale per campione.
- **R3.** Lo storage Gold cresce ×3. Mitigazione: scaling-knob su `k` (1 o 2); il
  manifest registra `k` effettivo → riproducibilità intatta.

### Bivi richiesti al CEO

- **B1.** Approvare Opzione B per i 3 range (§4.1)? *(default raccomandato: sì)*
- **B2.** Approvare `k = 2` varianti? *(default: sì; CP-1 lo rivedrà se serve)*
- **B3.** Approvare DNA-Trace 7-segment? *(default: sì — minore impatto sulla codebase
  di F0-T2a §3.7)*
- **B4.** Approvare incremento storage da $30 a ~$90? *(default: sì — dentro $200)*

## 6. Docs Update (post-approvazione)

- `DOSSIER §3.1` — sostituire prosa vaga con tabella parametrica (range + `k` + seed).
- `F0-T2a §3.7` — barcode 6→7 segment, definire formato segmento `J`.
- `MASTER_SCHEDULING T1-prep-A` — già emendato (recipe matrix 3-assi).
- `AUGMENTATION_AUDIT_BACKLOG` — sezione MIDI segnata come superseded da questo doc.
- Implementazione **F0-T16-pre** sblocca: `src/data_engineering/midi_augment/` +
  oracoli `tests/unit/midi_augment/` + estensione `tools/build_recipe_matrix.py`.

---

*Documento STRP-001 (LIN-DT-SPEC-F0T15PRE) — Strategic Advisor: Gianpiero Scappelloni.
Decision Lock CEO atteso prima di passare alla fase 6 (Docs Update) e all'implementazione
F0-T16-pre.*
