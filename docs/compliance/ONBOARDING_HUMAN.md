---
id: LIN-DT-ONBOARD-001
title: Manuale di Sopravvivenza & Data Recovery (Human-Only)
type: reference
status: ACTIVE
phase: cross-cutting
domain: Operations
version: 1.0.0
updated: 2026-05-20
tags: [onboarding, recovery, operations]
related: [LIN-DT-MSCHED-001]
supersedes: []
---

# 🆘 MANUALE DI SOPRAVVIVENZA & DATA RECOVERY (HUMAN-ONLY)
**Livello di Accesso:** CEO / Executive
**Scopo:** Garantire l'accesso totale ai dati (Data Sovereignty) e la riattivazione della pipeline in caso di assenza, malfunzionamento o sostituzione degli agenti AI (o perdita dell'hardware fisico locale).

---

## SCENARIO: "IL MAC È ESPLOSO E L'IA È OFFLINE"
Questa guida spiega come ricollegare il codice sorgente (su GitHub) all'enorme massa di dati di addestramento (su Azure) partendo da un computer vergine.

### FASE 1: Recupero del "Cervello" (Il Codice)
1. Installa `git` e `python` sul nuovo computer.
2. Clona il repository da GitHub:
   ```bash
   git clone <URL_DEL_REPOSITORY_GITHUB>
   cd drum-trigger-fresh
   ```
3. Installa le dipendenze Python e DVC:
   ```bash
   python -m venv venv
   source venv/bin/activate  # (Oppure venv\Scripts\activate su Windows)
   pip install -r requirements.txt
   pip install dvc dvc-azure
   ```

### FASE 2: Creazione delle "Chiavi di Casa" (Azure)
DVC non sa come entrare in Azure. Devi fornirgli una chiave temporanea (SAS Token).
1. Apri il browser e vai su `portal.azure.com` (Usa l'account Microsoft dell'azienda).
2. Vai su **Storage accounts** -> Clicca sull'account di storage del progetto (es. `neurotriggerdatalake`).
3. Nel menu a sinistra, cerca la sezione **Security + networking** e clicca su **Shared access signature (SAS)**.
4. Spunta tutte le voci (Read, Write, Delete, List, Add, Create) e imposta una data di scadenza (es. tra 1 anno).
5. Clicca su **Generate SAS and connection string**.
6. Copia l'intera stringa lunghissima sotto la voce **Connection string**. Questo è il tuo Token Segreto.

### FASE 3: Saldatura del "Ponte" Dati (DVC a Azure)
Ora devi incollare quella stringa in modo che rimanga **solo sul tuo computer locale** e non vada mai su Internet.

1. Apri il terminale, assicurati di essere nella cartella `drum-trigger-fresh`.
2. Esegui questo comando, sostituendo `<LA_TUA_STRINGA_COPIATA>` (comprese le virgolette) con la stringa di Azure:
   ```bash
   dvc remote modify azure_remote --local connection_string "<LA_TUA_STRINGA_COPIATA>"
   ```
   *(Nota: l'opzione `--local` è il salvavita. Dice a DVC di salvare il segreto nel file `.dvc/config.local`, che Git è istruito a ignorare).*

### FASE 4: Il Recupero del "Corpo" (I Dati)
Ora che il ponte è collegato, puoi riavere i Terabyte di audio e tensori.
1. Esegui il comando di download totale:
   ```bash
   dvc pull
   ```
DVC leggerà tutti i piccoli file "pointer" dentro le cartelle e scaricherà magicamente l'esatta versione dei dataset necessaria per far girare il codice.

---

## 🔒 LA "BOTOLA DI EMERGENZA" (ANTI-AZURE / ANTI-DVC)
Se Azure chiude il tuo account, o se DVC smette di esistere come software, i dati originali (Raw) e finali (Gold) sono salvati **IN CHIARO**.

1. Cerca il tuo backup secondario (es. Google Drive Aziendale, NAS dell'ufficio, o Hard Disk fisico).
2. Troverai dei file compressi chiamati `neurotrigger_gold_dataset_v1.tar.zst` (o simili).
3. Non ti serve DVC. Non ti serve Azure. Ti basta un programma di decompressione (come Keka, 7-Zip o il comando `tar` da terminale) per estrarre direttamente i tensori `.npy` pronti per l'addestramento.

**Regola d'oro:** L'Intelligenza Artificiale non possiede i dati. Tu possiedi i dati. Questa guida ne è la garanzia crittografica.