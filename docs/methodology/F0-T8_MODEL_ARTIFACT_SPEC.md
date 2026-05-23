---
id: LIN-DT-SPEC-F0T8
title: F0-T8 — Model Artifact (export, packaging & trasporto)
type: spec
status: LOCKED
phase: F0
domain: AI / Plugin Integration / Security
version: 1.0.0
updated: 2026-05-23
tags: [model-artifact, rtneural, soft-drm, aes-gcm, juce, binarydata, F0-T8]
related: [LIN-DT-DOSSIER-001, LIN-DT-SPEC-F0T2a, LIN-DT-SPEC-F0T4a, LIN-DT-CHKLST-001, LIN-DT-ENGSTD-001]
supersedes: []
---

# 📦 F0-T8 — SPEC: MODEL ARTIFACT

**Status:** LOCKED — *direzione* ratificata dall'Executive Briefing STRP-001
del 2026-05-20 (Decision D3); questo documento ne **dettaglia lo schema**
operativo per implementazione. Vincolante per F4 (plugin C++/JUCE).

**Riferimenti:**
[`DOSSIER §11 — Soft-DRM`](DOSSIER_TECNICO.md#licensing) ·
[`F0-T4a §5 — PDC & latency_samples`](F0-T4a_TCN_TOPOLOGY_SPEC.md#pdc) ·
[`MASTER_CHECKLIST §1 — AI/Neural`](../../MASTER_CHECKLIST.md#ai-neural) ·
[`ENGINEERING_STANDARDS §1 — determinismo`](../../04_INTELLIGENCE/ENGINEERING_STANDARDS.md#determinism) ·
[`MASTER_SCHEDULING §6 — F0-T8`](../../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks).

---

## 0. Sintesi esecutiva (1 paragrafo)

Il *Model Artifact* è il file binario che contiene il **cervello** del plugin
— i pesi della TCN addestrata in F2-T3 + i metadati che ne dichiarano
identità, latenza PDC, compatibilità di runtime, lineage. È **prodotto in
Python** da uno strumento offline (`tools/build_model_artifact.py`), è
**embedded nel plugin C++/JUCE** via `juce::BinaryData` al build-time, è
**caricato a startup** dal plugin per popolare l'header del badge UI
`LOOK-AHEAD: [X]ms (PDC SYNCED)` (DOSSIER §5.3) e per inizializzare il
grafo d'inferenza RTNeural-equivalente (F0-T4b ☑). Il payload (i pesi)
viaggia **cifrato AES-256-GCM** con chiave derivata da una master key
compilata nel plugin tramite la dottrina *Poisoned DSP* (DOSSIER §11.3) —
una mossa che innalza il costo del cracking senza appesantire la CPU
dell'utente onesto. Schema versionato, fail-loud, compatibile col round-trip
PyTorch ↔ C++ già verificato a `1.19e-07 ≈ epsilon fp32` (Gate L3, 2026-05-23).

---

## 1. Razionale — perché serve questo documento

Tre cose oggi non sono scritte da nessuna parte:

1. **Come si protegge il modello dalla pirateria.** Il payload `.bin`
   prodotto da `src/neural/export_bin.py` (F0-T4b) è in **chiaro**: bastano
   `strings` e un editor esadecimale per estrarlo dal `.vst3` e
   redistribuirlo. Serve almeno una barriera di costo: AES-GCM con chiave
   non hardcoded *in chiaro*.
2. **Come fa il plugin a sapere "ho 100 ms di latenza"?** F0-T4a §5 dice
   "*`latency_samples` esatto misurato da F0-T4b e scritto nell'header del
   Model Artifact*". Quel header non esiste ancora. Va definito *prima* di
   F4 — altrimenti il badge UI `LOOK-AHEAD: 100ms` diventa una costante
   hardcoded e ogni model bump richiede una nuova build del plugin.
3. **Come si gestisce la compatibilità.** Plugin v1.0 con modello v1.0
   funziona. Plugin v1.0 con modello v2.0 — cosa succede? Crash? Fallback?
   Caricamento parziale? Va deciso adesso, non sotto pressione di un
   bug-report dopo il lancio.

Questo documento risponde alle tre domande, fissando lo schema binario,
l'algoritmo di cifratura, le regole di versioning, e il tooling Python che
produce e verifica gli artifact.

---

## 2. Competitor & Market Analysis (compressed)

| Plugin / vendor | Strategia di trasporto pesi modello | Cifratura | Versioning |
| :-- | :-- | :-- | :-- |
| **Valhalla DSP** (Sean Costello) | DSP analogo, no ML — ma il modello Soft-DRM offline (`juce::RSAKey`) è il nostro riferimento di policy | n.a. | n.a. |
| **FabFilter Pro-Q** | DSP parametrico classico — pesi non applicabili | n.a. | n.a. |
| **iZotope Neutron / RX** (ML embedded) | Modelli `.izmod` proprietari embedded nel binario; cifratura non documentata; struttura non pubblica | sì (sconosciuto) | major.minor con downgrade silente |
| **Sonible smart:EQ** | Modelli embedded compilati in `.bundle`/`.so`; presumibilmente XOR/AES con chiave hardcoded | sì | major.minor |
| **Tonex / Neural DSP Quad Cortex** | Modelli `.tnx` portabili user-side; **XOR ofuscation** rapidamente reverse-engineered (community ha tool open per estrarre i pesi) | XOR debole | flat |
| **NAM (Neural Amp Modeler)** | Modelli `.nam` **non cifrati** — community first, OSS | nessuna | schema JSON |
| **OP-NeuroTrigger** (this) | **AES-256-GCM + Poisoned key derivation + header in chiaro** | sì (forte) | semver + compat-range esplicito |

**Lettura strategica.**

- **Soglia "abbastanza sicuro":** Neural DSP ha pagato un costo reputazionale
  per la cifratura XOR debole — community ha scritto extractor in poche
  settimane. AES-256-GCM è quattro ordini di grandezza più costoso da
  attaccare in modo brute-force; il punto debole reale diventa la **chiave**,
  che deve essere *non estraibile con strings*. Da qui la dottrina Poisoned
  DSP (DOSSIER §11.3) applicata anche alla key derivation, non solo al
  license check.
- **Header in chiaro è un'arma di marketing.** I vendor che cifrano *tutto*
  (FabFilter, Sonible) non possono mostrare metadati utili nell'UI senza
  pre-decifrare. Noi cifriamo solo il payload pesi; l'header (model_id,
  version, latency_samples, dataset_sha256) resta leggibile e alimenta il
  badge `LOOK-AHEAD: 100ms` e — per uso interno — un comando "About this
  model" nell'UI futura. Questo è coerente con la doctrine "Laboratory
  Precision" (DOSSIER §5.2) — niente magia, tutto leggibile.

---

## 3. Open-Source Codebase Analysis

| Component | Library | Licenza | Note |
| :-- | :-- | :-- | :-- |
| **AES-256-GCM (Python build-side)** | `cryptography` (PyCA) | Apache-2.0 / BSD | de facto standard; battle-tested; FIPS-cert |
| **AES-256-GCM (C++ load-side)** | `juce::AES` (JUCE) | dual GPL / commercial | già in dipendenza del plugin; CBC-only nelle versioni < 7 → *non sufficiente* |
| **AES-256-GCM (C++ load-side) — alt** | `mbedtls` | Apache-2.0 | leggera, embeddable, GCM nativo |
| **AES-256-GCM (C++ load-side) — alt** | `libsodium` | ISC | API "misuse-resistant", GCM via AES-256-GCM-SIV |
| **HMAC-SHA-256** | stdlib (Python: `hashlib`) + JUCE (`juce::CryptoHash::SHA256`) | n.a. | usato solo per integrity check ridondante (GCM auth tag già copre) |
| **Key Derivation Function** | `cryptography.hazmat.primitives.kdf.hkdf.HKDF` (PyCA) + C++ riproduzione (HKDF è ~30 righe di stdlib) | Apache-2.0 | RFC 5869, deterministica |

**Decisione tooling:**

- **Build side (Python):** `cryptography` PyCA → unica dipendenza nuova
  in `requirements.txt`. Pinnata a versione stabile (≥ 41.0).
- **Load side (C++):** `mbedtls` come dipendenza vendor in `vendor/mbedtls`
  (Apache-2.0 → compatibile con la nostra distribuzione commerciale).
  `juce::AES` scartato perché non espone GCM nelle versioni di JUCE su cui
  poggia il progetto. `libsodium` valido ma più pesante e API meno
  esplicita per GCM.
- **HKDF:** riprodotto manualmente in C++ (~30 righe stdlib) per evitare
  un'altra dipendenza solo per quello.

**Pattern stabili osservati** (Pluginguru forum, KVR DSP-forum,
discussion in `iPlug2/wdl-ol`):

- Magic bytes 4 byte distinto + schema_version 4 byte → la convenzione di
  fatto per binary plugin assets.
- Header *in chiaro* con HMAC (o GCM additional authenticated data, AAD)
  → previene tampering anche sulla parte non cifrata.
- KDF deterministica con salt embedded nel file → permette stesso file su
  più plugin senza ri-cifratura.
- "Poisoned" key derivation: la master key non vive in una singola
  funzione `getMasterKey()` ma è ricostruita pezzo per pezzo da costanti
  sparse in moduli diversi del binario, tipicamente nel hot path
  d'inferenza per ostacolare l'estrazione statica.

---

## 4. UX / UI Impact

| Superficie UI | Cosa legge dal Model Artifact | Comportamento se assente / corrotto |
| :-- | :-- | :-- |
| **Badge `LOOK-AHEAD: [X]ms (PDC SYNCED)`** (DOSSIER §5.3) | `header.latency_ms = header.latency_samples × 1000 / sample_rate` | Fail-loud: plugin rifiuta di passare in *active* — mostra `MODEL ARTIFACT ERROR`; nessun fallback silenzioso |
| **`MODE: MIXING GRADE ONLY`** (F0-T4a §5) | `header.profile_id` (enum: `mixing_grade` / `tracking_grade` *future*) | come sopra |
| **"About this model"** (UI futura, F4) | `header.model_id`, `header.version`, `header.build_timestamp`, `header.dataset_sha256` | sezione "About" disabilitata |
| **`REGISTERED TO: [NOME]`** (DOSSIER §11.2) | *non* dal Model Artifact — dal `.license` file; **disaccoppiato** | n.a. |

**Doctrine `Laboratory Precision`** (DOSSIER §5.2): l'header è
leggibile-da-uomo perché *trasparenza tecnica = arma di marketing* (lo
stesso pattern di pubblicare bootstrap CI in F0-T17). Cifrare *anche*
l'header sarebbe sicurezza-teatro: nessuna informazione strategica vive
nei metadati.

---

## 5. Tech Implementation Matrix

### 5.1 Schema binario LOCKED

Tutti i numeri in **little-endian** (ENGINEERING_STANDARDS §1).

```
┌─────────────────────────────────────────────────────────────────────┐
│ FRAME ARTIFACT — file ``model_<id>_<version>.opna``                 │
├─────────────────────────────────────────────────────────────────────┤
│ 0x00  magic               4 bytes   = "OPNA"                        │
│ 0x04  format_version      uint32    = 1                             │
│ 0x08  header_length       uint32    = N (offset payload = 16 + N)   │
│ 0x0C  payload_length      uint32    = M (cifrato, incluso auth tag) │
│                                                                     │
│ 0x10  header_json         N bytes   utf-8 JSON (vedi §5.2)          │
│                                                                     │
│ 0x10+N  iv                12 bytes  AES-GCM nonce (random per file) │
│ 0x10+N+12  ciphertext     M-12-16 bytes  payload cifrato (vedi §5.3)│
│ 0x10+N+M-16  auth_tag     16 bytes  GCM authentication tag          │
└─────────────────────────────────────────────────────────────────────┘
```

**Estensione file:** `.opna` (OP-NeuroTrigger Artifact). Distinta da
`.opnt` (il payload in chiaro, F0-T4b, sidecar di sviluppo).

**Magic 4-byte:** `OPNA` — distinto da `OPNT` del payload F0-T4b.
Permette `file artifact.opna` / `od -c` di vedere a colpo d'occhio se è
il wrapper cifrato o il payload in chiaro.

<a id="header-json"></a>
### 5.2 Header JSON LOCKED

L'header è **JSON utf-8 in chiaro**, pretty-printed con chiavi sortate
(ENGINEERING_STANDARDS §1 — riproducibilità byte-per-byte). Schema:

```json
{
  "artifact_schema_version": 1,
  "model_id": "neurotrigger-tcn-v1",
  "model_version": "1.0.0",
  "runtime_compat_min": 1,
  "runtime_compat_max": 1,
  "build_timestamp_utc": "2026-10-15T12:00:00Z",
  "build_tool_version": "0.1.0",
  "profile_id": "mixing_grade",
  "sample_rate": 44100,
  "n_channel_in": 8,
  "n_channel_out": 25,
  "latency_samples": 4410,
  "latency_ms": 100.0,
  "target_frame_rate_hz": 344.53125,
  "training_seed": 4242,
  "dataset_sha256": "abc123...",
  "recipe_matrix_seed": 8675309,
  "n_parameters": 83673,
  "payload_format": "OPNT/1",
  "payload_sha256": "def456...",
  "kdf_salt": "base64:..."
}
```

**Campi anchor (vincolanti per il loader C++):**

| Campo | Tipo | Uso plugin |
| :-- | :-- | :-- |
| `artifact_schema_version` | uint | Loader rifiuta se non-matching con la propria compat-range |
| `model_id` | string | identità logica del modello (immutabile attraverso versioni) |
| `model_version` | semver | `MAJOR.MINOR.PATCH` — `MAJOR` bump = breaking |
| `runtime_compat_min/max` | uint | range di `artifact_schema_version` che questo file dichiara di supportare (vedi §5.5) |
| `latency_samples` | uint | sorgente di verità del badge PDC — `juce::AudioProcessor::setLatencySamples(this)` |
| `latency_ms` | float | derivato da `latency_samples / sample_rate × 1000` — ridondante ma leggibile |
| `payload_sha256` | hex64 | calcolato sul payload **in chiaro** (pre-cifratura) — verificato post-decifratura |
| `kdf_salt` | base64 16-byte | salt per HKDF derivation (vedi §5.4) |

Tutti gli altri campi sono metadati informativi (lineage) — utili al
debug, non bloccanti.

### 5.3 Cifratura del payload

| Asse | Opzione A (XOR debole) | Opzione B (AES-256-GCM) | Opzione C (chunked AES + HMAC sep.) | Raccomandazione |
| :-- | :-- | :-- | :-- | :-- |
| Algoritmo | XOR con chiave 256-bit | **AES-256-GCM**, AAD = header_json bytes | AES-256-CTR + HMAC-SHA-256 sep | **B** — singolo passo, auth integrata, AAD lega header al payload |

**Parametri LOCKED:**

- **Cipher:** AES-256-GCM (NIST SP 800-38D).
- **Key length:** 256-bit derivata via HKDF (§5.4).
- **IV / nonce:** 12 byte random per file (CSPRNG `os.urandom(12)`).
- **AAD (additional authenticated data):** l'intero `header_json` bytes
  (incluso il `kdf_salt` che lo lega univocamente a questa cifratura).
- **Auth tag:** 16 byte appesi al ciphertext.
- **Payload pre-cifratura:** identico al `.bin` di F0-T4b
  (`src/neural/export_bin.py`) — magic `OPNT`, schema v1, layer-by-layer.

### 5.4 Key derivation — la parte critica

**Vincolo di prodotto:** la master key non può vivere come blob `static
const uint8_t MASTER_KEY[32] = {...}` nel sorgente C++. Un attaccante
con `strings` o un debugger statico la troverebbe in minuti.

**Soluzione: HKDF + Poisoned distributed assembly.**

```
master_seed_C  =  bytes ricostruiti da 4 costanti integer sparse in 4 moduli C++:
                  Tcn::kSensitivityFloor (DSP file)
                  Tcn::kSampleQuantum    (latency file)
                  Tcn::kFocalGamma       (loss-equivalente file)
                  Tcn::kBleedDecay       (DSP file)
                  → master_seed_C = pack32(a, b, c, d) || pack32(d, c, b, a) || ... (32 byte)

artifact_key   =  HKDF-SHA256(
                    ikm   = master_seed_C,
                    salt  = header.kdf_salt   (random 16 byte per file),
                    info  = b"OPNA/v1/" || model_id.encode() || model_version.encode(),
                    L     = 32  bytes
                  )
```

**Conseguenze pratiche:**

- Il sorgente del plugin **non contiene mai** la stringa "master key" né
  alcun array dichiarato come tale.
- Cambiando un solo bit di una qualsiasi delle 4 costanti, l'intero
  modello smette di decifrare → il cracker che modifica una costante
  per testarne il ruolo *rompe* il plugin in modo silenzioso.
- Le 4 costanti sono **realmente usate** nel hot path d'inferenza
  (`kSensitivityFloor` modula la soglia onset, `kSampleQuantum` è usato
  nel buffer della delay-line, ecc.) → un attaccante non può
  identificarle solo guardando i call site.
- Lo salt è random per file → due artifact dello stesso modello hanno
  ciphertext diversi (proprietà GCM).
- La derivation è deterministica → stesso artifact + stesso plugin →
  stessa chiave senza necessità di handshake.

**Limite riconosciuto.** Questo schema sposta la barriera dal "estrarre
una chiave da `strings`" al "ricostruire una chiave da analisi dinamica
del binario con debugger / Ghidra". È un costo additivo, non assoluto.
Coerente con la doctrine Soft-DRM (DOSSIER §11): aumentare il *costo*
del cracking, non renderlo impossibile.

### 5.5 Versioning rules

```
artifact_schema_version  (struttura del wrapper .opna — questo documento)
    1  =  schema iniziale (questa spec)
    2  =  futuro breaking change del wrapper (es. cifra anche l'header)

runtime_compat_min/max   (range di schema il file dichiara di accettare)
    plugin v1.0 sa leggere schema 1     → carica solo artifact con compat_min <= 1 <= compat_max

payload_format           (string "OPNT/N" — schema del payload interno)
    "OPNT/1"  =  F0-T4b layout
    "OPNT/2"  =  futuro breaking change del payload

model_id                 (identità logica — case-insensitive)
    deve matchare al plugin: "neurotrigger-tcn-v1"

model_version (semver)
    MAJOR bump → breaking nel comportamento del modello (es. layout target diverso)
    MINOR bump → backward-compat (es. miglior accuracy, stesso I/O)
    PATCH bump → bug fix interno (no comportamento osservabile)
```

**Comportamento del loader (LOCKED):**

```
1. Apri file .opna.
2. Verifica magic == "OPNA"; format_version supportato? altrimenti FAIL.
3. Parsa header_json. Verifica artifact_schema_version ∈ [runtime_compat_min,
   runtime_compat_max] del PLUGIN. altrimenti FAIL.
4. Verifica model_id == EXPECTED_MODEL_ID. altrimenti FAIL.
5. Verifica MAJOR(model_version) == EXPECTED_MAJOR. altrimenti FAIL.
6. Ricostruisci la master key (§5.4); deriva artifact_key con header.kdf_salt.
7. Decifra payload con AES-GCM(key=artifact_key, iv, AAD=header_json bytes).
   GCM auth_tag mismatch → FAIL (header o payload manomesso).
8. Verifica sha256(payload_plaintext) == header.payload_sha256. altrimenti FAIL.
9. Verifica payload magic == "OPNT", payload schema v == header.payload_format.
   altrimenti FAIL.
10. Carica i pesi nel grafo RTNeural-equivalente.
11. setLatencySamples(header.latency_samples).
```

**Tutte le `FAIL` sono fail-loud** — UI mostra `MODEL ARTIFACT ERROR`,
output silente. Nessun fallback automatico verso un modello bundled "di
emergenza" (sarebbe sicurezza-teatro: un cracker disabilita comunque i
controlli).

### 5.6 Tooling Python (build & verify)

| Tool | Input | Output | Verifica |
| :-- | :-- | :-- | :-- |
| `tools/build_model_artifact.py` | `--checkpoint pesi.pt --metadata header.yaml --master-seed-hex 64hex` | `artifact.opna` | nessuna (genera) |
| `tools/verify_model_artifact.py` | `--artifact artifact.opna --master-seed-hex 64hex --reference-output reference.npy` | exit 0 / 1 + report JSON | apre, decifra, parsifica, ri-esegue round-trip su input deterministico, confronta con `reference.npy` |

Pattern simmetrico a `tools/run_round_trip.py` (F0-T4b). I master-seed
in CLI sono **per testing** — in produzione il C++ li ricostruisce da
costanti reali del codebase. Lo script Python genera anche un report
JSON con il diff di tutti i campi header (per CI / spot-check).

---

## 6. Executive Briefing — Raccomandazioni numerate

Le 7 raccomandazioni richiedono ratifica esplicita (✅ / ❌ / modifica).

### B1. Magic + estensione

Adottare magic `OPNA` (4 bytes) + estensione file `.opna`. Distinto
da `OPNT` (payload F0-T4b in chiaro, sidecar di sviluppo).

### B2. Schema binario

Adottare il layout §5.1: header_json in chiaro + IV 12 byte + ciphertext
+ GCM auth tag 16 byte. AAD = header_json bytes (lega header al payload).

### B3. Header JSON

Adottare il payload §5.2 (15 campi LOCKED + 5 lineage). Sortato chiavi,
utf-8, pretty-printed → byte-identico per stessi metadati.

### B4. Cifratura

Adottare **AES-256-GCM** con chiave a 256 bit derivata via **HKDF-SHA256**.
IV random per file. Niente HMAC separato (GCM auth tag basta). Niente
chunked encryption (modello pesa ~250 KB, single-shot va bene).

### B5. Key derivation Poisoned

Adottare la dottrina §5.4: master seed assemblato a runtime da **4
costanti integer** dichiarate nei file `tcn_dsp.cpp`, `tcn_latency.cpp`,
`tcn_loss.cpp`, `tcn_dsp.cpp` (lo stesso file due volte di proposito);
HKDF con salt random per file + info `OPNA/v1/<model_id>/<version>`. Le
4 costanti devono essere **realmente usate** nel hot path d'inferenza.

### B6. Versioning rules

Adottare §5.5 — `artifact_schema_version` per il wrapper +
`payload_format` per il payload + `runtime_compat_min/max` per il range
+ `model_id` per identità + semver `MAJOR.MINOR.PATCH` per il modello.
Loader fail-loud su ogni mismatch.

### B7. Tooling Python

Aggiungere `tools/build_model_artifact.py` + `tools/verify_model_artifact.py`
in F0-T8b (implementazione, ~1 sessione). Dipendenza nuova:
`cryptography ≥ 41` in `requirements.txt`.

---

## 7. Costo, timing, impatto fasi

| Voce | Costo | Quando |
| :-- | :-- | :-- |
| Sviluppo spec (questo file) | ☑ chiuso 2026-05-23 | — |
| Implementazione tooling Python (F0-T8b) | ~1 sessione locale | post Decision Lock CEO; gated F2-T3 (artifact prodotto a fine training) |
| Costo Azure | **$0** — gira sul Mac M5; il modello cifrato finisce su Blob a fine F2-T3 | — |
| Implementazione loader C++ (F4) | ~1-2 settimane (mbedtls integration + tests + Poisoned wiring) | F4 fase 2-3 |
| Audit di sicurezza esterno (opzionale) | ~$2-5k commerciale | post-F5, prima del lancio v1.0 EA |

**Sblocca / de-rischia:**

- **F2-T3 (training Gold):** lo script di end-of-training produce
  direttamente l'artifact cifrato → niente "post-processing" manuale
  delle weight, riduce surface di errore.
- **F4 (plugin):** ha già lo schema da implementare, non improvvisa.
- **F5 (release v1.0):** la build prod di JUCE/`BinaryData` ingerisce
  l'artifact via una sola riga del CMake.

---

## 8. Decision Lock — applicato

Decision Lock CEO 2026-05-23 (in linea col STRP-001 D3 del 2026-05-20).
Le 7 raccomandazioni B1..B7 sono ratificate come sopra.

Fase 6 (Docs Update) — propagato:

1. **DOSSIER §11** → puntatore a questa spec per i dettagli formato
   (rimane come dottrina di alto livello, non duplicato).
2. **F0-T4a §5** → aggiornare "scritto nell'header del Model Artifact
   (`F0-T8`)" con link alla §5.2 di questo file.
3. **MASTER_CHECKLIST §1** → marcare `F0-T8` come `[x]`.
4. **MASTER_SCHEDULING §7** → F0-T8 da `☐` → `☑`; aggiungere F0-T8b
   (implementazione tooling Python) come sotto-task `[F]` P3, sbloccato
   da questa spec.

---

## 9. Note operative — implementazione (per F0-T8b, fuori scope qui)

Per il futuro implementatore di `build_model_artifact.py`, traccia
operativa minima:

1. Lettura header da file `meta.yaml` (formato semplice, lineage
   leggibile da CI).
2. Lettura `.pt` checkpoint → invocazione `export_tcn` + `export_binary`
   esistenti (F0-T4b) → genera il payload `.opnt` temporaneo.
3. Calcolo `payload_sha256` sul payload in chiaro.
4. Generazione `kdf_salt` = `os.urandom(16)`.
5. Derivazione `artifact_key` via HKDF (PyCA `HKDFExpand`).
6. Compilazione header JSON definitivo (con `payload_sha256` e
   `kdf_salt` base64-encoded) — chiavi sortate.
7. Encoding header utf-8 + cifratura payload con AES-GCM
   (AAD=header_bytes, iv=`os.urandom(12)`).
8. Scrittura file binario `.opna` finale (con `header_length` e
   `payload_length` calcolati post-cifratura).
9. Verifica: ri-apertura immediata + decifratura + diff payload
   plaintext (smoke self-test).

Lo script `verify_model_artifact.py` è simmetrico: lettura, parsing,
decifratura, comparazione con un input/output di riferimento (round-trip
F0-T4b style, ma a *runtime*).

---

*Spec F0-T8 — STRP-001 fase 4-5 chiusa. **LOCKED 2026-05-23.**
Vincolante per F0-T8b (tooling) e F4 (loader C++). Round-trip già
verificato a 1.19e-07 ≈ epsilon fp32 (F0-T4b ☑, Gate L3).*
