#!/usr/bin/env bash
# Loss design competition runner — CEO directive 2026-05-25 (post-listening-test).
#
# Lancia in sequenza 4 candidati di loss design sullo stesso pool mixed-5kit
# e produce un report comparativo. Tempo totale stimato: ~95 min.
#
# Usage:  bash tools/loss_competition.sh
#
# Outputs:
#   - logs/loss-competition-<preset>-2026-05-25.log
#   - artifacts/mini_l3_tcn_loss-<preset>.pt
#   - docs/gates/F0-T4c_MINI_L3/mini-l3-loss-<preset>-2026-05-25/report.html
#   - docs/gates/F0-T4c_MINI_L3/listening_test_loss-<preset>-2026-05-25/
set -euo pipefail

PRESETS=(A B C D)
COMMON_ARGS=(
  --preprocessing p1p2
  --tcn-channels 64
  --use-cosine-lr
  --early-stop-patience 30
  --grad-clip-max-norm 0.5
  --skip-nonfinite-step
  --baseline-only
  --epochs 150
)

mkdir -p logs artifacts

for PRESET in "${PRESETS[@]}"; do
  RUN_ID="mini-l3-loss-${PRESET}-2026-05-25"
  CKPT="artifacts/mini_l3_tcn_loss-${PRESET}.pt"
  LOG="logs/loss-competition-${PRESET}-2026-05-25.log"

  echo "=========================================================================="
  echo "[loss-comp] PRESET=${PRESET}  RUN_ID=${RUN_ID}  $(date '+%H:%M:%S')"
  echo "=========================================================================="

  .venv/bin/python -u tools/mini_l3_train.py \
    --loss-preset "${PRESET}" \
    "${COMMON_ARGS[@]}" \
    --run-id "${RUN_ID}" \
    --save-to "${CKPT}" \
    2>&1 | tee "${LOG}"

  echo "[loss-comp] training ${PRESET} done — running listening test…"

  .venv/bin/python -u tools/listening_test_shittykit.py \
    --checkpoint "${CKPT}" \
    --run-id "loss-${PRESET}-2026-05-25" \
    2>&1 | tee "logs/listening-${PRESET}-2026-05-25.log"

  echo "[loss-comp] PRESET=${PRESET} complete."
done

echo "=========================================================================="
echo "[loss-comp] ALL DONE  $(date '+%H:%M:%S')"
echo "=========================================================================="
