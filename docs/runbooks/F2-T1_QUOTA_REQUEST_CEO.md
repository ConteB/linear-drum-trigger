---
id: LIN-DT-RUNBOOK-F2T1QUOTA
title: Runbook F2-T1 — Quota Request Azure (per il CEO)
type: runbook
status: ACTIVE
phase: F2
domain: Operations / Infrastructure
version: 1.0.0
updated: 2026-05-23
tags: [azure, quota, F2-T1, ceo-action, italynorth]
related: [LIN-DT-MSCHED-001, LIN-DT-RUNBOOK-F2T1, LIN-DT-SIA-001]
supersedes: []
---

# 🎫 F2-T1 — Quota Request Azure (Guida CEO)

> Step-by-step da seguire **una volta sola** sul portale Azure per sbloccare
> le SKU che ci servono. Tempo CEO: ~5 minuti di compilazione + attesa
> approval (5-15 min auto, fino a 1-3 gg se manuale). Io in parallelo lavoro
> a F0-T17 in locale a $0.

## Perché serve questa richiesta

Ho provato a lanciare la VM smoke `Standard_M8ms` in italynorth. Errore vero:

```
(QuotaExceeded) Operation could not be completed as it results in exceeding
approved LowPriorityCores quota. Current Limit: 3, Additional Required: 8.
```

Quote attuali in italynorth della tua sottoscrizione:

| Famiglia VM | Quota oggi | Cosa ci serve |
| :-- | :-- | :-- |
| Total Regional vCPUs (on-demand) | 4 | 40 |
| Total Regional Spot vCPUs | 3 | 40 |
| Standard MS Family (per render M16ms) | **0** | **16** |
| Standard NCADSA100v4 Family (per training A100) | non listata | **24** |

Microsoft assegna quote basse ai nuovi account; vanno richieste on-demand.
Per piccoli incrementi (<50 vCPU) sono tipicamente **auto-approved in 5-15 min**.

---

## STEP 1 — Apri il portale e vai a Quotas

1. Vai a **https://portal.azure.com**
2. Nella barra in alto, scrivi "**Quotas**" e clicca sul risultato (icona pin).
3. Sceglie il provider **Compute**.
4. In alto seleziona:
   - **Subscription:** "Azure subscription 1" (quella che usiamo)
   - **Region:** "Italy North"

Vedrai una lunga lista di famiglie VM con la colonna "Current usage / Quota".

## STEP 2 — Click "Request quota increase"

In alto, click sul pulsante **"New Quota Request"** (o "Request quota increase").

Scegli il tipo: **"Standard quota: increase limits by VM series"**.

## STEP 3 — Compila i 4 incrementi richiesti

Inserisci le 4 famiglie con i nuovi limiti:

| Famiglia | Nuovo limite | Calcolo |
| :-- | :-- | :-- |
| **Standard MS Family vCPUs** | **16** | M16ms (16 vCPU) per render F2-T1 |
| **Standard NCADSA100v4 Family vCPUs** | **24** | NC24ads_A100_v4 (24 vCPU) per training F2-T3 |
| **Total Regional vCPUs** | **40** | somma delle famiglie + buffer |
| **Total Regional Spot vCPUs** | **40** | spot pricing -70 % su entrambe le famiglie |

> **Se l'interfaccia chiede una motivazione**, incolla questo testo:
> > Project: ML drum transcription model training. Azure $200 credit
> > use-it-or-lose-it (expires 2026-06-19). Need to render ~4.5 TB of
> > synthetic training data (~14h on M16ms) and train one A100 model
> > (~12h on NC24ads_A100_v4). One-shot compute, single subscription,
> > no ongoing usage.

Click **Submit**.

## STEP 4 — Aspetta l'email di conferma

Microsoft manda un'email a `marco.palermo9901@gmail.com` (o l'email
dell'account Azure). Tipici tempi:

- **Auto-approval** (più frequente per piccoli incrementi): 5-15 minuti
- **Revisione manuale** (se Microsoft vuole verificare): 1-3 giorni lavorativi

Lo stato della richiesta si vede anche nel portale → Quotas → tab
**"My Quota Requests"**.

## STEP 5 — Quando l'approval arriva

Scrivimi solo:

> "**quota approved**"

E io riparto immediatamente da:

1. Lancio VM smoke `M8ms` spot in italynorth (~$0.08, 15 min)
2. Verifico provisioning + smoke render verde
3. Lancio VM burn `M16ms` spot (~$9.40, 14h)
4. Monitor TUI attivo sul tuo terminale durante il burn

Tutti gli artefatti sono già committati e pushati su `origin/develop`
(ultimo commit `e35155a`).

---

## Possibile risposta negativa: cosa fare

Se per qualche motivo Microsoft NEGA la richiesta (raro, ma succede su
account nuovi senza spending history), abbiamo due fallback:

### Fallback A — provare altra region

Italy North è region recente con quote restrittive. Region più mature
(westeurope, northeurope, eastus) hanno spesso quote default più generose
ma il limite "NotAvailableForSubscription" sui D-series ci colpisce
ovunque. Da verificare caso per caso.

### Fallback B — Azure Free Trial / Azure Students

Se l'account corrente ha restrizioni strutturali, puoi creare un secondo
account Azure Free Trial ($200 + 12 mesi free per nuovi utenti) usando
un'altra email. Lavoro identico a quello attuale, ricreo F1-T1/T2 in
~20 minuti.

Lasciamo questi come piano B — partiamo dall'assumere che la quota
request passi liscia (caso usuale).

---

## Stato lavoro in parallelo (mentre attendi)

Mentre la quota request si risolve, io lavoro su:

- **F0-T17** — implementazione `src/evaluation/`:
  - `data_audit.py` — distribuzione del Gold (pre-F2-T3 gate)
  - `split_consistency.py` — train vs val vs Holdout consistency
  - `anti_leak_audit.py` — verifica numerica Decision Lock A+C
  - `evaluation_suite.py` — Gate L4 dossier (post-F2-T3)

Spec già LOCKED in [`F0-T17_STATISTICAL_TEST_PLAN.md`](../methodology/F0-T17_STATISTICAL_TEST_PLAN.md).
Costo Azure: $0 (gira tutto in locale su Mac M5).

Quando torni con "quota approved", ho già pronto anche questo pezzo —
F2-T3 (training A100) sarà ratificato dai gate F0-T17 prima del burn.

---

*Decision Lock 2026-05-23 (sessione T1-prep-D). Aggiornare se Microsoft cambia
le quote default o se cambiamo regione.*
