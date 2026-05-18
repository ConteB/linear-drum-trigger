# 🛡️ REGISTRO PROVENIENZA DATI & COMPLIANCE (DPL)
**Prodotto:** OP-NeuroTrigger
**Responsabile:** Strategic Advisor (Gianpiero Scappelloni)
**Status:** ACTIVE - AUDIT READY

## 1. DOTTRINA LEGALE (COMPLIANCE-BY-DESIGN)
Per garantire la vendibilità internazionale di OP-NeuroTrigger a prezzi Premium (€149+), il dataset di addestramento segue la regola "Zero-Risk IP". Ogni campione audio o file MIDI utilizzato deve avere una licenza che permetta esplicitamente l'uso commerciale.

## 2. INVENTARIO ASSET & LICENZE

| Asset ID | Nome | Fonte | Licenza | Uso |
| :--- | :--- | :--- | :--- | :--- |
| **MIDI-01** | Groove MIDI Dataset | Google/Magenta | CC-BY 4.0 | Core Ground Truth (Timing/Velocity) |
| **AUDIO-01** | SM Drums | Scott McLean | Open (Donationware) | Campionamento Multi-layer Ludwig |
| **AUDIO-02** | DrumGizmo Kits | DrumGizmo Project | CC-BY | Campionamento Multi-mic (Bleeding) |
| **AUDIO-03** | Salamander Drumkit | Alexander Holm | CC-BY 3.0 | Campionamento Yamaha (Pop/Clean) |
| **AUDIO-04** | Slakh2100 | Lakh MIDI/Stems | CC-BY 4.0 | Negative Sampling & Mix Mode |
| **AUDIO-05** | LibriSpeech | OpenSLR | CC-BY 4.0 | Noise/Speech Rejection (Negative) |

## 3. PROTOCOLLO DI TRASFORMAZIONE (DERIVATIVE WORKS)
Il modello neurale TCN finale è considerato un "Lavoro Derivato Trasformativo". 
- L'audio originale non viene distribuito (niente rivendita di campioni).
- I pesi della rete neurale sono astrazioni matematiche dei pattern appresi.
- La licenza CC-BY viene onorata tramite l'attribuzione obbligatoria nel documento `CREDITS.md` del prodotto finale.

## 4. AUDIT TRAIL
- **2026-05-18:** Definizione Stack Guerrilla (Sfizz/GMD). Esclusione asset proprietari (SD3/Kontakt) per massima indipendenza economica e legale.
- **2026-05-18:** Validazione licenze per uso commerciale dei dataset GMD e Slakh.

---
*Documento generato sotto protocollo OpenPhase (SOP-004).*
