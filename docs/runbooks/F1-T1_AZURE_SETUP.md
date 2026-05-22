---
id: LIN-DT-RUNBOOK-F1T1
title: Runbook F1-T1 — Setup Azure (per il CEO)
type: runbook
status: ACTIVE
phase: F1
domain: Operations / Infrastructure
version: 1.0.0
updated: 2026-05-23
tags: [azure, setup, infrastructure, F1, ceo-action]
related: [LIN-DT-MSCHED-001, LIN-DT-INFRA-001]
supersedes: []
---

# F1-T1 — Setup Azure (Guida CEO)

> Guida operativa **per il CEO**, da eseguire una volta sola sul portale Azure.
> Quando hai finito mi mandi i 4 valori che ti chiedo alla fine e io riparto da lì
> con F1-T2 (configurazione DVC remote) e F2-T1 (render).

## Cosa stiamo facendo, in 30 secondi

Creiamo lo **scaffale cloud** dove andrà il dataset Gold quando lo renderizzeremo
su Azure. Tre cose:

1. **Lo storage** — un Blob Storage privato dove DVC scrive il dataset.
2. **Le protezioni** — Soft Delete (cestino 7 giorni) + WORM su Bronze
   (anti-cancellazione) + accesso solo via token con scadenza.
3. **Gli allarmi di spesa** — due email automatiche quando arriviamo al **50%**
   ($100) e all'**80%** ($160) del credito.

Tempo stimato: **30–40 min** se non hai sorprese.

Costo immediato: **~$0**. Lo storage paga ~$27/mese, ma fino a che non carichiamo
1.5 TB di dati siamo a zero. F2-T1 (render) si stima ~$3.5 in totale.

---

## Prima di iniziare — checklist requisiti

- [ ] Accesso al portale [https://portal.azure.com](https://portal.azure.com) con
      l'email su cui è stato attivato il credito (2026-05-20).
- [ ] Saldo credito visibile — vai su **Cost Management + Billing**, deve
      mostrarti **~$200** disponibili (potrebbero esserci pochi cent già spesi se
      Azure ha consumato qualcosa di test).
- [ ] Una **email di alert valida** (la stessa va benissimo) per ricevere gli avvisi
      di spesa.
- [ ] Un posto sicuro dove salvare i 4 valori finali — vedi §"Cosa salvare" alla
      fine. **NON** committarli in git: tutto sotto `~/azure-credentials/` fuori
      dal repo, o un password manager.

> 🛑 **Regola d'oro per la sicurezza** (matrice rischio SEC-01): mai usare la
> **Account Key master** dello storage. Usa solo **SAS Token scoped**. La master
> key, se trapela, dà accesso totale ed è revocabile solo ruotandola.

---

## Step 1 — Resource Group

Una "Resource Group" è una scatola che contiene tutto il resto. Aiuta a
cancellare tutto in un colpo solo se serve.

1. Portale → barra di ricerca in alto → digita **"Resource groups"** → clic.
2. Tasto **`+ Create`**.
3. **Subscription:** seleziona quella con il credito attivo (di solito è una
   sola — qualcosa tipo "Azure subscription 1" o "Free Trial").
4. **Resource group name:** `rg-neurotrigger-prod`
5. **Region:** **West Europe** (Amsterdam — più vicino all'Italia, meno latenza
   sui push DVC).
6. Tasto **`Review + create`** → **`Create`**.

Verifica: dopo ~10 secondi vedi il banner verde **"Your deployment is complete"**
e la Resource Group appare nella lista.

---

## Step 2 — Storage Account

L'account di storage è il "disco cloud". Dentro ci stanno i container (cartelle
di primo livello).

1. Portale → barra di ricerca → **"Storage accounts"** → clic.
2. Tasto **`+ Create`**.

### Tab "Basics":

| Campo | Valore |
| :-- | :-- |
| **Subscription** | la stessa con il credito |
| **Resource group** | `rg-neurotrigger-prod` |
| **Storage account name** | `stneurotrigger<NN>` — sostituisci `<NN>` con due cifre random (es. `stneurotrigger42`). Il nome deve essere unico al mondo, 3–24 caratteri, solo minuscole e cifre |
| **Region** | West Europe |
| **Primary service** | **Azure Blob Storage** |
| **Performance** | **Standard** |
| **Redundancy** | **Locally-redundant storage (LRS)** — *importante: NON GRS, costerebbe il doppio* |

> Se il nome è già usato Azure ti dice "name is already taken" — cambia le due
> cifre finali e riprova.

### Tab "Advanced":

| Campo | Valore |
| :-- | :-- |
| **Require secure transfer for REST API operations** | ✅ Enabled (default) |
| **Allow enabling anonymous access on individual containers** | ❌ **Disabled** *(critico — anti SEC-04)* |
| **Enable storage account key access** | ✅ Enabled *(serve per generare SAS — lo useremo, non lo daremo via)* |
| **Default to Azure Active Directory authorization in the Azure portal** | ✅ Enabled (raccomandato) |
| **Minimum TLS version** | **Version 1.2** |
| **Permitted scope for copy operations** | "From any storage account" (default) |

### Tab "Data protection":

Questo è il tab più importante per la sicurezza.

| Campo | Valore |
| :-- | :-- |
| **Enable point-in-time restore for containers** | ❌ Off (costa) |
| **Enable soft delete for blobs** | ✅ **Enabled — Retention: 7 days** |
| **Enable soft delete for containers** | ✅ **Enabled — Retention: 7 days** |
| **Enable soft delete for file shares** | ❌ Off (non usiamo file shares) |
| **Enable versioning for blobs** | ✅ **Enabled** *(salva la storia di ogni blob — protegge da overwrite)* |
| **Enable blob change feed** | ❌ Off |
| **Enable version-level immutability support** | ✅ **Enabled** *(serve per il WORM dello Step 4)* |

### Tab "Encryption":

Lascia tutto default — Microsoft-managed keys vanno benissimo per noi.

### Tab "Networking":

Lascia tutto default — **"Enable public access from all networks"** è OK perché
proteggiamo l'accesso col SAS, non con firewall di rete (per la nostra scala
sarebbe overkill).

### Finalizzazione:

Tasto **`Review + create`** → **`Create`**.

Il deployment richiede ~30 secondi. Verifica: la Storage Account compare nella
Resource Group con icona blu.

---

## Step 3 — Blob Containers (Bronze / Silver / Gold)

I container sono le cartelle di primo livello. Seguiamo la struttura
**Medallion** ([`DOSSIER §9.2`](../methodology/DOSSIER_TECNICO.md#medallion)):

- **bronze** — fonti raw (MIDI da GMD, ecc.)
- **silver** — WAV intermedi del render (rigenerabili)
- **gold** — i tensori FP16 finali (irrimpiazzabili — il "tesoro")

1. Apri la Storage Account che hai appena creato.
2. Menu di sinistra → **Data storage** → **Containers**.
3. Tasto **`+ Container`** e ripeti **tre volte** con questi valori:

| Name | Public access level | Anonymous access |
| :-- | :-- | :-- |
| `bronze` | **Private (no anonymous access)** | ❌ |
| `silver` | **Private (no anonymous access)** | ❌ |
| `gold`   | **Private (no anonymous access)** | ❌ |

Verifica: tutti e tre i container compaiono nella lista con icona "private".

---

## Step 4 — Immutability Policy (WORM) sul container Bronze

WORM = "Write Once, Read Many" — una volta scritto, il file non può essere
cancellato fino a che il periodo non scade. Protegge i sorgenti raw da
cancellazioni accidentali (matrice rischio SEC-02).

1. Clic sul container **`bronze`**.
2. Menu in alto → **`...`** (tre puntini) → **Access policy**.
3. Sezione **"Immutable blob storage"** → tasto **`+ Add policy`**.
4. **Policy type:** **Time-based retention**.
5. **Retention period:** **30 days**.
6. **Scope:** **Container** (default).
7. **Allow protected append writes:** ✅ checked (così DVC può scrivere blob
   nuovi mentre quelli esistenti restano protetti).
8. Tasto **`Save`**.

> ⚠️ La policy ora è **unlocked** — può essere cancellata. Quando avremo
> popolato Bronze e saremo sicuri, la "locheremo" (azione irreversibile per la
> durata del periodo). Per ora resta unlocked, è normale.

Verifica: la sezione "Immutable blob storage" del container mostra una policy
attiva con stato **Unlocked**, 30 days.

---

## Step 5 — SAS Token (le chiavi che mi darai)

Il SAS è un token con permessi e scadenza esatti. **Niente master key**.

1. Torna sulla Storage Account (livello superiore, non dentro un container).
2. Menu di sinistra → **Security + networking** → **Shared access signature**.
3. Compila così:

| Campo | Valore |
| :-- | :-- |
| **Allowed services** | ✅ Blob — *solo questo* |
| **Allowed resource types** | ✅ Service, ✅ Container, ✅ Object |
| **Allowed permissions** | ✅ Read, ✅ Write, ✅ List, ✅ Add, ✅ Create — **NON Delete, NON Permanent Delete** |
| **Blob versioning permissions** | ✅ Enable deletion of versions (per gestire le versioni se servisse — comunque protetti da soft delete) |
| **Allowed blob index permissions** | Lasciare deselezionato |
| **Start** | adesso (default) |
| **Expiry** | **+90 giorni da oggi** — quindi `2026-08-21` se firmi il 2026-05-23 |
| **Allowed IP addresses** | lasciare vuoto (filtraggio IP fa più male che bene per noi) |
| **Allowed protocols** | **HTTPS only** |
| **Preferred routing tier** | Basic (default) |
| **Signing key** | **key1** (default) |

4. Tasto **`Generate SAS and connection string`**.
5. Compaiono **tre stringhe**. A noi servono **due**:
   - **Connection string** — la useremo per `dvc remote modify` (Step 5
     successivo, lato Mac).
   - **SAS token** — la stringa che inizia con `?sv=…` — backup, se serve.
   - **Blob service SAS URL** — non ci serve adesso.

6. **COPIA SUBITO** le due stringhe in un file di testo sul tuo Mac fuori dal
   repo (es. `~/azure-credentials/neurotrigger-sas-2026-05-23.txt`). **Non
   sono recuperabili** dopo aver chiuso la pagina — se le perdi devi ri-generare.

> 🛑 **Mai committare il SAS in git**. È nel `.gitignore` di default per estensione,
> ma per sicurezza mettilo in una cartella fuori dal repo.

---

## Step 6 — Budget + Alert di spesa ($100 e $160)

Doppio cuscinetto: il primo a $100 = "stiamo bruciando metà credito, è il
momento di valutare"; il secondo a $160 = "ottanta percento, attenzione massima".

1. Portale → barra di ricerca → **"Cost Management + Billing"** → clic.
2. Seleziona la subscription con il credito (in alto a sinistra).
3. Menu di sinistra → **Cost Management** → **Budgets**.
4. Tasto **`+ Add`**.

### Pannello "Create budget":

| Campo | Valore |
| :-- | :-- |
| **Scope** | (precompilato sulla subscription corrente) |
| **Name** | `budget-neurotrigger-200usd` |
| **Reset period** | **Billing month** |
| **Creation date** | oggi |
| **Expiration date** | **2026-07-31** (un mese dopo la scadenza del credito — copre eventuali ritardi nella chiusura) |
| **Budget amount** | **200** USD |

Tasto **`Next`** per arrivare alla pagina degli alert.

### Pannello "Alerts":

Crea **due alert**, uno per ogni soglia:

**Alert 1:**

| Campo | Valore |
| :-- | :-- |
| **Type** | **Actual** |
| **% of budget** | **50** (= $100) |
| **Action group** | lascia vuoto |
| **Alert recipients (email)** | la tua email |
| **Alert language** | English (o Italian se disponibile) |

**Alert 2:**

| Campo | Valore |
| :-- | :-- |
| **Type** | **Actual** |
| **% of budget** | **80** (= $160) |
| **Action group** | lascia vuoto |
| **Alert recipients (email)** | la tua email |
| **Alert language** | English |

Tasto **`Create`**.

> Nota: Azure Cost Alerts hanno un ritardo di ~8-24 ore sulla telemetria di
> spesa. Vanno benissimo come early warning ma non come freno hardware. Se vedi
> spesa anomala in tempo reale, lo strumento giusto è "Cost analysis" sotto Cost
> Management — controllo manuale, raccomandato ogni paio di giorni durante F2.

Verifica: la lista Budgets mostra `budget-neurotrigger-200usd` con i due alert
configurati.

---

## Cosa salvare e dove

Dopo aver finito, mettimi questi **4 valori** in un file di testo nel Mac, sotto
`~/azure-credentials/neurotrigger-2026-05-23.txt`, **fuori dal repo**:

```
1. Resource Group name:  rg-neurotrigger-prod
2. Storage Account name: stneurotrigger<NN>            ← quello esatto che hai usato
3. Connection string:    DefaultEndpointsProtocol=https;BlobEndpoint=...   ← Step 5
4. SAS token:            ?sv=2024-...&se=2026-08-21...                    ← Step 5
```

Quando mi dai il via per la prossima sessione (F1-T2), mi dici solo i primi due
(nome RG + nome storage account) — la connection string e il SAS me li passi
quando configuro DVC remote, in modo che restino sul tuo Mac (io non ho
bisogno di vederli persistenti, li uso e bon).

---

## Checklist DoD F1-T1 — quando aver finito

- [ ] Resource Group `rg-neurotrigger-prod` creata in West Europe.
- [ ] Storage Account `stneurotrigger<NN>` creata, **LRS**, Standard, soft delete
      blob+container 7 giorni, versioning ON, version-level immutability ON.
- [ ] Tre container privati: `bronze`, `silver`, `gold`.
- [ ] Immutability policy (time-based, 30 days, **unlocked**) attiva su `bronze`.
- [ ] SAS token generato — permessi Read/Write/List/Add/Create — **scadenza
      2026-08-21** — copiato fuori dal repo.
- [ ] Budget `budget-neurotrigger-200usd` da 200 USD attivo con **due alert
      email** a 50% ($100) e 80% ($160).
- [ ] I 4 valori salvati nel file fuori repo.

---

## Cosa farò io nella prossima sessione

Quando mi dai i primi due valori (nome RG + nome storage), io riparto e:

1. **F1-T2 — dvc remote Azure.** Installo `dvc-azure` nella venv,
   configuro il remote DVC sul container `gold`, faccio un `dvc push` di prova
   con un file da pochi byte. ~15 min.

2. **F0-T4b — TCN mini-prototipo (track parallelo locale, €0).** Implemento la
   rete neurale secondo `F0-T4a_TCN_TOPOLOGY_SPEC.md`, la alleno sui 12 campioni
   Gold di F0-T2e, misuro le metriche di onset, esporto in RTNeural JSON e
   verifico il round-trip C++. Questo è il pezzo che sblocca **Gate L3** e
   quindi lo spend di training. È lavoro di giorni, ma se parte ora arriva
   in tempo per la scadenza credito.

In parallelo, tu non hai più niente da fare lato Azure fino a che non vedi
arrivare un alert email (e a quel punto è solo un "stato come sta?", non
un'azione da intraprendere). Tu sei libero.

---

## Se qualcosa va storto

- **"Subscription disabled" o credito non visibile:** vai su Cost Management +
  Billing → Subscriptions. Se vedi "Disabled" → il credito è stato attivato su
  un'altra subscription. Cerca l'email di attivazione del 2026-05-20 e usa il
  link da lì.
- **Nome storage account già preso:** cambia le due cifre finali. Il nome deve
  essere unico al mondo.
- **"You don't have permission to create resources":** verifica di essere
  loggato con l'account a cui è stato accreditato il bonus, non con un account
  Microsoft personale diverso.
- **SAS token "Generate" disabilitato:** scrolla giù — c'è un riepilogo dei
  parametri prima del tasto. Probabile che manchi un checkbox in
  "Allowed resource types".
- **Budget alert non si attivano:** sono normali fino a che la spesa non
  supera la soglia. Per testare la pipeline c'è "Cost analysis" con la
  proiezione attuale.

Qualunque blocco — mandami lo screenshot dell'errore in chat alla prossima
sessione e ripartiamo da lì.

---

*Runbook F1-T1, 2026-05-23. Gianpiero Scappelloni (Strategic Advisor) — per il CEO.*
