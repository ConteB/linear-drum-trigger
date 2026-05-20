---
id: LIN-DT-AUDIT-001
title: Audit Resolution Log — Coerenza Documentale
type: registro
status: ACTIVE
phase: cross-cutting
domain: Operations / Knowledge Management
version: 1.0.0
updated: 2026-05-20
tags: [audit, governance, consistency]
related: [LIN-DT-DOCSTD-001, LIN-DT-CHKLST-001, LIN-DT-DOSSIER-001]
supersedes: []
---

# 🔧 AUDIT RESOLUTION LOG — COERENZA DOCUMENTALE
**Data:** 2026-05-20
**Tipo:** Audit di pre-produzione documentale (Gate L1)
**Esito:** ~30 falle individuate e risolte su 15 documenti
**Protocollo:** STRP-001 (6 fasi) applicato alle 3 decisioni strategiche; correzione diretta per le incoerenze formali.

---

## 1. DECISION LOCK (Fase 5 STRP-001 — approvazione CEO)

### DL-01 — Motore di Rendering Audio: **Sfizz + DrumGizmo**
- *Problema:* la documentazione indicava Sfizz/pedalboard/DrumGizmo, il codice-test usava FluidSynth/SF2.
- *Competitor/OSS analysis:* le pipeline di dati per drum-detection di qualità (es. progetti basati su DrumGizmo) usano librerie multi-microfono; i SoundFont `.sf2` non espongono tracce multi-mic.
- *Razionale:* il moat primario del prodotto è la simulazione del **bleeding microfonico**, fisicamente impossibile da generare con `.sf2`. FluidSynth era un test usa e getta.
- *Decisione:* **Sfizz (SFZ multi-layer) + DrumGizmo (CLI multi-mic)**. FluidSynth scartato.

### DL-02 — Price Lock: **$149 USD / $99 Early-Access**
- *Problema:* prezzo indicato come $149 / $199 / €99 / €149+ in documenti diversi, con valute miste.
- *Razionale:* allineamento allo Scenario B della Quantitative Analysis; Early-Access per validare il mercato.
- *Decisione:* prezzo a regime **$149 USD**, Early-Access **$99 USD**. Valuta prezzo = USD; budget interno di progetto = EUR.

### DL-03 — Formati v1.0: **VST3 + AU** (AAX escluso)
- *Problema:* la roadmap elencava AAX, ma il Dossier §11 rifiuta il DRM PACE/iLok; AAX richiede firma PACE.
- *Decisione:* v1.0 = **VST3 + AU**. AAX rinviato post-v1.0 come eventuale eccezione documentata.

---

## 2. REGISTRO DELLE RISOLUZIONI

### A. Contraddizioni critiche
| # | Falla | Risoluzione | File |
| :-- | :-- | :-- | :-- |
| A1 | Render engine: doc vs codice | Decision Lock DL-01 | `MASTER_CHECKLIST` §2, `DOSSIER` §3.2, `PROJECT_MASTER_INDEX`, `PROJECT_ROADMAP` |
| A2 | Prezzo incoerente ($149/$199/€99/€149+) | Decision Lock DL-02; valuta unificata | `MASTER_CHECKLIST` §5, `MARKETING_STRATEGY`, `QUANTITATIVE_MARKET_ANALYSIS`, `DATA_PROVENANCE_LOG` |
| A3 | Claim "latenza zero" vs 100ms PDC | Claim rimosso; USP riformulato su "Deterministic Engine / Mixing-Grade" | `MARKETING_STRATEGY` §3 |
| A4 | Budget GPU €100 vs €25 | Riconciliato: €100 allocati, ~€25-40 attesi | `STRATEGIC_INFRASTRUCTURE_AUDIT` §7, `PROJECT_ROADMAP` M-T2.2 |
| A5 | Credito Azure "10-12 mesi" vs $27/mo | Corretto a ~7 mesi ($200 / $27) | `STRATEGIC_INFRASTRUCTURE_AUDIT` §7, `MASTER_CHECKLIST` §2 |
| A6 | CAC a pagamento vs "zero ad-spend" | CAC riformulato come blended/organic-first | `QUANTITATIVE_MARKET_ANALYSIS` §5 |
| A7 | Revenue Anno-1 $940k vs SOM $1.5-2.2M/3y | Aggiunto scenario base/conservativo + nota di riconciliazione | `QUANTITATIVE_MARKET_ANALYSIS` §3 |

### B. Rischi legali / compliance
| # | Falla | Risoluzione | File |
| :-- | :-- | :-- | :-- |
| B1 | ENST-Drums / MedleyDB fuori inventario | Introdotta Classe B "Evaluation-Only"; inseriti come EVAL-01/02 | `DATA_PROVENANCE_LOG` §1, §2.B |
| B2 | SM Drums "Donationware" non commerciale-esplicito | Segnalato ⚠️ con azione di verifica scritta | `DATA_PROVENANCE_LOG` §2.A |
| B3 | Overclaim GDPR ("fuori dal perimetro") | Riscritto come *data minimization*; ambito ristretto ai crash log | `ZERO_PII_LOG_POLICY` §4 |
| B4 | AAX vs filosofia anti-DRM | Decision Lock DL-03 | `DOSSIER` §11, `PROJECT_ROADMAP` M-T4.2 |

### C. Dubbi / errori tecnici
| # | Falla | Risoluzione | File |
| :-- | :-- | :-- | :-- |
| C1 | Path Logic "MIDIProcessor + Sidechain" irrealizzabile | Riscritto: AU di tipo Effect + Ghost File export come workflow Logic primario | `DOSSIER` §5.4 |
| C2 | Tripla descrizione della compensazione 100ms | Modello temporale unico chiarito (delay-line = PDC, no doppio offset) | `MIDI_CHRONOS_SPEC` §2, `DOSSIER` §5.4 |
| C3 | "16-bit (FP16/BF16)" — formati confusi | Chiarito: training mixed-precision, storage FP16, inferenza float32 | `MASTER_CHECKLIST` §1, `DOSSIER` §6.1 |
| C4 | Hi-Hat CC continuo non specificato | Aggiunta testa di regressione dedicata (CC#4, loss L1/MSE) | `DOSSIER` §2.2 |
| C5 | Inferenza plugin su GPU/Metal/DirectML | Chiarito: inferenza plugin CPU-only RTNeural; GPU solo per training | `DOSSIER` §2.4 |
| C6 | Routing "8 canali MIDI" ambiguo | Aggiunta nota: 8 bus logici, schemi Note-Mapped (default) / Multi-Channel | `DOSSIER` §4 |

### D. Omissioni
| # | Falla | Risoluzione | File |
| :-- | :-- | :-- | :-- |
| D1 | `audit_dsp_rigor.py` citato ma inesistente | Marcato come specifica pianificata; gate via grep manuale fino all'implementazione | `SUB_AGENT_GOVERNANCE` §3 |
| D2 | Gate L1-L4 mai definiti | Aggiunta definizione canonica L1-L4 | `MASTER_CHECKLIST` §6 |
| D3 | LibriSpeech in inventario ma assente dalla dottrina | Aggiunta voce "Speech Rejection" nei Transient Saboteurs | `DOSSIER` §3.4 |
| D4 | Salamander Drumkit non citato nel Dossier | Aggiunto agli asset di rendering | `DOSSIER` §3.2 |

### E. Ambiguità, refusi, disallineamenti
| # | Falla | Risoluzione | File |
| :-- | :-- | :-- | :-- |
| E1 | `[x]` confuso con "implementato" | Aggiunta legenda: `[x]` = Design Lock; stato implementazione 0% | `MASTER_CHECKLIST` (intro) |
| E2 | STRP-001 "5 fasi" vs "6 fasi" | Uniformato a 6 fasi; aggiunte Fasi 5-6 al blueprint UX | `TASK_BLUEPRINT`, `UX_BLUEPRINT_STRP-001` §4 |
| E3 | Due file `REGISTRO_AVANZAMENTO.md` divergenti | Consolidati: root → puntatore; canonico in `04_INTELLIGENCE/` | `REGISTRO_AVANZAMENTO.md` (root) |
| E4 | Date stale (checklist, master index, pipeline status) | Aggiornate al 2026-05-20 | vari |
| E5 | Doppia numerazione "5.1" | Rinumerata in "7.1" | `STRATEGIC_INFRASTRUCTURE_AUDIT` |
| E6 | `compliance_check: CERTIFIED` con azioni aperte | Cambiato in `REVIEW_PENDING` | `PIPELINE_STATUS.json` |
| E7 | Claim assoluti demo ("0% interferenza" ecc.) | Aggiunto vincolo di onestà: claim solo post-L4 | `MARKETING_OCULAR_PROOF` |
| E8 | Soft Delete vs "Immutable Layers" (SEC-02) | Aggiunta Immutability Policy WORM sul layer Bronze | `STRATEGIC_INFRASTRUCTURE_AUDIT` §5.2.B |

---

## 3. AZIONI APERTE (residui da chiudere prima del Gate L2)
1. **[Compliance]** Ottenere conferma scritta dei termini di licenza di **ENST-Drums** e **MedleyDB**. Se non ammettono la valutazione interna a supporto di un prodotto commerciale → sostituirli.
2. **[Compliance]** Verificare per iscritto il permesso d'uso commerciale derivativo di **SM Drums** (Donationware).
3. **[Tech]** Implementare lo script di gate `audit_dsp_rigor.py` (oggi specifica pianificata).
4. **[Scope]** Confermare l'ingresso in scope v1.0 del sottoinsieme "export sincrono" del Ghost File System (necessario per la compatibilità Logic — vedi C1).

---

## 4. NOTE NON BLOCCANTI (segnalazioni minori, non corrette)
- I symlink `data/` e `lib/` puntano al vecchio repo `drum-trigger/` dichiarato "wiped": dipendenza locale da valutare quando si riorganizza l'asset storage.
- `requirements.txt` contiene pacchetti estranei (`twine`, `yt-dlp`, `readme_renderer`): probabile freeze di un venv non pulito, da rigenerare all'avvio dello sviluppo reale.
- Hardware benchmark "Mac Air M5" assunto come valido per la data di progetto (2026).

---
*Audit prodotto sotto protocollo STRP-001. Documentazione ora a Gate L1 — Design Lock.*
