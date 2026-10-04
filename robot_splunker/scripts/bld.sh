#!/usr/bin/env bash
# =============================================================================
# bld.sh — build EVERYTHING robot_splunker needs, from inside WSL2.
#
# Stages (run in this order; the first failure stops the build):
#   1. Preflight        – ROS 2 sourced, required tools present
#   2. Worlds           – worlds/*.world.yaml -> Gazebo .sdf + UE layout .json,
#                         plus a xacro -> URDF sanity check (check_urdf)
#   3. ROS 2 packages   – symlink src/ into ~/robot_splunker_ws, rosdep, colcon build
#   4. Unreal project   – compiles unreal/SplunkerViz (Windows) via bld_ue.ps1
#   5. Tests            – colcon test + colcon test-result (only with --test)
#   6. Summary          – table of stage results and durations
#
# Usage:     ./scripts/bld.sh [TARGETS] [OPTIONS]      (see usage() below)
# Env vars:  UE_ROOT (scripts/.env), WS_DIR, ROS_DISTRO
# Creates:   ~/robot_splunker_ws/{src,build,install,log}, build_artifacts/,
#            generated world files, unreal/SplunkerViz/{Binaries,Intermediate},
#            ~/.robot_splunker/run/logs/build-<timestamp>.log
# Exit codes: 0 success, 1 a stage failed, 2 bad option
# Example:   ./scripts/bld.sh --ros --test
# =============================================================================

# -e: stop on the first failing command; -u: unset variables are errors;
# -o pipefail: a pipeline fails if any command in it fails (needed for `| tee`).
set -euo pipefail

# ---- Usage text ------------------------------------------------------------------
usage() {
    cat <<'EOF'
Usage: bld.sh [TARGETS] [OPTIONS]

Builds every robot_splunker artifact: the generated world files, the ROS 2
packages (colcon, in ~/robot_splunker_ws on the Linux filesystem) and the
Unreal Engine 5 project (compiled on Windows through WSL interop).
With no TARGETS, all three targets are built.

Targets:
  --worlds                 Regenerate Gazebo SDF + UE layout JSON from worlds/*.world.yaml
                           and validate the robot xacro -> URDF.
  --ros                    Build the ROS 2 packages (rosdep + colcon build).
  --ue                     Build the Unreal project (needs UE_ROOT in scripts/.env).

Options:
  --clean                  Delete build/ install/ log/, build_artifacts/ and UE
                           Binaries/ Intermediate/ before building.     (default: off)
  --test                   Run colcon test + colcon test-result afterwards. (default: off)
  --packages-select P...   Only build these ROS packages (list ends at the next option).
  --release                CMake Release build.                          (default: RelWithDebInfo)
  --no-rosdep              Skip `rosdep install`.                        (default: run it)
  -j, --jobs N             colcon parallel workers.                      (default: nproc)
  -h, --help               Show this help and exit.

Environment (scripts/.env or shell):
  UE_ROOT                  Windows path to the UE install, e.g. 'C:\Program Files\Epic Games\UE_5.5'.
                           If empty, the --ue stage is skipped with a warning.
  WS_DIR                   colcon workspace (default: ~/robot_splunker_ws)
  ROS_DISTRO               default: jazzy

Examples:
  ./scripts/bld.sh                         # build everything
  ./scripts/bld.sh --ros --test            # ROS packages + unit tests only
  ./scripts/bld.sh --clean --ros --packages-select robot_splunker_exploration

Related scripts: setup_wsl.sh (install deps), up.sh (start), dn.sh (stop), bld_ue.ps1 (UE from Windows)
EOF
}

# ---- Parse options BEFORE any side effects -----------------------------------------
DO_WORLDS=0; DO_ROS=0; DO_UE=0; ANY_TARGET=0
DO_CLEAN=0; DO_TEST=0; DO_ROSDEP=1
BUILD_TYPE="RelWithDebInfo"
JOBS="$(nproc 2>/dev/null || echo 4)"
PACKAGES=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --worlds)  DO_WORLDS=1; ANY_TARGET=1 ;;
        --ros)     DO_ROS=1;    ANY_TARGET=1 ;;
        --ue)      DO_UE=1;     ANY_TARGET=1 ;;
        --clean)   DO_CLEAN=1 ;;
        --test)    DO_TEST=1 ;;
        --release) BUILD_TYPE="Release" ;;
        --no-rosdep) DO_ROSDEP=0 ;;
        -j|--jobs)
            [[ $# -ge 2 ]] || { echo "Option $1 needs a number" >&2; usage; exit 2; }
            JOBS="$2"; shift ;;
        --packages-select)
            # Collect package names until the next option (anything starting with '-').
            shift
            while [[ $# -gt 0 && "$1" != -* ]]; do PACKAGES+=("$1"); shift; done
            [[ ${#PACKAGES[@]} -gt 0 ]] || { echo "--packages-select needs at least one package" >&2; usage; exit 2; }
            continue ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
    shift
done
# No explicit target means "build everything".
if [[ ${ANY_TARGET} -eq 0 ]]; then DO_WORLDS=1; DO_ROS=1; DO_UE=1; fi

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
load_env          # picks up UE_ROOT etc. from scripts/.env
mkdir -p "${LOG_DIR}"
BUILD_LOG="${LOG_DIR}/build-$(date +%Y%m%d-%H%M%S).log"

TOTAL=6
STAGE_NAMES=(); STAGE_RESULTS=(); STAGE_TIMES=()

# run_stage NAME FUNCTION — run FUNCTION in a subshell with `set -e` active, tee its
# output into the build log and record the result.
# FUNCTION exit codes: 0 = ok, 3 = skipped, anything else = failed.
# (A plain `if fn; then` would silently DISABLE set -e inside fn — a bash gotcha —
#  so we run it as a separate statement and read PIPESTATUS instead.)
run_stage() {
    local name="$1" fn="$2" t0=${SECONDS} rc
    set +e
    ( set -e; "${fn}" ) 2>&1 | tee -a "${BUILD_LOG}"
    rc=${PIPESTATUS[0]}
    set -e
    STAGE_NAMES+=("${name}")
    STAGE_TIMES+=("$(( SECONDS - t0 ))s")
    case ${rc} in
        0) STAGE_RESULTS+=("OK") ;;
        3) STAGE_RESULTS+=("skipped") ;;
        *) STAGE_RESULTS+=("FAILED")
           print_summary
           die "Stage '${name}' failed (exit ${rc}). Full log: ${BUILD_LOG}" ;;
    esac
}

# print_summary — table of every stage that ran.
print_summary() {
    local i
    printf '\n%-22s %-9s %s\n' "STAGE" "RESULT" "TIME"
    printf '%-22s %-9s %s\n'   "-----" "------" "----"
    for i in "${!STAGE_NAMES[@]}"; do
        printf '%-22s %-9s %s\n' "${STAGE_NAMES[$i]}" "${STAGE_RESULTS[$i]}" "${STAGE_TIMES[$i]}"
    done
    printf '\nBuild log: %s\n' "${BUILD_LOG}"
}

# ---- Optional: --clean ------------------------------------------------------------
# Removes previous build outputs so the next build starts from scratch.
if [[ ${DO_CLEAN} -eq 1 ]]; then
    info "Cleaning previous build outputs (--clean)"
    rm -rf "${WS_DIR}/build" "${WS_DIR}/install" "${WS_DIR}/log" "${REPO_DIR}/build_artifacts"
    rm -rf "${REPO_DIR}/unreal/SplunkerViz/Binaries" "${REPO_DIR}/unreal/SplunkerViz/Intermediate"
fi

# =============================================================================
# Stage functions (each runs in its own subshell via run_stage)
# =============================================================================

# ---- Step 1: Preflight ---------------------------------------------------------------
# Make sure ROS is installed and every tool used by the later stages exists, so we
# fail fast with a clear message instead of halfway through a long build.
stage_preflight() {
    step 1 ${TOTAL} "Preflight checks"
    source_ros
    require_cmd colcon rosdep python3
    # xacro is a ROS package; its CLI is on PATH once ROS is sourced.
    require_cmd xacro
    python3 -c "import yaml" 2>/dev/null || die "python3-yaml missing (sudo apt install python3-yaml)."
    info "ROS_DISTRO=${ROS_DISTRO}  WS_DIR=${WS_DIR}  BUILD_TYPE=${BUILD_TYPE}  JOBS=${JOBS}"
    ok "Preflight passed."
}

# ---- Step 2: Generated world files + URDF check -----------------------------------
# generate_world.py turns each worlds/*.world.yaml into BOTH the Gazebo SDF and the
# Unreal layout JSON, so the two simulators always show the same walls.
stage_worlds() {
    step 2 ${TOTAL} "Generate worlds and validate robot URDF"
    [[ ${DO_WORLDS} -eq 1 ]] || { info "Not requested."; exit 3; }
    source_ros
    python3 "${SCRIPTS_DIR}/generate_world.py"

    # Expand the xacro once outside colcon: xacro errors are much easier to read here.
    mkdir -p "${REPO_DIR}/build_artifacts"
    local urdf="${REPO_DIR}/build_artifacts/robot_splunker.urdf"
    xacro "${REPO_DIR}/src/robot_splunker_description/urdf/robot_splunker.urdf.xacro" > "${urdf}"
    info "Wrote ${urdf}"
    # check_urdf (liburdfdom-tools) prints the link tree and fails on a broken model.
    if command -v check_urdf >/dev/null 2>&1; then
        check_urdf "${urdf}"
    else
        warn "check_urdf not installed (sudo apt install liburdfdom-tools); skipping URDF tree check."
    fi
    ok "Worlds generated and URDF valid."
}

# ---- Step 3: ROS 2 packages -----------------------------------------------------------
stage_ros() {
    step 3 ${TOTAL} "Build ROS 2 packages"
    [[ ${DO_ROS} -eq 1 ]] || { info "Not requested."; exit 3; }
    source_ros

    # 3a. The repo stays on the Windows drive (UE needs unreal/ there), but colcon
    #     builds on the Linux filesystem for speed. We link the repo's src/ into the
    #     workspace's src/ so colcon finds the packages.
    mkdir -p "${WS_DIR}/src"
    local link="${WS_DIR}/src/robot_splunker"
    if [[ -e "${link}" && ! -L "${link}" ]]; then
        die "${link} exists and is not a symlink; move it away first."
    fi
    ln -sfn "${REPO_DIR}/src" "${link}"     # -n: replace an existing link instead of nesting into it
    info "Linked ${link} -> ${REPO_DIR}/src"

    cd "${WS_DIR}"

    # 3b. Install any system dependencies declared in the package.xml files.
    #     -r: keep going if one key can't be resolved; --ignore-src: our own packages aren't apt packages.
    if [[ ${DO_ROSDEP} -eq 1 ]]; then
        info "rosdep install (may ask for your sudo password)"
        rosdep install --from-paths src --ignore-src -y -r --rosdistro "${ROS_DISTRO}"
    else
        info "Skipping rosdep (--no-rosdep)."
    fi

    # 3c. colcon build.
    #     --symlink-install: launch/config/python files are symlinked, so edits take
    #       effect without rebuilding.
    #     --cmake-args must come LAST because it swallows the remaining arguments.
    local args=(build --symlink-install --parallel-workers "${JOBS}")
    if [[ ${#PACKAGES[@]} -gt 0 ]]; then args+=(--packages-select "${PACKAGES[@]}"); fi
    args+=(--cmake-args "-DCMAKE_BUILD_TYPE=${BUILD_TYPE}")
    info "colcon ${args[*]}"
    colcon "${args[@]}"
    ok "ROS 2 packages built into ${WS_DIR}/install"
}

# ---- Step 4: Unreal project (Windows) -----------------------------------------------
# UE5 runs on Windows, so we hand the build to PowerShell through WSL interop.
# bld_ue.ps1 calls UE's Build.bat for the SplunkerVizEditor target.
stage_ue() {
    step 4 ${TOTAL} "Build Unreal project (Windows)"
    [[ ${DO_UE} -eq 1 ]] || { info "Not requested."; exit 3; }
    if [[ -z "${UE_ROOT:-}" ]]; then
        warn "UE_ROOT is not set (scripts/.env). Skipping the Unreal build."
        exit 3
    fi
    if ! is_wsl || ! command -v powershell.exe >/dev/null 2>&1; then
        warn "Not running in WSL with Windows interop; build UE from Windows with scripts\\bld_ue.ps1."
        exit 3
    fi
    # UE (a Windows program) can only build the project if it lives on a Windows drive.
    if [[ "${REPO_DIR}" != /mnt/* ]]; then
        warn "Repo is on the Linux filesystem (${REPO_DIR}); UE needs it on a Windows drive. Skipping."
        exit 3
    fi
    # wslpath -w converts /mnt/c/... into C:\... which Windows tools need.
    local ps1_win; ps1_win="$(wslpath -w "${SCRIPTS_DIR}/bld_ue.ps1")"
    local extra=()
    [[ ${DO_CLEAN} -eq 1 ]] && extra+=(-Clean)
    # Run from a Windows directory so cmd/powershell don't complain about a UNC working dir.
    cd "${REPO_DIR}"
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${ps1_win}" \
        -UeRoot "${UE_ROOT}" -Config Development "${extra[@]}"
    ok "Unreal project built."
}

# ---- Step 5: Tests -----------------------------------------------------------------------
stage_test() {
    step 5 ${TOTAL} "Run tests"
    [[ ${DO_TEST} -eq 1 ]] || { info "Not requested (use --test)."; exit 3; }
    source_ros
    source_ws          # tests import our installed packages
    cd "${WS_DIR}"
    local args=(test --parallel-workers "${JOBS}")
    if [[ ${#PACKAGES[@]} -gt 0 ]]; then args+=(--packages-select "${PACKAGES[@]}"); fi
    colcon "${args[@]}"
    # colcon test always exits 0; test-result is what reports failures.
    colcon test-result --verbose
    ok "All tests passed."
}

# =============================================================================
# Main: run the stages in order
# =============================================================================
info "Build log: ${BUILD_LOG}"
run_stage "1 preflight"       stage_preflight
run_stage "2 worlds+urdf"     stage_worlds
run_stage "3 ros2 packages"   stage_ros
run_stage "4 unreal project"  stage_ue
run_stage "5 tests"           stage_test

# ---- Step 6: Summary -------------------------------------------------------------------
step 6 ${TOTAL} "Summary"
print_summary
ok "Build finished. Next: ./scripts/up.sh explore --ue"
