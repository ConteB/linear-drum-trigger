# 🔐 ZERO-PII LOG POLICY (ANONYMOUS-TRACE)
**Versione:** 1.0
**Status:** MANDATORY / LEGAL LOCK

## 1. PRINCIPIO CARDINE
"Non proteggere ciò che non possiedi". Il sistema di diagnostica deve essere tecnicamente incapace di raccogliere, archiviare o trasmettere dati sensibili (PII), password o percorsi file reali dell'utente.

## 2. SPECIFICHE DI ANONIMIZZAZIONE
- **Hardware ID:** Nessun nome macchina. Viene utilizzato esclusivamente un hash SHA-256 dell'ID hardware per scopi statistici (es. identificare crash ricorrenti su specifiche architetture CPU).
- **Path Scrubbing:** Ogni percorso file rilevato nei log viene filtrato tramite Regex. Esempio: `/Users/nome_utente/Documents/` diventa sempre `<USER_HOME>/`.
- **Enum Logging:** Il log interno utilizza esclusivamente ID numerici o Enums predefiniti (es. `OPX_ERR_302`). È proibito loggare stringhe di testo libero che potrebbero contenere dati inseriti dall'utente.

## 3. TRASMISSIONE E SOVRANITÀ
- **No Auto-Upload:** Il plugin non effettua connessioni in background. Il log del crash è salvato localmente in formato leggibile.
- **User-Initiated:** L'invio della diagnostica avviene solo su esplicito consenso e azione dell'utente (Modello "Pull").
- **Server-Side Purge:** Il server di ricezione Azure esegue uno script di pulizia finale prima di archiviare il report, scartando qualsiasi dato non conforme alla matrice tecnica.

## 4. CONFORMITÀ GDPR
**Ambito della policy.** Questa policy regola **esclusivamente la telemetria diagnostica / crash log**. Il trattamento dei dati di acquisto e licenza (nome, email — modello "Email-as-Identity") è un flusso **distinto**, governato dal provider e-commerce e descritto in `DOSSIER_TECNICO.md` §11.4: questa policy non lo copre né lo annulla.

**Sui crash log.** L'hash SHA-256 dell'hardware ID resta un dato **pseudonimizzato** (GDPR, Considerando 26): è *data minimization* spinta, non anonimizzazione assoluta. Formulazione corretta: il sistema diagnostico applica *data minimization by design*, riducendo drasticamente la superficie di data breach e gli oneri di conservazione — ma **non** si dichiara "fuori dal perimetro GDPR" in senso assoluto.

> ⚠️ Nota di audit 2026-05-20: la formulazione precedente — *"il sistema opera al di fuori del perimetro dei dati personali"* — era un overclaim legale ed è stata rettificata.

---
*Approvato dalla Linear Division / OpenPhase Governance.*
