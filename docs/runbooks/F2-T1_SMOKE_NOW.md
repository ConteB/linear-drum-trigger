---
id: LIN-DT-RUNBOOK-F2T1-SMOKE
title: F2-T1 — Smoke test VM render Azure (15 min, ~$0.03 spot)
type: runbook
status: ACTIVE
phase: F2
domain: Operations / Azure
version: 1.0.0
updated: 2026-05-23
tags: [azure, smoke, render, f2-t1, vm-spot]
related: [LIN-DT-MSCHED-001, LIN-DT-RUNBOOK-F2T1]
supersedes: []
---

# 🟢 RUNBOOK — Smoke test F2-T1 (15 minuti, $0.03)

> **Cosa stiamo facendo, in 30 secondi.** Accendiamo una VM Linux piccola
> (`Standard_D16s_v3` 16 vCPU Spot) in Italy North, le facciamo installare
> il toolchain di render (Sfizz + DrumGizmo + kit roster), renderizzare
> **2 sample di prova** (1 Sfizz + 1 DrumGizmo), uploadare su Blob via DVC
> e poi la spegniamo. Costo: ~**$0.03 spot** (15 min × $0.13/h × 0.6 spot
> ratio). Se va, abbiamo validato la pipeline operativa e possiamo lanciare
> il bulk render senza paura.

## ✅ Region alignment — già perfetto

| Risorsa | Region | Note |
|---|---|---|
| **Storage Account `stneurotrigger22` (Blob Gold)** | **italynorth** | verificato dal portale 2026-05-23 |
| **Quota DSv3 16 vCPU** | **italynorth** | approvata 2026-05-23 |

VM e Blob nella stessa region → **zero egress fees** su upload (intra-region
è gratis su Azure). Il bulk render (1.5 TB) costa solo il render compute
(~$3.5 spot), niente sorprese di transfer.

> *(Storico:* il runbook F1-T1 originale citava West Europe come default,
> ma è stato cambiato in italynorth nella sessione T1-prep-D quando si è
> scoperto che D-series è `NotAvailableForSubscription` in West Europe.
> Lo SA è stato creato in italynorth seguendo il riallineamento, ma il
> runbook F1-T1 testo non era stato aggiornato — irrilevante operativamente,
> lo screenshot del portale conferma `Location: italynorth`.)

---

## 0. Pre-flight (1 min)

Apri il terminale macOS e verifica:

```bash
# 1) Azure CLI installato?
az --version | head -1
# Atteso: azure-cli 2.x.x (qualsiasi 2.50+ va bene)

# 2) Sei loggato e vedi la sub col credito?
az account show --query '{name:name, id:id}' -o table
# Atteso: la sub "Azure subscription 1" con ID e2137e0a-7341-47b3-8db3-9843344e5c35
```

**Se `az --version` dice "command not found":**
```bash
brew update && brew install azure-cli
```

**Se `az account show` dà errore o mostra una sub sbagliata:**
```bash
az login
# Apre il browser, autenticati con marco.palermo9901@gmail.com
az account set --subscription "e2137e0a-7341-47b3-8db3-9843344e5c35"
```

**Se il login funziona ma la sub mostrata è diversa:**
```bash
az account list -o table
# Trova quella con $200 credit e
az account set --subscription "<id-corretto>"
```

---

## 1. Variabili shell — copia-incolla in una volta sola

Nella **stessa** sessione terminale (se chiudi devi rifare):

```bash
# Identità Azure — già esistenti da F1-T1
export AZ_RG="rg-neurotrigger-prod"
export AZ_REGION_VM="italynorth"           # ← dove ha approvato la quota DSv3
export AZ_VM_SMOKE="vm-smoke-d16s"
export AZ_VM_SIZE="Standard_D16s_v3"

# Repo + branch — la VM clonerà questo per il provisioning
export NTG_REPO_URL="https://github.com/OP-Magenta/drum-trigger-fresh.git"
export NTG_REPO_BRANCH="develop"

# Seed del recipe matrix — qualsiasi non-negativo. Va nel manifest dna.json.
export NTG_MASTER_SEED=20260524

# Profile di provisioning: smoke = solo 2 kit DrumGizmo + Sfizz minimal
export NTG_KIT_PROFILE="smoke"

# Connection string DVC — la prendiamo da .dvc/config.local
export NTG_BLOB_SAS=$(grep '^    connection_string' .dvc/config.local | sed 's/^    connection_string = //')
echo "SAS: ${NTG_BLOB_SAS:0:60}..."   # primi 60 char (l'intera è lunga, niente leak)
```

> ⚠️ **`NTG_BLOB_SAS` resta solo in questa sessione bash.** Mai committarlo,
> mai stamparlo per intero in chat o in file. La VM lo riceve via
> `--custom-data` (Azure cifra in transit).

---

## 2. Crea la VM smoke (un comando, 3-5 min)

```bash
az vm create \
    --resource-group "$AZ_RG" \
    --name "$AZ_VM_SMOKE" \
    --location "$AZ_REGION_VM" \
    --image "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest" \
    --size "$AZ_VM_SIZE" \
    --priority Spot --max-price -1 --eviction-policy Delete \
    --admin-username azureuser \
    --generate-ssh-keys \
    --custom-data tools/provision_render_vm.sh \
    --os-disk-size-gb 64 \
    --output table
```

**Cosa significa ogni flag:**

| Flag | Cosa fa |
|---|---|
| `--priority Spot --max-price -1` | Spot pricing (≈60% di sconto vs on-demand) con max-price = "qualsiasi prezzo fino a on-demand" |
| `--eviction-policy Delete` | Se Azure evicta la VM, la cancella (no billing residuo) |
| `--generate-ssh-keys` | Genera/usa la tua chiave SSH locale (`~/.ssh/id_rsa.pub`) |
| `--custom-data tools/provision_render_vm.sh` | Passa il provisioning script come cloud-init |
| `--os-disk-size-gb 64` | Disco bastante per smoke (kit DRSKit ~3 GB + Sfizz + venv) |

**Output atteso** (~2-3 min):
```
- ResourceGroup: rg-neurotrigger-prod
- Name: vm-smoke-d16s
- PowerState: VM running
- PublicIpAddress: 20.xxx.xxx.xxx
- ...
```

⚠️ **Se vedi `SkuNotAvailable` o `QuotaExceeded`:**
- `SkuNotAvailable` → DSv3 non disponibile in italynorth (sorpresa). Cambia region: `export AZ_REGION_VM="westeurope"` (la quota DSv3 va richiesta nuova lì)
- `QuotaExceeded` → la quota DSv3 16 vCPU è meno di quanto pensavamo. Riguarda la pagina quote

**Salva il public IP** restituito dal comando (lo userai nel passo 3):
```bash
export VM_IP=$(az vm show --resource-group "$AZ_RG" --name "$AZ_VM_SMOKE" \
    --show-details --query publicIps -o tsv)
echo "VM IP: $VM_IP"
```

---

## 3. Passa le variabili env al provisioning script

⚠️ **Il `--custom-data` di `az vm create` passa il file letterale**, non
sostituisce le variabili. Quindi le variabili `NTG_*` vanno passate alla
VM **dopo** la creazione, via SSH. Comando:

```bash
# Crea un file .env nella VM con le variabili
ssh -o StrictHostKeyChecking=accept-new azureuser@$VM_IP "cat > /tmp/ntg.env <<EOF
NTG_REPO_URL=$NTG_REPO_URL
NTG_REPO_BRANCH=$NTG_REPO_BRANCH
NTG_MASTER_SEED=$NTG_MASTER_SEED
NTG_KIT_PROFILE=$NTG_KIT_PROFILE
NTG_BLOB_SAS='$NTG_BLOB_SAS'
EOF
chmod 600 /tmp/ntg.env"

# Esegui il provisioning script sourcing l'env
ssh azureuser@$VM_IP "set -a; source /tmp/ntg.env; set +a; \
    sudo bash /var/lib/cloud/instance/scripts/runcmd 2>&1 | tee /tmp/provision.log"
```

⚠️ Se il cloud-init è già partito da solo (alcune VM lo fanno
automaticamente al boot), salta i comandi sopra e vai diretto a **§4**
per il monitor.

---

## 4. Monitor cloud-init in tempo reale

Apri un **secondo terminale** (lascia il primo libero), e dalla cartella
del repo:

```bash
# Recupera il VM_IP se hai chiuso la shell
export VM_IP=$(az vm show --resource-group "$AZ_RG" --name "$AZ_VM_SMOKE" \
    --show-details --query publicIps -o tsv)

# Tail dei log del provisioning script
ssh azureuser@$VM_IP "sudo tail -f /var/log/cloud-init-output.log"
```

**Cosa cerchi nei log** (in ordine):

| Linea attesa | Significato |
|---|---|
| `step apt — installing drumgizmo + sfizz...` | Installazione binari |
| `step kits — profile=smoke` | Inizio download kit |
| `  DRSKit: cached (sha256 matches)` | Kit verificato |
| `step venv — creating Python virtualenv` | Setup Python |
| `step dvc — configuring azure remote` | DVC configurato |
| `step smoke — 4-recipe end-to-end` | **Inizio render** |
| `smoke OK — VM is READY` | **🟢 SMOKE GREEN** |

**Se vedi `smoke OK — VM is READY`:** procedi al §5 (verifica Blob).

**Se vedi un errore (`FAILED`, `ERROR`, `non-zero exit`):**
- Premi `Ctrl-C` per uscire dal tail
- Copia l'errore in chat
- Vai diretto al §6 (teardown) — non sprecare clock

⏱ **Tempo atteso totale provisioning + smoke:** 10-15 min.

---

## 5. Verifica che il Blob abbia ricevuto i sample (1 min)

```bash
# Lista i blob nel container "gold" sotto la directory "smoke"
az storage blob list \
    --account-name stneurotrigger22 \
    --container-name gold \
    --prefix "smoke/" \
    --sas-token "$(echo $NTG_BLOB_SAS | sed 's/.*SharedAccessSignature=//')" \
    --query "[].{name:name, size:properties.contentLength}" \
    --output table | head -20
```

**Output atteso:** vedi ~4-8 blob, con `name` tipo
`smoke/<key>.audio.f16`/`.target.f16`/`.dna.json` e `size` non-zero
(audio ~5-10 MB, target ~150 KB, dna ~1.5 KB).

Se la lista è **vuota o size = 0:** il provisioning ha fallito l'upload —
ma comunque non bruci ulteriore credito. Vai al §6.

---

## 6. Teardown — spegni la VM (un comando)

```bash
az vm delete \
    --resource-group "$AZ_RG" \
    --name "$AZ_VM_SMOKE" \
    --yes \
    --no-wait
```

`--no-wait` ritorna subito (la cancellazione avviene in ~30s sul backend).
`--yes` salta la conferma interattiva.

**Verifica che sia sparita** dopo 1-2 minuti:
```bash
az vm list --resource-group "$AZ_RG" --output table
# Atteso: lista vuota (o senza vm-smoke-d16s)
```

⚠️ **Cancella anche i blob orfani lasciati dallo smoke**, se non li
vogliamo nel bulk:
```bash
az storage blob delete-batch \
    --account-name stneurotrigger22 \
    --source gold \
    --pattern "smoke/*" \
    --sas-token "$(echo $NTG_BLOB_SAS | sed 's/.*SharedAccessSignature=//')"
```

---

## 7. Kill switch — se qualcosa va storto

Se vedi un comportamento strano (VM che gira da > 30 min senza output,
costi che salgono, comando bloccato), abbiamo già lo script di emergenza
`tools/azure_kill.sh`:

```bash
# Modalità 1: deallocate (stop billing compute, mantiene storage)
bash tools/azure_kill.sh deallocate

# Modalità 2: teardown (cancella VM + disco + NIC + IP pubblico)
bash tools/azure_kill.sh teardown

# Modalità 3: nuclear (cancella TUTTA la RG — non lo voglio per lo smoke)
# bash tools/azure_kill.sh nuclear
```

Lo script chiede magic-word di conferma per `teardown` e `nuclear`.

---

## 8. Checklist DoD — quando aver finito

- [ ] `az --version` ≥ 2.50 verificato
- [ ] `az account show` mostra sub `e2137e0a-7341-47b3-8db3-9843344e5c35`
- [ ] Variabili shell `NTG_*` settate
- [ ] VM `vm-smoke-d16s` creata in italynorth (output `az vm create` OK)
- [ ] Cloud-init mostra `smoke OK — VM is READY` nei log
- [ ] Blob `stneurotrigger22/gold/smoke/` contiene ≥ 4 file non-zero
- [ ] VM eliminata (`az vm list` non la mostra più)
- [ ] Blob `smoke/*` opzionalmente cancellati
- [ ] Costo finale visibile sul portale Azure → **Cost Management** entro 24h, atteso **≤ $0.10**

---

## 9. Cosa torna in chat dopo lo smoke

Quando hai chiuso il teardown, **incolla in chat**:

1. **Output del comando `az storage blob list`** del §5 (i blob trovati)
2. **Tail finale di `/var/log/cloud-init-output.log`** — le ultime 30 righe
3. **Eventuali errori** che hai visto

Da quello capisco se possiamo lanciare il **bulk render** (~5h, ~$3.5)
o se serve correggere qualcosa prima.

---

## 10. Decisione post-smoke — bulk render

Se lo smoke è verde, **partiamo dritti col bulk** (vedi `F2-T1_RENDER_BURN.md`):
SA + VM + quota tutti in italynorth, zero cross-region fees, zero attese.

⚠️ **Pre-bulk: fix di un bug latente nel barcode encoding.**

Il dataset R&D locale generato in parallelo (2026-05-23) ha rivelato che il
codice attuale del **DNA-Trace barcode** non distingue variant_idx 1 vs 2
quando i parametri di `MidiJitter` sono identici (entrambe le varianti
jittered producono lo stesso barcode `V3T1`, la seconda sovrascrive la
prima → si perde il 33 % dei sample). Per lo **smoke** non è bloccante
(usa solo 4 recipe con barcode distinto), ma **prima del bulk F2-T1**
servirà:

- estendere `Barcode` (F0-T2a §3.7) per includere il segmento `Jnn` ratificato
  da F0-T15-pre (già nella spec, non ancora propagato all'orchestrator), oppure
- distinguere le varianti via un campo discriminante nel `MidiJitter` block
  (es. propagare `variant_idx` direttamente nella recipe).

Stima fix: ~30 min, locale, $0 Azure. Da fare prima di lanciare il bulk.

Stima bulk dopo il fix: ~5h, ~$3.5 spot (calibrazione L2 con 16 vCPU).

---

*Runbook F2-T1 smoke, 2026-05-23. Gianpiero Scappelloni (Strategic Advisor) — per il CEO.
Quando il dataset locale R&D (parallel-track) è verde e la quota DSv3 16 vCPU è
approvata, questo runbook è il prossimo passo operativo del CEO.*
