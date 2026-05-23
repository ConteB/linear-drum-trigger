---
id: LIN-DT-RUNBOOK-AZURE-ENABLEMENT
title: Azure Support — SKU Enablement NCADSA100v4 + Quota Standard_D16s_v3
type: runbook
status: ACTIVE
phase: F2
domain: Operations / Azure provisioning
version: 1.0.0
updated: 2026-05-23
tags: [azure, support, quota, gpu, f2-t1]
related: [LIN-DT-MSCHED-001]
---

# 🎫 RUNBOOK — Apertura ticket Azure Support per F2-T1

> **Contesto.** Sei davanti al portale Azure, devi sbloccare due cose per
> F2-T1 (render) e F2-T3 (training):
>
> 1. **GPU `NCADSA100v4`** — la pagina Quote mostra *"No quota data found"*
>    → la SKU GPU non è esposta sulla tua sottoscrizione (anti-frode standard
>    su sub nuove con credito promozionale).
> 2. **CPU `Standard_D16s_v3`** — serve verificare/alzare la quota a 16 vCPU
>    in Italy North per il render F2-T1.
>
> Apriamo **2 ticket separati**: uno per la GPU (enablement),
> uno per la CPU (quota). Costo: $0. Tempo CEO: ~15 min totali.
> Tempo Microsoft: 24-72h.

---

## ⏱ Pre-flight (1 min)

Tieni a portata:

- [ ] Browser su `https://portal.azure.com` loggato con l'account del credito
- [ ] Questo file aperto sull'altro monitor
- [ ] Un blocco note / file di testo per **salvare i Support Request ID**
      che Azure ti darà alla fine di ogni ticket
- [x] **ID della tua sottoscrizione** salvato:
      ```
      Subscription ID: e2137e0a-7341-47b3-8db3-9843344e5c35
      ```
      *(già pre-incollato nelle due Description sotto — non devi più sostituirlo)*

---

# 🟦 TICKET #1 — GPU NCADSA100v4 (enablement)

## Step 1.1 — Apri il New Support Request

1. In alto a destra clicca l'**icona `?`** (Help) → **`Help + support`**
2. *(Oppure URL diretto: copia-incolla `https://portal.azure.com/#blade/Microsoft_Azure_Support/HelpAndSupportBlade`)*
3. Pulsante blu **`+ Create a support request`** (in alto a sinistra)

## Step 1.2 — Tab "Problem description"

Compila **esattamente così**:

| Campo | Cosa scrivere |
|:--|:--|
| **Summary** | `Enable NCADSA100v4 SKU family on subscription — currently not exposed in Quotas (Italy North)` |
| **Issue type** | clicca menu → seleziona **`Service and subscription limits (quotas)`** |
| **Subscription** | seleziona dalla tendina la tua sub (quella col credito $200) |
| **Quota type** | clicca menu → seleziona **`Compute-VM (cores-vCPUs) subscription limit increases`** |

Clicca pulsante **`Next: Additional details >>`** in basso.

## Step 1.3 — Tab "Additional details" — Request details

Vedrai una sezione **"Request details"** con un link blu **`Enter details`**.

1. Cliccalo. Si apre un pannello laterale a destra.

2. Compila:

| Campo | Cosa scrivere |
|:--|:--|
| **Deployment model** | `Resource Manager` |
| **Locations** | spunta solo **`Italy North`** |
| **Types** | lascia spuntato **`Standard`** |
| **SKU family** | cerca/spunta **`Standard NCADSA100_v4 Series`** |
| **New vCPU limit** | scrivi `24` |

> ⚠️ **Se la SKU `Standard NCADSA100_v4 Series` NON appare nella lista**
> (cosa probabile perché ti dava "No quota data found"):
> spunta una qualsiasi SKU presente nella lista (es. `Standard NCv3 Series`)
> e metti `New vCPU limit = 6` come placeholder. Il messaggio nella
> Description sotto chiarirà al supporto cosa serve veramente.
> Senza una SKU spuntata il pannello "Save" non funziona.

3. Clicca **`Save and continue`** nel pannello laterale.

## Step 1.4 — Tab "Additional details" — Problem details / Description

Trovi un grande campo testo **"Provide details"** o **"Description"**.

**Incolla letteralmente** questo blocco (è la business justification che
Microsoft legge davvero — il punto chiave è la frase iniziale che chiarisce
"ENABLEMENT, not quota increase"):

```
ENABLEMENT REQUEST — not a simple quota increase.

The NCADSA100v4 SKU family is currently NOT exposed on this
subscription. When I filter the Quotas blade (Compute → Italy
North → "nc family A100 v4") the Azure portal returns:
"No quota data found — No quotas found matching the current
filters."

I need this SKU family enabled on my subscription so I can then
request 24 vCPU quota in Italy North for the Standard_NC24ads_A100_v4
SKU.

Business need: Single-tenant ML training workload for a commercial
audio plugin (drum transcription neural network, PyTorch).

Workload profile:
- ONE VM, 24 vCPU, 1x A100 GPU (80 GB)
- Maximum runtime per job: 12 hours
- Total compute spend: ~$15 spot / ~$50 on-demand for one training run
- Data already on Azure Blob LRS (1.5 TB rendered audio dataset,
  same region)
- No multi-VM scaling, no auto-scaling, no persistent infrastructure
- No cryptocurrency, no proof-of-work, no blockchain workload

Time sensitivity: $200 Azure promotional credit expires on 2026-06-19.
Without SKU enablement we cannot consume the credit on the GPU
workload it was budgeted for.

Region rationale: Italy North chosen because NCADSA100v4 is listed
available in this region while NOT available in West Europe for our
subscription. Standard_D*_v3 SKUs already validated as working in
Italy North on this same subscription.

Requested actions:
1. Enable the NCADSA100v4 SKU family on this subscription.
2. Grant 24 vCPU quota for Standard_NC24ads_A100_v4 in Italy North.
3. (Optional) Enable the same family in West Europe as fallback.

Subscription ID: e2137e0a-7341-47b3-8db3-9843344e5c35
```

> ✅ Subscription ID già pre-incollato. Copia-incolla l'intero blocco
> qui sopra (dall'`ENABLEMENT REQUEST` alla riga `Subscription ID:`) così
> com'è.

**File upload:** lascia vuoto, non serve nessun allegato.

Clicca **`Next: Review + create >>`**.

## Step 1.5 — Tab "Review + create"

### Support plan

- Vedrai probabilmente **`Basic support plan`** (default di Pay-As-You-Go)
- ✅ **Le quota/enablement request sono GRATUITE sul Basic plan.**
- Se Azure suggerisce "Upgrade to Developer/Standard support" → **IGNORA**,
  non pagare nulla. Clicca avanti senza upgrade.

### Severity, contact, language

| Campo | Cosa scegliere |
|:--|:--|
| **Severity** | `C - Minimal impact` (l'unica disponibile sul Basic) |
| **Preferred contact method** | `Email` (più tracciabile di Phone) |
| **Your availability** | la tua timezone (Europe/Rome) |
| **Support language** | **`English`** (la queue inglese è più veloce dell'italiana di ~24h) |
| **Contact info** | verifica che email e nome siano corretti |

### Crea il ticket

Clicca il pulsante blu **`Create`** in basso a destra.

## Step 1.6 — Salva il Support Request ID

Dopo qualche secondo Azure ti darà:

- Un **Support Request ID** del tipo `2605230040001234` o simile
- Un messaggio "Your request has been submitted"
- Una email di conferma entro 5 min

**Scrivilo qui:**

```
TICKET #1 (GPU enablement) — Support Request ID: ___________________
                              Submitted at:        ___________________
```

---

# 🟩 TICKET #2 — CPU Standard_D16s_v3 (quota)

Ripeti lo stesso flow, ma con questi valori diversi:

## Step 2.1 — Apri un nuovo Support Request

Torna su **`Help + support`** → **`+ Create a support request`**.

> **NON modificare il ticket #1.** Vogliamo due ticket separati perché
> vanno a team diversi (Subscription Enablement per la GPU, Quota team
> per la CPU) — gestirli insieme fa solo confusione.

## Step 2.2 — Tab "Problem description"

| Campo | Cosa scrivere |
|:--|:--|
| **Summary** | `Quota increase: Standard_D16s_v3 to 16 vCPU in Italy North` |
| **Issue type** | `Service and subscription limits (quotas)` |
| **Subscription** | la tua sub (stessa di ticket #1) |
| **Quota type** | `Compute-VM (cores-vCPUs) subscription limit increases` |

Clicca **`Next: Additional details >>`**.

## Step 2.3 — Request details

Clicca **`Enter details`**, poi:

| Campo | Cosa scrivere |
|:--|:--|
| **Deployment model** | `Resource Manager` |
| **Locations** | spunta solo **`Italy North`** |
| **Types** | spunta **`Standard`** |
| **SKU family** | cerca/spunta **`Standard Dsv3 Family vCPUs`** (la D con la "s" — è quella di `D16s_v3`) |
| **New vCPU limit** | scrivi `16` |

Clicca **`Save and continue`**.

## Step 2.4 — Description

Incolla:

```
Quota increase request.

I need 16 vCPU of Standard_Dsv3 family in Italy North for an audio
rendering workload.

Workload profile:
- ONE VM, Standard_D16s_v3 (16 vCPU, no GPU)
- CPU-only, runs Sfizz + DrumGizmo render binaries
- Total expected runtime: ~5 hours
- Total spend: ~$4 spot / ~$13 on-demand
- Output written to Azure Blob LRS (same region)
- No multi-VM scaling, no persistent infrastructure

Time sensitivity: $200 Azure promotional credit expires on 2026-06-19.

Region rationale: Italy North is the only region where the GPU SKU
needed for the downstream training step (NCADSA100v4) is available
on this subscription — keeping render and training in the same region
avoids egress costs on the 1.5 TB rendered dataset.

Subscription ID: e2137e0a-7341-47b3-8db3-9843344e5c35
```

> ✅ Subscription ID già pre-incollato. Copia-incolla l'intero blocco
> qui sopra così com'è.

**File upload:** vuoto.

Clicca **`Next: Review + create >>`**.

## Step 2.5 — Review + create

Stessi valori del ticket #1:

- Support plan: **Basic**, no upgrade
- Severity: **C - Minimal impact**
- Contact: **Email**
- Language: **English**

Clicca **`Create`**.

## Step 2.6 — Salva il secondo Support Request ID

```
TICKET #2 (CPU quota) — Support Request ID: ___________________
                          Submitted at:       ___________________
```

---

# 📬 Dopo aver inviato i due ticket

## Cosa succede ora

1. **Entro 5 minuti:** ricevi 2 email di conferma su `marco.palermo9901@gmail.com`
2. **Entro 1 ora:** ricevi 2 risposte automatiche "We received your request"
3. **Entro 24-72h lavorative:** prima risposta umana
4. **Approvazione definitiva:** 24-48h dopo la prima risposta umana

## Tracciamento

In qualsiasi momento puoi vedere lo stato:

`Help + support` → **`All support requests`** (menu a sinistra) → vedi i due
ticket con il loro status (`Open`, `Customer action needed`, `Closed`).

## Se Microsoft chiede chiarimenti

Succede sul ~30-40% dei casi su sub nuove. **Rispondi sempre via email,
NON aprire un nuovo ticket.** Domande tipiche e risposte pronte:

| Domanda Microsoft | Risposta da inviare |
|:--|:--|
| *"Confirm this is not for cryptocurrency mining"* | "Confirmed. The workload is supervised learning of an audio transcription neural network in PyTorch. No cryptocurrency mining, no proof-of-work, no blockchain workload." |
| *"What is your monthly Azure spend forecast?"* | "We have a $200 promotional credit expiring 2026-06-19. Expected total spend on this project is under $200." |
| *"Have you considered Azure Machine Learning Studio instead?"* | "No — we need direct VM access for a custom PyTorch training script with vendored dependencies. Azure ML Studio does not fit our deterministic-build requirements." |
| *"Can you start with a smaller quota?"* | "The 24 vCPU is dictated by the Standard_NC24ads_A100_v4 SKU which has exactly 24 vCPU. A smaller quota would prevent the VM from starting." |

## Se entrambi i ticket vengono rifiutati

Plan B (in ordine):

1. **Apri un terzo ticket** per `Standard_NC6s_v3` (1x V100, 6 vCPU) in
   Italy North. V100 è generazione precedente, quote spesso pre-approvate.
   Training più lento ma sufficiente per il primo modello.

2. **Chiedi escalation:** rispondi al ticket rifiutato con
   *"Please escalate this case to the Subscription Enablement team."*

3. **Decision Lock CEO:** se non si sblocca entro **CP-1 (2026-05-30)**,
   valutiamo insieme se ripiegare su scenario YELLOW (training compresso)
   o cercare workaround (Azure batch su altra region).

---

# ✅ Checklist finale

Quando hai finito, segna:

- [ ] Ticket #1 (GPU NCADSA100v4 enablement) creato
- [ ] Ticket #1 — Support Request ID salvato
- [ ] Ticket #2 (CPU Standard_D16s_v3 quota) creato
- [ ] Ticket #2 — Support Request ID salvato
- [ ] 2 email di conferma ricevute su marco.palermo9901@gmail.com
- [ ] Ritorni in chat con gli ID dei ticket per aggiornare il runbook
      `docs/runbooks/F2-T1_RENDER_BURN.md` e il `MASTER_SCHEDULING.md`

---

**Tempo totale stimato per il CEO: 15 min.**
**Costo: $0.**
**Risposta Microsoft attesa: 24-72h.**

*Quando arriva la prima risposta — positiva, richiesta di chiarimenti o
rifiuto — incollala in chat e procediamo col passo successivo.*
