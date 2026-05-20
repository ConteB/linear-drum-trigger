# 📐 F0-T2a — SPEC DI DETTAGLIO: RECIPE + CONTRATTO DATI
**ID:** LIN-DT-SPEC-F0T2a · **Status:** LOCKED — Decision Lock 2026-05-20 (Executive Briefing F0-T2a)
**Riferimenti:** `DOSSIER_TECNICO.md` §3.2/§3.5/§4/§9.2 · `MASTER_CHECKLIST.md` §1–§2 ·
Decision Lock STRP-001 2026-05-20 (D1/D2/D2-bis) · `MASTER_SCHEDULING.md` §6 F0-T2a

> Questo documento blocca il dettaglio implementativo di **recipe** e **contratto dati**.
> La direzione macro è già locked (D1/D2/D2-bis); qui si fissano schemi, layout di byte e
> formati che `F0-T2b/c/d` dovranno implementare alla lettera. Frame-rate e finestra del
> target restano **parametrici**, ratificati a `F0-T4a` (vedi §3.4).

---

## 1. Recipe — schema dichiarativo

Una **recipe** descrive uno scenario di render riproducibile: produce uno (o una famiglia
di) campione Gold. Formato proposto: **YAML** (autorabile a mano, diff-friendly, commentabile).

### 1.1 Campi

| Campo | Tipo | Note |
| :-- | :-- | :-- |
| `recipe_id` | str | Univoco, kebab/maiuscolo. Es. `R-GMD042-DGZ-001`. |
| `schema_version` | str | Versione di questo schema (`"1.0"`). |
| `split` | enum | `train` \| `val`. *(Holdout = dati reali ENST/MedleyDB, non Gold renderizzato — §3.6.)* |
| `midi_source.dataset` | enum | `GMD` (Groove MIDI Dataset). |
| `midi_source.file` | path | Path relativo al MIDI sorgente nel layer Bronze. |
| `midi_source.bus_mapping` | ref | `midi_mapping_table.yaml@<ver>` — tabella GM→8-bus. |
| `midi_jitter.time_jitter_ms` | [min,max] | Range uniforme spostamento onset (DOSSIER §3.1: 2–15 ms). |
| `midi_jitter.flam_probability` | float | Doppi colpi artificiali (default 0.05). |
| `midi_jitter.velocity_jitter` | enum | `none` \| `ghost_mask` \| `gain_shift` \| `both`. |
| `midi_jitter.component_drop_probability` | float | Mute randomico componenti (default 0.10). |
| `midi_jitter.seed` | int | Seme RNG — **determinismo DNA-Trace**. |
| `render.engine` | enum | `sfizz` \| `drumgizmo`. |
| `render.kit` | str | ID kit/libreria (vedi §2). |
| `render.kit_path` | path | Path al `.sfz` (Sfizz) o al kit `.xml` (DrumGizmo). |
| `render.sample_rate` | int | Fisso **44100** (DOSSIER §6.1: nessun resampling). |
| `render.mic_config` | enum | `mono` \| `solo_stereo` \| `glyn_johns` \| `multitrack_full` (§2.2). |
| `augmentation.level` | int | `1` Stem-Isolate · `2` Studio-Mutilation · `3` Inferno (DOSSIER §3.2–3.4). |
| `augmentation.reverb_ir` | str\|null | ID Impulse Response (OpenAIR) o `null` = dry. |
| `augmentation.mutilation` | map | Parametri clipping/phase/comp/EQ/pitch (livello ≥2). |
| `augmentation.saboteur` | map\|null | Sorgente + ratio di mix Transient Saboteur (livello 3). |
| `output.target_frame_rate_hz` | float | **PROVVISORIO** — ratificato a F0-T4a (§3.4). |
| `dna_trace.barcode` | str | Generato (non scritto a mano) — vedi §4. |

### 1.2 Esempio completo

```yaml
recipe_id: R-GMD042-DGZ-001
schema_version: "1.0"
split: train
midi_source:
  dataset: GMD
  file: bronze/gmd/drummer1/session1/42_rock_120_beat_4-4.mid
  bus_mapping: midi_mapping_table.yaml@1.0
midi_jitter:
  time_jitter_ms: [2, 15]
  flam_probability: 0.05
  velocity_jitter: both
  component_drop_probability: 0.10
  seed: 4242
render:
  engine: drumgizmo
  kit: DRSKit
  kit_path: bronze/drumgizmo/DRSKit/DRSKit.xml
  sample_rate: 44100
  mic_config: glyn_johns
augmentation:
  level: 2
  reverb_ir: openair_r2_york_minster
  mutilation: { clipping: 0.3, phase_flip: [snare_bot], comp_ratio: 8, pitch_semitones: -1 }
  saboteur: { source: SLK102, mix_ratio: 0.4 }
output:
  target_frame_rate_hz: 344.53125   # PROVVISORIO — vedi §3.4
```

---

## 2. Render engine — schema recipe per Sfizz e DrumGizmo

### 2.1 Sfizz (librerie SFZ multi-layer)
- Pilotato via CLI (`sfizz_render --sfz <file> --midi <file> --wav <out>`).
- Le librerie SFZ (SM Drums, Salamander, VSCO-2 CE) gestiscono **internamente** velocity
  layer e round-robin: la recipe non li espande, referenzia solo il `.sfz`.
- Uscita: stem **pulito** stereo o mono — **nessun bleed** inter-strumento.
- Ruolo: baseline Livello-1 (precisione del transiente) + sintesi percussioni accessorie
  sincrone (DOSSIER §3.4) + kit Salamander/SM Drums.

### 2.2 DrumGizmo (kit multi-microfono)
- Pilotato via CLI; il kit `.xml` espone N canali microfonici reali → **sorgente del bleed**.
- È l'unico engine che produce il rientro microfonico (moat primario del prodotto).
- Render multi-canale: ogni mic su un canale del file d'uscita.

### 2.3 Configurazioni microfoniche (`mic_config`) — Input Agnostico (DOSSIER §2.1)

| `mic_config` | `n_mic` | `channel_labels` (ordine canonico) |
| :-- | :-- | :-- |
| `mono` | 1 | `["mix"]` |
| `solo_stereo` | 2 | `["mix_L","mix_R"]` |
| `glyn_johns` | 4 | `["kick","snare","oh_L","oh_R"]` |
| `multitrack_full` | 8 | `["kick","snare_top","snare_bot","tom","floor","oh_L","oh_R","room"]` |

`n_mic` e `channel_labels` sono registrati nel `dna.json`. Il contratto ammette
`n_mic ∈ [1,8]` arbitrario; la standardizzazione a tensore fisso avviene al data-loading
(layer di pre-processing del modello, §2.1 DOSSIER), **non** in fase di scrittura Gold.

---

## 3. Contratto dati — Gold tensor FP16 + shard WebDataset

### 3.1 Struttura WebDataset (Decision Lock D1)
- Layer Gold = file **`.tar`** (WebDataset), shard ~**1 GB**, tracciati da DVC come shard.
- Naming shard: `gold-{split}-{index:06d}.tar` — es. `gold-train-000123.tar`.
- Ogni campione = **terna** con `key` comune (= barcode DNA, privo di punti):
  - `{key}.audio.f16`  — input audio
  - `{key}.target.f16` — matrice di trascrizione
  - `{key}.dna.json`   — DNA-Trace (§4)

### 3.2 `audio.f16` — tensore di input
- Buffer **raw float16 little-endian**, C-contiguous.
- Shape logica: **`[n_mic, n_sample]`** · `n_mic ∈ [1,8]` · `sample_rate = 44100`.
- Shape, `dtype`, `mic_config`, `channel_labels` → in `dna.json` (file raw senza header).
- Ampiezza: campioni in `[-1.0, +1.0]`, **non normalizzati** (si preservano le dinamiche).

### 3.3 `target.f16` — matrice di trascrizione
- Buffer **raw float16 little-endian**, C-contiguous.
- Shape logica flat: **`[n_frame, 25]`** — layout `flat-25`:
  - per il bus `b ∈ [0,7]`: colonna `3b` = **onset** (prob. Gaussian-smeared ∈ [0,1]),
    `3b+1` = **velocity** (∈ [0,1], normalizzata da 0–127), `3b+2` = **microtiming**
    (offset sub-frame ∈ [-1,1], §3.5).
  - colonna `24` = **Hi-Hat opening** (testa continua ∈ [0,1], DOSSIER §2.2).
- Il data-loader fa reshape `cols 0:24 → [n_frame,8,3]`; `col 24 → [n_frame]`.
- `onset` segue il **Gaussian Target Smearing** ±3 ms (DOSSIER §6.2): nessuno "spillo".

### 3.4 Frame-rate del target — parametro DEFERRED a F0-T4a
Il numero di frame dipende dal frame-rate d'uscita, che è una **decisione di topologia**
(stride totale della TCN) — fissata in `F0-T4a` (Decision Lock D2-bis).
- `n_frame = ceil(duration_s × R_target)` · `R_target` = frame-rate target (Hz).
- **Valore raccomandato (provvisorio):** `R_target = 44100/128 ≈ 344.53 Hz`
  (periodo ≈ 2.9 ms — coerente con lo smear ±3 ms; usato per il mini-batch F0-T2e).
- La **sample-accuracy è preservata indipendentemente da `R_target`**: il canale
  microtiming codifica l'offset residuo entro `±(half-frame)` campioni, normalizzato a
  `[-1,1]`. Onset (frame) + microtiming (residuo) ⇒ ricostruzione sample-accurate.
- `R_target` effettivo è scritto in ogni `dna.json` (`target.frame_rate_hz`).

### 3.5 Convenzioni numeriche
| Grandezza | Range | Unità di misura | Note |
| :-- | :-- | :-- | :-- |
| `audio` | [-1, +1] | ampiezza normalizzata | non normalizzato per-campione |
| `onset` | [0, 1] | probabilità | Gaussian smear σ ↔ ±3 ms |
| `velocity` | [0, 1] | — | `= midi_velocity / 127` |
| `microtiming` | [-1, +1] | frazione di mezzo-frame | `offset_samples / (R_target⁻¹·sr/2)` |
| `hihat_opening` | [0, 1] | — | 0 = chiuso, 1 = aperto |

### 3.6 Split
Gli shard Gold coprono **solo `train` e `val`** (materiale renderizzato/sintetico).
Lo **Holdout** (DOSSIER §10.3) è dato reale (ENST-Drums / MedleyDB) e **non** transita
per il packaging WebDataset Gold. Vincolato all'esito di F0-T1 (compliance).

### 3.7 Integrità FP16 (verifica per Gate L2 / DoD F0-T2d)
Il writer Gold calcola e registra in `dna.json`: `sha256` dei buffer `audio` e `target`,
`dtype`, `shape`, conteggio di `NaN/Inf` (deve essere 0). Il validatore L2 ricomputa gli
hash e verifica `0 NaN/Inf` — Ocular Proof.

---

## 4. DNA-Trace — formato (DOSSIER §3.5)

### 4.1 Barcode (parte `key`, privo di punti)
Schema: `{MIDISRC}-{MIDIALT}-{ENGINE}-{REVERB}-{AUDIOALT}-{SABOTEUR}`

| Segmento | Esempio | Significato |
| :-- | :-- | :-- |
| `MIDISRC` | `GMD042` | dataset + indice file MIDI |
| `MIDIALT` | `V1T1` | `V`=codice velocity-jitter, `T`=codice time-jitter |
| `ENGINE` | `DGZ` | `DGZ`=DrumGizmo, `SFZ`=Sfizz |
| `REVERB` | `R2` | indice Impulse Response · `R0` = dry |
| `AUDIOALT` | `C1H0` | codice mutilation (clipping/phase/comp…) |
| `SABOTEUR` | `SLK102` | sorgente+indice saboteur · `NONE` se assente |

### 4.2 `dna.json` — "Libretto Sanitario"
JSON che permette il reverse-engineering totale del campione:

```json
{
  "dna_version": "1.0",
  "barcode": "GMD042-V1T1-DGZ-R2-C1H0-SLK102",
  "key": "GMD042-V1T1-DGZ-R2-C1H0-SLK102",
  "recipe_id": "R-GMD042-DGZ-001",
  "recipe_sha256": "<hash della recipe YAML>",
  "split": "train",
  "generated_at": "2026-05-20T00:00:00Z",
  "lineage": {
    "midi_source": { "dataset": "GMD", "file": "bronze/gmd/.../42_rock_120.mid" },
    "midi_jitter": { "time_shifts_ms": [...], "flams_added": 3,
                     "velocity_jitter": "both", "components_dropped": ["tom_hi_mid"],
                     "seed": 4242 },
    "render": { "engine": "drumgizmo", "kit": "DRSKit",
                "mic_config": "glyn_johns", "sample_rate": 44100 },
    "augmentation": { "level": 2, "reverb_ir": "openair_r2_york_minster",
                      "reverb_wet": 0.35, "clipping": 0.3, "phase_flip": ["snare_bot"],
                      "comp_ratio": 8, "pitch_semitones": -1 },
    "saboteur": { "source": "SLK102", "mix_ratio": 0.4 }
  },
  "audio":  { "shape": [4, 1323000], "dtype": "float16", "sample_rate": 44100,
              "mic_config": "glyn_johns",
              "channel_labels": ["kick","snare","oh_L","oh_R"],
              "sha256": "<hash>", "n_nonfinite": 0 },
  "target": { "shape": [10334, 25], "dtype": "float16", "layout": "flat-25",
              "frame_rate_hz": 344.53125, "smear_ms": 3.0,
              "sha256": "<hash>", "n_nonfinite": 0 }
}
```

---

## 5. Survey articolazioni Hi-Hat

| Libreria | Articolazioni HH disponibili | Note d'uso |
| :-- | :-- | :-- |
| **DrumGizmo (kit multi-mic)** | Closed, Pedal, Open (a gradi), Tip/Shank | I kit espongono più stati di apertura → sorgente primaria per addestrare la **testa continua**. |
| **SM Drums** | Closed, Open, Pedal (multi-layer) | Stati discreti; mappati su valori di apertura `{0.0, 0.5, 1.0}` per il target continuo. |
| **Salamander** | Closed, Semi-open, Open, Pedal | 4 gradi → granularità intermedia utile. |

**Conseguenza per il contratto:** la testa continua `hihat_opening` è addestrata da stati
**discreti** delle librerie, proiettati su `[0,1]`. Recipe DrumGizmo con più gradi di
apertura sono prioritarie per dare densità al segnale di regressione. Il toggle d'uscita
(CC continuo / Note discrete) è definito nella `midi_mapping_table.yaml` (`hihat_output`).

---

## 6. Decision Lock (2026-05-20)
Le 5 risoluzioni della Tech Matrix sono state **approvate dal CEO** (Executive Briefing F0-T2a):
1. ✅ Recipe in **YAML**.
2. ✅ Target tensor **`flat-25`** in file unico `[n_frame,25]`.
3. ✅ `R_target` **parametrico** — provvisorio `44100/128 ≈ 344.5 Hz`, ratifica a F0-T4a.
4. ✅ Velocity storata **normalizzata [0,1]** FP16.
5. ✅ Articolazioni intra-bus **collassate in v1.0**; classificazione per-articolazione rinviata a v2.0 (Dual-Path Network, DOSSIER §6.3).

---
*Spec F0-T2a — STRP-001 (snello). **LOCKED 2026-05-20.** Vincolante per F0-T2b/c/d.*
