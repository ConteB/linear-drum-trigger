---
id: LIN-DT-ENGSTD-001
title: Engineering Standards — OP-NEUROTRIGGER
type: standard
status: ACTIVE
phase: cross-cutting
domain: Engineering / DSP / AI
version: 1.0.0
updated: 2026-05-20
tags: [engineering, determinism, bit-exactness, coding-standards, dependencies, validation]
related: [LIN-DT-DOSSIER-001, LIN-DT-CHKLST-001, LIN-DT-TESTDOC-001, LIN-DT-SPEC-F0T2a, LIN-DT-SPEC-F0T4a]
supersedes: []
---

# ENGINEERING STANDARDS — OP-NEUROTRIGGER

> Standard ingegneristici trasversali del progetto: determinismo, bit-exactness DSP,
> codifica, dipendenze, validazione statistica del modello, robustezza d'esecuzione.
> Coprono il livello *tecnico* che la dottrina di processo del progetto (STRP-001,
> [`SCHEDULING_DOCTRINE`](SCHEDULING_DOCTRINE.md), [`TESTING_DOCTRINE`](TESTING_DOCTRINE.md))
> non specificava. Vincolante per il codice Python di pipeline (F0/F2) e per il core
> C++/JUCE (F4).

<a id="provenance"></a>
## 0. Provenienza e autorità

Questo documento è il prodotto dell'**audit dell'archivio OpenPhase** (2026-05-20): la
conoscenza ingegneristica universale di quel corpus è stata **distillata e internalizzata
qui**, recidendo ogni dipendenza di percorso dall'archivio (nessun link esterno, nessun
symlink — il progetto è autosufficiente). Le parti specifiche della simulazione acustica
(PySimpa / 001_OP) e le regole operative dell'infrastruttura OP-X sono state **scartate**
perché non pertinenti o in conflitto con le scelte di NeuroTrigger. Dettaglio della
selezione: §8.

**Regola di precedenza:** in caso di conflitto, le decisioni di NeuroTrigger
(Design Lock, Decision Lock CEO, [`MASTER_CHECKLIST`](../MASTER_CHECKLIST.md),
[`DOSSIER_TECNICO`](../docs/methodology/DOSSIER_TECNICO.md)) **prevalgono sempre** su
qualunque standard ereditato.

<a id="determinism"></a>
## 1. Determinismo & Riproducibilità della pipeline dati

La pipeline di rendering Gold produce un **asset permanente e costoso** (spesa Azure
irreversibile). Deve essere riproducibile bit per bit: stessa recipe + stesso seed →
stesso tensore Gold.

- **Seed esplicito e archiviato.** Ogni sorgente di entropia della pipeline
  (augmentation — Machine-Gun Chaos, Studio Mutilation, Transient Saboteurs — selezione
  round-robin, jitter di velocity) usa un RNG con **seed esplicito**. Il seed è parte del
  contratto dati: va registrato nel **DNA-Trace** del campione
  ([`F0-T2a` §3 — DNA-Trace](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#dna-trace-format),
  [`DOSSIER` §3.5](../docs/methodology/DOSSIER_TECNICO.md#dna-trace)). Un campione Gold
  senza seed nel lineage non è riproducibile → è un difetto di contratto.
- **Zero-State.** Build e run della pipeline non dipendono da variabili d'ambiente locali
  non dichiarate né da cache residue. «Funziona sulla mia macchina» non è una prova.
- **Vietato il non-determinismo implicito.** Nessun uso di RNG globale non seedato nella
  logica core. Il training PyTorch fissa i seed (`torch`, `numpy`, `random`) e registra
  la configurazione hardware/precisione nel log dell'esperimento.

<a id="bit-exactness"></a>
## 2. Bit-Exactness numerico (DSP / round-trip RTNeural)

Il prodotto vive o muore sulla coerenza numerica tra l'addestramento (PyTorch, Python) e
l'inferenza nel plugin (RTNeural, C++). Questo è il rischio architetturale che il Gate L3
de-rischia ([`F0-T4b`](../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks)).

- **Test della Somma Inversa (gate del round-trip).** Esportato il modello PyTorch in
  RTNeural JSON e ricaricato in C++, l'output del motore C++ su un input di riferimento
  deve coincidere con l'output PyTorch. Il confronto è **vettoriale e stampato su stdout**
  (max abs delta, RMSE), mai «a occhio». Il Gate L3 si apre solo se le metriche parsate
  sono sotto la tolleranza dichiarata in
  [`F0-T4a` — soglia L3](../docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md#l3-threshold).
- **Core DSP C++ — regole di consistenza floating-point:**
  - **Vietato `-ffast-math` / `/fp:fast`.** Violano IEEE-754. Usare `/fp:precise`.
  - **Denormali → Flush-to-Zero + Denormals-Are-Zero** abilitati nel callback audio: i
    denormali causano spike di CPU non deterministici e rumore di fondo incoerente.
  - **SIMD guard.** Ogni percorso vettorizzato (AVX/SSE) deve dare lo stesso risultato
    numerico della versione scalare di riferimento.
- Coerente col mandato **Zero-Allocation** del thread audio
  ([`MASTER_CHECKLIST` §3 — DSP](../MASTER_CHECKLIST.md#dsp); gate `audit_dsp_rigor.py`,
  F0-T6): determinismo numerico e assenza di allocazioni sono due facce dello stesso
  requisito real-time.

<a id="coding-standards"></a>
## 3. Standard di codifica

### 3.1 Python (pipeline dati F0/F2, training)
- **Type hints completi** su ogni funzione (argomenti e ritorno); `mypy --strict` pulito.
- **Linter:** `ruff` senza errori. Docstring in formato Google/NumPy su moduli e classi.
- **Versione minima** dichiarata; dipendenze bloccate (vedi §4).
- **No silent failure:** vietato `try/except: pass`. Un errore deve essere visibile
  (fail-loud, §6). Vale anche nel codice esplorativo/prototipale.

### 3.2 C++ / JUCE (plugin F4)
- **Standard C++20.** `enum class` al posto di `enum`; `const`/`constexpr` ovunque
  possibile per massimizzare il determinismo a compile-time.
- **RAII:** ownership esplicita; smart pointer (`std::unique_ptr`/`std::shared_ptr`) per
  le risorse; **niente `new`/`delete` manuali**. Distinzione netta tra owning e observer
  pointer. Per ogni classe che gestisce risorse, dichiarazione esplicita di move/copy.
- Nel thread audio valgono i vincoli più stretti del mandato Zero-Allocation (§2).

<a id="dependency-policy"></a>
## 4. Gestione delle dipendenze

Ogni dipendenza esterna è debito tecnico e superficie di rischio supply-chain.

- **Strict pinning.** Versioni bloccate in `requirements.txt` / `pyproject.toml` (Python)
  e nel manifest del build C++. **Vietate le versioni «latest»/floating.** Ogni bump è
  un'azione deliberata. *Eccezione:* patch di sicurezza per una CVE documentata.
- **Isolamento (Adapter Pattern).** Le dipendenze pesanti non «inquinano» il codebase:
  vanno confinate dietro un adapter, così sono sostituibili senza toccare la logica core.
- **Vendoring degli asset di render.** I binari del motore di render (**Sfizz**,
  **DrumGizmo**) e le librerie SFZ del roster vanno conservati in copia locale/mirror: la
  sparizione di un repository a monte non deve rendere il dataset Gold non riproducibile.
- **`ThirdPartyNotices.md` mandatorio nel prodotto spedito.** Il plugin v1.0 EA include
  un file di attribuzione di terze parti. Non è formalità: i kit del roster F0-T1b sono
  in larga parte **CC-BY**, che *impone* l'attribuzione — l'assenza del NOTICE è una
  violazione di licenza ([`DATA_PROVENANCE_LOG` §2.A](../docs/compliance/DATA_PROVENANCE_LOG.md)).
- **Audit pre-release.** Prima della v1.0: scan vulnerabilità note (es. `safety` per
  Python) e verifica che ogni dipendenza spedita sia censita nel NOTICE.

<a id="statistical-validation"></a>
## 5. Validazione statistica del modello

L'output della rete è **stocastico**: i Gate L3/L4 non possono basarsi su una singola run
fortunata (confirmation bias). Integra — non sostituisce — la
[`TESTING_DOCTRINE`](TESTING_DOCTRINE.md) (che governa i layer di test del *codice*).

- **Soglia d'errore esplicita.** Le metriche di accettazione (F-measure onset, errore di
  microtiming, ecc.) hanno una soglia numerica dichiarata *prima* del training — già
  fissata per L3 in [`F0-T4a`](../docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md#l3-threshold).
- **Controllo di varianza.** Una metrica di gate va misurata su **N run indipendenti**
  (seed diversi); si riporta media **e** varianza. Una metrica che passa la soglia in
  media ma con varianza alta non certifica il Gate: indica un modello instabile.
- **Intervallo di confidenza.** I claim pubblici di accuratezza (post-L4) si esprimono
  con intervallo di confidenza al 95 %, non come numero secco.
- **Report machine-verifiable.** Le metriche di validazione sono stampate su stdout/JSON
  da uno script; il gate apre sul *parsing* di quei numeri, mai sull'ispezione visiva di
  un grafico (coerente con l'Ocular Proof).

> **Spec operativa.** I principi sopra sono tradotti in test concreti, soglie numeriche
> e moduli di esecuzione da [`F0-T17 — Statistical Test Plan`](../docs/methodology/F0-T17_STATISTICAL_TEST_PLAN.md)
> (LOCKED 2026-05-23). I gate operativi pre-F2-T3 (`split_consistency`,
> `anti_leak_audit`) e il gate L4 (`evaluation_suite`) sono definiti lì.

<a id="execution-robustness"></a>
## 6. Robustezza d'esecuzione

- **Watchdog sui processi esterni.** Ogni invocazione di Sfizz/DrumGizmo via CLI e ogni
  job di render Azure è avvolto da un **timeout esplicito**. Un processo bloccato che si
  maschera da «esecuzione in corso» è la *Tracker-Integrity Trap*: su Azure significa
  bruciare credito in silenzio.
- **Fail-loud sul «Silent Zero».** Un render che produce silenzio digitale (output
  identicamente zero) senza sollevare errore è un **difetto strutturale**, non un caso
  limite statistico. La pipeline deve fare un sanity-check di non-nullità sull'audio
  renderizzato prima di scrivere il tensore Gold. Aggancia il Gate L2
  ([`F0-T3`](../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks)).
- **Watchdog di sessione lunga.** Il render di massa (F2-T1, 1.5 TB) emette progresso a
  intervalli; uno stallo prolungato senza avanzamento va trattato come fallimento, non
  come lentezza.

<a id="commits"></a>
## 7. Comunicazione operativa — Conventional Commits

I messaggi di commit seguono `<tipo>(<ambito>): <descrizione>`. Tipi: `feat`, `fix`,
`docs`, `refactor`, `ops` (script/infra), `audit` (esito di audit o patch). L'ambito è il
componente o il task impattato (es. `docs: F0-T11 — …`). Autore git: `OP_Magenta`.

---

## 8. Audit OpenPhase — registro della selezione

Cosa è stato **preso** dall'archivio (e adattato), e cosa è stato **scartato**.

### 8.1 Internalizzato (adattato al dominio NeuroTrigger)
| Origine OP-X | Confluito in | Perché utile qui |
| :-- | :-- | :-- |
| `DCM-001` Continuità deterministica | §1 | Render Gold = asset costoso e irreversibile → dev'essere riproducibile. |
| `DCM-002` Bit-Exactness DSP | §2 | Coerenza numerica train↔inferenza: è esattamente il rischio del round-trip RTNeural (Gate L3). |
| `PIP-005` Codifica moderna; `Standard_Architetturali` (RAII) | §3 | Il progetto non aveva uno standard di codifica esplicito per Python + C++. |
| `Gestione_Dipendenze`; `ERM-002` (TCO) | §4 | Molte dipendenze (PyTorch, RTNeural, Sfizz, DrumGizmo, JUCE…); il vendoring protegge la riproducibilità del dataset; il NOTICE è imposto dalle licenze CC-BY del roster. |
| `GVM-003` Validazione statistica | §5 | L'output del modello è stocastico; i Gate L3/L4 vanno protetti dal confirmation bias. |
| `Standard_Architetturali` §8 (watchdog); `Registro_Lezioni_Guerra` §1/§3 | §6 | Sfizz/DrumGizmo girano come subprocess; il render Azure può stallare bruciando credito. |
| `TOP-004` Conventional Commits | §7 | Standardizza i messaggi di commit (già usati di fatto). |

### 8.2 Scartato — e perché
| Origine OP-X | Motivo dello scarto |
| :-- | :-- |
| `ASM-002` Project Harness — *divieto di duplicare il DNA*, SSoT remota | **In conflitto diretto** con la scelta del CEO: NeuroTrigger si **disaccoppia** dall'archivio e internalizza la conoscenza. NeuroTrigger vince. |
| `ERM-006` `PIPELINE_STATUS.json` | NeuroTrigger ha **rimosso** questo file (controllone F0-T10). Tracking via [`MASTER_SCHEDULING`](../04_INTELLIGENCE/MASTER_SCHEDULING.md) §7. |
| `SOP-000` SHIELD / codice override `OP-ALPHA-SIGMA` / kill-switch `GEMINI.md` | Sicurezza-teatro legata all'infrastruttura OP-X; NeuroTrigger ha la propria governance ([`SUB_AGENT_GOVERNANCE`](SUB_AGENT_GOVERNANCE.md)). |
| `POL-AI-001` §3 — *Zero-Direct-Write* (delega obbligatoria di ogni scrittura ai sub-agenti) | Regola operativa OP-X non adottata: NeuroTrigger delega per *governance del rischio*, non per divieto assoluto. |
| `ERM-002` 5-turn budget; `ERM-008` model tiering | Regole operative; `ERM-008` cita per giunta modelli obsoleti. La cadenza è governata da [`SCHEDULING_DOCTRINE`](SCHEDULING_DOCTRINE.md). |
| `FILOSOFIA` Art. B (*PySimpa unica fonte di verità*); `PIP-003` Pure Physics; `Standard_Modellazione_Audio` (t0 −180 dB, ISO 3382) | Specifici della **simulazione acustica** (PySimpa/001_OP). NeuroTrigger fa trascrizione ML di batteria, non acustica computazionale: non pertinenti. |
| `ERM-005` TERS / `SOP-016` Triage / `GVM-002` 4-Gate | Sovrapposti a meccanismi NeuroTrigger già più maturi: STRP-001 (6 fasi), arbitraggio a 7 criteri, Gate L1–L4 della checklist. Non reimportati per non duplicare. |

> *Nota:* alcuni documenti NeuroTrigger ereditati (`TASK_BLUEPRINT.md`, `GEMINI.md`,
> `CLAUDE.md`) contengono ancora riferimenti in prosa a sigle OP-X (`ERM-005`, `SOP-010`,
> `SOP-016`). Sono *dangling* dopo il decoupling: vanno ripuliti in un task separato di
> de-referenziazione — non rientra nello scopo di questo audit.

---
*Engineering Standards v1.0 — derivato dall'audit OpenPhase del 2026-05-20.
NeuroTrigger è la sola autorità vincolante.*
