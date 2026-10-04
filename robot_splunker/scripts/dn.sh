#!/usr/bin/env bash
# =============================================================================
# dn.sh — stop everything up.sh started (and any stray robot_splunker processes).
#
# Steps:
#   1. Graceful stop: SIGINT to the launch process group (same as Ctrl-C), wait 10 s
#   2. Escalate: SIGTERM to the group (wait 5 s), then SIGKILL
#   3. Sweep strays: pkill known process names (TERM, then KILL)
#   4. Stop the ROS 2 CLI daemon (clears cached graph info)
#   5. Verify: nothing left running, UE bridge port is free
#   6. Optional: close Unreal on Windows (--ue)
#   7. Remove the PID file; optional log cleanup
#
# Safe to run when nothing is running (it is a no-op then).
#
# Usage:      ./scripts/dn.sh [OPTIONS]        (see usage() below)
# Env vars:   UE_BRIDGE_PORT (scripts/.env)
# Removes:    ~/.robot_splunker/run/stack.pid; with --clean-logs, logs older than 7 days
# Exit codes: 0 everything stopped, 1 something survived, 2 bad option
# Example:    ./scripts/dn.sh --force --ue
# =============================================================================

# -e: stop on the first failing command; -u: unset variables are errors;
# -o pipefail: a pipeline fails if any command in it fails.
set -euo pipefail

# ---- Usage text --------------------------------------------------------------------
usage() {
    cat <<'EOF'
Usage: dn.sh [OPTIONS]

Stops the robot_splunker stack started by up.sh: first gracefully (Ctrl-C to the
whole launch process group), then forcefully, then sweeps up stray processes
(Gazebo, bridge, SLAM, Nav2, explorer, ue_bridge, RViz, teleop) left behind by a
crash or by launches started by hand. Running it when nothing is up is harmless.

Options:
  --force         Skip the graceful Ctrl-C phase; TERM then KILL immediately.   (default: graceful)
  --ue            Also close Unreal (UnrealEditor.exe) on Windows.              (default: leave UE open)
  --clean-logs    Delete run logs older than 7 days.                             (default: keep)
  --grace SEC     Seconds to wait after Ctrl-C before escalating.                (default: 10)
  -h, --help      Show this help and exit.

Environment (scripts/.env or shell):
  UE_BRIDGE_PORT  Port checked in the verification step                        (default: 9090)

Examples:
  ./scripts/dn.sh                 # normal shutdown
  ./scripts/dn.sh --force --ue    # kill everything now, including Unreal

Related scripts: up.sh (start), bld.sh (build)
EOF
}

# ---- Parse options BEFORE any side effects -----------------------------------------
FORCE=0; CLOSE_UE=0; CLEAN_LOGS=0; GRACE=10
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)      FORCE=1 ;;
        --ue)         CLOSE_UE=1 ;;
        --clean-logs) CLEAN_LOGS=1 ;;
        --grace)
            [[ $# -ge 2 ]] || { echo "Option --grace needs seconds" >&2; usage; exit 2; }
            GRACE="$2"; shift ;;
        -h|--help)    usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
    shift
done

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
load_env
TOTAL=7

# Process patterns (matched against the full command line with pkill -f).
# Each is commented with what it catches.
STRAY_PATTERNS=(
    "ros2 launch robot_splunker"        # the launch process itself (if started by hand)
    "gz sim"                            # Gazebo server + GUI (`gz sim` runs as a ruby script)
    "ruby.*gz sim"                      # ...the ruby wrapper process of gz sim
    "parameter_bridge"                  # ros_gz_bridge
    "ros_gz_sim/create"                 # robot spawner (normally exits by itself)
    "robot_state_publisher"             # URDF -> TF
    "joint_state_publisher_gui"         # display mode slider window
    "async_slam_toolbox_node"           # SLAM Toolbox
    "controller_server"                 # Nav2 nodes ...
    "planner_server"
    "smoother_server"
    "behavior_server"
    "bt_navigator"
    "waypoint_follower"
    "velocity_smoother"
    "lifecycle_manager"
    "frontier_explorer"                 # our autonomous explorer
    "ue_bridge_node"                    # our ROS -> Unreal WebSocket bridge
    "rviz2"                             # RViz
    "teleop_twist_keyboard"             # teleop window opened by up.sh --teleop
)

# group_alive PGID — true while any process in the process group exists.
# (kill -0 with a NEGATIVE id tests the whole group.)
group_alive() { [[ -n "${1:-}" ]] && kill -0 -- "-$1" 2>/dev/null; }

# wait_group_exit PGID SECONDS — poll until the group is gone; returns 1 on timeout.
wait_group_exit() {
    local pgid="$1" secs="$2" i
    for (( i = 0; i < secs * 2; i++ )); do
        group_alive "${pgid}" || return 0
        sleep 0.5
    done
    ! group_alive "${pgid}"
}

# any_strays — true if any STRAY_PATTERNS process (owned by this user) is still running.
any_strays() {
    local p
    for p in "${STRAY_PATTERNS[@]}"; do
        pgrep -u "${USER}" -f "${p}" >/dev/null 2>&1 && return 0
    done
    return 1
}

# ---- Step 1: Graceful stop -----------------------------------------------------------
# SIGINT == Ctrl-C. ros2 launch catches it and shuts every node down in order, which
# lets SLAM/Nav2 exit cleanly and Gazebo close its window. The minus sign in
# `kill -INT -PGID` sends the signal to the whole process group created by setsid.
step 1 ${TOTAL} "Graceful stop (Ctrl-C to the launch group)"
STACK_PGID=""
if read_pid_file && [[ -n "${STACK_PGID}" ]] && group_alive "${STACK_PGID}"; then
    info "Running stack: mode=${STACK_MODE} pid=${STACK_PID} pgid=${STACK_PGID}"
    if [[ ${FORCE} -eq 1 ]]; then
        info "Skipped (--force)."
    else
        kill -INT -- "-${STACK_PGID}" 2>/dev/null || true
        if wait_group_exit "${STACK_PGID}" "${GRACE}"; then
            ok "Stack stopped cleanly."
        else
            warn "Still running after ${GRACE}s."
        fi
    fi
else
    info "No stack recorded by up.sh (or it already exited)."
fi

# ---- Step 2: Escalate --------------------------------------------------------------------
# SIGTERM asks politely but without launch's ordered shutdown; SIGKILL cannot be ignored.
step 2 ${TOTAL} "Escalate if needed (TERM, then KILL)"
if [[ -n "${STACK_PGID}" ]] && group_alive "${STACK_PGID}"; then
    kill -TERM -- "-${STACK_PGID}" 2>/dev/null || true
    if ! wait_group_exit "${STACK_PGID}" 5; then
        warn "Group ${STACK_PGID} ignored TERM; sending KILL."
        kill -KILL -- "-${STACK_PGID}" 2>/dev/null || true
        wait_group_exit "${STACK_PGID}" 2 || true
    fi
    ok "Launch process group is gone."
else
    info "Nothing to escalate."
fi

# ---- Step 3: Sweep stray processes -----------------------------------------------------
# Catches nodes that escaped the process group (crashes, launches started by hand,
# Gazebo GUI respawns). -u $USER: never touch other users' processes.
step 3 ${TOTAL} "Sweep stray processes"
found=0
for p in "${STRAY_PATTERNS[@]}"; do
    if pgrep -u "${USER}" -f "${p}" >/dev/null 2>&1; then
        found=1
        info "TERM: ${p}"
        pkill -TERM -u "${USER}" -f "${p}" 2>/dev/null || true
    fi
done
if [[ ${found} -eq 1 ]]; then
    sleep 3
    for p in "${STRAY_PATTERNS[@]}"; do
        if pgrep -u "${USER}" -f "${p}" >/dev/null 2>&1; then
            warn "KILL: ${p}"
            pkill -KILL -u "${USER}" -f "${p}" 2>/dev/null || true
        fi
    done
    sleep 1
else
    info "No strays found."
fi

# ---- Step 4: Stop the ROS 2 daemon ------------------------------------------------------
# The ros2 CLI daemon caches the node/topic graph; stopping it prevents stale nodes
# from showing up in `ros2 node list` on the next run.
step 4 ${TOTAL} "Stop the ROS 2 CLI daemon"
if [[ -f "/opt/ros/${ROS_DISTRO}/setup.bash" ]]; then
    source_ros
    ros2 daemon stop >/dev/null 2>&1 || true
    ok "ros2 daemon stopped."
else
    info "ROS not installed; nothing to do."
fi

# ---- Step 5: Verify ---------------------------------------------------------------------------
step 5 ${TOTAL} "Verify everything is down"
rc=0
if any_strays; then
    err "Some processes are still alive:"
    for p in "${STRAY_PATTERNS[@]}"; do pgrep -u "${USER}" -af "${p}" || true; done
    rc=1
else
    ok "No robot_splunker processes running."
fi
# The UE bridge port must be free, otherwise the next up.sh --ue cannot bind it.
if ss -ltn 2>/dev/null | grep -q ":${UE_BRIDGE_PORT} "; then
    err "Port ${UE_BRIDGE_PORT} is still in use:"
    ss -ltnp 2>/dev/null | grep ":${UE_BRIDGE_PORT} " || true
    rc=1
else
    ok "Port ${UE_BRIDGE_PORT} is free."
fi

# ---- Step 6: Optional: close Unreal on Windows -------------------------------------------
# taskkill.exe is the Windows equivalent of kill; /F forces it (only with --force).
step 6 ${TOTAL} "Close Unreal (--ue)"
if [[ ${CLOSE_UE} -eq 1 ]]; then
    if is_wsl && command -v taskkill.exe >/dev/null 2>&1; then
        tk_args=(/IM UnrealEditor.exe)
        [[ ${FORCE} -eq 1 ]] && tk_args=(/F "${tk_args[@]}")
        if taskkill.exe "${tk_args[@]}" >/dev/null 2>&1; then
            ok "Unreal closed."
        else
            info "Unreal was not running (or refused to close; retry with --force)."
        fi
    else
        warn "taskkill.exe not available (not WSL?); close Unreal manually."
    fi
else
    info "Leaving Unreal open (use --ue to close it)."
fi

# ---- Step 7: Clean up state ------------------------------------------------------------------
step 7 ${TOTAL} "Clean up state"
rm -f "${PID_FILE}"
info "Removed ${PID_FILE}"
if [[ ${CLEAN_LOGS} -eq 1 && -d "${LOG_DIR}" ]]; then
    # -mtime +7: files last modified more than 7 days ago.
    find "${LOG_DIR}" -type f -name '*.log' -mtime +7 -print -delete
    info "Old logs removed."
fi

if [[ ${rc} -eq 0 ]]; then
    ok "All stopped."
else
    err "Some things are still running (see above). Try: ./scripts/dn.sh --force"
fi
exit ${rc}
