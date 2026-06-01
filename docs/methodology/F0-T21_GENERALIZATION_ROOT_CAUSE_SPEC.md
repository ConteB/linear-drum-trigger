---
title: "F0-T21 · Generalization Root-Cause — why the model fits but doesn't generalize (STRP-001)"
tags: [F0-T21, STRP-001, generalization, architecture, loss, mel, azure-gate]
status: DRAFT
---

# F0-T21 · Generalization Root-Cause (STRP-001)

**Origine:** la diagnostica F0-T20b/c/d (sfida CEO «0.16 è random») ha provato, *con
esperimenti*, che il mini-L3 non rompe il floor con NESSUNA leva, e — decisivo — il test
**scala-a-convergenza** (F0-T20d): a 400 epoche (loss 0.48/0.59 = fittato) **val F resta
~0.08** e **4× dati non aiutano**. Quindi il collo NON è quantità-dati: è
**generalizzazione**. Il modello fitta il train ma non generalizza ai grooves held-out
*dello stesso kit*, ed è **sotto-confident** (precision ~7%, F sale solo tunando la
soglia). STRP-001 per trovare la causa-radice prima di spendere $200 su Azure.

> **Stato:** STRP-001 IN REVIEW. Fasi 1-5 compilate; implementazione post-Decision-Lock.
> **Nessun codice prima dell'approvazione.**

## Fase 1 — Competitor & Market Analysis (la ricetta ADT che generalizza)

Dalla letteratura ADT recente (Vogl CRNN, Wei/Tatum-level CRNN 2020, ADTOF, StemGMD/
LarsNet, diffusion-based 2024/2025):
- **Input = spettrogramma log-mel del MIX** (mono/stereo), spesso **multi-risoluzione**
  (3 canali, finestre 23/46/92 ms, 128 bande mel, **hop 10 ms ⇒ ~100 Hz**). *Non* raw
  audio, *non* 8 microfoni separati.
- **Architettura = CNN** (pattern spettro-temporali locali) **+ GRU bidirezionale**
  (CRNN, dipendenze ritmiche a lungo raggio).
- **Loss = (weighted) BCE** sulle attivazioni di onset, pesi *moderati*.
- **Output ~100 Hz**, poi peak-picking.
- **Generalizzazione** via kit-swap augmentation (≈ il nostro franken) + **scala**.

## Fase 2 — Open-Source Codebase Analysis
`madmom`, `ADTLib`, `omnizart`, `polimi-ispl/larsnet`, ADTOF: tutti **log-mel + CNN/CRNN
+ BCE + ~100 Hz**. Pattern stabilissimo e ripetuto. Nessuno usa raw-audio-encoder a
344 Hz con 8 mic e focal-loss pos_weight 1000.

## Le DIVERGENZE del nostro setup (i sospetti, in ordine di leva)

| # | Asse | ADT-che-funziona | Nostro | Perché può rompere la generalizzazione |
| :- | :- | :- | :- | :- |
| S1 | **Frame rate** | ~100 Hz (hop 10 ms) | **344 Hz** (hop 2.9 ms) | densità onset 4× più bassa per-frame ⇒ **pos_weight estremo (50-1000)** ⇒ la rete impara a predire diffusa/sotto-confident (precision 7%). **Sospetto primario.** |
| S2 | **Loss** | weighted-BCE moderata | AFL focal + pos_weight cap 1000 | conseguenza di S1; la pressione asimmetrica enorme produce calibrazione rotta |
| S3 | **Input** | log-mel multi-res del **mix** | 8-mic raw + strided conv (mel base ko) | feature di onset non date "gratis"; imparare da raw richiede molti più dati |
| S4 | **Architettura** | CNN + **GRU bidirez.** | TCN **causale** | il bidirezionale (vietato dal vincolo real-time) cattura contesto ritmico che la TCN causale fatica a estrarre |

**Tensione di prodotto:** S4 (bidir GRU) è **incompatibile** col real-time/streaming
(PDC). Ma una **GRU unidirezionale causale** È streamabile (RTNeural la supporta) → un
"CRNN causale" è ammesso. E 344 Hz (S1) è stato scelto per la precisione di microtiming
del trigger — coarsening è un trade-off da pesare.

## Fase 3 — UX/UI Impact
Nessun impatto UI. S1 (frame rate) tocca la **risoluzione di microtiming** del trigger
(344 Hz = ±1.45 ms vs 100 Hz = ±5 ms) — rilevante per il claim "timing al ms". Mitigabile
con una testa di microtiming sub-frame (già presente) anche a 100 Hz.

## Fase 4 — Tech Implementation Matrix (candidati, leva × compatibilità-prodotto)

| Candidato | Leva attesa | Real-time? | Costo | Note |
| :- | :- | :- | :- | :- |
| **A. Frame rate 344→~100 Hz + pos_weight moderato (BCE)** | **ALTA** (attacca S1+S2 alla radice) | ✅ | medio (cambia stride encoder + target rate + loss) | la microtiming-head recupera la precisione persa |
| **B. Front-end log-mel multi-res (mix o per-canale)** | MEDIA-ALTA (S3) | ✅ (STFT streamabile) | medio | mel base testato ko, ma non multi-res né a 100 Hz |
| **C. CRNN causale (GRU unidirezionale dopo la TCN)** | MEDIA (S4, parziale) | ✅ (GRU causale, RTNeural ok) | medio | recupera contesto ritmico senza rompere lo streaming |
| D. Solo scala (Azure) | ignota | ✅ | **$$** | il test convergenza dice che la scala-locale non aiuta → rischioso |

Tutto Python/locale, $0 fino a Azure. RTNeural compatibile per A/B/C (no bidir).

## Fase 5 — Executive Briefing (per Decision Lock CEO)

**Diagnosi:** il modello non generalizza perché è **sotto-confident/diffuso**, e la
causa-radice più probabile è **S1: il frame rate 344 Hz forza una densità onset
minuscola → pos_weight estremo → loss patologica** (S2). Il nostro setup diverge dalla
ricetta ADT provata su 4 assi insieme; abbiamo scelto ciascuno per buone ragioni
(8-mic, microtiming, streaming) ma **collettivamente** ci mettono in un regime che non
impara.

**Raccomandazione:** prima di Azure, **un esperimento di allineamento alla ricetta
provata**, sull'asse di leva più alta e $0:
- **D1 — Candidato A (frame rate ~100 Hz + weighted-BCE moderata)** come primo test:
  attacca S1+S2 (il sospetto primario). Se la val F (in-distribution, convergenza)
  sale nettamente sopra 0.08 → trovata la radice → poi Azure con la ricetta giusta.
- **D2 —** se A non basta, **B (log-mel multi-res)** poi **C (CRNN causale)**.
- **D3 —** Azure **gated** finché un cambio non dimostra val F in-distribution ≫ 0.08
  a convergenza (il segnale che il modello *generalizza*).

**Costo:** $0 locale per A/B/C; Azure solo dopo che uno dimostra generalizzazione.

## Fase 6 — Docs Update (post-approvazione)
*Pending Decision Lock.* All'approvazione: amendment `F0-T4a` (frame rate / stride /
loss se A ratificato), `DOSSIER §6`, `MASTER_SCHEDULING` (task F0-T21 + gate Azure).
Implementazione = sotto-task `[F]`.

---
*STRP-001 — F0-T21. Fasi 1-5 compilate 2026-06-01 (fondate su ricerca ADT). Attende
Executive Briefing / Decision Lock CEO prima di scrivere codice.*
