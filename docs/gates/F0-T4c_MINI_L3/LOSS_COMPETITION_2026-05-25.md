# Loss Design Competition — Findings 2026-05-25

**Origine:** Decision Lock CEO 2026-05-25 (post-listening-test). Dopo che il listening test ha rivelato che il problema non era cross-kit OOD ma **predict-everywhere collapse** sui bus non-kick, abbiamo lanciato 4 candidati di loss design concorrenzialmente per discriminare quale leva chiude il gap.

**Setup invariante:** mixed-5kit pool (577 baseline-only sample), C=64 (331k param), P1+P2 preprocessing, cosine LR + warmup, early-stop patience 30, grad-clip 0.5, skip-nonfinite. Solo la loss varia.

---

## Tabella riassuntiva

| Preset | Loss config | Train loss final | val F (tuned) | **ShittyKit val F (fixed 0.1)** | **DRSKit train F (fixed 0.1)** | Wall |
|---|---|:--:|:--:|:--:|:--:|:--:|
| **CTRL** | AFL + per-bus + γ=2 + fp=3 | 0.357 | 0.099 | 0.084 | 0.107 | 22 min |
| **A** | AFL + cap pos_w=50 + γ=2 + fp=3 | **0.219** | 0.098 | 0.076 | **0.120** ↑12% | 22 min |
| **B** | AFL + per-bus + γ=2 + **fp=30** | 0.78 | 0.095 | **0.087** ↑4% | 0.114 ↑7% | 24 min |
| **C** | AFL + cap pos_w=50 + **γ=4** + fp=3 | 0.103 | 0.082 | 0.069 | 0.104 | 25 min |
| **D** | **Tversky α=0.7 β=0.3** | 1.77 | 0.020 | 0.045 | 0.068 | 15 min (early stop ep 88) |

## FP/FN ratio per bus (ShittyKit val, threshold fisso 0.1)

Indicatore di "predict-everywhere collapse" — più alto = più FP rispetto ai FN. Target ideale: ≤ 5×.

| Bus | CTRL | **A** | **B** | C | D |
|---|:--:|:--:|:--:|:--:|:--:|
| **kick** ✅ | 1.98 | **1.31** | 2.80 | 51.5 🔴 | 81 🔴 |
| snare | 27.15 | 30.17 | 26.52 | 29.59 | 47 |
| **hihat** | 86 | **27** | **16** ⬇ | 90 | 143 🔴 |
| tom_hi_mid | 4.41 | 20.49 | 9.30 | 132 🔴 | 210 🔴 |
| **floor** | 82 | 85 | **23** ⬇⬇ | 88 | 148 🔴 |
| **ride** | 85 | **4.4** ⬇⬇⬇ | 6.9 ⬇⬇ | 104 | 0 (no predictions) |
| **crash_a** | 67 | **7.5** ⬇⬇⬇ | 57 | 821 🚨 | 0 |
| **crash_b** | 8.34 | **2.0** ⬇⬇ | 13.72 | 56.9 | 547 🚨 |

## Diagnosi per candidato

### CTRL — status quo
**Verdetto:** la rete impara solo il kick (FP/FN 1.98). Tutti gli altri bus collapse 67-86×. Train loss bassa (0.357) ma F crolla per via di confidence diffuse sotto 0.1.

### A — cap pos_weight=50
**Verdetto:** ✅ **MIGLIOR CALIBRAZIONE DEI BUS RARI.** Ride da 85→4.4, crash_a da 67→7.5, crash_b da 8.3→2.0. DRSKit F sale a 0.120 (best del campo). Snare/floor restano alti (la cap uniforme non risolve i bus comuni con densità alta).
- **Pro:** training stabile (1 skip su 145 ep vs 325 in CTRL), train loss 0.219 (-39%)
- **Pro:** elimina la pressione FN sproporzionata sui bus rari
- **Con:** snare/floor restano predict-everywhere

### B — per-bus + fp_to_fn_ratio=30
**Verdetto:** ✅ **MIGLIOR CALIBRAZIONE DEI BUS COMUNI.** Hihat da 86→16, floor da 82→23, snare da 27→26. ShittyKit F sale a 0.087 (best del campo). Crash regredisce.
- **Pro:** triplica la penalty FP → costringe la rete a essere più selettiva
- **Pro:** mantiene info densità per pos_weight
- **Con:** crash_a peggiora (67→57) — il fp_ratio 30 non basta per pos_weight 1000
- **Con:** training meno stabile (grad_max 5-18 vs <2 in A)

### C — γ=4 + cap 50
**Verdetto:** 🚨 **CATASTROFICO.** γ=4 ha causato vanishing gradient (grad_max 0.32-0.5). La rete non ha imparato a discriminare nemmeno il kick (FP/FN 1.98→51.5). Tom 4→132, crash_a 67→**821**.
- **Diagnosi:** focal γ=4 sopprime tutti i contributi quando p ≈ 0.5 → gradient piccolo ovunque
- **Lesson learnt:** γ=4 va combinato con pos_weight forte (es. 200+), non con cap 50

### D — Tversky α=0.7 β=0.3
**Verdetto:** 🚨 **COLD-START FAIL.** Train loss bloccata a 1.77-1.78 da epoch 10 fino al early stop @ ep 88. La rete non si è mossa.
- **Diagnosi:** Tversky soft con smooth=1.0 e p iniziale ≈ 0.5 → loss costante a 0.7, gradient ≈ 0
- **Lesson learnt:** Tversky pure non funziona qui. Servirebbe ibrido AFL+Tversky o smooth schedule

---

## Hypothesis: A+B combinato

Il listening test mostra che **A è complementare a B**:
- A calibra perfettamente i bus rari (cap pos_weight rimuove la pressione FN sproporzionata)
- B calibra i bus comuni (fp_ratio alto bilancia la BCE)

**Candidato E (raccomandato per il prossimo round):** cap pos_weight=50 + fp_to_fn_ratio=30 + γ=2.

**Ipotesi di funzionamento:**
- Pressione FN uniforme e moderata (50×) su tutti i bus → no spam predict
- FP penalty 10× più alta della FN penalty → la rete è incentivata a essere selettiva
- γ=2 mantiene il focal in regime stabile (non vanishing come γ=4)

**Stima FP/FN attesi (interpolando A e B):**
- kick: ~2 (entrambi ≈ 1.5-3)
- snare: ~25 (entrambi 27-30) — POSSIBILE deviazione: forse calibrato meglio se la combinazione amplifica
- hihat: ~16 (B vinse a 16)
- floor: ~23 (B vinse a 23)
- ride: ~5 (A vinse a 4.4)
- crash_a: ~10 (A vinse a 7.5)
- crash_b: ~3 (A vinse a 2.0)

**Se ipotesi confermata** → riduzione media di FP/FN del ~5-7× rispetto a CTRL, con ShittyKit F target ≥ 0.12.

## File generati

- `LOSS_COMPETITION_2026-05-25.md` (questo)
- `mini-l3-loss-{A,B,C,D}-2026-05-25/report.html` — HTML training report per ogni preset
- `listening_test_loss-{A,B,C,D}-2026-05-25/` — per-bus comparison + waveform per ogni checkpoint

## Raccomandazione operativa

1. **Scartare C e D** — entrambi catastrofici per ragioni diverse (vanishing gradient / cold-start FAIL)
2. **Lanciare candidato E (A+B combinato)** — il prossimo logico
3. **Eventualmente F (Tversky con smooth schedule + warmup AFL→Tversky)** se E non chiude
4. **Una volta scelto il vincitore** → re-listening test full + presentazione CEO per voto B4 + sblocco F2-T1

## Costo Azure: $0

Tutto compute locale (~95 min totali per round 1). Ledger: 4 nuove entry (CTRL già esistente).

---

## ADDENDUM — Round 2 (E, F, G) — 2026-05-25 17:00-18:30

Lanciati 3 candidati addizionali per testare le ipotesi del round 1.

### E — A+B combinato (cap pos_w=50 + fp_to_fn_ratio=30, γ=2)

**Ipotesi:** A e B sono ortogonali → la combinazione dovrebbe avere il meglio di entrambi.

**Risultati:**
- ShittyKit fixed F = **0.087** (tied con B)
- DRSKit fixed F = 0.106
- kick FP/FN = 0.90 ✅ (miglior bilanciamento)
- tom = 1.75 ✅, floor = 12 ✅, ride = 4.4 ✅
- **MA: crash_a/b ZERO-DETECT** (la rete non predice mai i crash)

**Diagnosi del fallimento crash:** cap pos_weight=50 sui bus rari + fp_to_fn_ratio=30 → la pressione FP (30×) eccede la pressione FN (50× × density_crash 0.7-1.5 %) → la rete preferisce non predicere crash. Crash density-corrected FN penalty < FP penalty.

### F — Tversky con warmup AFL

**Ipotesi:** 30 epoch di AFL (CTRL) → confidence non-zero sui veri positivi → Tversky può partire senza cold-start.

**Risultati:**
- val F = **0.003** (tuned) / **nan** (fixed) — catastrofico
- Switch netto AFL→Tversky @ epoch 31 ha distrutto i pesi
- Loss balza da 0.77 (AFL) a ~1.40 (Tversky scale diversa) → early-stop confuso, scatta a epoch 60
- **Bug logico aggiuntivo identificato:** early-stop guarda valore assoluto loss, ignora cambi di scala mid-training

**Diagnosi:** il switch è troppo netto. Servirebbe (a) LR re-warmup post-switch, (b) smooth blending α(t)·AFL + (1-α(t))·Tversky, (c) early-stop reset al switch. Tutti questi sono refactor di gradiente per una sessione futura — non priorità immediata.

### G — Smart-cap differenziato (50 bus comuni, 150 bus rari) + fp_ratio=30

**Ipotesi:** E con cap differenziato risolve il crash zero-detect mantenendo il bilanciamento dei bus comuni.

**Risultati:**
- val F tuned = **0.100** (il migliore di tutti!) ma fixed F = 0.082 (sotto B/E)
- Distribuzione confidence asymmetric: pochi sample ad alta confidence (tune trova thr>0.1), molti a confidence bassa (crollano a thr fissa)
- crash_a ancora zero-detect ❌, crash_b parzialmente recuperato (FP/FN 3.4)
- **Hihat/floor peggiorano vs E** (70/69 vs 42/12)

**Diagnosi:** il cap differenziato cambia la pressione relativa tra bus → la rete *re-alloca* risorse in modo non-ottimale, peggiorando i bus comuni mentre tenta di recuperare i crash. Non additivo.

---

## Decision Lock CEO — Vincitore: B

**Loss config ratificata:**
```python
LossConfig(
    pos_weight = tuple(density_per_bus),  # density-based, F0-T4c B6c
    focal_gamma = 2.0,                     # status quo
    fp_to_fn_ratio = 30.0,                 # NEW default (was 3.0)
    # ...other defaults
)
```

**Razionale:**
- Best ShittyKit fixed F = 0.087 (tied con E)
- Best hihat calibration = FP/FN 16 (vs CTRL 86)
- No bus zero-detect (a differenza di E/G)
- Training stabile (25 skip su ~12k step = 0.2 %)
- Cambio minimal: una sola riga modificata in `LossConfig` defaults
- Backcompat: regression test F0-T4c può ancora usare `fp_to_fn_ratio=3.0` con override esplicito

**Implicazione operativa:**
- `src/neural/loss.py`: nuovo default `fp_to_fn_ratio = 30.0`
- `F0-T4a §6` doctrine "FP 3× FN" → SUPERSEDED dal Loss Competition 2026-05-25
- `DOSSIER §6.2` → aggiornare nelle prossime spec
- F2-T1 sbloccabile (loss config empiricamente ratificata)
- F2-T3 training A100 girerà con `fp_to_fn_ratio=30` di default

## Costo totale Loss Competition: $0 Azure, ~3 h compute locale (7 training × 22 min + 7 listening test)

## Ledger entries: 7 (A, B, C, D, E, F, G) + CTRL già esistente

