---
id: LIN-DT-RPTBP-001
title: Model Training Report Blueprint
type: spec
status: LOCKED
phase: F0
domain: AI / Reporting
version: 1.1.0
updated: 2026-05-24
tags: [reporting, training, ux, ai, blueprint]
related: [LIN-DT-DCBP-001, LIN-DT-ENGSTD-001, LIN-DT-MSCHED-001]
supersedes: []
---

# Model Training Report Blueprint

> **Status:** LOCKED — Decision Lock CEO 2026-05-23 (Executive Briefing STRP-001).
> **Mandato operativo:** *ogni* training run del progetto produce, a fine epoch
> ciclo, un **report HTML single-file** generato deterministicamente dal modulo
> `src/neural/reporter.py` secondo la spec di questo documento. Non è opzionale:
> il report è parte del DoD di ogni esperimento, non un extra.

## 0. Perché questo blueprint esiste

Il CEO è il consumatore primario dei numeri prodotti dai training. Tre vincoli
fissano la forma del report:

1. **Single-file.** Un solo file HTML, doppio-click → si apre in Safari/Chrome.
   Niente cartelle di PNG da sfogliare, niente notebook che richiedono Jupyter.
2. **Self-documenting.** Ogni report contiene una sezione canonica "Come leggere
   il report" con le definizioni di Precision / Recall / F-measure / Timing-MAE
   e le soglie di lettura. Il CEO non deve mai cercarle altrove.
3. **Auditabile come codice.** Plain-text (HTML + SVG inline), Lychee valida i
   link interni, git ne diffa il contenuto. Sostituisce zero workflow esistenti:
   estende la convenzione **Ocular Proof** (L2, L3) — è la sua forma
   automatizzata.

Risolve in un colpo solo: (a) un CEO che non vuole più aprire foto separate;
(b) il rischio di "report verbali" non riproducibili; (c) la necessità di
confrontare run multipli con criteri identici.

<a id="output-specification"></a>
## 1. Output specification

**Convenzione di nomenclatura:**

```
reports/<YYYY-MM-DD>-<run_id>/
└── report.html        ← single file, CSS + SVG inline, ~300-500 KB
```

`<run_id>` è una stringa stabile, scelta dal codice di training (es.
`f0t4b-tcn-c32-seed0`, `f2t3-a100-sweep-lr3e3`). Niente UUID, niente
timestamp puro (la data è nel parent dir).

**Requisiti tecnici dell'HTML:**

| Requisito | Specifica |
| :-- | :-- |
| Auto-contenuto | tutti gli asset (CSS, SVG, dati) **inlined** — nessun riferimento esterno |
| Grafici | **SVG inline** (non PNG base64) — testo scalabile, diff-leggibile |
| Tipografia | monospace per i numeri (`SF Mono`/`Menlo`), sans per la prosa (`-apple-system`/`SF Pro`) |
| Palette | `viridis` per heatmap, `tab10` per categorie, niente neon |
| Layout | portrait, page-by-page, mobile-friendly (no widget interattivi) |
| Determinismo | stessi dati di input → stesso HTML bit-by-bit (`ENGINEERING_STANDARDS §1`) |
| TOC | navigazione interna via `<nav>` con anchor `#section-N`, sempre in cima |
| Print-to-PDF | render coerente con `Cmd+P` del browser — il PDF è una funzione, non un secondo formato |

<a id="canonical-sections"></a>
## 2. Le 11 sezioni canoniche

L'ordine è **fisso**, così a colpo d'occhio sai dove guardare. Una sezione che
non si applica resta presente con un placeholder `n/a` motivato.

### § 0 — TL;DR

Tabella sintetica, leggibile in 5 secondi:

| Voce | Valore | Gate | Esito |
| :-- | :--: | :--: | :--: |
| F-measure onset (holdout, mean per-bus) | X.XXX | ≥ 0.80 | ✅/⚠️/❌ |
| F-measure shuffato (controllo) | X.XXX | < 0.10 | ✅/⚠️/❌ |
| Timing-MAE matched (ms) | X.XX | < 5.00 | ✅/⚠️/❌ |
| HiHat-opening MAE | X.XXX | < 0.150 | ✅/⚠️/❌ |
| Round-trip max\|Δ\| C++↔PyTorch | X.XXe-NN | < 1e-5 | ✅/⚠️/❌ |
| **Verdetto complessivo** |   |   | ✅/⚠️/❌ |

Le soglie sono **gate-specifiche** (definite in F0-T4a §7 per L3, in
`MASTER_CHECKLIST §6` per L4). Il template le riceve come parametri — non sono
hard-coded nel reporter.

### § 1 — Cosa stiamo guardando

- Dataset: `<nome>` versione `<v>`, n_train / n_holdout, ore totali di audio.
- Modello: topologia (riferimento a `F0-T4a` o equivalente), n parametri.
- Hardware: `device` (MPS / A100 / CPU), wall-clock training time.
- Run ID, commit git, data di esecuzione.

### § 2 — Curve di training

Line plot: loss totale + per-head loss vs epoch. Asse X = epoch, Y = loss
(scala lineare; log opzionale se `loss_max / loss_min > 100`).

### § 3 — Metriche di onset

- **Tabella per-bus**: `bus_name`, `n_true`, `n_pred`, `n_matched`, `precision`,
  `recall`, `f_measure`, `threshold_used`. Una riga per bus, sortata per
  `bus_id`. Numeri in monospace.
- **Bar chart per-bus**: F-measure con linea orizzontale tratteggiata alla
  soglia gate (es. 0.80 per L3, ridefinita per L4). Bus con `n_true == 0`
  marcati con `n/a` esplicito, non con `0` (la metrica è indefinita, non
  zero).

Doppia versione: una per il **train set**, una per l'**holdout**. Il gap
train→holdout è la diagnosi del generalization.

### § 4 — Metriche regressive

- **Istogramma Timing-MAE** dei drift `(pred − vero)` in ms per ogni onset
  matchato. Bin width = `frame_period_ms` (≈ 2.9 ms a 344.53 Hz). Linea
  verticale a 0 (ideal) e shading entro ±20 ms (match window).
- **HiHat-opening MAE** + chart scatter pred-vs-vero (con linea y=x come
  reference).
- **R²** delle teste continue (velocity, microtiming, hihat) quando ground
  truth disponibile.

### § 5 — Confusion matrix per-bus

Griglia 4×2 o 2×4 di mini-heatmap [TP FP; FN TN] per ciascun bus.
Annotazione numerica al centro di ogni cella. Colormap `viridis`.

### § 6 — Controllo negativo (F-shuffle)

Bar chart: F-measure mean per-bus reale vs F-measure su label shuffate
nell'asse temporale. Gap visivo = prova qualitativa che la rete *non* è
random. Soglia gate (`< 0.10`) come linea orizzontale.

### § 7 — Esempi qualitativi

**1..N sample** dal holdout (amendment v1.1, 2026-05-24 — direttiva CEO: per
diagnosi clinica del modello su pattern multipli, non solo 1-2 cherry-picked).
Per ognuno:

- Piano-roll con **ground-truth** (cerchi verdi) **+ predetto** (croci rosse)
  sovrapposti, 8 bus × T frame.
- Caption con `f_mean`, `timing_mae_ms` per quick-scan.
- Asse X in secondi (più leggibile di "frame").

**Numero di sample:** `1..N`, configurato dal driver del report:

- **Auto-emit da `train.py` (default):** `len(holdout_keys)` — tipicamente 2.
- **Regression test / Tier-1 sweep:** `len(samples_under_test)` — tipicamente 6–18.
- **Tier-2 / Ocular Proof (L3, L4):** **tutti i sample del holdout reale**
  (E-GMD / Slakh-Mix), per non lasciare angoli del dataset non ispezionati.

Implementazione: `build_default_context()` itera su ogni elemento di
`holdout_evals` (`for e in holdout_evals: charts["piano_roll_samples"].append(...)`)
— il template emette automaticamente N caption + N piano-roll, in ordine di
input. Nessun cap hard-coded.

**Linee guida visuali (>10 sample):** quando N supera ~10, il render diventa
verticalmente lungo. Resta accettabile (page-by-page scroll in browser), ma
i Tier-2 con dataset grandi dovrebbero produrre un report "campione" con i
12 peggiori + 12 migliori, mai un singolo HTML con migliaia di piano-roll.

### § 8 — Iperparametri usati

Tabella key-value: tutti i campi della config (channels, encoder strides,
trunk dilations, lr, batch_size, epochs, seed, loss weights, pos_weight,
focal_gamma, threshold di peak-pick). Una riga per voce. Crittografabile via
git hash del commit per audit di compliance.

<a id="how-to-read-canonical"></a>
### § 9 — Come leggere il report (SEZIONE CANONICA)

> Questa sezione appare **identica** in ogni report. Il testo sorgente vive in
> [`templates/_how_to_read.html.j2`](../templates/_how_to_read.html.j2) — *single
> source of truth*. Per aggiornare il testo (es. nuove soglie, nuove metriche),
> edita quel file: tutti i report futuri si aggiornano automaticamente.

Cosa deve contenere:

1. **Definizione di TP / FP / FN / TN** in 4 frasi con esempio di batteria.
2. **Precision / Recall / F-measure** con formule e interpretazione.
3. **F-shuffle** — il controllo negativo, perché esiste.
4. **MAE / RMSE / R²** — metriche per teste continue.
5. **PR-AUC** — perché preferita a ROC-AUC su classi sbilanciate.
6. **Soglie L3 / L4** — i valori target di gate e dove sono definiti.
7. **Trappole** — accuracy ingannevole su classi sbilanciate, F=0 per bus
   senza ground-truth, importanza della match window ±20 ms.

Tono: spiegabile a un CEO con esperienza ML *rusty*. Italiano. Senza
condiscendenza.

### § 10 — Verdetto vs gate (TIER-2 ONLY)

Presente **solo** quando il run è gate-relevant (L3, L4). Contiene:

- Checklist di gate firmabile.
- Blocco "Decisione del CEO" con campo firma + data.
- Tabella di stato finale (PASS / FAIL per ciascun criterio).

Per i run Tier-1 (sweep, esperimenti) questa sezione è **omessa**.

## 3. Tier 1 / Tier 2 — promozione a Ocular Proof

| Tier | Frontmatter `status` | Quando | § 10 presente? | Firma CEO |
| :--: | :-- | :-- | :--: | :--: |
| **1** | `AUTO-GENERATED` | ogni training (no exceptions) | ❌ | — |
| **2** | `APPROVED` o `PENDING_CEO_DECISION` | run gate-relevant (L3, L4) | ✅ | richiesta |

Promozione: lo stesso HTML viene rigenerato con `tier=2` settato nel
`ReportContext`. Il template aggiunge automaticamente § 10. Tool
`tools/promote_to_ocular_proof.py` automatizza la transizione.

I **L2 / L3 Ocular Proof** esistenti (Markdown signabile) restano come sono —
sono record storici. Il nuovo standard inizia da L4.

## 4. Determinismo e riproducibilità

Il reporter rispetta `ENGINEERING_STANDARDS §1` (stessa input → stesso output):

- **matplotlib**: `mpl.rcParams['svg.hashsalt']` settato a costante fissa;
  backend `Agg` obbligatorio.
- **Jinja2**: ordine delle chiavi di dict normalizzato (sorted), float
  formattati a precisione fissa.
- **Embedding**: gli SVG sono normalizzati (no timestamp inline, no UUID
  random per i clip path).
- **Test**: il pacchetto `tests/unit/test_reporter_determinism.py` (F0-T9b
  scope) verifica che due chiamate consecutive sullo stesso input producano
  HTML identici byte-by-byte.

## 5. Estensione del blueprint — come aggiungere

Una nuova sezione o un nuovo chart **deve** passare per questo documento (è
parte della doctrine, non un'opzione del momento):

1. Edit di `04_INTELLIGENCE/MODEL_REPORT_BLUEPRINT.md`: aggiungi la sezione
   nella spec, incrementa `version` (semver).
2. Edit di `templates/training_report.html.j2`: aggiungi il blocco.
3. Edit di `src/neural/reporter.py`: aggiungi il chart factory method o il
   data field nel `ReportContext`.
4. Aggiorna `_how_to_read.html.j2` con la definizione della nuova metrica.
5. Test di non-regressione (snapshot del HTML su un fixture noto).

Niente "chart ad-hoc per un esperimento". Tutto canonico, tutto riusabile.

## 6. Mappatura ai gate del progetto

| Gate | Report di riferimento | Tier | Note |
| :-- | :-- | :--: | :-- |
| **L1** (Ocular L1) | nessuno | — | gate documentale, non training-based |
| **L2** | `docs/gates/L2_OCULAR_PROOF/L2_INSPECTION_*.md` | 2 (legacy) | Markdown manuale; non rigenerato |
| **L3** | `docs/gates/L3_OCULAR_PROOF/L3_INSPECTION_2026-05-23.md` | 2 (legacy) | + retroactive `reports/2026-05-23-f0t4b-tcn-c32/report.html` per proof-of-life del blueprint |
| **L4** | `docs/gates/L4_OCULAR_PROOF/<date>/report.html` | 2 (nativo) | primo gate generato direttamente in questo formato |

---

*Decision Lock 2026-05-23. Aggiornamenti = versione + bump semver. Il file
[`templates/_how_to_read.html.j2`](../templates/_how_to_read.html.j2) è la
single source of truth della sezione § 9.*
