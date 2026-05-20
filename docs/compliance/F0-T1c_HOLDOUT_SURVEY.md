---
id: LIN-DT-HOLDOUT-F0T1c
title: F0-T1c — Survey Holdout + Ridisegno Validation Protocol
type: registro
status: LOCKED
phase: F0
domain: Legal / Compliance
version: 1.0.0
updated: 2026-05-20
tags: [compliance, holdout, validation, F0-T1c]
related: [LIN-DT-DPL-001, LIN-DT-DOSSIER-001, LIN-DT-CHKLST-001]
supersedes: []
---

# 🎯 F0-T1c — SURVEY HOLDOUT + RIDISEGNO VALIDATION PROTOCOL
**Task:** F0-T1c · **Avviato:** 2026-05-20 · **Stato:** ☑ CHIUSO — Decision Lock CEO 2026-05-20
**Origine:** esclusione di ENST-Drums e MedleyDB (dottrina §1.1) → Holdout reale e
Franken-Mix rimasti senza asset. **Riferimenti:** `DOSSIER_TECNICO.md` §10, `MASTER_CHECKLIST.md` §1.

## 1. Il buco da chiudere
Il vecchio Validation Protocol (DOSSIER §10) poggiava su 3 gambe:
- **Holdout reale** ← ENST-Drums ❌ escluso
- **Franken-Mix** (test Stealth Mix Mode) ← MedleyDB ❌ escluso
- **Ocular Proof** ← indipendente, ✅ resta valido

Servono sostituti a **licenza commerciale formale** (dottrina §1.1).

## 2. Survey — candidati e verdetto

| Dataset | Cos'è | Licenza pubblicata | Verdetto |
| :-- | :-- | :-- | :-- |
| **E-GMD** (Expanded Groove MIDI Dataset, Google Magenta) | 444 h di performance umane reali, 43 kit, registrate su Roland TD-17, audio allineato ±2 ms al MIDI, con velocity | **CC-BY 4.0** | 🟢 **IDONEO** |
| **MDB Drums** | Annotazioni di trascrizione su un subset di MedleyDB | Annotazioni CC-BY 4.0 — **ma l'audio sottostante è MedleyDB (CC-BY-NC)** | 🔴 **ESCLUSO** (l'audio resta NonCommercial) |
| **ADTOF** | 114 h di musica commerciale reale annotata (da chart Rock Band) | Derivato da musica commerciale protetta | 🔴 **ESCLUSO** (nessuna licenza commerciale pulita) |
| **Slakh2100** | Multitraccia sintetico: full-mix + stem isolati | **CC-BY 4.0** (già in inventario, AUDIO-04) | 🟢 **IDONEO** (per il test Mix-Mode) |
| **IDMT-SMT-Drums** | Batterie **acustiche reali** + sample + synth, onset annotati | CC **BY-NC-ND** 4.0 | 🔴 **ESCLUSO** (NonCommercial + NoDerivatives) |
| **STAR Drums** | Trascrizione su registrazioni reali | licenza "per la comunità di ricerca" | 🔴 **ESCLUSO** |

### 2bis. Esiste un'opzione a pagamento? (quesito del CEO)
**No — e pagare non rende l'asset più sicuro: lo rende meno sicuro.**
- **Librerie di sample commerciali** (Superior Drummer, GetGood, Slate…): la EULA concede
  l'uso dei *suoni in produzioni musicali*, **non** il diritto di addestrare/testare un
  modello ML né di creare opere derivate AI. "Comprare" il prodotto non compra quel
  diritto — servirebbe una licenza negoziata ad hoc, cioè esattamente la corrispondenza e
  la divulgazione che la dottrina §1.1 vieta. In più non includono ground-truth annotato.
- **Dataset di trascrizione annotati venduti commercialmente:** non esistono come
  prodotto; i dataset annotati sono accademici / research-only.
- **Conclusione:** una licenza **CC-BY / CC0** (gratuita) è *legalmente più sicura* di una
  libreria a pagamento, perché concede in anticipo e per iscritto i diritti commerciali e
  derivati. **E-GMD (CC-BY 4.0) non è un ripiego — è la scelta più pulita disponibile.**

## 3. Proposta di Validation Protocol ridisegnato

| Gamba | Vecchio | **Nuovo (proposto)** | Note |
| :-- | :-- | :-- | :-- |
| **Holdout reale** | ENST-Drums | **E-GMD** (CC-BY 4.0) | Performance umane vere, ground-truth velocity+timing affidabile (±2 ms). |
| **Test Stealth-Mix** | Franken-Mix / MedleyDB | **Slakh-Mix** su Slakh2100 (CC-BY 4.0) | Stessa logica: trascrivere dal full-mix e confrontare con la trascrizione dello stem batteria isolato. |
| **Ocular Proof** | (invariato) | (invariato) | Woodblock in controfase — funziona su qualsiasi registrazione. |

## 4. ⚠️ Trasparenza — i limiti della proposta
1. **E-GMD è registrato su Roland TD-17:** timing e dinamica sono *umani veri*, ma l'audio
   è generato dal modulo elettronico — **non** cattura microfoni reali in una stanza né il
   bleed acustico. Il moat del prodotto (gestione del bleed) **non** è testato da E-GMD su
   audio acustico reale.
2. **Slakh2100 è sintetico:** struttura del test Mix-Mode valida, ma non è "mondo reale".
3. **Conseguenza sui claim L4:** con questi due set, il Gate L4 può certificare
   accuratezza su *performance reali* e *robustezza al mix*, ma **non** su *registrazioni
   acustiche con bleed reale*. I claim pubblici andrebbero formulati di conseguenza.

## 5. Piano B — DECISIONE: non si fa (CEO, 2026-05-20)
L'opzione "registrazioni proprietarie acustiche reali annotate" è **scartata** dal CEO.
Il caso acustico reale resta coperto **qualitativamente** dalla Ocular Proof (test
woodblock-controfase, eseguibile su qualsiasi registrazione); si rinuncia alla metrica
numerica sul bleed acustico reale. I claim pubblici a L4 vanno formulati di conseguenza.

## 6. Stato DoD
- [x] Survey completato; licenze verificate.
- [x] Validation Protocol ridisegnato — proposta in §3.
- [x] Decision Lock del CEO sul protocollo ridisegnato (2026-05-20).
- [x] `DOSSIER_TECNICO` §10.3 e `MASTER_CHECKLIST` §1 aggiornati.

---
*F0-T1c — OpenPhase SOP-004. Fonti: magenta.withgoogle.com/datasets/e-gmd,
musicinformatics.gatech.edu, arxiv.org/abs/2111.11737 (2026-05-20).*
