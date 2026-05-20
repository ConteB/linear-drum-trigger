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
- **Cloud Infrastructure (Azure):** €0 cash — coperto dal credito Azure di $200. Allo storage stimato (~$27/mo per 1.5 TB Blob LRS) il credito copre **~7 mesi** di R&D. Oltre i 7 mesi: burn rate cash atteso **<€15/mo**.
- **GPU Cloud (Final Training):** €100 allocati; spesa attesa **€25–40** per la "cottura" del dataset Gold (RunPod A100, ~15–25h). Il margine prudenziale copre eventuali re-run.
- **Sviluppo & IP Protection:** €50 (Domini, certificati).
- **Marketing & Launch:** €350.

### 7.1 Nota sulla Sostenibilità
L'utilizzo dei crediti Azure permette di estendere la fase di R&D a costo monetario quasi zero per ~7 mesi, preservando il capitale liquido per la fase di Go-To-Market. *(Nota di audit 2026-05-20: la stima "10-12 mesi" precedente era errata — $200 / ~$27/mo ≈ 7,4 mesi.)*

---
*Approvato: CEO & Strategic Advisor*
