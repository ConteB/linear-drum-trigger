---
id: LIN-DT-SIA-001
title: Strategic Infrastructure Audit
type: reference
status: ACTIVE
phase: cross-cutting
domain: Infrastructure / Strategy
version: 1.1.0
updated: 2026-05-22
tags: [infrastructure, azure, budget, strategy]
related: [LIN-DT-MSCHED-001, LIN-DT-SCHED-001]
supersedes: []
---

# 🛰️ STRATEGIC INFRASTRUCTURE AUDIT (OP-SIA-001)
**Prodotto:** OP-NeuroTrigger
**Responsabile:** Gianpiero Scappelloni (Strategic Advisor)
**Status:** DECISION LOCKED - SCENARIO BETA
**Budget Allocato:** €500 (Target Burn Rate: <€15/mo)

## 1. EXECUTIVE SUMMARY
L'analisi mira a bilanciare la flessibilità della "Lean-Guerrilla" con gli standard professionali dell'industria AI. La scelta è ricaduta sullo **SCENARIO BETA (Professional Hybrid)**, garantendo sovranità del dato, versionamento industriale e ottimizzazione dei costi.

## 2. ANALISI COMPARATIVA DEGLI SCENARI

### Scenario ALPHA: Pure Guerrilla (Costo €0)
- **Descrizione:** Tutto locale su Mac Air M5.
- **Vulnerabilità:** Rischio totale di perdita dati; zero scalabilità; valore di mercato dell'asset ridotto (non replicabile).
- **Esito:** SCARTATO (Rischio eccessivo).

### Scenario BETA: Professional Hybrid (Costo ~€80-100 Totali)
- **Descrizione:** 
    - **Storage:** Azure Blob Storage + DVC (Data Version Control).
    - **Training:** Sviluppo locale (M5) + Final Training su Azure Spot / RunPod.
- **Vantaggi:** 100% standard industriale, backup geografico, costi variabili (pay-per-use).
- **Esito:** **APPROVATO (Best Balance).**

### Scenario GAMMA: Cloud Native (Costo >€250)
- **Descrizione:** Pipeline automatizzata su Azure ML.
- **Vulnerabilità:** Burn rate troppo elevato per il budget di €500; rischio di paralisi da configurazione.
- **Esito:** SCARTATO (Over-engineering).

---

## 3. ARCHITETTURA DEL DATO (MEDALLION ARCHITECTURE)
Per la gestione professionale su Azure Blob Storage, i dati seguiranno questo flusso:

1.  **BRONZE (Raw):** Dataset originali (GMD, Slakh) in formato grezzo. Licenze CC-BY incluse.
2.  **SILVER (Processed):** Audio renderizzato e normalizzato. Script di pulizia versionati.
3.  **GOLD (Inference Ready):** Tensori PyTorch (.pt) pronti per l'addestramento della TCN.

## 4. STACK TECNOLOGICA INFRASTRUTTURALE
- **Versionamento Dati:** `DVC` (integrazione Git-to-Azure).
- **Storage Remoto:** `Azure Blob Storage` (LRS - Locally Redundant Storage).
- **Tracking Esperimenti:** `MLflow` (interno ad Azure o locale).
- **Database Metadata:** `SQLite` (locale, versionato nel repo).
- **Ambiente Linux locale:** `OrbStack` — macchina Ubuntu (`ubuntu`) usata come
  ambiente Linux su macOS. Istanziata (2026-05-22) per eseguire il **gate mutation**
  (`mutmut`): mutmut 3.x impone il `fork`, e su macOS un figlio forkato con librerie
  native caricate (numpy BLAS, `libsndfile`) va in **segfault** — il gate è quindi
  inservibile sul Mac. La macchina ospita un venv dedicato (`~/ntg-venv`); il gate si
  lancia con `tools/run_mutation.sh`. Dettaglio policy e provisioning:
  [`TESTING_DOCTRINE §3.1`](TESTING_DOCTRINE.md#equivalent-mutants).

## 5. DATA INFRASTRUCTURE SECURITY & RISK ANALYSIS (ERM)
Per proteggere il capitale intellettuale (il nostro dataset "Gold" e i modelli addestrati), adottiamo un approccio di sicurezza basato sull'efficienza di costo e sulla bassa complessità di manutenzione (Lean-Sec).

### 5.1 Matrice dei Rischi

| ID Rischio | Descrizione dell'Evento (Minaccia) | Impatto | Probabilità | Strategia di Mitigazione |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | **Leakage dei Credenziali (SAS Token / Keys).** Committare per errore le chiavi Azure in GitHub pubblico. | CATASTROFICO (Furto IP, Costi Cloud fuori controllo) | ALTA (Errore umano comune) | Prevenzione hard-coded (Git Hooks). |
| **SEC-02** | **Cancellazione Accidentale Blob.** Errore nello script DVC o comando Azure CLI che distrugge il livello Bronze/Gold. | GRAVE (Blocco R&D, Necessità di ri-rendering) | MEDIA | Soft Delete & Immutable Layers. |
| **SEC-03** | **Ransomware / Compromissione Mac Locale.** Infezione del laptop di sviluppo che cifra i dati non pushati. | MODERATO (Perso solo il lavoro non ancora pushato su DVC) | BASSA | Zero-Trust locale + DVC Push frequente. |
| **SEC-04** | **Attacco DDoS / Egress Billing.** Qualcuno scarica ripetutamente i nostri dati pubblici (se mal configurati) esaurendo il budget Azure. | GRAVE (Rovina economica) | BASSA | Private-Only Container + Soglie di spesa. |

### 5.2 Soluzioni Implementative (Costo vs Beneficio)

#### A. Protezione Credenziali (Prevenzione SEC-01)
- **Soluzione:** `git-secrets` / Pre-commit hooks locali + `.gitignore` rigoroso.
- **Costo Monetario:** €0.
- **Complessità:** Bassa (Setup di 5 minuti).
- **Efficacia:** Altissima.
- **Decisione:** **MANDATORIA.** Nessuna chiave master sarà usata; solo Token SAS con scadenza (es. 90 giorni) e scope limitato (Solo Lettura/Scrittura, no Cancellazione per l'Agente).

#### B. Protezione Dati (Prevenzione SEC-02)
- **Soluzione:** Abilitare "Soft Delete" (Ritenzione 7 giorni) sui container Azure Blob.
- **Costo Monetario:** Irrisorio (si paga solo lo storage dei dati cancellati temporaneamente per 7 giorni, < €0.10/mese).
- **Complessità:** Bassa (Un flag nella console Azure).
- **Efficacia:** Altissima contro errori umani.
- **Decisione:** **MANDATORIA.** Protegge l'investimento di ore di rendering senza impattare il workflow DVC. In aggiunta, il container **BRONZE** (dataset raw) è configurato con **Immutability Policy** time-based (WORM), coerentemente con la matrice di rischio SEC-02.

#### C. Protezione Finanziaria (Prevenzione SEC-04)
- **Soluzione:** Azure Cost Alerts + Blocco automatico. Accesso al container strettamente `Private` (no Anonymous Read).
- **Costo Monetario:** €0.
- **Complessità:** Media (richiede configurazione IAM/Billing).
- **Efficacia:** Vitale per la sopravvivenza del progetto.
- **Decisione:** **MANDATORIA.** Il container deve rifiutare qualsiasi richiesta non firmata. Impostare alert al 50% e 90% del **credito Azure ($200)** — soglie a $100 e $180. *(Da non confondere col budget complessivo di progetto, €500.)*

#### D. Crittografia a Riposo (Data-at-Rest)
- **Soluzione:** Azure Storage Service Encryption (SSE) gestita da Microsoft.
- **Costo Monetario:** €0 (Incluso di default).
- **Complessità:** Nulla (Trasparente).
- **Efficacia:** Media (Protegge da furti fisici nei data center Microsoft, non protegge da credenziali rubate).
- **Decisione:** **ACCETTATA.** Non introduciamo crittografia custom (es. crittografare i file in locale prima di DVC) per evitare latenza ed errori di decrittazione, poiché il vero rischio è logico (SEC-01), non fisico.

## 6. DATA SOVEREIGNTY & BUSINESS CONTINUITY (THE "ESCAPE HATCH")
Il rischio sistemico maggiore è il lock-in o la perdita di accesso al provider Cloud (Azure). Per garantire al CEO l'accesso perenne e incondizionato al capitale intellettuale, si attua il seguente protocollo:

### 6.1 Dual Remote Routing (DVC)
DVC sarà configurato con **due** remote:
- **Primary (Azure):** Per le operazioni quotidiane (Push/Pull ad alta velocità).
- **Secondary (Cold Storage):** Un bucket ultra-economico (es. Cloudflare R2, Backblaze B2, o NAS Locale) dove eseguire un `dvc push -r cold_backup` settimanale. Se Azure crolla o chiude l'account, DVC può estrarre l'intero storico dal secondary.

### 6.2 L'Archivio "In Chiaro" (Anti-DVC Lock-in)
DVC ofusca la struttura dei file nel remote rinominandoli con hash MD5. Per scongiurare la dipendenza software da DVC per i dataset critici:
- Le versioni **GOLD (Finali)** dei tensori saranno compresse in standard aperti (`.tar.zst`) e caricate in chiaro (senza hashing DVC) su storage personali (es. Google Drive aziendale o NAS).
- Questo garantisce che il dato sia recuperabile con un semplice download manuale e il comando universale `tar`, anche se il progetto DVC si corrompesse irreparabilmente.

## 7. ALLOCAZIONE BUDGET STRATEGICO (€500)

> **Mandate (Decision Lock 2026-05-20):** Azure copre **tutto il compute** del progetto — generazione dataset (rendering, augmentation, Demucs) e training neurale. Obiettivo: completare l'intero ciclo data+training entro il credito di $200. La voce "GPU Cloud RunPod" è eliminata: era ridondante con Azure A100 Spot.

- **Cloud Infrastructure + Compute (Azure):** €0 cash — coperto dal credito Azure di $200 (rendering + augmentation + Demucs + training TCN). Vedere §7.1 per piano di spesa per task.
- **Storage Fisico (HDD 2 TB):** €120 (archivio permanente Gold tensor + recipes post-Azure).
- **Sviluppo & IP Protection:** €50 (domini, certificati).
- **Marketing & Launch:** €330.

<a id="azure-spend-plan"></a>
### 7.1 Piano di Spesa Azure ($200 Credit — Budget-Driven)

Il credito è l'unità di misura primaria. La strategia è massimizzare il valore estratto prima di esaurirlo, indipendentemente dal tempo impiegato.

#### Stimato per task (costi Azure indicativi)

| Task | Servizio Azure | Stima ore compute | Costo stimato |
| :--- | :--- | :--- | :--- |
| **Storage Gold 1.5 TB (Blob LRS)** | Blob Storage | — | ~$27/mese |
| **Rendering Sfizz/DrumGizmo** (450h audio, CPU parallelizzato) | Standard_D8s_v3 (~$0.38/h) | ~5–10h wall-clock | ~$4–8 |
| **Augmentation Python** (pedalboard, mixing, MIDI jitter) | Standard_D8s_v3 | ~10–20h | ~$4–8 |
| **Demucs AI-Isolation** (scenario AI-Isolates, 150h audio su T4) | Standard_NC4as_T4_v3 Spot (~$0.56/h) | ~17h | ~$10–15 |
| **Training Gold (TCN finale su A100)** | Standard_NC24ads_A100_v4 Spot (~$3.67/h) | ~15–25h | ~$55–92 |
| **Re-run training + sperimentazione** | A100 Spot | ~10h margine | ~$37 |
| **Misc (rete, log, MLflow)** | — | — | ~$5 |
| **TOTALE STIMATO** | | | **~$115–175** |

Il margine residuo (~$25–85) copre re-run imprevisti o iterazioni architetturali.

#### Priorità di utilizzo del credito

1. **Prima priorità — Data Sprint:** rendering + augmentation + Demucs. I Gold tensor sono il capitale irreplaceable. Fino a che il credito non è esaurito si genera dataset.
2. **Seconda priorità — Training:** una o più run complete sul dataset Gold. Ciclo prototipazione locale (Mac M5/MPS) → run finale A100 Azure.
3. **Terza priorità — Sperimentazione:** re-training su sotto-set, ablation study, tuning degli iperparametri.

#### Soglie di allerta credito (CEO le monitora)

- **$100 residui:** segnalazione al team → valutazione se interrompere storage e spostare i Gold tensor su HDD.
- **$40 residui:** STOP nuovo compute. Eseguire `dvc push -r cold_backup` (Gold + recipes su HDD). Azure usato solo per storage residuo se ancora conveniente.
- **$10 residui:** chiudere tutto su Azure. Archivio offline su HDD diventa unico master.

### 7.2 Storage Post-Azure (HDD Fisico — Archivio Permanente)

Quando il credito Azure si esaurisce, i Gold tensor (~1.5 TB) e le recipes (codice + DNA-Trace JSON, ~pochi GB) vengono trasferiti su un **HDD esterno da 2 TB (€100–150)**. Il modello di archivio:

| Dato | Dimensione | Archivio HDD? | Motivo |
| :--- | :--- | :--- | :--- |
| Gold tensors (.npy FP16) | ~1.5 TB | **Sì — irreplaceable** | Compute non riproducibile a zero costo |
| Recipes (codice + DNA-Trace) | ~1–2 GB | **Sì** | Necessario per rigenerare Silver da Bronze |
| Silver layer (WAV renderizzati) | ~variabile | **No** | Rigenerabile da Bronze + recipes |
| Bronze layer (raw stems) | ~50–100 GB | **No** | Re-scaricabile (dataset pubblici) |

*(Nota di audit 2026-05-20: la stima precedente "~7 mesi" era basata sul burn rate mensile $27/mo, non sulla durata reale del credito. Quella stima è stata ritirata. La pianificazione usa esclusivamente il budget totale disponibile.)*

---
*Approvato: CEO & Strategic Advisor*
