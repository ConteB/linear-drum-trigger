---
id: LIN-DT-RUNBOOK-F2T1
title: Runbook F2-T1 — Burn Render Gold (per il CEO)
type: runbook
status: ACTIVE
phase: F2
domain: Operations / Compute
version: 1.0.0
updated: 2026-05-23
tags: [azure, render, F2-T1, ceo-action, gold]
related: [LIN-DT-MSCHED-001, LIN-DT-SIA-001, LIN-DT-RUNBOOK-F1T1, LIN-DT-SPEC-F0T15PRE]
supersedes: []
---

# F2-T1 — Burn Render Gold (Guida CEO)

> **Runbook operativo per il CEO**, da eseguire sul portale Azure / Azure CLI
> dopo che la prossima sessione conferma il via. Output: il dataset Gold
> (1.5 TB × 3 varianti jitter ≈ 4.5 TB) sul Blob, versionato via DVC.
>
> Pattern identico a `F1-T1_AZURE_SETUP.md`: io ho preparato tutti gli
> artefatti locali (`tools/build_recipe_matrix.py`, `tools/provision_render_vm.sh`,
> `tools/azure_kill.sh`); tu li lanci sulla VM, monitori, e mi torni con il
> log finale.

## Cosa stiamo facendo, in 30 secondi

Accendiamo **una VM Linux su Azure**, le facciamo scaricare i 10 kit
del roster F0-T1b (sha256-verified), installare il toolchain di render
(Sfizz + DrumGizmo) e renderizzare la **recipe matrix** `MIDI × jitter × engine`
prodotta da `tools/build_recipe_matrix.py`. La VM impacca gli shard WebDataset
con `ShardWriter` (F0-T5) e li carica sul Blob via `dvc push`. A fine
rendering la spegniamo (è un *one-shot job*, non un servizio).

**Costo stimato:** ~$10.8 compute (D16s_v3 × ~14h) + ~$90 storage / mese
Blob Gold. Totale F2-T1 ≈ $100, dentro $200 con margine $100 per
F2-T2 + F2-T3 + Tier 2/3.

**Vincolo temporale:** il credito Azure scade **2026-06-19** (27 gg da oggi).
Avvio F2-T1 ≤ 2026-05-30 (CP-1) è la finestra GREEN.

---

## 1. Pre-checklist (prima di accendere la VM)

- [ ] **Saldo Azure**: visibile sul portale → almeno $150 residui (≥ buffer).
- [ ] **F1-T1 ☑** — Resource Group + Storage Account + container `gold` + alert spesa.
- [ ] **F1-T2 ☑** — DVC remote `azure://gold/dvc` con SAS valido (scade 2026-08-21).
- [ ] **`tools/build_recipe_matrix.py`** smoke-tested in locale (gira sul mini-batch
  e genera 4 ricette parsabili — già verificato in questa sessione).
- [ ] **`tools/provision_render_vm.sh`** committato nel branch `develop`.
- [ ] **`AZ_RG`, `AZ_VM`** decisi (suggeriti: `rg-neurotrigger`, `vm-render-d16s`).

## 2. Decisione di scala — VM size (italynorth)

**Default raccomandato:** **`Standard_M16ms` spot** (16 vCPU, 437 GB RAM,
~$0.66/h spot · $2.20/h on-demand) — Decision Lock CEO 2026-05-23
(sessione T1-prep-D, riallineamento post-`SkuNotAvailable` D-series).

> La sottoscrizione ha `Standard_D*_v3` come `NotAvailableForSubscription`
> sia in italynorth che in westeurope. In italynorth sono disponibili
> `M-series` (memory-optimised, RAM esuberante ma vCPU OK) e
> `NC*_A100_v4` (training F2-T3). Restiamo in italynorth: l'A100 per il
> training è listata qui, non in westeurope.

Calibrazione L2 estesa con la recipe matrix ×3 (4.5 TB):

| VM | Wall-clock | Costo spot | Costo on-demand | Note |
| :-- | :-- | :-- | :-- | :-- |
| **`Standard_M16ms` spot** ✅ | ~14h | **~$9.4** | $31 | semplice, min wall-clock |
| `Standard_M8ms` spot | ~28h | ~$9.4 | $31 | più lento, doppio rischio eviction |
| `Standard_DC16as_v6` on-demand | ~14h | n/a (no spot) | ~$15-18 | Confidential Compute premium, fallback se spot RED |

**Rischio spot eviction:** Azure può rilasciare la VM con 30s di preavviso.
Il runner è **resume-safe** (manifest + ShardWriter persistenti); un'eviction
perde max ~8 shard (~$1 di lavoro), ripresa automatica al re-launch.
Probabilità tipica < 5 % su 14h.

**Smoke pre-burn:** `Standard_M8ms` spot per 15 min ($0.08) — il profilo
`smoke` del provisioning scarica solo 2 kit (~5 GB) e fa render di 2
campioni end-to-end.

## 3. Comandi Azure CLI (copia-incolla)

### 3.1 Variabili — settale una volta sola

```bash
export AZ_RG="rg-neurotrigger-prod"
export AZ_VM="vm-render-m16ms"
export AZ_VM_SIZE="Standard_M16ms"
export AZ_REGION="italynorth"          # stessa regione del Blob (F1-T1)
export NTG_REPO_URL="https://github.com/<USER>/drum-trigger-fresh.git"
export NTG_REPO_BRANCH="develop"
export NTG_BLOB_SAS='<la connection string SAS di F1-T2>'
export NTG_MASTER_SEED=20260524        # qualsiasi non-negativo; va nel manifest
```

> ⚠️ **NON committare mai** `NTG_BLOB_SAS` da nessuna parte — vive solo nella
> shell della tua sessione. La VM lo riceve via `--custom-data` cifrato in
> transito Azure.

### 3.2 Smoke prima del burn — VM piccola, 15 min

```bash
# 1) Crea la VM smoke spot (Ubuntu 22.04 LTS, M8ms ~$0.33/h spot)
az vm create \
    --resource-group "$AZ_RG" \
    --name "${AZ_VM}-smoke" \
    --location "$AZ_REGION" \
    --image "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest" \
    --size Standard_M8ms \
    --priority Spot --max-price -1 --eviction-policy Delete \
    --admin-username azureuser \
    --generate-ssh-keys \
    --custom-data /tmp/cloud-init-smoke.sh \
    --os-disk-size-gb 64 \
    --output table

# 2) Tail dei log cloud-init (apre SSH, segue /var/log/cloud-init-output.log)
VM_IP=$(az vm show --resource-group "$AZ_RG" --name "${AZ_VM}-smoke" \
    --show-details --query publicIps -o tsv)
ssh azureuser@$VM_IP "sudo tail -f /var/log/cloud-init-output.log"

# 3) Quando vedi 'smoke OK — VM is READY' → spegnila
az vm delete --resource-group "$AZ_RG" --name "${AZ_VM}-smoke" --yes
```

Il provisioning script (env `NTG_KIT_PROFILE=smoke`) scarica solo 2 kit
DrumGizmo (~5 GB) + tutti gli SFZ (~3 GB), per validare la pipeline senza
attendere i ~13 GB dei kit manifest-only restanti. Costo smoke: ~$0.08.

`--priority Spot --max-price -1` significa "spot, paga fino al prezzo
on-demand" (rare eviction). `--eviction-policy Delete` rilascia la VM
se evicted invece di lasciarla "stopped, deallocated" (zero risk di
billing residuo).

### 3.3 Burn vero — D16s_v3, 14h

Il `provision_render_vm.sh` lascia la VM in stato READY. Per lanciare il
burn vero della recipe matrix completa, accedi via SSH e lancia:

```bash
az ssh vm --resource-group "$AZ_RG" --name "$AZ_VM" \
    -- "cd /opt/neurotrigger/drum-trigger-fresh && \
        source /opt/neurotrigger/venv/bin/activate && \
        nohup python tools/run_f2_t1_render.py \
            --recipe-dir recipes/f2-t1 \
            --gold-dir   data/gold \
            --state-file /opt/neurotrigger/state.json \
            --master-seed $NTG_MASTER_SEED \
            --vm-name $AZ_VM \
            --vm-size $AZ_VM_SIZE \
            --vm-hourly-usd 0.77 \
            --dvc-push-every 8 \
            > /opt/neurotrigger/runner.log 2>&1 &"
```

`nohup ... &` lancia il runner in background — può tu staccarti
dall'SSH e il rendering continua. Lo state.json viene aggiornato dopo
ogni recipe completata; il monitor TUI (§3.4) lo legge in real-time.

### 3.3.bis VM creation iniziale

```bash
# Crea la VM render. Custom-data = provisioning script. La VM si auto-provisiona
# in ~30 min, poi lancia il burn.
az vm create \
    --resource-group "$AZ_RG" \
    --name "$AZ_VM" \
    --location "$AZ_REGION" \
    --image "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest" \
    --size "$AZ_VM_SIZE" \
    --priority Spot --max-price -1 --eviction-policy Delete \
    --admin-username azureuser \
    --generate-ssh-keys \
    --custom-data /tmp/cloud-init-burn.sh \
    --os-disk-size-gb 256 \
    --output table

# Tail dei log (puoi staccarti, il job continua sulla VM)
VM_IP=$(az vm show --resource-group "$AZ_RG" --name "$AZ_VM" \
    --show-details --query publicIps -o tsv)
ssh azureuser@$VM_IP "tail -f /opt/neurotrigger/provision.log"
```

### 3.4 Monitor TUI — barra di avanzamento real-time

Apri un secondo terminale e lancia:

```bash
# Su Mac: pubblicizza l'IP della VM via az
VM_IP=$(az vm show --resource-group "$AZ_RG" --name "$AZ_VM" \
        --show-details --query publicIps -o tsv)

# Apre la TUI a tutto schermo — Ctrl-C per uscire (la VM continua)
python tools/f2_t1_monitor.py \
    --source ssh \
    --ssh-target "azureuser@${VM_IP}" \
    --interval 30
```

Cosa mostra:

- **phase** corrente (provisioning / smoke / rendering / packing / done)
- **progress bar** ricette (X/Y) + shard (X/Y) + volume cumulativo
- **now rendering** — quale recipe sta girando in questo istante
- **cost estimate** — spent live (elapsed × $/h), proiezione full-burn, **budget left** colorato verde/giallo/rosso secondo le soglie §5
- **log tail** ultime ~8 righe dal renderer

Fail-soft: una SSH glitch transitoria → mostra `⚠ poll failed`, mantiene
l'ultimo stato visibile. Una JSON corrotta → idem. Niente crash.

Per testarlo in locale **senza VM** (smoke):

```bash
python tools/gen_mock_state.py --tick 1 --total 50 &
python tools/f2_t1_monitor.py --source mock --interval 1
```

### 3.5 Monitor spesa CLI (legacy, ogni 2 ore)

```bash
# Vedi le ultime 5 voci di consumo
az consumption usage list --top 5 --output table
```

**Soglie** (`MASTER_SCHEDULING §5`):
- **$100** spesi → valutazione: scenario YELLOW? procedi con cautela
- **$40 residui** → stop compute, push HDD
- **$10 residui** → chiudi tutto (`./tools/azure_kill.sh nuclear`)

### 3.6 Kill switch — emergenze

```bash
# Stop billing immediato (compute spento, dati preservati)
./tools/azure_kill.sh deallocate

# Cancella VM ma preserva Blob (richiede typing 'TEARDOWN')
./tools/azure_kill.sh teardown

# Distruzione totale — solo se Blob è già teardown via DVC (richiede 'NUCLEAR')
./tools/azure_kill.sh nuclear
```

## 4. Quando hai finito

Quando il burn finisce (sulla VM vedi `dvc push complete` e `manifest.json`
caricato), invia il seguente trio di valori — io riparto da lì con F2-T2:

1. **`recipe_matrix_seed`** (= `NTG_MASTER_SEED`)
2. **Numero shard** generati (= `manifest.json.n_shard`)
3. **Saldo Azure residuo** (dal portale)

Poi `az vm delete` sulla VM render — il compute è finito, lo storage
Blob continua a costare ~$30/mese (1.5 TB LRS, F1-T1 alert già configurato).

---

*Runbook autonomo — non dipende da OP-X. Stesso pattern di F1-T1. Decision
Lock CEO 2026-05-23 (sessione T1-prep-D) — VM size = D16s_v3 default.*
