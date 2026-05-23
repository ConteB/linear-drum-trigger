#!/usr/bin/env bash
# F2-T1 — emergency kill switch for the Azure render burn.
#
# When the credit-monitoring threshold trips ($100 → eval, $40 → stop,
# $10 → close everything — MASTER_SCHEDULING §5), the CEO runs this
# script. It is:
#
# * **idempotent** — repeated runs converge to the same final state;
# * **fail-soft on missing resources** — every command tolerates "already
#   deallocated / already deleted" so we can spam-press the button;
# * **logged** — every action is timestamped to ``$HOME/.neurotrigger/
#   azure_kill.log`` so a forensic trail survives.
#
# Modes:
#
#   ./azure_kill.sh deallocate            # stop billing on the render VM
#                                         # (compute stops; storage stays)
#   ./azure_kill.sh teardown              # also delete the VM, NIC, disk
#                                         # (Blob/Soft-Delete kept — recoverable)
#   ./azure_kill.sh nuclear               # last-resort: delete the entire
#                                         # resource group (Blob included)
#
# Required environment variables (CEO sets them in shell rc or ad-hoc):
#
#   AZ_RG     — Azure Resource Group (e.g. ``rg-neurotrigger``)
#   AZ_VM     — VM name (e.g. ``vm-render-d16s``)
#
# Confirms a *typed magic word* before ``teardown`` and ``nuclear`` so a
# stray shell history recall cannot accidentally vapourise the data.

set -uo pipefail
# Note: NOT `set -e` — we want fail-soft on individual `az` calls.

readonly LOG_DIR="${HOME}/.neurotrigger"
readonly LOG_FILE="${LOG_DIR}/azure_kill.log"
mkdir -p "$LOG_DIR"

log() {
    local now; now="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    echo "[${now}] $*" | tee -a "$LOG_FILE"
}

require_env() {
    local name="$1"
    if [[ -z "${!name:-}" ]]; then
        log "ABORT: missing env var ${name}"
        exit 2
    fi
}

require_az() {
    if ! command -v az >/dev/null 2>&1; then
        log "ABORT: Azure CLI 'az' not found on PATH"
        exit 3
    fi
}

confirm_magic_word() {
    local action="$1" expected="$2"
    echo "About to ${action}. Type the magic word '${expected}' (without quotes) to proceed:"
    local word
    read -r word
    if [[ "$word" != "$expected" ]]; then
        log "magic word mismatch — aborting ${action}"
        exit 4
    fi
}

mode_balance_check() {
    # Print the current spend snapshot so the CEO can see what triggered
    # the kill. No teardown — read-only.
    log "balance check (read-only)"
    az consumption usage list --top 5 --output table 2>>"$LOG_FILE" || true
}

mode_deallocate() {
    log "deallocate ${AZ_VM} in ${AZ_RG}"
    az vm deallocate --resource-group "$AZ_RG" --name "$AZ_VM" --no-wait \
        2>>"$LOG_FILE" || log "  vm deallocate failed (already stopped?)"
}

mode_teardown() {
    confirm_magic_word "teardown VM + NIC + disk" "TEARDOWN"
    log "teardown VM ${AZ_VM} (compute resources only)"
    az vm delete --resource-group "$AZ_RG" --name "$AZ_VM" --yes --no-wait \
        2>>"$LOG_FILE" || log "  vm delete failed"
    # NIC and OS disk are named after the VM by default — best-effort delete.
    az network nic delete --resource-group "$AZ_RG" --name "${AZ_VM}VMNic" --no-wait \
        2>>"$LOG_FILE" || log "  nic delete failed (different name?)"
    log "  teardown queued; Blob Storage UNTOUCHED — Gold tar shards survive"
}

mode_nuclear() {
    confirm_magic_word "DELETE the ENTIRE resource group (Blob included!)" "NUCLEAR"
    log "NUCLEAR — deleting RG ${AZ_RG}"
    az group delete --name "$AZ_RG" --yes --no-wait \
        2>>"$LOG_FILE" || log "  group delete failed"
}

main() {
    require_az
    require_env AZ_RG
    require_env AZ_VM

    local mode="${1:-help}"
    case "$mode" in
        balance)    mode_balance_check ;;
        deallocate) mode_deallocate ;;
        teardown)   mode_teardown ;;
        nuclear)    mode_nuclear ;;
        help|--help|-h|"")
            cat <<'EOF'
F2-T1 emergency kill switch — order from gentle to nuclear:

  balance    print spend snapshot (read-only — no resource touched)
  deallocate stop the render VM (compute billing halted; data preserved)
  teardown   delete VM + NIC + disk (Blob Storage UNTOUCHED — Gold survives)
  nuclear    delete the entire resource group (irrecoverable — Blob too)

Environment: AZ_RG, AZ_VM must be set.
Logged to ~/.neurotrigger/azure_kill.log
EOF
            ;;
        *)
            log "unknown mode: ${mode}"
            exit 1
            ;;
    esac
}

main "$@"
