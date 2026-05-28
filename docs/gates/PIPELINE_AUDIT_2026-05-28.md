---
title: "Pipeline Dataset Audit — integrità & coerenza inter-stadio (2026-05-28)"
id: LIN-DT-PIPEAUDIT-20260528
status: REPORT
date: 2026-05-28
authors: [Strategic Advisor (Gianpiero Scappelloni)]
---

# Pipeline Dataset Audit — 2026-05-28

> Audit completo richiesto dal CEO post-Step-B. Obiettivo: trovare problemi di
> **integrità dei dati** e di **coerenza tra i passaggi** della pipeline di
> creazione del dataset Gold, della stessa classe dei bug già risolti
> (midimap fantasma / Plan A, BigRustyDrums zero-fill, layout hard-coded).
> Ogni finding è **falsificabile** su dati reali.

## Pipeline auditata (12 stadi)

```
MIDI GMD bronze → midi_augment(jitter) → recipe_matrix → render(Sfizz/DrumGizmo)
   → target_builder(MIDI→flat-25) → orchestrate(tail std + cucitura)
   → gold_writer(audio.f16 + target.f16) → dna_trace → [shard_writer] → data.py(loader)
   → audio_augment + channel_agnostic_aug → preprocessing(P1/P2)
```

## Findings — classificati per severità

### 🔴 MAJOR-1 · Hi-hat "edge" (GM 22/26) droppato — 34 % di tutto l'hihat

**Il problema.** La `midi_mapping_table.yaml` usa il **General MIDI standard**
(note 35–59). Ma la **GMD (Magenta Groove MIDI Dataset)** — la nostra unica
sorgente MIDI reale — usa il **mapping Roland TD-11**, in cui:

| GM | Significato (Roland TD-11 / GMD) | Stato attuale |
| --: | :-- | :-- |
| **22** | Hi-Hat Closed (**edge**) | ❌ non in mapping table → droppato |
| **26** | Hi-Hat Open (**edge**) | ❌ non in mapping table → droppato |
| 58 | High Floor Tom (raggruppato con 43 in GMD) | ❌ non in mapping table → droppato |

`target_builder.py:242` scarta silenziosamente ogni nota non in tabella
(`mapped = [o for o in onsets if o.note in bus_mapping.gm_to_bus]`). I midimap
DrumGizmo **anch'essi** non hanno 22/26 → l'audio non viene reso. Quindi il colpo
di hihat **sparisce da audio E target** (coerente, ma il dato è perso).

**Evidenza falsificabile (scan GMD v1, 1150 file, 446 312 onset):**
- **GM 22 = 34 857 onset · GM 26 = 10 246 onset · GM 58 = 1 003 onset**
- **10,1 % di TUTTI gli onset GMD** sono droppati (45 103 hihat edge + 1 003 floor)
- **33,9 % di tutto l'hihat** è edge → perso. Mappare 22/26 darebbe **+51 % di onset hihat** (87 975 → 133 078)
- **50,7 % dei file GMD** contiene ≥1 nota droppata
- **23,9 % dei file (203)** hanno >50 % dell'hihat sull'edge → hihat per lo più sparito
- File come `155_soul_98_fill`, `117_jazz-fusion_96_fill` sono **100 % edge → hihat interamente svanito**

**Conferma sul Gold reale su disco** (mini_l3, 80 sample):
- hihat presente solo nel **62–68 %** dei sample (fisicamente impossibile: l'hihat è lo strumento più denso in batteria)
- hihat onset_frames **< snare** (721 vs 1820) — invertito rispetto alla realtà (l'hihat dovrebbe dominare)

**Impatto.** L'hihat è il bus storicamente peggiore in TUTTI i mini-L3 della
settimana. Questo è (in parte) **causa-dati, non causa-modello**: 1/3 dei colpi
hihat è mislabeled-by-omission. Inoltre crea un **gap train/inference**: l'audio
reale di un utente avrà tutti i colpi (edge incluso), la rete è addestrata solo
su bow. **Scalerebbe al render F2-T1 1,5 TB** → il training A100 ($50-80)
girerebbe su un Gold con l'hihat sventrato.

**Fix raccomandato (richiede Decision Lock — cambia il data contract):**
canonicalizzazione MIDI **pre-split** che ripiega edge→bow una volta sola, così
sia render sia target vedono note bow:
- `22 → 42` (closed edge → closed bow), `26 → 46` (open edge → open bow), `58 → 43` (floor)
- ~10 LOC come stadio in `orchestrate.build_gold_sample` prima di render+target_builder
- In alternativa: aggiungere 22→hihat(3), 26→hihat(3), 58→floor(5) alla mapping
  table **E** patchare i midimap DrumGizmo (più invasivo, per-kit)

### 🟡 MEDIUM-2 · Audio peak > 1.0 sui render DrumGizmo (contratto violato)

**Evidenza:** 8/100 sample reali superano peak 1.0, fino a **1.61**
(`MINI_L3059-V3T1-J01-DGZ`). Il contratto F0-T2a / L2 Ocular Proof dichiara
"peak audio ∈ (0,1]". DrumGizmo multi-mic non normalizza il peak; il velocity
jitter (gain shift) lo accentua sui variant J01.

**Impatto:** mitigato dal P1 (per-channel z-score in ChannelNorm) che normalizza
comunque → non corrompe il training. Ma: (1) viola il contratto dichiarato;
(2) crea un potenziale gap di scala train/inference (il DAW consegna [-1,1]);
(3) la voice `peak_normalize` dell'audio_augment può comportarsi inatteso.
**Fix:** peak-normalize o soft-clip post-render in `orchestrate`, oppure
emendare il contratto a "peak ∈ (0, ~2]" se si preferisce preservare la dinamica.

### 🟢 MINOR-3 · GM 58 mismatch su 2 kit

Aasimonster + CrocellKit (small) hanno `note="58"` nei midimap → rendono audio,
ma 58 non è in mapping table → target vuoto. **Mismatch reale** (audio sì, target
no) della classe Plan-A, ma volume basso (1 003 onset = 0,2 %). Risolto dallo
stesso fix di MAJOR-1 (58→floor).

### ✅ OK — verificati e sani

| Aspetto | Esito |
| :-- | :-- |
| Allineamento audio↔target | **0 mismatch** su 100 sample. `n_frame = ceil(dur·344.53)`, `n_sample = round((last_onset+0.5)·44100)`, rapporto 128 esatto. |
| NaN/Inf in audio e target | **0** su 100 sample. |
| Range onset target ∈ [0,1] | **0 violazioni**. |
| Canali audio zero | val ShittyKit: 0. train: 6 sample con 6 canali zero = **Big Rusty Drums SFZ via `solo_stereo`** (noto, **gestito by design** da F0-T4e input-agnostic + count-mask). Non un bug. |
| crash_a quasi-assente | **Rarità legittima** (GM 49 = 720 onset vs crash_b 5157; ~0.6/file). Mapping 49→bus7 corretto. Non un bug. |
| DNA-Trace lineage | sha256/shape validati dal loader (`load_pool`) su tutti i sample senza errori. |

## Correzione al record

L'handoff F0-T4e citava "Bug #3: GM 75/54 (splash/tambourine) ignorati". **Impreciso:**
GM 55 (splash) È mappato (bus 8); GM 54 (tambourine) e 75 (claves) **non compaiono
affatto** nella GMD. Il vero bug di copertura mapping è **GM 22/26 (hihat edge)**,
un ordine di grandezza più grande (10 % degli onset vs ~0 %).

## Stadi non esercitati in questo audit

- `shard_writer.py`: il mini_l3 usa Gold "loose" (file sciolti), non tar-shard.
  Lo sharding è F2-T1-scale; testato dai suoi 31 oracoli ma non verificato su dati
  di produzione (non esistono ancora). Da ri-verificare al primo render F2-T1.
- File legacy `ugt_generator.py` / `midi_renderer.py` / `batch_generator.py` /
  `augmentation_engine.py`: prototipi FluidSynth **scartati** (Design Lock
  2026-05-20), non nel path attivo. Candidati a rimozione per pulizia.

## Raccomandazione strategica

**MAJOR-1 va risolto PRIMA di F2-T1** (Decision Lock CEO). È il candidato più forte
per spiegare il floor persistente dell'hihat in tutti i mini-L3, ed eviterebbe di
bruciare $50-80 di A100 su un Gold con l'hihat strutturalmente degradato. Costo del
fix: ~10 LOC + re-render mini_l3 locale (~11 min, $0) per validare il lift hihat
prima di committare al render full-scale.
