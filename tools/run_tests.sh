#!/usr/bin/env bash
# F0-T9b — F0 pipeline test-harness runner (TESTING_DOCTRINE §6).
# Runs the pytest suite inside the project venv. Extra args pass through, e.g.:
#   tools/run_tests.sh -m critical          # only the critical-module oracles
#   tools/run_tests.sh tests/meta            # only the Layer-0 self-check
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${VENV:-.venv}"
if [[ ! -x "$VENV/bin/python" ]]; then
    echo "error: venv not found at $VENV — create it with:" >&2
    echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt" >&2
    exit 1
fi
exec "$VENV/bin/python" -m pytest "$@"
