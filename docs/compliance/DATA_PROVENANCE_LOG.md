# 🛡️ REGISTRO PROVENIENZA DATI & COMPLIANCE (DPL)
**Prodotto:** OP-NeuroTrigger
**Responsabile:** Strategic Advisor (Gianpiero Scappelloni)
**Status:** ACTIVE - AUDIT READY

## 1. DOTTRINA LEGALE (COMPLIANCE-BY-DESIGN)
Per garantire la vendibilità internazionale di OP-NeuroTrigger a prezzo Premium ($149 USD), gli asset seguono la regola "Zero-Risk IP", articolata su **due classi distinte**:

- **Classe A — Asset di Training:** ogni campione audio o MIDI dato in pasto alla rete per *aggiornarne i pesi* deve avere una licenza che permetta **esplicitamente l'uso commerciale** (CC-BY, CC0 o equivalente). Inventario in §2.A.
- **Classe B — Asset Evaluation-Only:** dataset usati **solo** per la validazione interna (Holdout / benchmark), mai dati in pasto al training, mai ridistribuiti, mai inclusi nel prodotto. Per questa classe è sufficiente una licenza che consenta l'uso a fini di **ricerca/valutazione**. Inventario in §2.B.

Vincolo: un asset di Classe B non può migrare in Classe A senza una nuova verifica di licenza.

## 2.A INVENTARIO ASSET DI TRAINING (CLASSE A)

| Asset ID | Nome | Fonte | Licenza | Uso |
| :--- | :--- | :--- | :--- | :--- |
| **MIDI-01** | Groove MIDI Dataset | Google/Magenta | CC-BY 4.0 | Core Ground Truth (Timing/Velocity) |
| **AUDIO-01** | SM Drums | Scott McLean | Donationware ⚠️ *(verificare: ottenere conferma scritta del permesso d'uso commerciale derivativo prima del training)* | Campionamento Multi-layer Ludwig |
| **AUDIO-02** | DrumGizmo Kits | DrumGizmo Project | CC-BY | Campionamento Multi-mic (Bleeding) |
| **AUDIO-03** | Salamander Drumkit | Alexander Holm | CC-BY 3.0 | Campionamento Yamaha (Pop/Clean) |
| **AUDIO-04** | Slakh2100 | Lakh MIDI/Stems | CC-BY 4.0 | Negative Sampling & Mix Mode |
| **AUDIO-05** | LibriSpeech | OpenSLR | CC-BY 4.0 | Noise/Speech Rejection (Negative) |
| **AUDIO-06** | OpenAIR Library | Univ. of York | CC-BY 4.0 | Impulse Responses (Convolution Reverb) |
| **AUDIO-07** | FSD50K | Freesound/UPF | CC-BY 4.0 | Foley / Stage Noise / Impact Sounds |
| **AUDIO-08** | MAESTRO Dataset | Google/Magenta | CC-BY 4.0 | Piano Stems (Transient Clashing) |
| **AUDIO-09** | GuitarSet | NYU/MARL | CC-BY 4.0 | Acoustic Slap / Strumming (Negative) |
| **AUDIO-10** | VSCO-2 CE | Versilian Studios | CC0 (Public Domain) | Generazione Sintetica Percussioni Accessorie |
| **AUDIO-11** | Virtual Playing Orchestra | Paul Battersby | CC-BY 3.0 | Generazione Sintetica Percussioni Accessorie |

## 2.B INVENTARIO ASSET EVALUATION-ONLY (CLASSE B)
Dataset usati esclusivamente come arbitro di qualità (vedi `DOSSIER_TECNICO.md` §10). **Mai usati per aggiornare i pesi, mai ridistribuiti, mai inclusi nel prodotto.**

| Asset ID | Nome | Fonte | Licenza | Uso | Vincolo |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EVAL-01** | ENST-Drums | IRCAM / Télécom Paris | Research-only ⚠️ | Holdout Test Set (Ground Truth umano) | Solo valutazione interna; verificare i termini accademici prima dell'impiego. |
| **EVAL-02** | MedleyDB | NYU MARL | Non-commercial / Research ⚠️ | Franken-Mix (test Stealth Mix Mode) | Solo valutazione interna; nessuna ridistribuzione di audio derivato. |

> ⚠️ **Azione aperta (blocco per Gate L2):** confermare per iscritto i termini di licenza di ENST-Drums e MedleyDB. Se non consentono nemmeno la valutazione interna a supporto di un prodotto commerciale, sostituirli con alternative (es. registrazioni proprietarie annotate manualmente).

## 3. PROTOCOLLO DI TRASFORMAZIONE (DERIVATIVE WORKS)
Il modello neurale TCN finale è considerato un "Lavoro Derivato Trasformativo". 
- L'audio originale non viene distribuito (niente rivendita di campioni).
- I pesi della rete neurale sono astrazioni matematiche dei pattern appresi.
- La licenza CC-BY viene onorata tramite l'attribuzione obbligatoria nel documento `CREDITS.md` del prodotto finale.

## 4. AUDIT TRAIL
- **2026-05-18:** Definizione Stack Guerrilla (Sfizz/GMD). Esclusione asset proprietari (SD3/Kontakt) per massima indipendenza economica e legale.
- **2026-05-18:** Validazione licenze per uso commerciale dei dataset GMD e Slakh.
- **2026-05-20:** Audit di coerenza documentale. Introdotta la distinzione Classe A / Classe B. Inseriti ENST-Drums e MedleyDB come asset Evaluation-Only (prima citati nel Dossier ma assenti dall'inventario). Segnalata la licenza "Donationware" di SM Drums come da verificare.

---
*Documento generato sotto protocollo OpenPhase (SOP-004).*
