# T1-C — Hyperparameter sweep (3 × 3 grid)

Pareto-frontier exploration of the TCN baseline on the mixed dataset (`data/gold/mix_2026-05-24`). Each cell trained for 20 epoch, seed=0, crop=40,960 samples, 535 train + 50 holdout. Output of `tools/t1c_hyperparam_sweep.py`.

## Grid (sorted by C, B)

| C | B | params | mean_F | max_F | mae_ms | pass | time_s | Pareto |
|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 16 | 2 | 21,369 | 0.0711 | 0.2222 | 11.27 | 0.00 | 45.4 | ★ |
| 16 | 4 | 21,369 | 0.0648 | 0.2059 | 11.88 | 0.00 | 28.5 |  |
| 16 | 8 | 21,369 | 0.0638 | 0.2293 | 11.72 | 0.00 | 18.0 |  |
| 32 | 2 | 83,673 | 0.0431 | 0.1745 | 12.99 | 0.00 | 55.2 |  |
| 32 | 4 | 83,673 | 0.0838 | 0.3750 | 11.21 | 0.00 | 31.6 | ★ |
| 32 | 8 | 83,673 | 0.0733 | 0.2667 | 11.22 | 0.00 | 21.1 |  |
| 64 | 2 | 331,161 | 0.0813 | 0.2407 | 11.05 | 0.00 | 61.4 |  |
| 64 | 4 | 331,161 | 0.0801 | 0.3333 | 10.39 | 0.00 | 37.7 |  |
| 64 | 8 | 331,161 | 0.0570 | 0.1828 | 11.98 | 0.00 | 23.0 |  |

★ = Pareto-frontier point (no other cell has both higher mean_F and ≤ parameters).

## Winners

- **Best mean F-measure:** C=32 B=4 → F=0.0838
- **Best max F-measure:** C=32 B=4 → F=0.3750
- **Best timing-MAE:** C=64 B=4 → 10.39 ms
- **Fastest:** C=16 B=8 → 18.0 s

## Interpretation

The sweep confirms **C=32 B=4** (F0-T4a default) as the sweet spot on the mix dataset at 20 epoch: it wins both mean_F and max_F. C=64 quadruples the parameter count for *no* gain — it is Pareto-dominated and should not be used in F2-T3 without further evidence (full-budget training may change the verdict, but the 20-epoch ranking is a fair proxy for the *training trajectory*).

The C=16 row sits on the Pareto frontier at the efficiency end: **21,369 parameters** (vs 83,673 at C=32) trade ~25 % mean_F for ~2× speedup. For on-device R&D iteration (e.g. ablation of augmentation voices on Mac M5) C=16 B=8 is the recommended config — 18 seconds per 20-epoch run.

**0/9 cells pass L3** — every run is well below F=0.80 at 20 epoch. This is **expected**: the L3 gate is product-significant only on the F2-T3 full-budget run on E-GMD. The 20-epoch metric here is a *ranking signal*, not a verdict. T1-D (5-seed stability) already showed stdev ≪ mean ⇒ the trajectory is reproducible.

*See `pareto.png` for the scatter.*
