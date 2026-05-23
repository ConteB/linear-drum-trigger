#!/usr/bin/env bash
# Render the mix dataset in OOM-tolerant chunks.
#
# OrbStack ubuntu shares the macOS memory pool — under pressure the kernel
# OOM-kills the renderer after a few dozen samples. Solution: chunk the
# workload across multiple process invocations; each restart frees the
# accumulated arena. `--skip-existing` lets us resume right where the
# previous chunk left off.
#
# Usage:
#   tools/render_mix_chunked.sh <mix_dir> <out_dir> [--chunk N] [--seed S] [--k K]
#
# Defaults: chunk=40 sample, seed=20260524, k=2.
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: $0 <mix_dir> <out_dir> [--chunk N] [--seed S] [--k K]" >&2
    exit 1
fi
MIX_DIR="$1"; shift
OUT_DIR="$1"; shift

CHUNK=40
SEED=20260524
K=2
while [[ $# -gt 0 ]]; do
    case "$1" in
        --chunk) CHUNK="$2"; shift 2 ;;
        --seed)  SEED="$2";  shift 2 ;;
        --k)     K="$2";     shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 1 ;;
    esac
done

REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
PY="${PY:-$HOME/ntg-venv/bin/python}"
LOG="${RENDER_LOG:-/tmp/mix_render_chunked.log}"

echo "=== chunked render ===" | tee "$LOG"
echo "mix_dir : $MIX_DIR"      | tee -a "$LOG"
echo "out_dir : $OUT_DIR"      | tee -a "$LOG"
echo "chunk   : $CHUNK"        | tee -a "$LOG"
echo "seed    : $SEED"         | tee -a "$LOG"
echo "k       : $K"            | tee -a "$LOG"
echo                            | tee -a "$LOG"

iteration=0
while true; do
    iteration=$((iteration + 1))
    echo "--- chunk $iteration ---" | tee -a "$LOG"
    # Capture the output to inspect "generated/skipped" counters.
    if ! out=$(
        cd "$REPO" && \
        PYTHONPATH=src "$PY" -u tools/generate_local_rnd_dataset.py \
            --source-mix "$MIX_DIR" \
            --out "$OUT_DIR" \
            --k "$K" \
            --seed "$SEED" \
            --skip-existing \
            --chunk-size "$CHUNK" 2>&1
    ); then
        echo "[chunk $iteration] python exited non-zero — retrying after 3s" | tee -a "$LOG"
        echo "$out" | tee -a "$LOG"
        sleep 3
        continue
    fi
    echo "$out" | tee -a "$LOG"
    # Termination: the runner reported 0 generated AND 0 skipped → nothing
    # left to do. We also stop on "rendering 0 sample(s)" output.
    if echo "$out" | grep -qE "rendering 0 sample\(s\)"; then
        echo "=== complete ===" | tee -a "$LOG"
        break
    fi
    if echo "$out" | grep -qE "DONE — 0 generated, [0-9]+ skipped, 0 failed"; then
        echo "=== complete (all-skipped) ===" | tee -a "$LOG"
        break
    fi
done
