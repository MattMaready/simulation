#!/usr/bin/env bash
# =============================================================================
# up.sh — bring up the robot_splunker stack with one command (run inside WSL2).
#
# Starts `ros2 launch` in the background in its OWN process group, records its
# PID/PGID so dn.sh can stop the whole tree, waits until the stack is actually
# ready (topics publishing, Nav2 up, UE bridge listening) and prints a summary.
#
# Steps:
#   1. Refuse to start if a stack is already running (live PID file)
#   2. Load environment (ROS, workspace overlay, scripts/.env); optional --build
#   3. Launch ros2 in the background (setsid + nohup), write PID file + log
#   4. Wait for readiness: /clock, /scan, /map, navigate_to_pose, port 9090
#   5. Optional extras: teleop window, Unreal launch on Windows
#   6. Print the status summary / next steps
#
# Usage:      ./scripts/up.sh [MODE] [OPTIONS]        (see usage() below)
# Env vars:   ROS_DOMAIN_ID, UE_ROOT, UE_EDITOR_EXE, UE_BRIDGE_PORT (scripts/.env)
# Creates:    ~/.robot_splunker/run/stack.pid, ~/.robot_splunker/run/logs/<ts>.log,
#             ~/.robot_splunker/run/logs/latest.log (symlink)
# Exit codes: 0 stack ready, 1 failure / readiness timeout, 2 bad option
# Example:    ./scripts/up.sh explore --ue --start-ue
# =============================================================================

# -e: stop on the first failing command; -u: unset variables are errors;
# -o pipefail: a pipeline fails if any command in it fails.
set -euo pipefail

# ---- Usage text --------------------------------------------------------------------
usage() {
    cat <<'EOF'
Usage: up.sh [MODE] [OPTIONS]

Starts the robot_splunker simulation stack in the background, waits until it
is ready, and prints how to interact with it. Stop it with ./scripts/dn.sh.

Modes:
  explore     (default) Gazebo + bridge + SLAM + Nav2 + autonomous frontier explorer
  mapping     Gazebo + bridge + SLAM; you drive with teleop (see --teleop)
  sim         Gazebo + bridge only (robot spawned, no SLAM/Nav2)
  display     RViz model viewer only (robot_state_publisher + joint sliders, no Gazebo)

Options:
  --ue              Also start the ROS->Unreal WebSocket bridge (ue_bridge).   (default: off)
  --start-ue        Also launch Unreal on Windows (implies --ue). Runs the game
                    viewer (-game) unless --ue-editor is given.                (default: off)
  --ue-editor       With --start-ue: open the full Unreal Editor instead of -game.
  --no-rviz         Do not open RViz.                                          (default: RViz on)
  --no-gazebo-gui   Run Gazebo without its GUI (CI/testing only).              (default: GUI on)
  --world NAME      World to load (file in robot_splunker_gazebo/worlds).      (default: splunker_cave)
  --build           Run ./scripts/bld.sh --ros first.                          (default: off)
  --teleop          Open teleop_twist_keyboard in a new terminal window.       (default: off)
  --timeout SEC     Max seconds to wait for each readiness check.              (default: 90)
  -h, --help        Show this help and exit.

Environment (scripts/.env or shell):
  ROS_DOMAIN_ID     ROS 2 domain for all nodes                 (default: 42)
  UE_BRIDGE_PORT    WebSocket port for ue_bridge               (default: 9090)
  UE_ROOT           Windows UE install folder (for --start-ue)
  UE_EDITOR_EXE     Explicit UnrealEditor.exe path (optional; default derived from UE_ROOT)

Examples:
  ./scripts/up.sh                          # autonomous exploration, Gazebo + RViz
  ./scripts/up.sh explore --ue --start-ue  # ...plus the Unreal digital twin
  ./scripts/up.sh mapping --teleop         # drive it yourself while SLAM maps

Related scripts: dn.sh (stop), bld.sh (build), setup_wsl.sh (install)
Logs: ~/.robot_splunker/run/logs/latest.log
EOF
}

# ---- Parse options BEFORE any side effects -------------------------------------------
MODE="explore"
WANT_UE=0; START_UE=0; UE_EDITOR_MODE=0
RVIZ="true"; GZ_GUI="true"
WORLD="splunker_cave"
DO_BUILD=0; DO_TELEOP=0
TIMEOUT=90
while [[ $# -gt 0 ]]; do
    case "$1" in
        explore|mapping|sim|display) MODE="$1" ;;
        --ue)            WANT_UE=1 ;;
        --start-ue)      WANT_UE=1; START_UE=1 ;;
        --ue-editor)     UE_EDITOR_MODE=1 ;;
        --no-rviz)       RVIZ="false" ;;
        --no-gazebo-gui) GZ_GUI="false" ;;
        --world)
            [[ $# -ge 2 ]] || { echo "Option --world needs a name" >&2; usage; exit 2; }
            WORLD="$2"; shift ;;
        --build)         DO_BUILD=1 ;;
        --teleop)        DO_TELEOP=1 ;;
        --timeout)
            [[ $# -ge 2 ]] || { echo "Option --timeout needs seconds" >&2; usage; exit 2; }
            TIMEOUT="$2"; shift ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
    shift
done

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
TOTAL=6

# ---- Step 1: Refuse to start twice ----------------------------------------------------
# A live PID file means a previous up.sh stack is still running; starting a second
# Gazebo/SLAM would fight over the same topics.
step 1 ${TOTAL} "Check for an already-running stack"
mkdir -p "${LOG_DIR}"
if read_pid_file; then
    if pid_alive "${STACK_PID}"; then
        die "A stack is already running (mode=${STACK_MODE}, pid=${STACK_PID}). Stop it first: ./scripts/dn.sh"
    fi
    warn "Removing stale PID file (process ${STACK_PID} is gone)."
    rm -f "${PID_FILE}"
fi
ok "Nothing running."

# ---- Step 2: Environment ---------------------------------------------------------------
step 2 ${TOTAL} "Load environment"
load_env              # scripts/.env -> ROS_DOMAIN_ID, UE_ROOT, UE_BRIDGE_PORT
if [[ ${DO_BUILD} -eq 1 ]]; then
    info "Building ROS packages first (--build)"
    "${SCRIPTS_DIR}/bld.sh" --ros
fi
source_ros            # /opt/ros/jazzy
source_ws             # our packages (fails with a hint if not built)
info "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}  mode=${MODE}  world=${WORLD}  ue=${WANT_UE}"

# ---- Step 3: Launch in the background ---------------------------------------------------
# Build the ros2 launch command for the chosen mode.
mkdir -p "${REPO_DIR}/maps"
COMMON_ARGS=("world:=${WORLD}" "rviz:=${RVIZ}" "gui:=${GZ_GUI}"
             "ue:=$([[ ${WANT_UE} -eq 1 ]] && echo true || echo false)"
             "ue_port:=${UE_BRIDGE_PORT}"
             "map_save_path:=${REPO_DIR}/maps/${WORLD}")
case "${MODE}" in
    explore) LAUNCH=(ros2 launch robot_splunker_bringup explore.launch.py "${COMMON_ARGS[@]}") ;;
    mapping) LAUNCH=(ros2 launch robot_splunker_bringup mapping.launch.py "${COMMON_ARGS[@]}") ;;
    sim)     LAUNCH=(ros2 launch robot_splunker_bringup explore.launch.py "${COMMON_ARGS[@]}"
                     slam:=false nav:=false explore:=false) ;;
    display) LAUNCH=(ros2 launch robot_splunker_description display.launch.py) ;;
esac

step 3 ${TOTAL} "Launch: ${LAUNCH[*]}"
LOG_FILE="${LOG_DIR}/$(date +%Y%m%d-%H%M%S)-${MODE}.log"
# setsid  -> the launch becomes the leader of a NEW process group, so dn.sh can
#            signal the whole tree (Gazebo, bridge, SLAM, Nav2, ...) with one kill.
# nohup   -> keeps running if this terminal closes.
# </dev/null -> ros2 launch must not read from our terminal.
setsid nohup "${LAUNCH[@]}" > "${LOG_FILE}" 2>&1 < /dev/null &
LAUNCH_PID=$!
sleep 1
# The PGID is normally the same as the PID after setsid; read it back to be sure.
LAUNCH_PGID="$(ps -o pgid= -p "${LAUNCH_PID}" 2>/dev/null | tr -d ' ' || true)"
[[ -n "${LAUNCH_PGID}" ]] || { tail -n 30 "${LOG_FILE}" >&2 || true; die "ros2 launch exited immediately. Log: ${LOG_FILE}"; }
echo "${LAUNCH_PID} ${LAUNCH_PGID} ${MODE}" > "${PID_FILE}"
ln -sfn "${LOG_FILE}" "${LOG_DIR}/latest.log"
info "pid=${LAUNCH_PID} pgid=${LAUNCH_PGID}  log=${LOG_FILE}"

# ---- Step 4: Wait for readiness ---------------------------------------------------------
# wait_for DESCRIPTION CMD... — retry CMD every 2 s until it succeeds, the launch
# process dies, or TIMEOUT seconds pass. On failure, print the end of the log.
wait_for() {
    local desc="$1"; shift
    local start=${SECONDS}
    printf '  waiting for %-38s' "${desc} ..."
    while true; do
        if "$@" >/dev/null 2>&1; then
            printf ' ready (%ss)\n' "$(( SECONDS - start ))"
            return 0
        fi
        if ! pid_alive "${LAUNCH_PID}"; then
            printf ' launch process died\n'
            tail -n 30 "${LOG_FILE}" >&2 || true
            rm -f "${PID_FILE}"
            die "The launch exited during start-up. Full log: ${LOG_FILE}"
        fi
        if (( SECONDS - start >= TIMEOUT )); then
            printf ' TIMEOUT after %ss\n' "${TIMEOUT}"
            tail -n 30 "${LOG_FILE}" >&2 || true
            die "Readiness check '${desc}' timed out. The stack is still running for inspection; stop it with ./scripts/dn.sh"
        fi
        sleep 2
    done
}
# Helpers used as readiness probes (each returns 0 when the condition holds).
topic_has_data()  { timeout 8 ros2 topic echo --once "$1" >/dev/null; }      # a message actually arrives
topic_exists()    { ros2 topic list 2>/dev/null | grep -qx "$1"; }            # someone advertises it
action_exists()   { ros2 action list 2>/dev/null | grep -qx "$1"; }           # action server is up
port_listening()  { ss -ltn 2>/dev/null | grep -q ":$1 "; }                   # TCP server bound

step 4 ${TOTAL} "Wait until the stack is ready (timeout ${TIMEOUT}s per check)"
if [[ "${MODE}" == "display" ]]; then
    wait_for "/robot_description"            topic_exists /robot_description
else
    # /clock proves Gazebo is running AND the ros_gz bridge works.
    wait_for "/clock (Gazebo + bridge)"      topic_has_data /clock
    # /scan proves the robot spawned and its lidar is publishing through the bridge.
    wait_for "/scan (robot lidar)"           topic_has_data /scan
    if [[ "${MODE}" == "explore" || "${MODE}" == "mapping" ]]; then
        wait_for "/map (SLAM Toolbox)"       topic_exists /map
    fi
    if [[ "${MODE}" == "explore" ]]; then
        # Nav2 is started ~5 s after SLAM; its action server appears once all nodes are active.
        wait_for "navigate_to_pose (Nav2)"   action_exists /navigate_to_pose
    fi
    if [[ ${WANT_UE} -eq 1 ]]; then
        wait_for "ue_bridge port ${UE_BRIDGE_PORT}" port_listening "${UE_BRIDGE_PORT}"
    fi
fi
ok "Stack is ready."

# ---- Step 5: Optional extras (teleop window, Unreal) ------------------------------------
step 5 ${TOTAL} "Optional extras"

# 5a. Teleop needs a real terminal (it reads keystrokes), so open a new window.
TELEOP_CMD="export ROS_DOMAIN_ID=${ROS_DOMAIN_ID} && source /opt/ros/${ROS_DISTRO}/setup.bash && source ${WS_DIR}/install/setup.bash && ros2 run teleop_twist_keyboard teleop_twist_keyboard"
if [[ ${DO_TELEOP} -eq 1 ]]; then
    [[ "${MODE}" == "explore" ]] && warn "Teleop and the autonomous explorer will both publish /cmd_vel."
    if is_wsl && command -v wt.exe >/dev/null 2>&1; then
        # Windows Terminal: new tab running WSL. Commands are joined with && because
        # wt.exe treats ';' as its own separator.
        wt.exe -w 0 nt wsl.exe -d "${WSL_DISTRO_NAME:-Ubuntu}" bash -lc "${TELEOP_CMD}" >/dev/null 2>&1 &
        info "Opened teleop in a new Windows Terminal tab."
    elif command -v gnome-terminal >/dev/null 2>&1; then
        gnome-terminal -- bash -lc "${TELEOP_CMD}" &
        info "Opened teleop in gnome-terminal."
    elif command -v xterm >/dev/null 2>&1; then
        xterm -e bash -lc "${TELEOP_CMD}" &
        info "Opened teleop in xterm."
    else
        warn "No terminal emulator found; run this in another shell:"
        echo "    ${TELEOP_CMD}"
    fi
else
    info "Teleop: not requested (--teleop)."
fi

# 5b. Launch Unreal on Windows via WSL interop (PowerShell Start-Process detaches it).
if [[ ${START_UE} -eq 1 ]]; then
    if ! is_wsl || ! command -v powershell.exe >/dev/null 2>&1; then
        warn "--start-ue needs WSL interop (powershell.exe); start Unreal manually on Windows."
    elif [[ -z "${UE_EDITOR_EXE:-}" && -z "${UE_ROOT:-}" ]]; then
        warn "Set UE_ROOT (or UE_EDITOR_EXE) in scripts/.env to use --start-ue."
    else
        UE_EXE="${UE_EDITOR_EXE:-}"
        [[ -n "${UE_EXE}" ]] || UE_EXE="${UE_ROOT}\\Engine\\Binaries\\Win64\\UnrealEditor.exe"
        # wslpath -w: Windows programs need C:\... paths, not /mnt/c/...
        UPROJECT_WIN="$(wslpath -w "${REPO_DIR}/unreal/SplunkerViz/SplunkerViz.uproject")"
        if [[ ${UE_EDITOR_MODE} -eq 1 ]]; then
            UE_ARGS="'\"${UPROJECT_WIN}\"'"                       # full editor
        else
            UE_ARGS="'\"${UPROJECT_WIN}\"','-game','-windowed','-ResX=1600','-ResY=900'"   # viewer only
        fi
        (cd "${REPO_DIR}" && powershell.exe -NoProfile -Command \
            "Start-Process -FilePath '${UE_EXE}' -ArgumentList ${UE_ARGS}") \
            && info "Started Unreal: ${UE_EXE}" \
            || warn "Could not start Unreal (check UE_ROOT / that bld.sh --ue succeeded)."
    fi
fi

# ---- Step 6: Summary ------------------------------------------------------------------------
step 6 ${TOTAL} "Summary"
cat <<EOF
  Mode            : ${MODE}
  World           : ${WORLD}
  Launch PID/PGID : ${LAUNCH_PID} / ${LAUNCH_PGID}
  Log             : ${LOG_FILE}   (tail -f ${LOG_DIR}/latest.log)
  ROS_DOMAIN_ID   : ${ROS_DOMAIN_ID}
EOF
if [[ ${WANT_UE} -eq 1 ]]; then
    echo "  UE bridge       : ws://127.0.0.1:${UE_BRIDGE_PORT}"
    [[ ${START_UE} -eq 1 ]] || echo "  Next            : open unreal/SplunkerViz on Windows and press Play"
fi
case "${MODE}" in
    explore) echo "  Exploring       : the robot maps on its own; map saved to ${REPO_DIR}/maps/${WORLD}.{pgm,yaml} when done" ;;
    mapping) echo "  Drive           : ${TELEOP_CMD##*&& }   (in a ROS-sourced shell)" ;;
    sim)     echo "  Drive           : ros2 topic pub /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.2}}'" ;;
    display) echo "  Display         : move the wheel sliders in joint_state_publisher_gui" ;;
esac
echo "  Stop            : ./scripts/dn.sh"
ok "Done."
