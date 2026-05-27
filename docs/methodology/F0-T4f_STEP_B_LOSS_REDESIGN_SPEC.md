---
title: "F0-T4f — Step B · Loss Redesign (Ridnik AsymmetricLoss + Label Smoothing)"
id: LIN-DT-F0T4F
status: LOCKED_v1.0.0
locked: true
locked_at: 2026-05-27
authors: [Strategic Advisor (Gianpiero Scappelloni)]
date: 2026-05-27
supersedes: []
related:
  - F0-T4a §6 (loss math — amendment Ridnik kind)
  - F0-T4c §6.1 (PARTIAL-LOCK B1/B2/B3/B6a/B6b/B6c — preserve)
  - F0-T4d (preprocessing harness — orthogonal, preserve)
  - F0-T4e (input-agnostic training — orthogonal, preserve)
  - Loss Competition 2026-05-25 (fp_to_fn_ratio=30 ratificato — kind="afl" path preserve)
  - F0-T4e listening + Step A 2026-05-27 (calibration_sweep.json — diagnostic anchor)
---

# F0-T4f · Step B — Loss Redesign (Ridnik AsymmetricLoss + Label Smoothing)

> **Status:** LOCKED v1.0.0 — Decision Lock CEO 2026-05-27 ratificato
> D1+D2+D3+D4. 6 fasi STRP-001 chiuse. §6.1 documenta le 4 ratifiche;
> Fase 6 Docs Update propagata negli amendment sotto.

## 0 · Inquadramento

**Origine — la diagnostica Step A.** Il `tools/calibration_sweep.py`
girato sul checkpoint `artifacts/mini_l3_tcn_F0T4e.pt` ha rivelato due
fatti che ribaltano il framing di tutta la settimana scorsa:

1. **Sotto-confidence sui TP, non over-prediction.** 6 bus su 8 preferiscono
   temperature `T < 1.0` (sharpening) nello sweep di calibration. La rete
   F0-T4e produce sigmoid 0.05–0.20 sui veri positivi — non saturati. Il
   pattern "predict-everywhere" delle FP/FN 30-86× era un **artefatto della
   soglia fissa 0.10 troppo bassa**: con soglia ottima 0.13–0.30 e
   sharpening, la qualità reale emerge.
2. **Cross-kit gap = 0.** Train F = 0.187, Val F = 0.189 (ratio 0.99×).
   F0-T4e ha rimosso la causa cross-kit; il bottleneck residuo è simmetrico
   cross-kit, non OOD-specific.

**Implicazione operativa.** La leva `fp_to_fn_ratio` (Loss Competition
2026-05-25 → 30, già LOCKED) è stata tirata fino alla sua dose massima
sicura. Spingerla a 100 (B1) andrebbe nella direzione **opposta** al
bottleneck reale: aggraverebbe la sotto-confidence punendo ancora più
duramente i FP che però sono già *sotto-attivi*. La cura va al ramo
positive: **spingere la confidence sui TP**.

**Step B (questo task).** Ridnik AsymmetricLoss (Alibaba MS-COCO 2020) —
γ+ e γ- separati + *probability shifting* sul ramo negative — combinato
con label smoothing leggero. Direzione di ottimizzazione: massimizzare
l'energia del gradient sul ramo positive senza moltiplicare ulteriormente
il già-massimo `fp_to_fn_ratio`.

## 1 · Competitor & Market Analysis

| Soluzione | Loro | Match con NeuroTrigger |
|---|---|---|
| **Onsets & Frames** (Hawthorne 2019, Magenta) | BCE pesata su onsets binarizzati, no temperature scaling. Dataset MAPS ~100× il nostro. | Loss pesata = nostro AFL. Manca asimmetria FP/FN, manca probability shifting. |
| **AsymmetricLoss** (Ridnik 2020, Alibaba — MS-COCO multi-label) | γ+, γ- separati + probability shifting (clip prob<m → contributo 0). SOTA multi-label sparso. | **Match perfetto** al nostro caso. ~8 LOC plug-in. |
| **Onset BCE + Asymmetric** (Schlüter 2022) | Asymmetric Focal con γ=2 fissato. | Nostro `kind="afl"` esistente. |
| **Calibration via Temperature** (Guo 2017) | Post-hoc temperature scaling su validation. | Già fatto in Step A (calibration_sweep). Conferma sotto-confidence. |
| **Label Smoothing** (Szegedy 2016 — Rethinking Inception) | Target 1.0 → 0.9, 0.0 → 0.1. Spinge logit a non saturare. | Plug-in 2 LOC nella `_asymmetric_focal_bce` e nel nuovo `_ridnik_asymmetric_loss`. |
| **ADTOF / MDB-Drums SOTA** | F ≈ 0.85 su drum onset detection generico. | Target: F production ≥ 0.20 mini-L3 stress test, F ≥ 0.55 gate L3, F ≥ 0.80 gate L4 (E-GMD). |

## 2 · Open-Source Codebase Analysis

| Repo | ⭐ | Cosa offre | Nostro uso |
|---|---|---|---|
| `Alibaba-MIIL/ASL` | ~600 | Reference Ridnik AsymmetricLoss in PyTorch (~30 LOC). | **Pattern di riferimento** per `_ridnik_asymmetric_loss`. Reimplementiamo in casa (dipendenza zero). |
| `pytorch-toolbelt.losses` | ~1.5k | Focal/Dice/Tversky già esistenti. | Già coperti dal nostro `_asymmetric_focal_bce` e `_tversky_loss`. Nessun aggiuntivo. |
| `madmom` | ~1k | Classic ML onset detection. | Non rilevante (no DL). |
| `onsets-and-frames` (Magenta) | ~5k | BCE pesata su onsets. | Già coperto. |

**Decisione:** zero nuove dipendenze. La reimplementazione Ridnik in
`src/neural/loss.py` è ~50 LOC + 5 LOC per label smoothing.

## 3 · UX/UI Impact

Nessuno diretto. La loss è interna al training. Doc-only update:
- `F0-T4a §6` amendment — nuovo `kind="ridnik"` + parametri.
- `DOSSIER §6.2` amendment — aggiornare la riga "Loss" della tabella.
- `MASTER_SCHEDULING.md` — bullet 2026-05-27 con risultato.

## 4 · Tech Implementation Matrix

### 4.1 · Schema parametrico Ridnik AsymmetricLoss

```
xs_pos = p                                # probabilità (post-sigmoid del modello)
xs_neg = 1 - p
xs_neg = (xs_neg + prob_clip_negative).clamp(max=1.0)   # probability shifting
log_pos = log(xs_pos.clamp(min=eps))
log_neg = log(xs_neg.clamp(min=eps))

# label smoothing (opzionale, applicato a target binari Gaussian-smeared)
t_smooth = t * (1 - label_smoothing) + label_smoothing / 2   # soft target

loss_pos = pos_weight * t_smooth * log_pos                   # ramo positive (FN penalty)
loss_neg = fp_to_fn_ratio * (1 - t_smooth) * log_neg          # ramo negative (FP penalty)

# focusing asimmetrico
pt0 = xs_pos * t_smooth
pt1 = xs_neg * (1 - t_smooth)
pt = pt0 + pt1
one_sided_gamma = gamma_pos * t_smooth + gamma_neg * (1 - t_smooth)
one_sided_w = (1 - pt) ** one_sided_gamma

loss = -(loss_pos + loss_neg) * one_sided_w
return loss.mean()
```

**Differenze chiave vs `_asymmetric_focal_bce`:**
1. `gamma_pos` ≠ `gamma_neg` — l'AFL classico ha un singolo `γ`. Ridnik
   permette `gamma_pos=1.0` (focusing morbido sui TP — non li punisce per
   essere già "facili") + `gamma_neg=4.0` (focusing duro sui FP — li
   punisce di più quando sono "facili da non predire").
2. `prob_clip_negative` — clip sui negative shift di +0.05 → ogni
   negative con prob < 0.05 ha contributo zero (irrilevanti, già ben
   classificati). Riduce noise dal mare dei TN.
3. `label_smoothing` — soft target lega la log-likelihood lontano dalla
   saturazione, lasciando spazio al gradient di spingere i logit dei TP
   verso valori più alti.

### 4.2 · Matrice di valutazione

| Candidato | Cosa cambia | Complessità | Aderenza Linear ENG STD | Rischio | ROI atteso vs Step A (0.149) |
|---|---|---|---|---|---|
| **B'-RIDNIK** *(ratificato)* | `kind="ridnik"` + γ+/γ-/clip/smoothing + preset `--loss-preset ridnik` | +60 LOC `loss.py`, +1 preset `mini_l3_train.py` | ✅ §1 determinism (no nuovi state), §3 codifica (frozen dataclass + Module register_buffer), §5 statistical validity (regression test) | Medio (4 nuovi knob — coperti da defaults Ridnik canonici) | **+30–50 %** → 0.19–0.22 |
| B1-FP_HEAVY | `fp_to_fn_ratio=100` | +0 LOC | ✅ | **Alto** — aggrava sotto-confidence dimostrata da Step A | −10 a −20 % |
| B2-FOCAL_HOT | γ=4–6 + cap pw 50 | +5 LOC | ✅ | Medio (vanishing kick già visto in candidate C) | +5–10 % |
| B3-AFL_DENSITY | AFL per-bus density-tuned | +20 LOC | ✅ | Basso (già parzialmente esistente) | +5–10 % |
| C-CAPACITY+B' | C=64 + B'-Ridnik | +60 LOC + 12h training | ✅ | Basso ma confonde l'effetto della loss isolata | +40–60 % (compound) |

**Scelta:** B'-RIDNIK isolato. Se +30 % → ratifichiamo come default per F2-T3.
Se < +10 % → escludiamo questa leva e pivotiamo a C-CAPACITY+B' o Bug #3
mapping table (GM 75/54 splash/tambourine non mappati).

### 4.3 · Defaults proposti (preset `--loss-preset ridnik`)

| Parametro | Valore | Razionale |
|---|---|---|
| `kind` | `"ridnik"` | Nuovo path dispatch. |
| `gamma_pos` | `1.0` | Standard Ridnik 2020. Focusing morbido sui TP → non li sotto-pesi. |
| `gamma_neg` | `4.0` | Standard Ridnik 2020. Focusing duro sui FP "facili". |
| `prob_clip_negative` | `0.05` | Standard Ridnik 2020. Filtra il mare dei TN già ben classificati. |
| `label_smoothing` | `0.05` | Soft target 0.95 / 0.05 — leggero, evita di destabilizzare il Gaussian smearing che è già "soft". |
| `pos_weight` | `pos_weight_tuple` (density-derived per-bus) | Preservato da F0-T4c B6b. |
| `fp_to_fn_ratio` | `30.0` | Preservato dalla Loss Competition 2026-05-25 (default LossConfig). |
| `focal_gamma` | (ignorato in `kind="ridnik"`) | `gamma_pos`/`gamma_neg` lo sostituiscono. |

## 5 · Executive Briefing (sintesi presentata al CEO 2026-05-27)

**D1 — Variante:** B'-RIDNIK (Ridnik AsymmetricLoss + label smoothing).
**D2 — Scope:** solo loss redesign (no capacity bump simultaneo).
**D3 — Training budget:** mini-L3 stesso pool (5 kit DG+SFZ, val ShittyKit
post midimap-patch), 150 epoch, ~6h notturno fp32 MPS (`--no-amp` per
evitare il deadlock MPS scoperto in F0-T4e).
**D4 — Pass criterion:** val F production ≥ 0.20 (+34 % vs Step A 0.149)
per ratificare; < 0.16 → pivot.

## 6 · Docs Update (Fase 6 STRP-001)

### 6.1 · Le 4 ratifiche CEO 2026-05-27

| ID | Decisione | Voto CEO |
|---|---|---|
| **D1** | Variante B'-RIDNIK (Ridnik AsymmetricLoss + label smoothing) | ✅ APPROVED |
| **D2** | Scope isolato (no capacity bump simultaneo) | ✅ APPROVED |
| **D3** | 150 epoch fp32 MPS, `--no-amp`, ~6h notturno | ✅ APPROVED |
| **D4** | Pass criterion val F production ≥ 0.20 | ✅ APPROVED |

### 6.2 · Amendment propagati

- **`F0-T4a §6`** — aggiunto path `kind="ridnik"` alla tabella loss; nota
  che `gamma_pos`/`gamma_neg` sostituiscono `focal_gamma` su questo path.
- **`DOSSIER §6.2`** — riga "Loss" estesa per documentare il path Ridnik
  come *additional kind* dell'AFL family.
- **`MASTER_SCHEDULING.md`** — bullet 2026-05-27 con riferimento a questo
  spec (LOCKED + risultato training notturno post-completion).
- **`docs/audit/training_ledger.yaml`** — entry `mini-l3-F0T4f-stepB-2026-05-27`
  con stato `RUNNING` durante il notturno, finalizzata al termine.

### 6.3 · Oracoli aggiunti (`tests/unit/test_loss_ridnik.py`)

**L1 unit (≈ 20):**
- `LossConfig` validation: `kind="ridnik"` accettato; `gamma_pos`/`gamma_neg`/`prob_clip_negative`/`label_smoothing` in range; fail-loud su out-of-range.
- `_ridnik_asymmetric_loss` forward: shape contract, dtype, finite output.
- Asymmetry direction: γ_pos < γ_neg riduce la perdita sui TP "facili" più che sui FP "facili" (atteso comportamentale).
- Probability shifting: `prob_clip_negative` > 0 azzera il contributo dei negative con prob < clip.
- Label smoothing: target 1.0 → 1−ε/2 nel ramo positive; target 0.0 → ε/2 nel ramo negative.
- `TCNLoss(kind="ridnik")` integration: la `forward` ritorna gli stessi 5 chiavi (`total`, `onset`, `velocity`, `microtiming`, `hihat`).
- Determinismo: seed identico → output identico (bit-per-bit su CPU).
- Backcompat: `kind="afl"` continua a funzionare invariato.

**L2 property Hypothesis (≈ 5):**
- Loss non-negativa per qualsiasi `(p, t)` in `[0,1]^2`.
- Invarianza alla permutazione dei bus (la loss è simmetrica nel bus dim).
- Monotonia: aumentare `pos_weight` aumenta la loss quando la rete sbaglia sui FN.
- Limit case: `prob_clip_negative → 0.5` → loss negative ≈ 0 (tutti i negative "facili").
- Limit case: `label_smoothing → 0` → equivale a hard targets.

## 7 · Costo & Timeline

- **Implementazione locale:** ~1 h.
- **Training notturno:** ~6 h fp32 MPS (no `audio_aug` per isolare l'effetto della loss; `--input-agnostic` + `--preprocessing p1p2` preservati).
- **Validation + listening + ledger update:** ~30 min mattina.
- **Costo Azure:** **$0**.

---

*Spec LOCKED v1.0.0 — 2026-05-27. Aggiornare §6.2 (ledger entry) al
completamento del training notturno.*
