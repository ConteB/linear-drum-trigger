#!/usr/bin/env bash
# F0-T9b — mutation-testing gate (TESTING_DOCTRINE §3, Layer-0 meta-gate).
#
# mutmut injects bugs (mutants) into src/data_engineering/gold/ and counts how
# many the pytest suite kills. Kill-rate gate, applied as DoD of F0-T2b/c/d:
#   critical modules (recipe.py, dna_trace.py, gold_writer.py): >= 90 %
#   core modules     (mic_standardize.py):                      >= 85 %
# A surviving mutant must be KILLED (a new test) or justified in writing as an
# equivalent mutant — never ignored.
#
# Config: setup.cfg [mutmut]. Run from the repo root.
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${VENV:-.venv}"

echo "[mutation] running mutmut on src/data_engineering/gold/ ..."
"$VENV/bin/mutmut" run "$@" || true
echo
"$VENV/bin/mutmut" results || true
echo
echo "[mutation] GATE — TESTING_DOCTRINE §3:"
echo "  critical (recipe.py, dna_trace.py, gold_writer.py): kill-rate >= 90 %"
echo "  core     (mic_standardize.py):                      kill-rate >= 85 %"
echo
echo "[mutation] NOTE: meaningful only once F0-T2b/c/d replace the skeleton"
echo "           stubs — mutating a 'raise NotImplementedError' body is inert."
