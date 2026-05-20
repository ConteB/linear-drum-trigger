# 🛡️ PROTOCOLLO LINEAR-SHIELD: GOVERNANCE SUB-AGENTI
**Versione:** 1.0 (OP-X Standard)
**Status:** MANDATORIO / ACTIVE LOCK

## 1. FILOSOFIA OPERATIVA
Nessun sub-agente (DSP, UI, Test) può operare nel repository `drum-trigger-fresh` senza aver superato l'inizializzazione del DNA Linear. L'obiettivo è garantire il "Senior Rigor" ed evitare l'inquinamento dell'architettura Zero-Allocation.

## 2. PROCEDURA DI ATTIVAZIONE (INNESCO)
Ogni volta che viene invocato un sub-agente, la prima istruzione deve essere:
1. **DNA Ingestion:** Lettura dei `Linear_DSP_Mandates.md`.
2. **Context Alignment:** Lettura del `DOSSIER_TECNICO.md` e della `MASTER_CHECKLIST.md`.
3. **Role Lock:** Accettazione formale dei divieti (es. No `malloc`, No `new`, No `printf` nel thread audio).

## 3. THE "SANDBOX & GATE" WORKFLOW
Il lavoro dei sub-agenti segue questo percorso obbligato:
- **STAGE 1 (Staging):** Il codice viene scritto in una directory isolata o presentato come proposta nel chat log.
- **STAGE 2 (Audit):** Esecuzione del gate di rigore DSP — scansione delle violazioni ai mandati della §4. *Stato: lo script `audit_dsp_rigor.py` è una specifica **pianificata, non ancora implementata** (pre-produzione). Fino alla sua disponibilità il gate è eseguito tramite scansione manuale `grep` dei pattern proibiti.*
- **STAGE 3 (Validation):** Revisione di Gianpiero (Lead AI) per coerenza architettonica.
- **STAGE 4 (Integration):** Solo dopo l'approvazione, il codice viene spostato in `src/`.

## 4. MATRICE DEI DIVIETI (DSP CORE)
| Elemento | Status | Alternativa Approvata |
| :--- | :--- | :--- |
| `std::vector` | PROIBITO | `juce::Array` (pre-allocated) / Fixed buffers |
| `std::mutex` | PROIBITO | Lock-free structures / `juce::SpinLock` (con cautela) |
| `new` / `delete` | PROIBITO | Object Pools / Stack allocation |
| `printf` / `std::cout` | PROIBITO | `juce::Logger` (non-realtime) |

## 5. ESCALATION PROTOCOL
Se un sub-agente non riesce a risolvere un task senza violare i mandati, deve fermarsi e richiedere un'analisi strategica a Gianpiero invece di procedere con "hack" temporanei.

---
*Documento approvato dal CEO e blindato nel sistema di Intelligence.*
