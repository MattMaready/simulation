#!/usr/bin/env bash
# =============================================================================
# common.sh — shared helpers for the robot_splunker scripts.
#
# This file is SOURCED by bld.sh, up.sh, dn.sh and setup_wsl.sh:
#     source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# It is not meant to be executed directly (doing so just prints this note).
#
# Variables it defines (all can be overridden from the environment):
#   REPO_DIR       repository root (the folder that contains scripts/ and src/)
#   WS_DIR         colcon workspace on the Linux filesystem   (~/robot_splunker_ws)
#   RUN_DIR        runtime state used by up.sh / dn.sh       (~/.robot_splunker/run)
#   LOG_DIR        $RUN_DIR/logs     — one log file per run / build
#   PID_FILE       $RUN_DIR/stack.pid — "PID PGID MODE" of the running launch
#   ROS_DISTRO     ROS 2 distribution (jazzy)
#   ROS_DOMAIN_ID  exported; default 42
#   UE_BRIDGE_PORT default 9090
#
# Functions it provides:
#   info/warn/err MSG...   coloured log lines (err goes to stderr)
#   die MSG...             err + exit 1
#   step N TOTAL MSG       prints a "Step N/TOTAL: MSG" banner
#   load_env               sources scripts/.env (UE_ROOT, ROS_DOMAIN_ID, ...) if present
#   source_ros             sources /opt/ros/$ROS_DISTRO/setup.bash
#   source_ws              sources $WS_DIR/install/setup.bash (fails if not built)
#   require_cmd CMD...     dies if any command is missing
#   is_wsl                 true when running inside WSL
#   pid_alive PID          true when the process exists
#   read_pid_file          sets STACK_PID, STACK_PGID, STACK_MODE from $PID_FILE
# =============================================================================

# ---- Guard: this file must be sourced, not executed -------------------------
# BASH_SOURCE[0] equals $0 only when the file is run directly.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cat <<'EOF'
common.sh is a helper library that is sourced by the other robot_splunker
scripts (bld.sh, up.sh, dn.sh, setup_wsl.sh). It has no options of its own.

Usage (inside another script):
    source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

Run one of these instead:
    ./scripts/setup_wsl.sh --help
    ./scripts/bld.sh --help
    ./scripts/up.sh --help
    ./scripts/dn.sh --help
EOF
    exit 0
fi

# ---- Paths --------------------------------------------------------------------
# Resolve the repo root from this file's location so the scripts work no matter
# which directory they are started from.
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "${SCRIPTS_DIR}/.." && pwd)}"

# Build on the Linux filesystem: colcon on /mnt/c (Windows drive) is very slow.
WS_DIR="${WS_DIR:-${HOME}/robot_splunker_ws}"

# Runtime state lives outside the repo so it never gets committed.
RUN_DIR="${RUN_DIR:-${HOME}/.robot_splunker/run}"
LOG_DIR="${RUN_DIR}/logs"
PID_FILE="${RUN_DIR}/stack.pid"

ROS_DISTRO="${ROS_DISTRO:-jazzy}"
UE_BRIDGE_PORT="${UE_BRIDGE_PORT:-9090}"

# ---- Logging helpers ----------------------------------------------------------
# Only use colours when writing to a terminal (keeps log files clean).
if [[ -t 1 ]]; then
    _C_INFO=$'\033[1;36m'; _C_WARN=$'\033[1;33m'; _C_ERR=$'\033[1;31m'
    _C_OK=$'\033[1;32m'; _C_STEP=$'\033[1;35m'; _C_OFF=$'\033[0m'
else
    _C_INFO=''; _C_WARN=''; _C_ERR=''; _C_OK=''; _C_STEP=''; _C_OFF=''
fi

# info MSG... — normal progress message.
info()  { printf '%s[INFO]%s  %s\n' "${_C_INFO}" "${_C_OFF}" "$*"; }
# ok MSG... — success message.
ok()    { printf '%s[ OK ]%s  %s\n' "${_C_OK}" "${_C_OFF}" "$*"; }
# warn MSG... — something is off but we can continue.
warn()  { printf '%s[WARN]%s  %s\n' "${_C_WARN}" "${_C_OFF}" "$*"; }
# err MSG... — error message to stderr (does not exit).
err()   { printf '%s[FAIL]%s  %s\n' "${_C_ERR}" "${_C_OFF}" "$*" >&2; }
# die MSG... — print an error and exit with status 1.
die()   { err "$*"; exit 1; }
# step N TOTAL MSG... — banner that matches the numbered "Step N" comments in each script.
step()  { local n="$1" t="$2"; shift 2; printf '\n%s==== Step %s/%s: %s ====%s\n' "${_C_STEP}" "${n}" "${t}" "$*" "${_C_OFF}"; }

# ---- Environment helpers ------------------------------------------------------

# load_env — read KEY=VALUE pairs from scripts/.env (if it exists) into the environment.
# `set -a` marks every variable assigned while sourcing for export, so child
# processes (ros2 launch, powershell.exe) see them too.
load_env() {
    local env_file="${SCRIPTS_DIR}/.env"
    if [[ -f "${env_file}" ]]; then
        # Strip Windows CR characters in case the file was saved with CRLF endings.
        set -a
        # shellcheck disable=SC1090
        source <(tr -d '\r' < "${env_file}")
        set +a
    fi
    export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
    UE_BRIDGE_PORT="${UE_BRIDGE_PORT:-9090}"
}

# source_ros — load the ROS 2 environment from /opt/ros/<distro>.
# ROS setup files reference unset variables, so `set -u` is paused while sourcing.
source_ros() {
    local setup="/opt/ros/${ROS_DISTRO}/setup.bash"
    [[ -f "${setup}" ]] || die "ROS 2 ${ROS_DISTRO} not found at ${setup}. Run ./scripts/setup_wsl.sh first."
    set +u
    # shellcheck disable=SC1090
    source "${setup}"
    set -u
}

# source_ws — load the built workspace overlay (our packages) on top of ROS.
source_ws() {
    local setup="${WS_DIR}/install/setup.bash"
    [[ -f "${setup}" ]] || die "Workspace not built (${setup} missing). Run ./scripts/bld.sh first (or up.sh --build)."
    set +u
    # shellcheck disable=SC1090
    source "${setup}"
    set -u
}

# require_cmd CMD... — exit with a helpful message if any command is missing.
require_cmd() {
    local c missing=0
    for c in "$@"; do
        if ! command -v "${c}" >/dev/null 2>&1; then
            err "Required command not found: ${c}"
            missing=1
        fi
    done
    [[ ${missing} -eq 0 ]] || die "Install the missing tools (./scripts/setup_wsl.sh installs everything)."
}

# is_wsl — returns 0 when running inside Windows Subsystem for Linux.
is_wsl() { grep -qi microsoft /proc/version 2>/dev/null; }

# pid_alive PID — returns 0 when a process with that PID exists.
pid_alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }

# read_pid_file — load STACK_PID / STACK_PGID / STACK_MODE from $PID_FILE.
# Returns 1 when there is no PID file.
read_pid_file() {
    STACK_PID=""; STACK_PGID=""; STACK_MODE=""
    [[ -f "${PID_FILE}" ]] || return 1
    read -r STACK_PID STACK_PGID STACK_MODE < "${PID_FILE}" || true
    return 0
}
