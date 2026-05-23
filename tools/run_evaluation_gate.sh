#!/usr/bin/env bash
# F0-T17 pre-F2-T3 evaluation gate orchestrator.
#
# Runs the three blocking modules in the spec's locked sequence:
#   1. data_audit         (informative — surfaces minority buses)
#   2. split_consistency  (BLOCKING F2-T3)
#   3. anti_leak_audit    (BLOCKING F2-T3 — Decision Lock A+C)
#
# The script exits 1 at the first module that refuses to pass. It is the
# operational check-list the CEO is expected to run before authorising the
# Azure A100 training spend (~$80/run).
#
# Spec: docs/methodology/F0-T17_STATISTICAL_TEST_PLAN.md §7.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    cat <<EOF >&2
usage: $(basename "$0") <gold-dir> [out-dir] [thresholds-path]

  <gold-dir>          Path to the Gold sample directory (post F2-T1).
                      May contain train/ and val/ subdirs or a flat layout.
  [out-dir]           Where the four report.{json,png} land.
                      Default: reports/evaluation_gate/
  [thresholds-path]   LOCKED thresholds file.
                      Default: src/evaluation/thresholds.yaml
EOF
    exit 2
fi

GOLD_DIR="$1"
OUT_DIR="${2:-reports/evaluation_gate}"
THRESHOLDS="${3:-src/evaluation/thresholds.yaml}"
SEED="${EVAL_GATE_SEED:-4242}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
PY="${PYTHON:-.venv/bin/python}"

if [[ ! -x "$PY" ]]; then
    echo "[evaluation_gate] error: $PY not executable — adjust \$PYTHON" >&2
    exit 3
fi

mkdir -p "$OUT_DIR"

echo "[evaluation_gate] gold_dir=$GOLD_DIR  out=$OUT_DIR  seed=$SEED"
echo "[evaluation_gate] thresholds=$THRESHOLDS"
echo

echo "── 1. data_audit ────────────────────────────────────────────────────"
"$PY" -m evaluation.data_audit \
    --gold-dir "$GOLD_DIR" \
    --thresholds "$THRESHOLDS" \
    --out "$OUT_DIR" \
    --seed "$SEED" \
    || { echo "[evaluation_gate] data_audit FAILED — see $OUT_DIR/data_audit.report.json" >&2; exit 1; }

echo
echo "── 2. split_consistency (BLOCKING) ──────────────────────────────────"
"$PY" -m evaluation.split_consistency \
    --gold-dir "$GOLD_DIR" \
    --thresholds "$THRESHOLDS" \
    --out "$OUT_DIR" \
    --seed "$SEED" \
    || { echo "[evaluation_gate] split_consistency FAILED — refuse F2-T3 launch" >&2; exit 1; }

echo
echo "── 3. anti_leak_audit (BLOCKING — Decision Lock A+C) ────────────────"
"$PY" -m evaluation.anti_leak_audit \
    --gold-dir "$GOLD_DIR" \
    --thresholds "$THRESHOLDS" \
    --out "$OUT_DIR" \
    --seed "$SEED" \
    || { echo "[evaluation_gate] anti_leak_audit FAILED — refuse F2-T3 launch" >&2; exit 1; }

echo
echo "[evaluation_gate] ALL GREEN — F2-T3 may proceed."
echo "[evaluation_gate] reports: $OUT_DIR/"
ls -la "$OUT_DIR"
