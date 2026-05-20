---
id: LIN-DT-QMA-001
title: Analisi Quantitativa di Mercato (Business Case)
type: reference
status: ACTIVE
phase: cross-cutting
domain: Marketing / Strategy
version: 1.0.0
updated: 2026-05-18
tags: [marketing, market-analysis, business-case]
related: [LIN-DT-COMPAN-001, LIN-DT-MKTSTRAT-001]
supersedes: []
---

# 📈 ANALISI QUANTITATIVA DI MERCATO (BUSINESS CASE)
**Progetto:** OP-NeuroTrigger
**Responsabile:** Gianpiero Scappelloni (Strategic Advisor)
**Data:** 18 Maggio 2026
**Status:** CONFIDENTIAL - OPENPHASE STRATEGY

## 1. DIMENSIONAMENTO DEL MERCATO (TAM / SAM / SOM)
Stime basate sui dati di mercato del settore Audio Software (CAGR ~7.5%).

- **TAM (Total Addressable Market):** $1.2B
  - Dimensione globale del mercato degli Audio Plugins e DAW.
- **SAM (Serviceable Addressable Market):** $85M
  - Segmento degli "Ingegneri di Mixaggio e Produttori" (Utenti di strumenti di batteria virtuale/trigger).
- **SOM (Serviceable Obtainable Market):** $1.5M - $2.2M (Target 3 anni)
  - La quota che Linear intende acquisire puntando alla nicchia High-End insoddisfatta da Slate/Toontrack.

## 2. ANALISI DELLE CINQUE FORZE DI PORTER

| Forza | Intensità | Nota |
| :--- | :--- | :--- |
| **Rivalità tra Concorrenti** | Alta | Slate Digital e Toontrack sono radicati, ma tecnologicamente statici. |
| **Potere Contrattuale Fornitori** | Bassa | Utilizziamo tecnologie Open Source (JUCE, Eigen) o proprietarie. |
| **Potere Contrattuale Acquirenti** | Media | Gli utenti pro sono fedeli alla qualità; gli amatori sono sensibili al prezzo. |
| **Minaccia di Nuovi Entranti** | Media | Richiede alta competenza in DSP/IA, ma nuovi framework facilitano l'ingresso. |
| **Minaccia di Sostituti** | Media | Registrazioni di batterie acustiche perfette (non necessitano di trigger). |

## 3. MODELLAZIONE REVENUE (PROIEZIONE 12 MESI POST-LANCIO)
Ipotesi di lancio: Q4 2026. Prezzo a regime $149 USD (Early-Access $99 nei primi mesi). Le cifre sotto usano $149 e rappresentano lo **scenario ottimistico**.

| Canale | Conversion Rate (Est.) | Unità Target | Revenue (Lorda) |
| :--- | :--- | :--- | :--- |
| **Direct Sales (Sito OpenPhase)** | 2.5% | 1.500 | $223.500 |
| **Affiliate/Distributors (PB/VstBuzz)**| 1.0% | 4.000 | $596.000 |
| **Bundle (Linear Suite)** | - | 500 | $120.000 (Valore stimato) |
| **TOTALE ANNO 1** | - | **6.000** | **~$940.000** |

> **Riconciliazione con il SOM (nota di audit 2026-05-20):** la cifra ~$940k è uno **scenario ottimistico (ceiling)** con tassi di conversione pieni. Lo **scenario base/conservativo** (conversione dimezzata, ~3.000 unità, effetto prezzo Early-Access) vale ~$400–470k Anno 1, coerente con un SOM a 3 anni di $1.5–2.2M. **Per la pianificazione finanziaria si usa lo scenario base**; l'ottimistico è solo upside potenziale.

## 4. ANALISI DI SENSIBILITÀ DEL PREZZO (PRICING STRATEGY)
- **Scenario A (Aggressive):** $99. Volume alto (12.000 unità), Revenue $1.1M. Rischio di de-posizionamento del brand (percepito come "budget").
- **Scenario B (Premium - SCELTO):** **$149 a regime, $99 in Early-Access**. Volume medio (~6.000 unità ottimistico / ~3.000 base). Posizionamento "Pro", margine alto, costi di supporto inferiori. **Prezzo ufficiale bloccato** (price lock 2026-05-20).
- **Scenario C (Elite):** $299. Volume basso (1.500 unità), Revenue $450k. Troppo elitario, rischio di fallimento commerciale se non supportato da hardware.

## 5. UNIT ECONOMICS (ESTIMATED)
- **CAC (Customer Acquisition Cost):** target $10 - $25 *blended*. Coerentemente con la strategia **organic-first / zero-ad-spend** (`MARKETING_STRATEGY.md` §4), l'Anno 1 poggia su crescita organica (Ocular Proof, build-in-public, SEO, affiliazioni a performance). Un budget Ads marginale è opzionale, non strutturale.
- **LTV (Lifetime Value):** ~$130–150 da prodotto singolo (acquisto una tantum, al netto delle commissioni di pagamento). La stima estesa $250+ presuppone update v2 a pagamento e cross-selling della suite Linear: proiezione **speculativa**, da non usare per decisioni di budget finché i prodotti collegati non esistono.
- **LTV/CAC Ratio:** ~5–15 a seconda dello scenario CAC. Sano (>3.0) grazie al basso costo di acquisizione organico, non a un LTV gonfiato.

---
*Analisi prodotta con rigore matematico e visione strategica Linear.*
