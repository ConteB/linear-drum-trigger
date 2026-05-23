---
id: LIN-DT-SPEC-F0T5
title: F0-T5 — Spec Sharding WebDataset + struttura Medallion
type: spec
status: LOCKED
phase: F0
domain: Data Engineering
version: 1.0.0
updated: 2026-05-23
tags: [sharding, webdataset, medallion, dvc, F0-T5]
related: [LIN-DT-SPEC-F0T2a, LIN-DT-DOSSIER-001, LIN-DT-MSCHED-001]
supersedes: []
---

# 📦 F0-T5 — SPEC: SHARDING WEBDATASET + STRUTTURA MEDALLION
**Status:** LOCKED — Decision Lock 2026-05-23
**Riferimenti:** [`F0-T2a` §3 — contratto dati](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract) ·
[`F0-T2a` §3.8 — tail standardization](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#tail-standardization) ·
[`DOSSIER` §9.2 — Medallion](DOSSIER_TECNICO.md#medallion) ·
[`STRATEGIC_INFRASTRUCTURE_AUDIT` §7.1](../../04_INTELLIGENCE/STRATEGIC_INFRASTRUCTURE_AUDIT.md#azure-spend-plan) ·
[`MASTER_SCHEDULING` §6 F0-T5](../../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks) ·
[`ENGINEERING_STANDARDS` §1 — determinismo](../../04_INTELLIGENCE/ENGINEERING_STANDARDS.md#determinism) ·
[`§6 — robustezza`](../../04_INTELLIGENCE/ENGINEERING_STANDARDS.md#execution-robustness).

> Questo documento chiude F0-T5: blocca la **strategia di sharding** del layer Gold
> (packing, naming, tracciamento DVC, manifest, atomicità), la **struttura Medallion**
> on-disk e i moduli da implementare prima di F2-T1. Costruito sopra il contratto F0-T2a
> §3 (terna `audio.f16` / `target.f16` / `dna.json`), che resta la fonte di verità per il
> singolo campione.

---

<a id="rationale"></a>
## 1. Razionale — perché shard e non micro-file

Il layer Gold pesa **~1.5 TB**. Senza sharding:

- **Filesystem.** Centinaia di migliaia di micro-file aprono problemi di `inode` su
  filesystem locali e di `LIST` lentissime su Blob Storage.
- **Throughput Azure.** Il rendering scrive, il training legge. Micro-file moltiplicano
  le chiamate HTTP al Blob → costo egress + latenza che brucia clock GPU su A100 (~$3.67/h
  in Spot).
- **DVC.** Tracciare 300k+ file singoli con DVC genera un `.dvc` di dimensioni assurde e
  push lentissimi. Tracciare per directory è invece efficiente: DVC v3+ calcola un hash
  ricorsivo (`.dir`) e gestisce migliaia di shard come unità atomica.

**Decisione direzionale già bloccata** in F0-T2a §3.1 (Decision Lock STRP-001 2026-05-20,
D1): tar-shard **WebDataset** ~1 GB, tracciati da DVC come shard, naming
`gold-{split}-{index:06d}.tar`. F0-T5 finalizza il *come*.

---

<a id="medallion-layout"></a>
## 2. Struttura Medallion on-disk

```
data/
├── bronze/                       # raw, immutable — re-scaricabile
│   ├── gmd/                      # Groove MIDI Dataset (CC-BY 4.0)
│   ├── drumgizmo/                # DRSKit, MuldjordKit, ...
│   ├── sfizz_kits/               # Salamander, Karoryfer, VSCO-2 CE, ...
│   └── e_gmd/                    # Holdout reale (F0-T1c) — F1-T1 download
├── silver/                       # intermedio rigenerabile — NON archiviato a fine sprint
│   └── (transitorio: WAV stem del render, target builder scratch)
└── gold/                         # capitale — archiviato su HDD post-Azure (F3)
    ├── train/
    │   ├── gold-train-000000.tar
    │   ├── gold-train-000001.tar
    │   └── manifest.json
    ├── val/
    │   ├── gold-val-000000.tar
    │   └── manifest.json
    └── (post F2-T2)
        ├── train-augmented/      # output di F2-T2 — branch parallelo, non sovrascrive
        └── val-augmented/
```

**Principi.**

- **Bronze immutabile**, ricostruibile dal web (GMD + kit pubblici) — nulla in DVC.
- **Silver volatile**, generato e consumato dentro il ciclo `recipe → write Gold`.
- **Gold permanente**, l'unico in DVC. Diviso per `split` (F0-T2a §3.6), pulito e
  augmented separati per non sovrascrivere il render originale (irriproducibile a basso
  costo dopo lo sprint Azure).

---

<a id="packing-policy"></a>
## 3. Politica di packing — `pack-on-fill` con pre-shuffle

**Strategia.** Pack-on-fill semplice (standard WebDataset / [Aaron Karpathy /
`webdataset` lib](https://github.com/webdataset/webdataset)):

1. La recipe matrix di F2-T1 è **pre-shuffled** con seed esplicito (registrato in
   `manifest.json`) — l'ordine di consumo è già randomizzato.
2. Lo `ShardWriter` apre lo shard `000000`; accoda campioni `{key}.audio.f16` +
   `{key}.target.f16` + `{key}.dna.json` finché la dimensione cumulata bytes-on-disk
   non supera `TARGET_SHARD_BYTES = 1 GB` (1 073 741 824 byte).
3. Al superamento della soglia: chiude lo shard (vedi §6 — atomicità), incrementa
   l'indice, apre il successivo.

**Diversità inter-shard.** Garantita dal pre-shuffle della recipe matrix, **non** da
stratification logic interna allo `ShardWriter` (che resterebbe inutilmente complessa).
Il pre-shuffle è il punto di controllo deterministico: cambiare seed = cambiare l'ordine
di tutti gli shard, in modo riproducibile.

**Diversità intra-shard.** Conseguenza diretta del pre-shuffle. Su uno shard ~1 GB
(~200 campioni medi, §4), la probabilità di concentrare un singolo engine/kit/durata è
~zero con shuffle uniforme su una recipe matrix bilanciata.

**Robustezza.** Il **pairing forzato MIDI×Engine** (Decision Lock 2026-05-23, F2-T1)
elimina la correlazione *durata↔engine* a monte. Insieme alla **tail standardization**
([`F0-T2a` §3.8](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#tail-standardization)),
chiude il canale di shortcut. Lo sharding pack-on-fill non deve compensare con
stratification logica: non c'è più nulla da bilanciare.

**Anti-pattern scartati.**

- ~~Stratified shards (uno shard per engine/kit)~~ → introduce bias di mini-batch
  se l'epoca viene troncata; complica l'implementazione; ridondante con pre-shuffle +
  pairing.
- ~~Round-robin pack-on-fill su N shard aperti~~ → marginalmente più equo, ma costa una
  scrittura aperta simultanea su N file → contende I/O su Blob durante l'upload
  streaming. Vinto dal pre-shuffle.

---

<a id="calibration"></a>
## 4. Calibrazione — stime quantitative

### 4.1 Dimensione per campione (calibrazione L2 reale)

Misurato sul mini-batch F0-T2e (12 campioni, render multi-mic verificato in Ocular Proof
L2):

| Engine | mic_config | n_mic | durata media | audio | target | dna.json | **totale/sample** |
|---|---|---:|---:|---:|---:|---:|---:|
| DrumGizmo | `multitrack_full` | 8 | 8.7 s | 6.10 MB | 0.150 MB | 1.3 KB | **~6.25 MB** |
| Sfizz | `solo_stereo` | 2 | 6.9 s | 1.21 MB | 0.118 MB | 1.3 KB | **~1.33 MB** |

> **Nota.** Le durate del mini-batch derivano da MIDI sintetici di lunghezza variabile (3–10 s).
> Per il dataset full-size la **tail standardization** (`tail_s = 0.5 s` uniforme,
> F0-T2a §3.8) rende la durata funzione esatta di `last_onset_s` del MIDI sorgente:
> stessa durata MIDI → stessa durata Gold, indipendente dall'engine.

### 4.2 Mix bilanciato atteso — 1.5 TB

Recipe matrix F2-T1 (pairing forzato MIDI×Engine, da formalizzare lì):

| Asse | Cardinalità tipica | Note |
|---|---:|---|
| MIDI sorgente (GMD) | ~1150 file | base |
| Engine × kit | 2×3 = 6 | Sfizz {Salamander, Karoryfer, VSCO-2}, DrumGizmo {DRSKit, MuldjordKit, ...} (roster F0-T1b) |
| `mic_config` | 4 | mono, solo_stereo, glyn_johns, multitrack_full |
| augmentation level | 3 | Stem-Isolate, Studio-Mutilation, Inferno (DOSSIER §3.2–3.4) |
| reverb IR | 2 | dry, +1 IR random |
| MIDI jitter seed | 2–3 | varianti |

Ordine di grandezza atteso (combinazioni effettive con pruning della doctrine
augmentation, post F0-T15): **~300 000 ÷ 500 000 campioni totali**. Media bytes/sample
~4 MB → **~1.2–2 TB**, centrato su 1.5 TB.

### 4.3 Conteggio shard

| Quantità | Valore |
|---|---|
| `TARGET_SHARD_BYTES` | 1 073 741 824 (1 GB) |
| Campioni medi/shard | ~250 |
| Shard totali a 1.5 TB | **~1500** |
| Split `train` (~90 %) | ~1350 shard |
| Split `val` (~10 %) | ~150 shard |
| File `.dvc` totali tracciati | **2** (uno per split — vedi §5) |

---

<a id="naming"></a>
## 5. Naming, tracciamento DVC, integrità

### 5.1 Naming shard

Locked in [F0-T2a §3.1](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract):

```
gold-{split}-{index:06d}.tar
```

- `split ∈ {train, val}`.
- `index` zero-padded a 6 cifre → ordine lessicografico = ordine numerico fino a 999 999
  shard. Margine ampio rispetto a ~1500 attesi.
- Estensione **`.tar`** (non compressa — vedi §5.4).

### 5.2 Contenuto del tar (WebDataset)

Ogni tar è un **archivio non compresso** che contiene, per ogni campione, la terna
[F0-T2a §3.1](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#data-contract):

```
{key}.audio.f16
{key}.target.f16
{key}.dna.json
```

dove `key` è il barcode DNA dot-free (F0-T2a §4.1). I tre file di un campione condividono
prefisso → WebDataset li raggruppa automaticamente al data-loading.

**Ordine all'interno del tar.** Lessicografico per `key`, deterministico (stesso input →
stesso byte-output) — vincolo di
[ENGINEERING_STANDARDS §1](../../04_INTELLIGENCE/ENGINEERING_STANDARDS.md#determinism).

### 5.3 Tracciamento DVC — per directory, non per file

```bash
dvc add data/gold/train
dvc add data/gold/val
```

Produce **2 file** `data/gold/train.dvc` + `data/gold/val.dvc`, ciascuno con l'hash
ricorsivo della directory (`.dir`). I ~1500 shard sono gestiti come unità sotto la
directory.

- **Push:** `dvc push -r azure` → upload incrementale dei soli shard nuovi/modificati.
- **Pull:** `dvc pull -r azure` → ricostruisce la directory.
- **Riproducibilità:** il file `.dvc` committato in Git lega il commit di codice a una
  versione esatta del dataset.

**Anti-pattern scartato.** ~~`dvc add data/gold/train/gold-train-000042.tar`~~ per ogni
shard → 1500 file `.dvc` in Git, diff illeggibili, push N volte più lento (1500 chiamate
metadata al remote invece di una).

### 5.4 Compressione — **no**

Decisione (Decision Lock 2026-05-23): tar **non compressi**.

- `audio.f16` è quasi-random (audio multi-mic FP16) → ratio gzip ~0.95 (3–5 % saving).
- `target.f16` è sparso (onset Gaussian + righe zero post-tail) → ratio gzip ~0.55–0.70
  ma pesa solo 2–3 % del totale.
- **Costo CPU della decompressione** sul nodo training A100 (~$3.67/h) supera di gran
  lunga il saving di banda. Il train loop deve saturare la GPU; non vogliamo CPU come
  collo di bottiglia.
- **Costo banda Blob** è marginale dentro la stessa region (rendering e training nella
  stessa region Azure — `westeurope` di default).

### 5.5 Manifest per split

Ogni directory di split contiene un `manifest.json` (versionato in DVC con gli shard):

```json
{
  "manifest_version": "1.0",
  "split": "train",
  "generated_at": "2026-06-XX",
  "recipe_matrix_seed": 4242,
  "target_shard_bytes": 1073741824,
  "tail_s": 0.5,
  "n_shard": 1352,
  "n_sample": 337891,
  "total_bytes": 1432198472104,
  "shards": [
    {
      "index": 0,
      "filename": "gold-train-000000.tar",
      "n_sample": 247,
      "bytes": 1071104512,
      "sha256": "<hash dello shard>",
      "key_range": ["GMD000-V0T0-DGZ-R0-L1-NONE", "GMD081-V1T1-SFZ-R0-L2-SLK102"]
    },
    "..."
  ]
}
```

**Usi del manifest.**

- **Resume.** Se il rendering Azure cade (Spot eviction, network blip), si rilegge il
  manifest, si trova `last_complete_shard`, si riparte da `last_complete_shard + 1`. No
  re-render dei campioni già committati.
- **Integrità.** `sha256` per shard → validatore post-pull verifica che lo shard non si
  sia corrotto in transito. Vincolo da `ENGINEERING_STANDARDS §6` (robustezza).
- **Data card.** Conteggi e seed alimentano il *dataset card* (template
  `04_INTELLIGENCE/DATASET_CARD_BLUEPRINT.md`) — tracciabilità reproducibile per
  pubblicazione tecnica.

---

<a id="atomicity"></a>
## 6. Atomicità & resume

**Vincolo.** Non deve mai esistere uno shard parziale visto come "completo" da un consumer
(training loader, dvc add, push Blob). Coerente con `ENGINEERING_STANDARDS §6`.

**Protocollo.**

1. Lo `ShardWriter` apre `gold-{split}-{index:06d}.tar.tmp` (estensione `.tmp`).
2. Accoda campioni finché non si raggiunge `TARGET_SHARD_BYTES`.
3. Chiude lo shard, calcola `sha256` sul file `.tmp`.
4. **Rename atomico** `.tmp` → finale (`os.rename` POSIX su filesystem locale,
   `BlobClient.commit_block_list` su Azure Blob): operazione atomica per filesystem.
5. Aggiorna `manifest.json` (anch'esso scritto via `.tmp` + rename).

**Riavvio dopo crash.**

- Eventuali `*.tmp` orfani vengono rimossi all'avvio (mai promossi).
- L'indice riparte da `max(shard finali esistenti) + 1`.
- Le recipe già consumate (campioni dentro shard chiusi) si tracciano per `key` nel
  manifest: la recipe matrix le salta al resume.

---

<a id="implementation"></a>
## 7. Implementazione — modulo `shard_writer.py`

Modulo nuovo: `src/data_engineering/gold/shard_writer.py`. Interfaccia (firma indicativa,
finalizzazione dei tipi al momento dell'implementazione):

```python
TARGET_SHARD_BYTES = 1 << 30  # 1 GB esatto

class ShardWriter:
    """Pack-on-fill WebDataset shard writer (F0-T5 §3, §6).

    Atomic on rotation: a partial shard never appears as final on disk.
    """

    def __init__(self, out_dir: Path, split: Literal["train", "val"],
                 target_bytes: int = TARGET_SHARD_BYTES,
                 recipe_matrix_seed: int) -> None: ...

    def add_sample(self, key: str, sample_dir: Path) -> None:
        """Append the {key}.audio.f16/.target.f16/.dna.json triple to the
        current open shard; rotate on size threshold."""

    def close(self) -> ShardManifest:
        """Flush the open shard, write the split manifest, return it."""
```

**Owner del modulo.** F0-T5 (questa spec). Implementazione concreta — codice + test
harness — è uno dei sotto-task di **F2-T1 prep** (la prep deve essere già pronta prima di
lanciare il render Azure: non si scopre un bug nel writer mentre si bruciano $/ora).

**Test oracoli minimi** (test-first, [`TESTING_DOCTRINE` §6](../../04_INTELLIGENCE/TESTING_DOCTRINE.md#f0-test-plan)):

- *L1 unit:* `pack-on-fill` rotation alla soglia esatta · atomicità rename · manifest
  shape e sha256 · resume da manifest esistente · pulizia dei `.tmp` orfani.
- *L2 property* (Hypothesis): pack-on-fill è deterministico data una stessa lista di
  campioni (`bytes-for-bytes` su due esecuzioni indipendenti, `ENGINEERING_STANDARDS §1`).
- *L3 acceptance:* pack di un mini-batch reale (F0-T2e) → tar leggibile da
  `webdataset` library, terne riassemblate correttamente, conteggi `manifest` corretti.

---

<a id="dvc-current-state"></a>
## 8. Stato DVC corrente (2026-05-23)

- `dvc init` ☑ eseguito (F1-T2) — `.dvc/` scaffold tracked.
- Remote `azure` ☑ configurato — `azure://gold/dvc` su account `stneurotrigger22`.
- SAS token valido fino al **2026-08-21**, in `.dvc/config.local` (gitignored,
  `ENGINEERING_STANDARDS §6`).
- `dvc push` smoke verde (F1-T2, 48 B test blob).
- Pronto a ricevere `dvc add data/gold/{train,val}` quando F2-T1 produce i primi shard.

**Non da fare ora.** `dvc add` sulla directory `data/gold/` *vuota* non ha senso —
genererebbe un hash della directory vuota che cambierebbe al primo shard. Si traccia
**dopo** il primo flush completo dello `ShardWriter`.

---

## 9. Decision Lock (2026-05-23) — sintesi

Le scelte di questa spec, **approvate dal CEO**:

1. ✅ **Pack-on-fill con pre-shuffle** — no stratification logic interna.
2. ✅ **Shard target 1 GB esatto** (1 073 741 824 byte); tolleranza `+1 sample` (un
   campione che fa sforare la soglia viene incluso, il successivo apre il nuovo shard).
3. ✅ **Tar non compresso** — CPU/A100 più caro del saving di banda intra-region.
4. ✅ **DVC per directory** (`data/gold/train`, `data/gold/val`) — non per file singolo.
5. ✅ **Manifest per split** con `sha256` per shard, seed di matrix, total bytes.
6. ✅ **Branch `*-augmented`** parallelo per F2-T2 — non sovrascrive Gold originale.
7. ✅ **Atomicità via `.tmp` + rename**; resume via manifest.
8. ✅ **`ShardWriter` modulo nuovo** in `src/data_engineering/gold/shard_writer.py`;
   implementazione concreta è sotto-task di F2-T1 prep (mai sul clock Azure).

---
*Spec F0-T5 — **LOCKED 2026-05-23.** Costruita sul contratto F0-T2a §3 (+ amendment §3.8).
Vincolante per F2-T1 e F2-T2.*
