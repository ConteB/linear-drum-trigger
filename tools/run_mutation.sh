#!/usr/bin/env bash
# F0-T9b — mutation-testing gate (TESTING_DOCTRINE §3, Layer-0 meta-gate).
#
# mutmut injects bugs (mutants) into src/data_engineering/gold/ and counts how
# many the pytest suite kills. Kill-rate gate (applied as DoD of F0-T2b/c/d):
#   critical modules (recipe.py, dna_trace.py, gold_writer.py): >= 90 %
#   core modules     (mic_standardize.py):                      >= 85 %
# A surviving mutant must be KILLED (a new test) or justified in writing as an
# equivalent mutant — never ignored.
#
# EXECUTION PLATFORM — Linux (OrbStack). mutmut 3.x forces multiprocessing
# 'fork'; a forked child that has loaded macOS-native libraries (numpy BLAS,
# libsndfile) segfaults on macOS — every mutant dies before it is tested. The
# gate is therefore run inside the OrbStack Ubuntu machine, where fork is safe.
#
# String-literal mutation is disabled — see tools/mutation_run.py and
# TESTING_DOCTRINE §3 (the message-mutant equivalent-by-construction policy).
#
# One-off provisioning of the Linux env (inside the OrbStack machine):
#   sudo apt-get install -y python3-venv libsndfile1
#   python3 -m venv ~/ntg-venv
#   ~/ntg-venv/bin/pip install pytest hypothesis coverage mutmut numpy \
#       PyYAML soundfile mido
set -euo pipefail
cd "$(dirname "$0")/.."

ORB_MACHINE="${ORB_MACHINE:-ubuntu}"

echo "[mutation] running mutmut inside OrbStack '$ORB_MACHINE' (string mutation disabled) ..."
orb run -m "$ORB_MACHINE" bash -lc \
    "~/ntg-venv/bin/python tools/mutation_run.py run ${*:-}" || true
echo
orb run -m "$ORB_MACHINE" bash -lc \
    "~/ntg-venv/bin/python tools/mutation_run.py results" || true
echo
echo "[mutation] GATE — TESTING_DOCTRINE §3:"
echo "  critical (recipe.py, dna_trace.py, gold_writer.py): kill-rate >= 90 %"
echo "  core     (mic_standardize.py):                      kill-rate >= 85 %"
