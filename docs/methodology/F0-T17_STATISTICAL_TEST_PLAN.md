---
id: LIN-DT-SPEC-F0T17
title: F0-T17 — Statistical Test Plan (Data Audit + Evaluation Suite)
type: spec
status: LOCKED
phase: F0
domain: Methodology / Statistical Validation
version: 1.0.0
updated: 2026-05-23
tags: [statistics, evaluation, data-audit, mir_eval, F0-T17]
related: [LIN-DT-ENGSTD-001, LIN-DT-DOSSIER-001, LIN-DT-SPEC-F0T2a, LIN-DT-SPEC-F0T4a]
supersedes: []
---

# 📐 F0-T17 — SPEC: STATISTICAL TEST PLAN
**Status:** LOCKED — Decision Lock CEO 2026-05-23 (Executive Briefing STRP-001).
**Riferimenti:** [`ENGINEERING_STANDARDS §5 — validazione statistica`](../../04_INTELLIGENCE/ENGINEERING_STANDARDS.md#statistical-validation) ·
[`DOSSIER §10 — Validation Protocol`](DOSSIER_TECNICO.md#validation) ·
[`F0-T4a — soglia L3`](F0-T4a_TCN_TOPOLOGY_SPEC.md#l3-threshold) ·
[`F0-T2a §3.8 — tail std`](F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#tail-standardization) ·
[`MASTER_SCHEDULING §6 — F0-T17`](../../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks).

> `ENGINEERING_STANDARDS §5` fissa i **principi** della validazione statistica (soglia
> dichiarata pre-training, varianza su N seed, intervallo di confidenza, report
> machine-verifiable). Questa spec li traduce nella **operazione**: i test specifici da
> girare sul Gold prima del training A100, le soglie pre-dichiarate, lo stack tecnico,
> i moduli e i loro contratti di output.

---

<a id="rationale"></a>
## 1. Razionale — perché questa spec esiste

Il training A100 in F2-T3 brucia ~$80/run. Senza un audit statistico esplicito del Gold
**prima** del lancio, ogni problema di distribuzione (class imbalance, leak
durata→engine, train/val drift, OOD train↔E-GMD) si scopre solo *dopo* aver bruciato il
credito. La doctrine `$200 use-it-or-lose-it` non tollera spese a vuoto.

A valle del training, il Gate L4 non può essere un singolo numero ("F ≥ 0.80 su
E-GMD"): serve un dossier **falsificabile** che regga la pressione di pubblicazione e
marketing (`Laboratory Precision` del prodotto). Per-bus F-score, bootstrap CI, sliced
metrics, calibration — pattern academic standard (ISMIR, MIREX, DCASE), assente nei
competitor commerciali. Pubblicarli è **arma di marketing**.

**Output netto:** quattro moduli statistici (`src/evaluation/`), eseguibili pre-F2-T3 e
post-F2-T3, che producono JSON parsabile + PNG vettoriale `Laboratory Precision`.

---

<a id="stack"></a>
## 2. Stack tecnico (Decision Lock CEO 2026-05-23, Risoluzione 1)

| Tool | Ruolo | Versione |
| :-- | :-- | :-- |
| `mir_eval` | F-measure onset/transcription, allineato MIREX | ≥ 0.7 |
| `scipy.stats` | KS test, χ², bootstrap CI, Wilcoxon, McNemar | ≥ 1.7 (per `scipy.stats.bootstrap`) |
| `scikit-learn` | `confusion_matrix`, `calibration_curve`, `mutual_info_classif` | ≥ 1.4 |
| `matplotlib` | PNG vettoriale monocromo (no UI heavy) | ≥ 3.8 |

**Scartati:** `great-expectations`, `evidently`, `alibi-detect` — over-tooling
UI-heavy che violano `ENGINEERING_STANDARDS §5` ("report machine-verifiable, mai
ispezione visiva di un grafico"). `ydata-profiling` ammesso opzionalmente come
*addendum* per il dataset card finale, non come gate.

---

<a id="modules"></a>
## 3. I quattro moduli

Tutti i moduli vivono in `src/evaluation/`, espongono una CLI deterministica
(seed esplicito, ENGINEERING_STANDARDS §1), e producono **due artefatti** per ogni
report:

- `<report>.json` — il gate machine-verifiable (parsato da CI / Gate L4).
- `<report>.png` — vector-style monocromo "Laboratory Precision", per il dossier umano.

### 3.1 `data_audit.py` — distribuzione del Gold (pre-F2-T3)

**Quando gira:** dopo F2-T1 (Gold renderizzato), prima di F2-T3.

**Cosa misura:**

| Metrica | Output |
| :-- | :-- |
| Class imbalance per bus | `n_onset[b] / n_onset_total` per ogni bus `b ∈ [0,7]` |
| Distribuzione velocity per bus | Istogramma `[0,1]` in 20 bin |
| Distribuzione tempi/BPM (MIDI sorgente) | Istogramma in `[40, 240]` BPM |
| Distribuzione durate Gold | Istogramma `last_onset_s + tail_s` — verifica F0-T2a §3.8 |
| Distribuzione articolazioni HH | Conteggi su `closed/pedal/open` |
| Distribuzione mic_config | `mono / solo_stereo / glyn_johns / multitrack_full` |
| Distribuzione engine × kit | Tabella di contingenza |

**Failure mode:** un bus con < 5 % degli onset → segnalato come *minoritario* (loss
reweighting necessario in F2-T3).

### 3.2 `split_consistency.py` — train vs val vs Holdout (pre-F2-T3)

**Quando gira:** dopo F2-T1, prima di F2-T3.

**Test bloccanti:**

| Test | Famiglia | Soglia |
| :-- | :-- | :-- |
| KS train↔val su velocity, durata, timing per bus | `scipy.stats.ks_2samp` | `p ≥ 0.05` (non distinti) |
| χ² train↔val su engine, kit, mic_config | `scipy.stats.chisquare` | `p ≥ 0.05` |
| MIDI leakage check | sha256 set intersection del MIDI source | `|train ∩ val| = 0` |
| OOD check Gold↔E-GMD | KS sulle stesse feature di Gold vs Holdout | informativo (logged), non bloccante |

**Razionale:** il **Val Gold** è il sensore di early-stopping del training. Se la sua
distribuzione differisce significativamente dal train, l'early-stopping è inaffidabile.
Pairwise consistency è il prerequisito metodologico.

### 3.3 `anti_leak_audit.py` — verifica numerica Decision Lock A+C

**Quando gira:** dopo F2-T1, prima di F2-T3. **Critico** — verifica che i Decision
Lock anti-shortcut del 2026-05-23 abbiano davvero chiuso il canale, non solo
teoricamente.

| Test | Misura cosa | Soglia |
| :-- | :-- | :-- |
| **Durata-Engine independence** | χ² condizionato su `(audio_duration_bin, engine)` — H0: indipendenti | `p ≥ 0.95` (no association rilevabile) |
| **MI(audio_first_1s ; engine)** | Mutual information tra feature audio (RMS+spectral centroid+ZCR) e engine label, via `sklearn.feature_selection.mutual_info_classif` | `I ≤ 0.10 bits` |
| **Cross-engine consistency su MIDI paired** | Per ogni MIDI in train con pairing forzato, `n_sample(Sfizz)` deve essere `== n_sample(DrumGizmo)` | 100 % match |
| **Tail-zero policy** | Ultimi `min(n_sample, sr*tail_s)` campioni → media |amplitude| | per ogni engine, distribuzione coerente |

Failure di uno qualsiasi → bug nel writer Gold o nella recipe matrix → **fail loud**,
F2-T3 non parte.

### 3.4 `evaluation_suite.py` — Gate L4 + dossier (post-F2-T3)

**Quando gira:** a fine F2-T3, sull'**Holdout E-GMD** (real data, F0-T1c).

| Metrica | Calcolo |
| :-- | :-- |
| **Per-bus F-score** | `mir_eval.onset.evaluate()` per ogni bus, tolerance window **±25 ms** |
| **Bootstrap CI 95 %** | `scipy.stats.bootstrap`, 1000 resamples |
| **Confusion matrix** | inter-bus (kick→tom?), `sklearn.confusion_matrix` |
| **Calibration curve** | `sklearn.calibration.calibration_curve` per ogni bus (10 bin) |
| **Sliced metrics** | F-score per velocity-bin · per tempo-bin · per kit-OOD (i 2 kit val "vergini") · per density (sparse/dense) |
| **McNemar A/B test** | Per confronto tra modelli (es. con/senza augmentation level 3) |

Tolerance window onset **±25 ms** — più stringente del default MIR ±50 ms (Decision
Lock CEO 2026-05-23, Risoluzione 6). Coerente con la "precision-first" del prodotto
(`DOSSIER §2.2`, microtiming sample-accurate).

---

<a id="thresholds"></a>
## 4. Soglie pre-dichiarate (Decision Lock CEO, Risoluzione 3)

Le soglie sono parametrizzate in un file YAML versionato:
`src/evaluation/thresholds.yaml`.

```yaml
# F0-T17 LOCKED 2026-05-23 — modifiche richiedono Decision Lock CEO.
data_audit:
  bus_minority_pct: 5.0          # bus sotto al 5 % onset = minoritario
  bpm_min: 40
  bpm_max: 240
  velocity_n_bin: 20
  duration_n_bin: 30

split_consistency:
  ks_p_min: 0.05                 # KS p-value soglia "non distinti"
  chi2_p_min: 0.05
  midi_leakage_max: 0

anti_leak_audit:
  duration_engine_chi2_p_min: 0.95   # H0 indipendenza non rifiutata
  mi_audio_engine_max_bits: 0.10
  cross_engine_match_pct_min: 100.0

evaluation_suite:
  onset_tolerance_ms: 25.0
  bootstrap_n_resamples: 1000
  bootstrap_ci_max_width: 0.05   # F95% - F5% <= 0.05 (modello stabile)
  per_bus_f_min: 0.80            # gate L4 — ogni bus
  f_macro_min: 0.85              # gate L4 — media bus
```

Modificare le soglie senza un nuovo Decision Lock CEO è una violazione di processo —
le metriche di accettazione sono *pre-dichiarate* per costruzione
(`ENGINEERING_STANDARDS §5`).

---

<a id="interfaces"></a>
## 5. Contratti di interfaccia (firma funzioni)

Tutti i moduli condividono questo pattern:

```python
def run(*,
        gold_dir: Path,          # post F2-T1 (data_audit, split, anti_leak)
        manifest_path: Path,     # the F0-T5 split manifest
        thresholds_path: Path,   # the locked thresholds.yaml
        out_dir: Path,           # where report.json + report.png are written
        seed: int) -> ReportResult:
    """Run the module's tests, write report.{json,png}, return verdict."""
```

`ReportResult` dataclass:

```python
@dataclass(frozen=True)
class ReportResult:
    module_name: str             # "data_audit" / "split_consistency" / ...
    passed: bool                 # gate verdict (False → caller refuses to proceed)
    metrics: dict[str, Any]      # the JSON payload
    failures: list[str]          # human-readable failure descriptions
    report_json: Path
    report_png: Path
```

CLI uniforme:

```
python -m evaluation.data_audit \
    --gold-dir data/gold/train \
    --manifest data/gold/train/manifest.json \
    --thresholds src/evaluation/thresholds.yaml \
    --out reports/data_audit/ \
    --seed 4242
```

Exit code: `0` se `passed=True`, `1` se fail loud (gate fallito) — pronto per `set -e`
in shell script CI.

---

<a id="testing"></a>
## 6. Harness di test (TESTING_DOCTRINE §6 — layer 1+2)

**Layer 1 (unit):** ogni metrica testata con un input controllato dove il risultato è
noto a-priori (es. KS test su due campioni dalla stessa distribuzione → `p ≈ 1`;
bootstrap CI su un set noto → CI atteso).

**Layer 2 (property, Hypothesis):**
- Determinismo: stesso seed → stesso output JSON bit-per-bit (`ENGINEERING_STANDARDS §1`).
- Idempotenza: rieseguire `run()` non altera il report.
- Monotonia di soglia: un input più "sano" non può produrre `passed=False` se uno
  meno sano è `passed=True`, a parità di soglie.

**Layer 3 (acceptance):** run completo sul mini-batch Gold di F0-T2e (12 campioni)
→ tutti e 4 i moduli producono report verdi sul Gold pulito post-Decision Lock §3.8.

---

<a id="execution-gate"></a>
## 7. Gate operativo

| Modulo | Quando | Gate bloccante? |
| :-- | :-- | :-- |
| `data_audit.py` | post F2-T1 | ⚠️ informativo (escalation se class imbalance estremo) |
| `split_consistency.py` | post F2-T1 | **🔒 bloccante** F2-T3 |
| `anti_leak_audit.py` | post F2-T1 | **🔒 bloccante** F2-T3 |
| `evaluation_suite.py` | post F2-T3 | **🔒 gate L4** |

Lo script `tools/run_evaluation_gate.sh` orchestra i tre pre-F2-T3 in sequenza
deterministica e si rifiuta di proseguire al primo `passed=False`. È il check-list
operativo del CEO prima del training A100.

---

<a id="costs"></a>
## 8. Costo & timing

| Voce | Costo |
| :-- | :-- |
| Sviluppo spec | ☑ chiuso 2026-05-23 |
| Implementazione 4 moduli + harness | ~2-3 sessioni locali |
| Esecuzione `data_audit` / `split_consistency` / `anti_leak_audit` | post-F2-T1, **CPU**, ~5 min sui 300k campioni Gold |
| Esecuzione `evaluation_suite` | post-F2-T3, **CPU**, ~10 min su E-GMD Holdout |
| Costo Azure | **$0** — non gira mai su VM Azure pagate, solo su macchina locale o VM CPU spot a basso costo |

---

<a id="decision-lock"></a>
## 9. Decision Lock (2026-05-23)

Le 6 risoluzioni approvate dal CEO (Executive Briefing STRP-001, 2026-05-23):

1. ✅ **Stack tecnico lean**: `mir_eval` + `scipy.stats` + `scikit-learn` + `matplotlib`. Scartati framework UI-heavy.
2. ✅ **4 moduli**: `data_audit`, `split_consistency`, `anti_leak_audit`, `evaluation_suite` come da §3.
3. ✅ **Soglie pre-dichiarate** in `src/evaluation/thresholds.yaml` (§4) — versionate, modifica = nuovo Decision Lock.
4. ✅ **Output dual**: JSON parsabile (gate) + PNG vettoriale monocromo "Laboratory Precision" (dossier umano + marketing).
5. ✅ **Gate operativo bloccante**: `split_consistency` + `anti_leak_audit` prima di lanciare F2-T3; `evaluation_suite` è il vero gate L4.
6. ✅ **Onset tolerance window 25 ms**, più stringente del default MIR ±50 ms — coerente col precision-first del prodotto.

---
*Spec F0-T17 — STRP-001. **LOCKED 2026-05-23.** Vincolante per `src/evaluation/`,
pre F2-T3 (gate), post F2-T3 (gate L4).*
