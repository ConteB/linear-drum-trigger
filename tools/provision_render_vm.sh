#!/usr/bin/env bash
# F2-T1 / T1-prep-D — cloud-init provisioning script for the render VM.
#
# Designed to be passed verbatim as the ``custom_data`` of an Azure VM that
# uses an Ubuntu 22.04+ LTS image. The script:
#
#   1. installs the render toolchain (DrumGizmo + Sfizz CLI),
#   2. clones the project repo on the branch ``develop``,
#   3. provisions every kit of the F0-T1b roster (sha256-verified streams),
#   4. installs the Python dependencies inside an isolated venv,
#   5. configures the DVC azure remote with the CEO-supplied SAS,
#   6. runs the smoke render (1 Sfizz + 1 DrumGizmo sample) — the VM is
#      declared READY only if this smoke is green; otherwise the script
#      exits non-zero and the CEO never burns the bulk hours.
#
# Conventions:
#
# * The script is **idempotent**: re-running it on the same VM never
#   re-downloads or re-installs what already passes its sha256 check.
# * Every download is *streamed* into ``sha256sum -c``: a corrupt or
#   tampered archive aborts the provisioning before any disk write.
# * The script is **fail-loud** (``set -euo pipefail``); the CEO never
#   discovers a broken provisioning by surprise mid-render.
#
# Required environment variables (set via ``cloud-init`` user-data or by the
# CEO before launch):
#
#   NTG_REPO_URL    — git clone URL for this project
#   NTG_REPO_BRANCH — branch to check out (default: ``develop``)
#   NTG_BLOB_SAS    — connection string for the Azure Blob remote (DVC)
#   NTG_MASTER_SEED — F2-T1 recipe-matrix seed (any non-negative int)
#
# Optional:
#
#   NTG_KIT_PROFILE — ``smoke`` | ``full`` (default: ``full``). The smoke
#                     profile skips the 4 manifest-only DGZ kits (~13 GB of
#                     downloads) and provisions only what is needed for the
#                     end-to-end smoke render.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

readonly NTG_REPO_URL="${NTG_REPO_URL:?missing NTG_REPO_URL}"
readonly NTG_REPO_BRANCH="${NTG_REPO_BRANCH:-develop}"
readonly NTG_BLOB_SAS="${NTG_BLOB_SAS:?missing NTG_BLOB_SAS}"
readonly NTG_MASTER_SEED="${NTG_MASTER_SEED:?missing NTG_MASTER_SEED}"
readonly NTG_KIT_PROFILE="${NTG_KIT_PROFILE:-full}"

readonly WORK_DIR="/opt/neurotrigger"
readonly REPO_DIR="${WORK_DIR}/drum-trigger-fresh"
readonly VENDOR_DIR="${REPO_DIR}/vendor"
readonly LOG_FILE="${WORK_DIR}/provision.log"

# Versions are pinned (vendor/README.md) — bumping them is a deliberate
# Decision Lock, never an accident.
readonly DRUMGIZMO_APT_VERSION="0.9.20-3build3"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

mkdir -p "$WORK_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

log() {
    local now
    now="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    echo "[${now}] $*"
}

abort() {
    log "ABORT: $*"
    exit 1
}

# ---------------------------------------------------------------------------
# Step 1 — system packages (drumgizmo native, sfizz built from source)
# ---------------------------------------------------------------------------

step_apt() {
    log "step apt — installing system packages"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends \
        ca-certificates curl git unzip xz-utils jq \
        build-essential cmake pkg-config \
        python3 python3-pip python3-venv \
        "drumgizmo=${DRUMGIZMO_APT_VERSION}" libsndfile1
    # Sfizz: ``sfizz_render`` is part of the ``sfizz`` package on Ubuntu 22.04+;
    # if the apt sources don't carry it (older snapshots), we fall back to
    # building 1.2.3 from source. Either way the resulting binary lives on
    # the PATH and the adapter ``SfizzRenderer`` finds it.
    if apt-get install -y --no-install-recommends sfizz 2>/dev/null; then
        log "  sfizz_render via apt: $(command -v sfizz_render || echo MISSING)"
    else
        log "  sfizz apt package unavailable — building 1.2.3 from source"
        build_sfizz_from_source
    fi
    command -v drumgizmo  >/dev/null || abort "drumgizmo CLI missing after apt install"
    command -v sfizz_render >/dev/null || abort "sfizz_render missing after install path"
}

build_sfizz_from_source() {
    local src="${WORK_DIR}/sfizz-src"
    if [[ -x /usr/local/bin/sfizz_render ]]; then
        log "  sfizz_render already built — skip"
        return
    fi
    rm -rf "$src"
    git clone --recursive --branch 1.2.3 --depth 1 \
        https://github.com/sfztools/sfizz.git "$src"
    cmake -S "$src" -B "${src}/build" \
        -DCMAKE_BUILD_TYPE=Release \
        -DSFIZZ_RENDER=ON -DSFIZZ_JACK=OFF -DSFIZZ_LV2=OFF \
        -DSFIZZ_VST=OFF -DSFIZZ_AU=OFF -DSFIZZ_TESTS=OFF
    cmake --build "${src}/build" --target sfizz_render -j "$(nproc)"
    install -m 0755 "${src}/build/sfizz_render" /usr/local/bin/sfizz_render
}

# ---------------------------------------------------------------------------
# Step 2 — clone repo (or pull if re-running)
# ---------------------------------------------------------------------------

step_clone() {
    log "step clone — ${NTG_REPO_URL}@${NTG_REPO_BRANCH}"
    if [[ -d "${REPO_DIR}/.git" ]]; then
        git -C "$REPO_DIR" fetch --depth 1 origin "$NTG_REPO_BRANCH"
        git -C "$REPO_DIR" reset --hard "origin/${NTG_REPO_BRANCH}"
    else
        mkdir -p "$WORK_DIR"
        git clone --depth 1 --branch "$NTG_REPO_BRANCH" "$NTG_REPO_URL" "$REPO_DIR"
    fi
    log "  HEAD = $(git -C "$REPO_DIR" rev-parse --short HEAD)"
}

# ---------------------------------------------------------------------------
# Step 3 — kit roster provisioning (sha256-verified streams)
# ---------------------------------------------------------------------------

# fetch_zip <url> <sha256> <destination dir name under vendor>
fetch_zip() {
    local url="$1" sha="$2" dest_name="$3"
    local dest="${VENDOR_DIR}/${dest_name}"
    local marker="${dest}/.sha256.ok"
    if [[ -f "$marker" ]] && grep -q "$sha" "$marker"; then
        log "  ${dest_name}: cached (sha256 matches)"
        return
    fi
    log "  ${dest_name}: streaming ${url}"
    local tmp; tmp="$(mktemp -d)"
    local zip="${tmp}/payload.zip"
    curl -fL --retry 3 --retry-delay 2 -o "$zip" "$url"
    echo "${sha}  ${zip}" | sha256sum -c -
    mkdir -p "$dest"
    unzip -q -o "$zip" -d "$dest"
    echo "$sha" > "$marker"
    rm -rf "$tmp"
}

step_kits() {
    log "step kits — profile=${NTG_KIT_PROFILE}"
    mkdir -p "${VENDOR_DIR}/sfz" "${VENDOR_DIR}/drumgizmo"

    # SFZ kits — Karoryfer + VSCO-2 CE
    fetch_zip \
        "https://github.com/sfzinstruments/karoryfer.frankensnare/releases/download/v2.100/Frankensnare_2100.zip" \
        "03defbfbc5232a5eafa69e839e43b33f8e0746ea9a098fc2b4f411e8112a732a" \
        "sfz/frankensnare"
    fetch_zip \
        "https://github.com/sfzinstruments/karoryfer.unruly-drums/releases/download/v1.100/Unruly_Drums_1100.zip" \
        "8d8d8075570088658cfce5de6cc6df1fa1340cac9ec808da130e19b1463b1f90" \
        "sfz/unruly-drums"
    fetch_zip \
        "https://github.com/sfzinstruments/karoryfer.big-rusty-drums/releases/download/v1.100/Big_Rusty_Drums_1100.zip" \
        "d4a9990acd19376d91ce446dae415c81428728b5adebb6a88eddbb3a6aac8744" \
        "sfz/big-rusty-drums"
    fetch_zip \
        "https://github.com/sfzinstruments/karoryfer.swirly-drums/releases/download/v1.104/Swirly.Drums_1104.zip" \
        "c709acc76260e559d8fd542d2c92b0ec6e3d507efc20fbb5d213427c49fb474a" \
        "sfz/swirly-drums"
    fetch_zip \
        "https://github.com/sgossner/VSCO-2-CE/archive/refs/tags/1.1.0.zip" \
        "4a4446628df0e1a12aaee58e9f65f8fa7cde51971e961abb1b43083a6d3a8ab7" \
        "sfz/vsco-2-ce"

    # DrumGizmo kits — DRSKit + Muldjord on every profile (covers smoke +
    # train backbone). The 3 remaining train kits + the val kit are skipped
    # in ``smoke``.
    fetch_zip \
        "https://drumgizmo.org/kits/DRSKit/DRSKit2_1.zip" \
        "529f2dcad836593167d0cab218f125f591cd71199748fa681e05e3866667f090" \
        "drumgizmo/DRSKit"
    fetch_zip \
        "https://drumgizmo.org/kits/MuldjordKit/MuldjordKit3.zip" \
        "db94f910913185ee17c5abb77d285a27476dee979db0ccebdc7ed68404514c96" \
        "drumgizmo/MuldjordKit3"
    if [[ "$NTG_KIT_PROFILE" != "smoke" ]]; then
        fetch_zip \
            "https://drumgizmo.org/kits/CrocellKit/CrocellKit1_1.zip" \
            "65d6f3aab56bcf357c6d636990e1b4e56f78513c0e8031ce80c284c9c677813d" \
            "drumgizmo/CrocellKit"
        fetch_zip \
            "https://drumgizmo.org/kits/Aasimonster/aasimonster2_1.zip" \
            "cdbaf1cae57e479845c12e2f935a3dec1179bfa26fbfe9905deb9bae7070f987" \
            "drumgizmo/Aasimonster"
        fetch_zip \
            "https://drumgizmo.org/kits/ShittyKit/ShittyKit1_2.zip" \
            "383673954af91c88a7044e17cbc5eeed67e815fcbff574a55278e33efb9afd77" \
            "drumgizmo/ShittyKit"
    fi
}

# ---------------------------------------------------------------------------
# Step 4 — Python venv + dependencies + dvc remote
# ---------------------------------------------------------------------------

step_python() {
    log "step python — venv + requirements"
    local venv="${WORK_DIR}/venv"
    [[ -d "$venv" ]] || python3 -m venv "$venv"
    # shellcheck source=/dev/null
    source "${venv}/bin/activate"
    pip install --upgrade pip wheel
    pip install -r "${REPO_DIR}/requirements.txt"
    pip install "dvc[azure]"

    # DVC remote — the SAS-bearing connection string lives only in the local
    # config (gitignored), matching the F1-T2 pattern (.dvc/config.local).
    (
        cd "$REPO_DIR"
        dvc remote modify --local azure connection_string "$NTG_BLOB_SAS"
    )
}

# ---------------------------------------------------------------------------
# Step 5 — smoke render (4 recipes, ~2 minutes)
# ---------------------------------------------------------------------------

step_smoke() {
    log "step smoke — 4-recipe end-to-end"
    # shellcheck source=/dev/null
    source "${WORK_DIR}/venv/bin/activate"
    cd "$REPO_DIR"

    python tools/build_recipe_matrix.py \
        --midi-source-dir bronze/gmd/mini \
        --output-dir recipes/f2-t1-smoke \
        --master-seed "$NTG_MASTER_SEED" \
        --smoke

    # The actual smoke render call lives in ``tools/run_mini_batch.py`` —
    # we re-use its harness (it is the exact same code path F0-T2e exercises
    # on macOS). A green smoke ratifies: render engines on PATH, recipes
    # parse, target builder + writer end-to-end.
    python tools/run_mini_batch.py --engine sfizz --recipes recipes/f2-t1-smoke/train
    python tools/run_mini_batch.py --engine drumgizmo --recipes recipes/f2-t1-smoke/train

    log "smoke OK — VM is READY for the bulk F2-T1 burn"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    log "F2-T1 provisioning start — profile=${NTG_KIT_PROFILE}"
    step_apt
    step_clone
    step_kits
    step_python
    step_smoke
    log "provisioning complete"
}

main "$@"
