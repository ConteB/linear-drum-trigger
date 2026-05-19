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

## 5. ALLOCAZIONE BUDGET STRATEGICO (€500)
- **Cloud Infrastructure (Azure):** €0 (Coperto da $200 di credito iniziale per i primi 10-12 mesi).
- **GPU Cloud (Emergency/Final):** €100.
- **Sviluppo & IP Protection:** €50 (Domini, certificati).
- **Marketing & Launch:** €350.

### 5.1 Nota sulla Sostenibilità
L'utilizzo dei crediti Azure permette di estendere la fase di R&D a costo monetario zero, preservando il capitale liquido per la fase di Go-To-Market.

---
*Approvato: CEO & Strategic Advisor*
