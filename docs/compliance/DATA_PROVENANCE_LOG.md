---
id: LIN-DT-DPL-001
title: Registro Provenienza Dati & Compliance
type: registro
status: ACTIVE
phase: cross-cutting
domain: Legal / Compliance
version: 1.0.0
updated: 2026-05-20
tags: [compliance, provenance, licensing, legal]
related: [LIN-DT-LICVER-F0T1, LIN-DT-ROSTER-F0T1b, LIN-DT-HOLDOUT-F0T1c]
supersedes: []
---

# 🛡️ REGISTRO PROVENIENZA DATI & COMPLIANCE (DPL)
**Prodotto:** OP-NeuroTrigger
**Responsabile:** Strategic Advisor (Gianpiero Scappelloni)
**Status:** ACTIVE - AUDIT READY

## 1. DOTTRINA LEGALE (COMPLIANCE-BY-DESIGN)
Per garantire la vendibilità internazionale di OP-NeuroTrigger a prezzo Premium ($149 USD), gli asset seguono la regola "Zero-Risk IP", articolata su **due classi distinte**:

- **Classe A — Asset di Training:** ogni campione audio o MIDI dato in pasto alla rete per *aggiornarne i pesi* deve avere una licenza che permetta **esplicitamente l'uso commerciale** (CC-BY, CC0 o equivalente). Inventario in §2.A.
- **Classe B — Asset Evaluation-Only:** dataset usati **solo** per la validazione interna (Holdout / benchmark), mai dati in pasto al training, mai ridistribuiti, mai inclusi nel prodotto. Per questa classe è sufficiente una licenza che consenta l'uso a fini di **ricerca/valutazione**. Inventario in §2.B.

Vincolo: un asset di Classe B non può migrare in Classe A senza una nuova verifica di licenza.

### 1.1 Regola "Self-Evident Commercial License" (Decision Lock CEO, 2026-05-20)
Si include un asset **solo** se la sua licenza **già pubblicata** concede
**inequivocabilmente** l'uso commerciale (CC0, CC-BY o equivalente formale, leggibile
direttamente alla fonte). **Zero corrispondenza** con i creatori; **zero divulgazione**
del progetto. Asset con sola dichiarazione informale ("donationware", "royalty-free" su
blog) o con licenza "research-only" / "NonCommercial" sono **esclusi a priori**, senza
richieste di conferma. La verifica è una pura lettura della licenza pubblicata.

## 2.A INVENTARIO ASSET DI TRAINING (CLASSE A)

| Asset ID | Nome | Fonte | Licenza | Uso |
| :--- | :--- | :--- | :--- | :--- |
| **MIDI-01** | Groove MIDI Dataset | Google/Magenta | CC-BY 4.0 | Core Ground Truth (Timing/Velocity) |
| ~~AUDIO-01~~ | ~~SM Drums~~ | Scott McLean | ❌ **ESCLUSO** (dottrina §1.1, 2026-05-20) — nessuna licenza formale, sola dichiarazione informale | — |
| **AUDIO-02** | DrumGizmo Kits (CrocellKit, DRSKit, MuldjordKit, Aasimonster, ShittyKit, Sommerhack) | DrumGizmo Project | CC-BY 4.0 | Campionamento Multi-mic (Bleeding) — 6 kit, sorgente primaria del bleed |
| **AUDIO-03** | Salamander Drumkit | Alexander Holm | CC-BY 3.0 | Campionamento Yamaha (Pop/Clean) |
| **AUDIO-04** | Slakh2100 | Lakh MIDI/Stems | CC-BY 4.0 | Negative Sampling & Mix Mode |
| **AUDIO-05** | LibriSpeech | OpenSLR | CC-BY 4.0 | Noise/Speech Rejection (Negative) |
| **AUDIO-06** | OpenAIR Library | Univ. of York | CC-BY 4.0 | Impulse Responses (Convolution Reverb) |
| **AUDIO-07** | FSD50K | Freesound/UPF | CC-BY 4.0 | Foley / Stage Noise / Impact Sounds |
| **AUDIO-08** | MAESTRO Dataset | Google/Magenta | CC-BY 4.0 | Piano Stems (Transient Clashing) |
| **AUDIO-09** | GuitarSet | NYU/MARL | CC-BY 4.0 | Acoustic Slap / Strumming (Negative) |
| **AUDIO-10** | VSCO-2 CE | Versilian Studios | CC0 (Public Domain) | Generazione Sintetica Percussioni Accessorie |
| **AUDIO-11** | Virtual Playing Orchestra | Paul Battersby | CC-BY 3.0 | Generazione Sintetica Percussioni Accessorie |
| **AUDIO-12** | Karoryfer Big Rusty Drums | Karoryfer Samples | CC0 | Campionamento kit (timbro vintage) |
| **AUDIO-13** | Karoryfer Unruly Drums | Karoryfer Samples | CC0 | Campionamento Multi-mic (10 round-robin) |
| **AUDIO-14** | Karoryfer Swirly Drums | Karoryfer Samples | CC0 | Campionamento kit |
| **AUDIO-15** | Karoryfer Frankensnare | Karoryfer Samples | CC0 | Libreria snare — varietà rullante |

> **Roster kit di training (F0-T1b, Decision Lock CEO 2026-05-20):** AUDIO-02 (6 kit
> DrumGizmo CC-BY-4.0, multi-mic) + AUDIO-03 Salamander (CC-BY-3.0) + AUDIO-12…15
> Karoryfer (CC0) + AUDIO-10 VSCO-2 CE (CC0, percussioni accessorie). Tutti a licenza
> formale con uso commerciale inequivocabile. SM Drums escluso. Dettaglio e matrice
> licenze: `F0-T1b_KIT_ROSTER_SURVEY.md`.

## 2.B INVENTARIO ASSET EVALUATION-ONLY (CLASSE B)
Dataset usati esclusivamente come arbitro di qualità (vedi `DOSSIER_TECNICO.md` §10). **Mai usati per aggiornare i pesi, mai ridistribuiti, mai inclusi nel prodotto.**

| Asset ID | Nome | Fonte | Licenza | Uso | Vincolo |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EVAL-01** | ENST-Drums | IRCAM / Télécom Paris | Research-only — *"no commercial use is possible"* | Holdout Test Set (Ground Truth umano) | ❌ **ESCLUSO** (dottrina §1.1, 2026-05-20): la licenza pubblicata vieta l'uso commerciale. |
| **EVAL-02** | MedleyDB | NYU MARL | CC BY-NC-SA 4.0 (NonCommercial) | Franken-Mix (test Stealth Mix Mode) | ❌ **ESCLUSO** (dottrina §1.1, 2026-05-20): clausola NonCommercial. |

> ⚠️ **Holdout reale da ridisegnare.** Per la dottrina §1.1 (Decision Lock CEO 2026-05-20) ENST-Drums e MedleyDB sono **esclusi** (research-only / NonCommercial). Erano gli asset dello Holdout reale e del Franken-Mix (`DOSSIER_TECNICO` §10.3, `MASTER_CHECKLIST` §1): il Validation Protocol va ridisegnato. Serve una fonte di registrazioni reali con ground-truth a licenza commerciale chiara, oppure il Piano B (registrazioni proprietarie annotate). **Task di ridisegno da aprire** — contesto in `F0-T1b_KIT_ROSTER_SURVEY.md` §6.

## 3. PROTOCOLLO DI TRASFORMAZIONE (DERIVATIVE WORKS)
Il modello neurale TCN finale è considerato un "Lavoro Derivato Trasformativo". 
- L'audio originale non viene distribuito (niente rivendita di campioni).
- I pesi della rete neurale sono astrazioni matematiche dei pattern appresi.
- La licenza CC-BY viene onorata tramite l'attribuzione obbligatoria nel documento `CREDITS.md` del prodotto finale.

## 4. AUDIT TRAIL
- **2026-05-18:** Definizione Stack Guerrilla (Sfizz/GMD). Esclusione asset proprietari (SD3/Kontakt) per massima indipendenza economica e legale.
- **2026-05-18:** Validazione licenze per uso commerciale dei dataset GMD e Slakh.
- **2026-05-20:** Audit di coerenza documentale. Introdotta la distinzione Classe A / Classe B. Inseriti ENST-Drums e MedleyDB come asset Evaluation-Only (prima citati nel Dossier ma assenti dall'inventario). Segnalata la licenza "Donationware" di SM Drums come da verificare.
- **2026-05-20 (F0-T1):** Avviato il task Compliance licenze. Ricerca su fonti primarie completata per SM Drums, ENST-Drums, MedleyDB. Esito: SM Drums = royalty-free dichiarato (uso commerciale permesso) ma senza licenza formale; ENST-Drums = research-only/no-commercial; MedleyDB = CC BY-NC-SA 4.0. Prodotto `F0-T1_LICENSE_VERIFICATION.md` (matrice + bozze di outreach).
- **2026-05-20 (F0-T1b / dottrina §1.1):** Decision Lock CEO — regola "Self-Evident Commercial License". **Outreach F0-T1 annullato** (niente email, niente divulgazione). ENST-Drums e MedleyDB **esclusi** per lettura diretta della licenza; SM Drums **escluso** (nessuna licenza formale — sola dichiarazione informale).
- **2026-05-20 (F0-T1b chiuso):** Decision Lock CEO sul roster — 11 voci approvate e inserite in §2.A: AUDIO-02 esploso nei 6 kit DrumGizmo CC-BY-4.0; aggiunti AUDIO-12…15 (Karoryfer, CC0). SM Drums (AUDIO-01) escluso. F0-T1 e F0-T1b chiusi. Aperto **F0-T1c** — ridisegno del Validation Protocol / Holdout reale (conseguenza dell'esclusione di ENST-Drums e MedleyDB).

---
*Documento generato sotto protocollo OpenPhase (SOP-004).*
