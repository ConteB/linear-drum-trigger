---
id: LIN-DT-DCBP-001
title: Dataset Card Blueprint (addendum)
type: spec
status: LOCKED
phase: F0
domain: AI / Reporting / Data
version: 1.0.0
updated: 2026-05-23
tags: [reporting, dataset, ux, ai, blueprint, addendum]
related: [LIN-DT-RPTBP-001, LIN-DT-ENGSTD-001, LIN-DT-DOSSIER-001]
supersedes: []
---

# Dataset Card Blueprint (addendum a `MODEL_REPORT_BLUEPRINT`)

> **Status:** LOCKED — Decision Lock CEO 2026-05-23 (Executive Briefing STRP-001).
> **Mandato operativo:** ogni **dataset versionato** (Bronze / Silver / Gold)
> ha la propria card HTML single-file, generata dallo stesso engine
> `src/neural/reporter.py`. La card è creata al passaggio Medallion (F0-T5) e
> aggiornata a ogni bump di versione del dataset.
>
> **Code generator status:** specificato qui, **implementazione differita a F0-T5**
> — quando definiamo lo sharding WebDataset e si materializzano i dataset reali.

## 0. Perché esiste

Hugging Face Model Cards / Datasheets-for-Datasets (Gebru et al. 2021) hanno
imposto lo standard: un dataset privo di provenance + statistiche + licenza
esplicita è **non-deployable**. Il nostro caso lo amplifica:

- Il roster F0-T1b è una combinazione di kit a licenze CC0/CC-BY (compliance
  granulare).
- Lo split Bronze/Silver/Gold genera 3 dataset *derivati* tracciati da DVC —
  ognuno ha la propria card.
- L4 sull'Holdout reale E-GMD (CC-BY 4.0) richiede l'evidenza scritta che il
  modello *non* è stato addestrato sul Holdout (data-leakage audit).

La card chiude i 3 fronti in un solo artefatto.

<a id="output-specification"></a>
## 1. Output specification

```
dataset_cards/<dataset_name>-<version>/
└── card.html                ← single file, stesso stack del training report
```

Convenzione `<dataset_name>`:
- `gold-train`, `gold-holdout`, `gold-mini` (i 3 split del Gold)
- `silver-train`, `silver-holdout` (Silver = Gold post-augmentation)
- `bronze-gmd`, `bronze-egmd`, `bronze-slakh` (i Bronze raw)

`<version>` = SHA-7 del manifest DVC oppure semver manuale (`1.0`, `1.1`).

**Stack tecnologico**: identico a `MODEL_REPORT_BLUEPRINT` —
HTML single-file con SVG inline, CSS "Laboratory Precision" embedded,
template Jinja2 `templates/dataset_card.html.j2`, generato da
`src/neural/reporter.py::write_dataset_card(...)`.

## 2. Sezioni canoniche

L'ordine è fisso. Una sezione N/A resta presente con motivazione.

### § 0 — Identity card

| Voce | Valore |
| :-- | :-- |
| `dataset_name` | `gold-train` |
| `version` | `1.0` |
| `tier` (Medallion) | Bronze / Silver / Gold |
| `n_samples` | numero |
| `total_duration_h` | ore di audio |
| `total_size` | GB |
| `dvc_manifest_sha256` | hash del manifest |
| `created_at` | ISO 8601 |
| `created_by` | run/commit reference |

### § 1 — Provenance & lineage

- Sorgenti (MIDI dataset, kit SFZ/DrumGizmo, audio raw).
- Recipe SHA-256 (riferimento a [`F0-T2a §1`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md)).
- Augmentation level (1, 2, 3 per spec [`DOSSIER §3`](../docs/methodology/DOSSIER_TECNICO.md#data-doctrine)).
- DVC chain: link al manifest, link al dataset parent (se derivato).

### § 2 — Licensing — la sezione critica

Tabella **kit-by-kit** con licenza verificata alla fonte (coerente con
[`DATA_PROVENANCE_LOG.md` §2.A](../docs/compliance/DATA_PROVENANCE_LOG.md)).
Colonne: `kit_name`, `source_url`, `license`, `commercial_use_ok`,
`redistribution_ok`, `verified_at`. Riga rossa per qualsiasi `commercial_use_ok = false`.

Status finale a fondo sezione: **CC0/CC-BY commercial only** (Decision Lock
2026-05-20).

### § 3 — Schema del campione

- Riferimento a [`F0-T2a §3`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract)
  (contratto dati `flat-25`).
- Diagramma del sample triple (audio.f16 / target.f16 / dna.json).
- Sample rate, frame rate, dtype, byte layout little-endian.

### § 4 — Statistiche

- **Audio**: distribuzione di durata per sample (istogramma), peak / RMS,
  silent-sample count (deve essere 0 per Gold).
- **Target**: onset density per-bus (bar chart — chi domina? kick/snare?),
  velocity distribution, microtiming distribution, hihat-opening occupancy.
- **mic_config breakdown**: pie chart `mono` / `solo_stereo` / `glyn_johns` /
  `multitrack_full`.
- **Engine breakdown**: `sfizz` vs `drumgizmo` (per Gold).

### § 5 — Augmentation chain (Silver / Gold only)

Tabella: `step_name`, `applied_to_fraction`, `parameters_hash`. Riferimento a
F0-T15 audit ratificato.

### § 6 — Data-leakage audit

Cross-check `bus_mapping` + `midi_source.file` tra train e holdout —
nessun MIDI condiviso. Output: tabella con `n_collisions` (deve essere 0)
+ heatmap di overlap.

Critico per L4: il modello *non* deve vedere il Holdout in training. La card
è la prova firmata di compliance.

### § 7 — Esempi qualitativi

Selezione random (seed fisso = `dataset_version`) di 3 sample. Per ognuno:

- Waveform multi-mic (le 8 canali).
- Target piano-roll.
- DNA-trace prettified.

### § 8 — Integrity check

- SHA-256 di un subset random (10 sample) ricalcolato vs `dna.json`
  registrato. Deve combaciare 100%.
- N_nonfinite check (deve essere 0).
- Verifica conformità ai vincoli del contratto F0-T2a (shape, dtype, range).

### § 9 — Come leggere il dataset card

> Sezione canonica importata da [`templates/_how_to_read_dataset.html.j2`](../templates/_how_to_read_dataset.html.j2).

Definizioni: `Bronze/Silver/Gold` (Medallion), `mic_config` (configurazioni
microfoniche), `flat-25` (layout target), `DNA-trace`, augmentation levels.
Trappole: come distinguere un kit "CC-BY con attribuzione richiesta" da un
"CC0" e perché le card lo evidenziano in rosso/verde.

### § 10 — Decisione del CEO (Tier 2 only)

Per i dataset critici (Gold train, Gold holdout, Silver finale) la card è
firmabile come Ocular Proof. § 10 contiene: checklist di compliance
(licensing OK, data-leakage zero, integrity OK), firma del CEO con data.

I dataset intermedi (Bronze raw, Silver intermedio) restano Tier-1 (auto).

## 3. Tiering — analogo al training report

| Tier | Quando | § 10 firma |
| :--: | :-- | :--: |
| 1 | Bronze raw, Silver intermedi, mini-batch di test | ❌ |
| 2 | Gold train, Gold holdout, Silver finale (training-grade) | ✅ |

## 4. Integrazione con il training report

Ogni `report.html` di training **deve** linkare alle dataset card dei dataset
usati. Il riferimento è il manifest DVC SHA-256 — il link punta alla card
locale (`../../dataset_cards/<name>-<version>/card.html`). Lychee valida il
link interno.

In questo modo: aprire un training report → click sul nome del dataset →
arrivi alla card. Catena navigabile, audit trail completo, zero ambiguità
su "quale dataset hai usato".

## 5. Implementazione (differita)

`src/neural/reporter.py::write_dataset_card(...)` riusa l'engine di
training: stesso `ChartFactory`, stesso CSS, stesso layout HTML. Cambia solo
il template (`dataset_card.html.j2`) e i campi di `ReportContext`.

Code generator implementato in **F0-T5** (Medallion + sharding WebDataset),
quando esistono dataset reali da descrivere. La spec di questa card resta
LOCKED ora, così quando F0-T5 si attiva non c'è discussione su cosa
generare.

## 6. Mappatura ai dataset previsti

| Dataset | Tier card | Quando viene generata | Note |
| :-- | :--: | :-- | :-- |
| `bronze-gmd` | 1 | F0-T5 (provisioning) | il MIDI raw da GMD |
| `gold-mini` | 1 | già generabile su F0-T2e | il mini-batch dei 12 sample |
| `gold-train` | 2 | F2-T1 (post render) | grosso, firmabile, link da L4 |
| `gold-holdout` | 2 | F2-T1 (post render) | il critical data-leakage audit |
| `silver-train` | 2 | F2-T2 (post augmentation) | manifest augmentation hash |
| `bronze-egmd` | 2 | F2-T3 (pre L4) | il Holdout reale, firma compliance |

---

*Decision Lock 2026-05-23. Implementazione codice differita a F0-T5;
spec normativa attiva da ora. Aggiornamenti = bump semver. Single source of
truth per § 9 in [`templates/_how_to_read_dataset.html.j2`](../templates/_how_to_read_dataset.html.j2).*
