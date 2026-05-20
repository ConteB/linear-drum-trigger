---
id: LIN-DT-TESTDOC-001
title: Testing & QA Doctrine — OP-NEUROTRIGGER
type: doctrine
status: LOCKED
phase: cross-cutting
domain: Quality Assurance
version: 1.0.0
updated: 2026-05-20
tags: [testing, qa, doctrine, governance, mutation-testing]
related: [LIN-DT-GOV-001, LIN-DT-SPEC-F0T2a, LIN-DT-CHKLST-001]
supersedes: []
---

# 🧪 TESTING & QA DOCTRINE — OP-NEUROTRIGGER
**ID:** LIN-DT-TESTDOC-001 · **Status:** LOCKED — Decision Lock 2026-05-20 (Executive Briefing STRP-001)
**Versione:** 1.0 · **Status operativo:** MANDATORIO / ACTIVE LOCK

> Documento di dottrina. Definisce *come si testa* in OP-NEUROTRIGGER — la pipeline dati
> Python, il core DSP C++/JUCE real-time, la GUI. È sibling di `SCHEDULING_DOCTRINE.md`
> (il *come si decide l'ordine*) e di `SUB_AGENT_GOVERNANCE.md` (il *come si delega*).
> Vincolante per ogni task di codice `[F]`/`[A]`/`[G]` e per ogni delega a sub-agente.

## 0. Come si legge

| Documento | Ruolo |
| :-- | :-- |
| **`TESTING_DOCTRINE.md`** (questo) | *Come si testa* — layer, metriche, gate. |
| `SUB_AGENT_GOVERNANCE.md` §6 | Il protocollo operativo dell'AI-Adversarial QA. |
| `MASTER_CHECKLIST.md` | Registra il presidio test come Design Lock. |
| `audit_dsp_rigor.py` (F0-T6) | Gate *statico* — è il Layer-S di questa dottrina. |

Ambito di dettaglio (Decision Lock): la **dottrina** (§1–§4) e il **test plan F0** (§6) sono
bloccati e implementabili; il piano per il **core DSP C++/GUI** (§5) è *coarse*, raffinato
all'avvio di F4 — il codice C++ è a 0%.

## 1. Principi

1. **Il numero di test non è una metrica.** Conteggio di test e *line coverage* sono
   vanity gameable: un test che esegue una riga senza asserirne il comportamento "copre"
   ma non *verifica*. Vietato scrivere test banali per gonfiare il totale.
2. **Il mutation testing è il gate.** L'efficacia di una suite si misura iniettando bug
   (mutanti) nel codice e contando quanti la suite *uccide*. Un test pigro sopravvive ai
   mutanti → viene smascherato meccanicamente. È la metrica anti-pigrizia (§3).
3. **La spec è l'oracolo.** I test si derivano dai contratti versionati
   (`F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`, `F0-T4a_TCN_TOPOLOGY_SPEC.md`), non dal codice.
   Test-first: l'harness precede l'implementazione (Decision Lock — F0-T9b gate-a F0-T2b/c/d).
4. **Il codice è scritto da AI.** Il codice di progetto è delegato a sub-agenti
   (`POL-AI-001` §3). Il mutation testing e l'AI-Adversarial QA (§4) sono la rete di
   sicurezza specifica di questo modello di sviluppo, non un extra.
5. **Il testing non sostituisce l'Ocular Proof.** I Gate L2–L4 restano firmati con Ocular
   Proof (ispezione umana). La dottrina *circonda* l'Ocular Proof di layer automatici;
   non lo rimpiazza (§8).

## 2. I layer di test

| Layer | Nome | Cosa fa | Ambito |
| :-- | :-- | :-- | :-- |
| **S** | Static gate | Grep dei pattern proibiti nel thread audio (`audit_dsp_rigor.py`) | C++ DSP (F4) |
| **0** | Mutation meta-gate | Testa i test: kill-rate dei mutanti iniettati | tutti |
| **1** | Unit | Test comportamentali, deterministici, veloci; ogni test asserisce una proprietà di contratto | tutti |
| **2** | Property-based / random | Proprietà derivate dalla spec; il framework genera input avversari + shrinking | tutti |
| **3** | Fuzz / input ostili | Input malformati/estremi → asserisce *fallimento controllato, mai crash/corruzione* | tutti |
| **4** | AI-Adversarial QA | Sub-agente indipendente, cieco sull'implementazione, attacca il contratto (§4) | tutti |

**Regola Layer 1 (anti-laziness):** ogni unit test deve asserire una proprietà reale del
contratto. È vietato il test che verifica solo "esegue senza eccezioni". La conformità è
imposta dal Layer 0, non dalla revisione a vista.

## 3. Metriche & soglie — il gate di DoD

Il *Definition of Done* di ogni task di codice è:

```
DoD = (suite verde)  AND  (mutation kill-rate ≥ soglia)  AND  (coverage ≥ floor)
```

| Metrica | Soglia | Natura |
| :-- | :-- | :-- |
| Mutation kill-rate — **moduli critici** (writer Gold-tensor, generatore DNA-Trace, parser recipe) | **≥ 90 %** | gate bloccante |
| Mutation kill-rate — **moduli core** (resto della pipeline) | **≥ 85 %** | gate bloccante |
| Branch coverage — moduli core | **≥ 90 %** | *floor diagnostico*, non target |
| pluginval strictness (C++, F4) | **≥ 8** | gate bloccante (coarse, §5) |

> La coverage è un *floor*: dice cosa **non** è testato, mai che ciò che è coperto è
> testato *bene*. Non è mai un obiettivo — il mutation kill-rate lo è. I mutanti
> sopravvissuti vanno *uccisi* (test aggiunto) o *giustificati per iscritto* (mutante
> equivalente), mai ignorati.

## 4. Protocollo AI-Adversarial QA (Layer 4)

L'idea: i test scritti dallo stesso agente che scrive il codice ereditano il bias
dell'implementatore — testano i percorsi che l'agente *ha pensato*. Il Layer 4 rimuove
il bias per costruzione.

- **Cecità strutturale.** L'agente QA riceve **solo**: la spec/contratto, l'interfaccia
  pubblica, questa dottrina. **Non** riceve il codice di implementazione.
- **Sessione e identità separate.** Agente-implementatore ≠ agente-QA. Il QA scrive i
  test *prima* di vedere qualunque sorgente.
- **Mandato:** attaccare il contratto — boundary, contraddizioni, ambiguità, input ostili.
- **Doppio frutto:**
  1. *Bug nell'implementazione* — il test rosso lo prova.
  2. *Difetti di spec* — se l'agente QA non riesce a scrivere un test perché la spec è
     sottospecificata, è un **bug di documentazione** loggato e risolto a monte.
- **Verification Gate (triage delle failure):** ogni test rosso del Layer 4 è triagiato
  in `{bug reale · ambiguità di spec · test non valido}`. Nessuna failure si chiude senza
  triage scritto.
- **Governance:** è un pattern di delega formale — vedi `SUB_AGENT_GOVERNANCE.md` §6.

## 5. Core DSP C++/JUCE & GUI — coarse (dettaglio a F4)

Direzione bloccata; i dettagli si raffinano all'avvio di F4 (codice C++ a 0%).

- **Validatore:** `pluginval` (Tracktion) — standard de-facto VST3/AU. Target
  **strictness ≥ 8** (sopra il 5 "minimo host-compat"); exit-code 0/1 come gate scriptabile.
- **Test Zero-Allocation dinamico:** test-build con override di `new`/`malloc` che
  asserisce **0 allocazioni** dentro `processBlock`. È il complemento *dinamico* del
  Layer-S statico (`audit_dsp_rigor.py`): il grep prende l'ovvio, il contatore prende
  l'allocazione nascosta (una `std::string`, una cattura di lambda, una chiamata di libreria).
- **Null-test di determinismo:** stesso input due volte → output bit-identico. Il claim
  Chronos Engine "sample-accurate / jitter-free" diventa un'asserzione automatica, non
  solo Ocular Proof.
- **Sicurezza numerica:** buffer con NaN/Inf/denormali → output finito, nessun picco CPU
  da denormali.
- **Differential test del Model Artifact:** il round-trip RTNeural di F0-T4b (match
  numerico PyTorch↔C++) è formalizzato come **regressione permanente** di ogni export
  di modello.
- **GUI JUCE:** stress dell'editor (open/close/resize, parametri da GUI-thread — coperto
  da pluginval) + eventuali snapshot test. Dettaglio a F4.
- **Unit/property C++:** Catch2 + RapidCheck — scelta ratificata a F4.

## 6. Test plan della pipeline F0 (dettagliato)

Implementato in **F0-T9b** (harness), che **gate-a F0-T2b/c/d** (test-first).

### 6.1 Scaffolding
`pytest` + `Hypothesis` (property-based) + `mutmut` (mutation) + `coverage.py` (floor) +
`Atheris` (fuzzing coverage-guided dei parser). Albero `tests/`, config versionata.

### 6.2 Test-oracolo derivati dal contratto F0-T2a (scritti prima del codice)
- **Writer Gold-tensor / `target.f16`** *(modulo critico — kill-rate ≥ 90 %)*: layout
  `flat-25` (per il bus `b`: col `3b/3b+1/3b+2`); `n_frame = ceil(duration_s · R_target)`
  con `R_target = 344.53125 Hz`; range numerici (§3.5 F0-T2a); 0 NaN/Inf; sha256 dei
  buffer == `dna.json`; shape in `dna.json` == shape del buffer.
- **DNA-Trace** *(modulo critico — kill-rate ≥ 90 %)*: il barcode è una **biiezione**
  (`decode∘encode = id`); il `dna.json` permette il reverse-engineering completo del campione.
- **Parser recipe YAML** *(modulo critico — kill-rate ≥ 90 %)*: ogni campo dello schema
  §1.1 F0-T2a validato; recipe malformata → errore esplicito, mai stato parziale.
- **Standardizzazione mic** *(core)*: ∀ `n_mic ∈ [1,8]` → 8 slot canonici, zero-fill
  corretto, nessuna perdita di dato, deterministico.

### 6.3 Accettazione per sotto-task
- **F0-T2b (Sfizz):** render deterministico per seed; `sample_rate = 44100`; conteggio
  canali per `mic_config`; ampiezza in `[-1,1]`.
- **F0-T2c (DrumGizmo):** `n_mic` coerente col `mic_config`; **bleed presente** —
  proprietà *falsificabile*: cross-correlazione inter-canale > 0 (non "a occhio").
- **F0-T2d (writer):** suite §6.2 completa + gate mutation ≥ 90 %.
- **F0-T2e (orchestrazione):** smoke end-to-end + conteggio di N campioni Gold.

### 6.4 Fuzz F0 (Layer 3)
YAML malformato; WAV/MIDI troncati o corrotti; audio NaN/Inf; clip a durata zero o
estrema; `n_mic` fuori range. Asserzione: errore controllato, **mai** crash o shard
WebDataset corrotto.

### 6.5 AI-Adversarial QA F0 (Layer 4)
Un sub-agente QA attacca il contratto F0-T2a *prima* che il codice di F0-T2d sia integrato.

## 7. Tooling — sintesi

| Layer | Python (F0) | C++ (F4, coarse) |
| :-- | :-- | :-- |
| Unit | `pytest` | Catch2 |
| Property-based | `Hypothesis` | RapidCheck |
| Fuzz | `Hypothesis` + `Atheris` | libFuzzer / pluginval fuzz |
| Mutation | `mutmut` *(cosmic-ray se serve parallelismo)* | da ratificare a F4 |
| Coverage (floor) | `coverage.py` | da ratificare a F4 |
| Validazione plugin | — | `pluginval` ≥ 8 |

## 8. Integrazione con i Gate L1–L4

- I layer automatici di questa dottrina sono **precondizione**, non sostituto, della
  firma di Gate. L'**Ocular Proof** resta la firma umana dei Gate L2/L3/L4.
- **Gate L2:** i check FP16/DNA-Trace (F0-T2a §3.7) sono eseguiti dalla suite F0-T9b; la
  firma L2 resta l'ispezione manuale (F0-T3).
- **Gate L3:** la soglia metrica è in `F0-T4a_TCN_TOPOLOGY_SPEC.md` §7; il round-trip
  RTNeural è il differential test canonico (§5).
- **Gate L4 / F5:** "QA conforme agli standard interni" = applicazione piena di questa
  dottrina, inclusa la validazione pluginval ≥ 8.

---

## 9. Decision Lock (2026-05-20)
Approvato dal CEO (Executive Briefing STRP-001 — Testing & QA Doctrine):
1. ✅ Numero di test rifiutato come metrica; **mutation kill-rate** come gate di DoD
   (critici ≥ 90 %, core ≥ 85 %); coverage solo come floor diagnostico (≥ 90 %).
2. ✅ Tassonomia a 4 layer + Layer-S statico.
3. ✅ Protocollo **AI-Adversarial QA** (§4) — formalizzato in `SUB_AGENT_GOVERNANCE.md` §6.
4. ✅ `pluginval` ≥ 8 come validatore C++ (coarse, dettaglio F4).
5. ✅ Nuovi task **F0-T9a** (questa dottrina) e **F0-T9b** (harness pipeline F0),
   quest'ultimo **gate di F0-T2b/c/d** (test-first).

---
*Testing & QA Doctrine v1.0 — STRP-001. **LOCKED 2026-05-20.** Vincolante per ogni task
di codice e ogni delega a sub-agente. Ambito C++/GUI raffinato a F4.*
