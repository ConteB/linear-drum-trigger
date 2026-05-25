#!/usr/bin/env bash
# Continua loss competition con i preset rimanenti B C D.
# Run after A is done. Each preset = ~22 min training + ~30s listening.
set -uo pipefail
# NB: NO `set -e` — `mini_l3_train.py` returns 1 when val_F is below the
# gate (which is the expected outcome here, since we're FAR below the
# gate). Without removing -e the script aborts after the training step.

PRESETS=(C D)
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

  echo "==========================================================================" | tee -a "${LOG}"
  echo "[loss-comp] PRESET=${PRESET}  RUN_ID=${RUN_ID}  $(date '+%H:%M:%S')" | tee -a "${LOG}"
  echo "==========================================================================" | tee -a "${LOG}"

  .venv/bin/python -u tools/mini_l3_train.py \
    --loss-preset "${PRESET}" \
    "${COMMON_ARGS[@]}" \
    --run-id "${RUN_ID}" \
    --save-to "${CKPT}" \
    >> "${LOG}" 2>&1

  echo "[loss-comp] training ${PRESET} done — running listening test…" >> "${LOG}"

  .venv/bin/python -u tools/listening_test_shittykit.py \
    --checkpoint "${CKPT}" \
    --run-id "loss-${PRESET}-2026-05-25" \
    > "logs/listening-${PRESET}-2026-05-25.log" 2>&1

  echo "[loss-comp] PRESET=${PRESET} complete." >> "${LOG}"
done

echo "[loss-comp] ALL DONE  $(date '+%H:%M:%S')"
