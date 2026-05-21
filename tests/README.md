# F0 Pipeline Test Harness — F0-T9b

Test-first harness for the Gold data-engineering pipeline. It is the **gate of
F0-T2b/c/d**: the contract oracles are written here *before* the implementation,
against the locked contract
[`F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md).
Governing doctrine: [`TESTING_DOCTRINE.md`](../04_INTELLIGENCE/TESTING_DOCTRINE.md) §6.

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
tools/run_tests.sh                 # full suite
tools/run_tests.sh -m critical     # only critical-module oracles
tools/run_mutation.sh              # mutation meta-gate (once code exists)
```

## Layout

| Path | Layer | Role |
| :-- | :-- | :-- |
| `meta/` | 0 | Harness self-check + locked contract constants. **Real green.** |
| `unit/` | 1 | Contract oracles — recipe parser, DNA-Trace, Gold writer, mic std. |
| `property/` | 2 | Hypothesis property oracles — barcode bijection, flat-25 layout. |
| `fuzz/` | 3 | Hostile-input oracles + the standalone Atheris harness. |
| `acceptance/` | — | §6.3 per-subtask acceptance — skipped until the engines exist. |
| `harness.py` | — | The shared `awaiting()` contract-oracle marker. |
| `conftest.py` | — | Fixtures, all derived from the F0-T2a contract. |

## The self-dismantling scaffold

The implementation modules (`src/data_engineering/gold/`) are **skeletons**:
real public types and constants, stub logic that raises `NotImplementedError`.

Every contract oracle carries `@awaiting("F0-T2x")` — a strict `xfail` scoped to
`raises=NotImplementedError`. This gives the harness three guarantees:

1. **Green now.** While the stub raises `NotImplementedError`, the oracle is
   reported `xfailed`; the suite is green and runnable today.
2. **No silent rot.** The marker absorbs *only* `NotImplementedError`. A bug in
   the oracle itself raises something else and surfaces as a real `FAILED`.
3. **Self-removal.** When F0-T2x implements the module, a correct oracle
   *passes* — but `xfail_strict = true` turns that `XPASS` into a **failure**.
   The run goes red until the owning sub-task removes the `@awaiting` marker.
   The scaffold cannot be left behind.

The `meta/` layer is the counterweight: genuinely green tests that pin the
locked F0-T2a constants and prove the stubs are wired (so the `xfail`s fail for
the right reason).

## Ownership handoff

| Marker | Owner | Module |
| :-- | :-- | :-- |
| `@awaiting("F0-T2b")` | F0-T2b | `recipe.py` parser |
| `@awaiting("F0-T2d")` | F0-T2d | `dna_trace.py`, `gold_writer.py` |
| `@awaiting("F0-T4b")` | F0-T4b | `mic_standardize.py` (data-loader stage) |

When you implement one of those modules: replace the stub, run the suite, watch
the now-`XPASS` oracles turn the run red, remove their `@awaiting` markers, then
satisfy the mutation gate (`tools/run_mutation.sh`) — kill-rate ≥ 90 % critical,
≥ 85 % core (TESTING_DOCTRINE §3).
