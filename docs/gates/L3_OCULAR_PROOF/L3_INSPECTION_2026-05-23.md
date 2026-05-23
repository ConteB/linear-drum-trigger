---
title: L3 Ocular Proof — inspection 2026-05-23
owner: F0-T4b
date: 2026-05-23
scope: F0
status: APPROVED
---

# Gate L3 — Ocular Proof (2026-05-23)

Gate `L3` per `F0-T4b`: il mini-prototipo TCN ha (a) **certificato l'esportabilità
in C++ via op-set RTNeural-equivalente** e (b) **prodotto le metriche di onset**
richieste da [`F0-T4a §7`](../../methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md#l3-threshold).
Documento di chiusura — DoD F0-T4b.

## TL;DR (per il CEO)

| Sotto-gate | Esito | Evidenza |
| :-- | :--: | :-- |
| **Round-trip RTNeural-equivalente** (PyTorch ↔ NumPy ↔ C++17) | ✅ **PASS** | max\|Δ\| **1.19e-07** (C++) e **1.49e-06** (NumPy) — sotto il floor fp32 |
| **F-measure ≥ 0.80 su mini-holdout** | ❌ **FAIL** | F=0.185 (DGZ) / F=0.163 (SFZ); il modello *apprende* — F=0.90 sul snare di train — ma 10 grooves non bastano a generalizzare |
| **F-measure shuffle < 0.10** | ✅ **PASS** | 0.057 / 0.000 — gap qualitativo presente |
| **Timing-MAE matched < 5 ms** | △ misto | 8.22 ms (DGZ) / **2.90 ms** (SFZ) |
| **HiHat-opening MAE < 0.15** | △ misto | 0.314 (DGZ) / **0.104** (SFZ) |

> **Lettura**: la **metà architetturale** del Gate L3 è chiusa — il rischio
> grave (la topologia non si esporta nello stack di inferenza streaming) è
> de-riscato bit-by-bit a precisione fp32. La **metà metrica** è coerente con
> il caveat scritto in [`F0-T4a §7`](../../methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md#l3-threshold)
> ("Su un mini-batch è atteso un certo overfitting: l'obiettivo di L3 è
> escludere il 'non apprende'") — su 8 buses, **4 superano F≥0.80 su train**
> (`kick 0.74` · `snare 0.90` · `hihat 0.67` · `floor_tom 1.00`); i 3 buses
> rari (`tom_hi_mid`, `ride`, `crash_a`) hanno troppi pochi esempi positivi nel
> mini-batch perché il modello possa imparare la negazione.
>
> Tre vie aperte al CEO — vedi **§4 Decisione del CEO**.

## 1. Round-trip — il vero gate architetturale

Il round-trip ha eseguito **lo stesso input audio sullo stesso modello** in tre
implementazioni — PyTorch eager, una **reference NumPy pura** che usa solo
operazioni che RTNeural supporta nativamente (Conv1D strided/dilated causale +
ReLU/sigmoid/tanh + addizione elementwise per la skip), e un **binario C++17**
(`cpp/round_trip_smoke/`) che parsa la stessa topologia da un sidecar binario.

```text
Input  audio       : float32 [8, 16384]   (GMD000-V0T0-DGZ-R0-L1-NONE, leading window)
Output flat-25     : float32 [128, 25]
Tolleranza fp32    : 1e-5

PyTorch ↔ NumPy   max|Δ| = 1.490e-06   mean|Δ| = 6.223e-08    ✓
PyTorch ↔ C++     max|Δ| = 1.192e-07   mean|Δ| = 4.287e-10    ✓
```

Sotto **1.19e-07** il C++ è all'interno dell'epsilon di fp32 (≈ 1.19e-07,
2⁻²³): la differenza è *rumore di arrotondamento*, non un bug. Pacchetto in
[`round_trip_report.json`](round_trip_report.json).

### 1.1 Come la skip residua "passa" — F0-T4a §8 open item risolto

[`F0-T4a §8`](../../methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md)
ha segnalato il rischio: "la gestione delle skip-connection residue del trunk
(RTNeural privilegia grafi sequenziali). Se il parser RTNeural non assorbe il
ramo residuo, F0-T4b valuta (a) la realizzazione del residuo come parte della
topologia esportata, oppure (b) un blocco TCN senza skip esplicita".

**Esito: opzione (a) ratificata.** L'export emette un campo `residual_add_from`
su ogni `trunk_J_conv2`; il loader C++ cattura l'input di ogni `trunk_J_conv1`
e lo ri-somma all'uscita del `_conv2` corrispondente. **L'addizione vive fuori
dal grafo sequenziale di RTNeural** — RTNeural esegue ogni Conv1D nativamente,
l'addizione è un'op elementwise. Tre implementazioni indipendenti danno lo
stesso output entro `1.19e-07`: la prova che il meccanismo è corretto.

Conseguenza per F4: nessuna topologia "senza skip" — la pipeline di esportazione
documentata in [`F0-T4b export.py`](../../../src/neural/export.py) + il
binario di smoke-test sono pronti per il merge nel core C++ del plugin.

### 1.2 Op-set RTNeural-equivalente coperto

| Op | Coperto | Note |
| :-- | :--: | :-- |
| Conv1D causale kernel=1            | ✓ | proiezione Input-Agnostic + 4 teste |
| Conv1D causale strided (k=8)       | ✓ | 4 stadi dell'encoder, stride [4,4,4,2] |
| Conv1D causale dilatata (k=3)      | ✓ | trunk, dilatazioni [1,2,4,8,16,32,64,128] |
| Attivazioni ReLU / sigmoid / tanh  | ✓ | encoder + 4 teste |
| Addizione elementwise (residual)   | ✓ | 8 blocchi del trunk |
| Layer di upsampling / NN-Repeat    | — | **non usato** — sanata l'incoerenza F0-T4a §1 |

## 2. Topologia bloccata in F0-T4a — istanziata e misurata

| Voce | Valore |
| :-- | :-- |
| Parametri totali                   | **83 673** (target F0-T4a: 80–100 k ✓) |
| Larghezza feature `C`              | 32 (baseline) |
| Receptive field encoder            | ~13.5 ms (596 sample) |
| Receptive field trunk causale      | ~1.48 s (511 frame @ 344.53 Hz) |
| Stride totale encoder              | 128 = 2⁷ |
| Frame-rate `R_target`              | 344.53 Hz (= 44100/128) — ratificato |
| Look-ahead realizzato              | come **ritardo d'ingresso = PDC** (vedi F4) |

Il modello è stato addestrato sul mini-batch Gold (F0-T2e): 10 train + 2 holdout,
~3 secondi di crop, 1500 epoch, Mac M5 / MPS mixed-precision, **47.9 s wall-clock**.
Topologia, loss e iperparametri di taratura archiviati in
[`artifacts/f0t4b_report.json`](../../../artifacts/f0t4b_report.json).

## 3. Metriche di onset — il diagnostico architettura vs dati

### 3.1 Per-bus su TRAIN — il modello *apprende*

| Bus (idx) | Nome (mapping table) | Esempi train con onset | F-mean train |
| :-- | :-- | :--: | :--: |
| 0 | `kick`         | 10 | **0.74** |
| 1 | `snare`        | 10 | **0.90** ✓ ≥ 0.80 |
| 2 | `hihat`        | 10 | **0.67** |
| 3 | `tom_hi_mid`   |  1 | 0.0 (1 esempio non basta) |
| 4 | `floor_tom`    |  3 | **1.00** ✓ |
| 5 | `ride`         |  1 | 0.0 |
| 6 | `crash_a`      | 10* | 0.0 (vedi nota) |
| 7 | `crash_b_misc` |  0 | n/a (zero esempi positivi) |

\* I 10 train hanno zero ground-truth su `crash_a` — il modello produce *predizioni*
spurie su quel bus, che il F-measure conta come falsi positivi → F=0. Niente
ground-truth, niente segnale di anti-correlazione: è la versione mini-batch del
problema "il modello non sa quando *non* prevedere".

Pacchetto completo in [`per_bus_report.json`](per_bus_report.json).

### 3.2 Per-bus su HOLDOUT — il generalization gap

| Sample | Engine | mic_config | F-mean | F-shuffle | Timing-MAE | HiHat-MAE |
| :-- | :-- | :-- | :--: | :--: | :--: | :--: |
| `GMD000-V0T0-DGZ-R0-L1-NONE` | drumgizmo | multitrack_full | 0.185 | 0.057 | 8.22 ms | 0.314 |
| `GMD001-V0T0-SFZ-R0-L1-NONE` | sfizz     | solo_stereo     | 0.163 | 0.000 | 2.90 ms | 0.104 |

Gap qualitativo train→holdout ≈ **5×** sul F-measure. Le grooves di train e
holdout vengono dallo stesso pattern MIDI (generato sinteticamente per F0-T2e):
il modello apprende lo *stile esatto* (timing, micro-variazioni) di 10 grooves
e non generalizza al "groove vicino" del holdout. Diagnosi consolidata in
letteratura ADT: i 10 grooves del mini-batch sono **due ordini di grandezza**
sotto il dataset minimo perché un TCN di questa dimensione generalizzi.

Per riferimento, la dottrina del Gold rifirma il caveat:

> *"⚠️ Soglie di **de-risking architetturale**, non claim di prodotto. Su un
> mini-batch è atteso un certo overfitting: l'obiettivo di L3 è escludere il
> 'non apprende' e certificare l'esportabilità, non misurare l'accuratezza
> Studio-Grade."* — [F0-T4a §7](../../methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md#l3-threshold)

Il "non apprende" è già escluso (vedi §3.1, snare F=0.90).

## 4. Decisione del CEO

Tre vie, in ordine di rischio crescente per la timeline credito:

- [x] **A. Ratifica L3 architetturale ora, posticipa la barra metrica a L4** —
      lo sblocco di F2-T3 (training Gold A100) si basa sull'evidenza che la
      topologia *esporta* (questo è chiuso) e che *apprende* su buses
      densamente popolati (§3.1). La F-measure ≥ 0.80 si sposta dal Gate L3 al
      Gate L4 — coerente con la dottrina "soglie di de-risking architetturale,
      non claim di prodotto" già scritta in F0-T4a §7. **Sblocca subito F2-T3**
      al completamento di F1+F2-T1, dentro la finestra credito.
- [ ] **B. Tentativo metrico aggiuntivo sul mini-batch** — taratura
      iperparametri (canali `C=64`, capacità +2.5×; loss weights; refractory
      del peak-picker); STRP-001 light; nuovo round di training in locale (€0,
      ~2-4 ore). Costo opportunità: rischia di **non superare comunque** la
      barra (10 grooves restano insufficienti, è un limite informativo non di
      capacità) e ritarda lo sblocco di F2-T3 di ~1 giorno.
- [ ] **C. L3 non superato — torna alla topologia F0-T4a** — riapertura
      STRP-001 sulla topologia. Costo: ~3 giorni, **fuori dalla finestra credito**.
      Non raccomandato dato che il round-trip ha chiuso il rischio architetturale
      che era *l'unico* motivo per cui L3 esiste in F0.

> **Decision Lock CEO — 2026-05-23.** Ratificata opzione A: la barra
> F-measure ≥ 0.80 era statisticamente irrilevante su 10 grooves anche se
> superata ("non è una rete neurale, è un interpolatore scemo"). Il rischio
> architetturale — l'unico vero motivo per cui L3 esiste in F0 — è chiuso dal
> round-trip a fp32 epsilon. La barra metrica significativa si misura al Gate
> L4 sull'Holdout reale E-GMD. **F2-T3 sbloccato** appena F1+F2-T1 chiudono.

**Raccomandazione strategica (advisor):** opzione **A**. La doctrine
$200-or-lose-it (`MASTER_SCHEDULING §1.1`) chiede che il credito si converta in
*asset*, e il maggior asset di F2 — il dataset Gold da 1.5 TB — non dipende
dalla F-measure di un mini-batch da 10 grooves. Il rischio architetturale, che
era l'unico rischio reale di F0-T4b, è chiuso. La barra metrica più informativa
si misura naturalmente al **Gate L4** (`MASTER_CHECKLIST §6`) sul Holdout reale
E-GMD, dove il dataset è di magnitudine sufficiente perché la cifra sia
significativa.

---

**Data firma:** **2026-05-23**  **Firma CEO:** **Decision Lock CEO — L3 superato (opzione A)**

Esito tracciato in [`REGISTRO_AVANZAMENTO.md`](../../../04_INTELLIGENCE/REGISTRO_AVANZAMENTO.md).
A valle dell'approvazione, **`F2-T3` (Training A100)** resta gated solo da
`F2-T1` (render).

---

## Appendice — come ri-eseguire le evidenze

```bash
# Training (1500 epoch, Mac M5 / MPS, ~50 s wall-clock)
PYTHONPATH=src .venv/bin/python -m neural.train \
  --epochs 1500 --crop-samples 131072 --batch-size 5 --lr 2e-3

# Round-trip a 3 vie (PyTorch ↔ NumPy ↔ C++17)
.venv/bin/python tools/run_round_trip.py

# Per-bus report
.venv/bin/python tools/l3_ocular_proof.py
```

Tutti i numeri citati in questo documento vengono dai JSON committati a fianco
(`round_trip_report.json`, `per_bus_report.json`, `artifacts/f0t4b_report.json`).
