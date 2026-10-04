#!/usr/bin/env bash
# =============================================================================
# setup_wsl.sh — one-time machine setup for robot_splunker inside WSL2 Ubuntu 24.04.
#
# Installs ROS 2 Jazzy, Gazebo Harmonic (via ros-jazzy-ros-gz), SLAM Toolbox,
# Nav2, teleop, xacro and the Python/tooling packages the workspace needs, then
# initialises rosdep and (optionally) adds ROS sourcing to ~/.bashrc.
#
# Usage:   ./scripts/setup_wsl.sh [OPTIONS]
# Options:
#   -y, --yes         answer "yes" to apt prompts (non-interactive install)
#   --no-bashrc       do not add "source /opt/ros/jazzy/setup.bash" to ~/.bashrc
#   --skip-apt-source do not (re)install the ROS 2 apt repository definition
#   -h, --help        print usage and exit
#
# Environment:   ROS_DISTRO (default jazzy)
# Creates:       /etc/apt/sources.list.d/ros2.sources (via ros2-apt-source .deb),
#                /etc/ros/rosdep/sources.list.d/20-default.list, ~/.bashrc lines
# Exit codes:    0 success, 1 failure, 2 bad option
# Example:       ./scripts/setup_wsl.sh -y
# =============================================================================

# -e: stop on the first failing command; -u: unset variables are errors;
# -o pipefail: a pipeline fails if any command in it fails (not just the last).
set -euo pipefail

# ---- Usage text (printed by -h/--help and on bad options) -----------------------
usage() {
    cat <<'EOF'
Usage: setup_wsl.sh [OPTIONS]

One-time setup of a WSL2 Ubuntu 24.04 machine for robot_splunker. Installs
ROS 2 Jazzy desktop, Gazebo Harmonic (ros-jazzy-ros-gz), SLAM Toolbox, Nav2,
teleop_twist_keyboard, xacro, colcon, rosdep and the Python libraries used by
the exploration and Unreal-bridge packages. Uses sudo for apt.

Options:
  -y, --yes           Non-interactive: pass -y to apt-get.            (default: ask)
  --no-bashrc         Do not append ROS sourcing to ~/.bashrc.        (default: append)
  --skip-apt-source   Skip installing the ROS 2 apt repository .deb.  (default: install if missing)
  -h, --help          Show this help and exit.

Environment:
  ROS_DISTRO          ROS 2 distribution to install (default: jazzy)

Examples:
  ./scripts/setup_wsl.sh            # interactive install
  ./scripts/setup_wsl.sh -y         # unattended install

Next steps / related scripts:
  ./scripts/bld.sh      build everything
  ./scripts/up.sh       start the simulation stack
  ./scripts/dn.sh       stop it
EOF
}

# ---- Parse options BEFORE doing anything with side effects --------------------
APT_YES=""
ADD_BASHRC=1
SKIP_APT_SOURCE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes)          APT_YES="-y" ;;
        --no-bashrc)       ADD_BASHRC=0 ;;
        --skip-apt-source) SKIP_APT_SOURCE=1 ;;
        -h|--help)         usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
    shift
done

# Load shared helpers (paths, logging). Done after option parsing so --help has no side effects.
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

TOTAL=6

# ---- Step 1: Check the operating system ---------------------------------------
# The ROS 2 Jazzy binaries are built for Ubuntu 24.04 "noble" only.
step 1 ${TOTAL} "Check OS (Ubuntu 24.04 expected)"
# shellcheck disable=SC1091
. /etc/os-release
if [[ "${VERSION_CODENAME:-}" != "noble" ]]; then
    warn "Detected ${PRETTY_NAME:-unknown}. ROS 2 Jazzy binaries target Ubuntu 24.04 (noble); continuing anyway."
fi
if is_wsl; then
    info "Running inside WSL2."
else
    warn "Not running in WSL; that's fine on a native Ubuntu machine."
fi

# ---- Step 2: Base tools + UTF-8 locale -----------------------------------------
# ROS requires a UTF-8 locale; curl is needed to fetch the apt-source package.
step 2 ${TOTAL} "Install base tools and UTF-8 locale"
sudo apt-get update
sudo apt-get install ${APT_YES} software-properties-common curl locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
# "universe" holds several ROS dependencies.
sudo add-apt-repository ${APT_YES} universe

# ---- Step 3: ROS 2 apt repository ----------------------------------------------
# The official method (since 2025) is the ros2-apt-source .deb, which installs the
# repository definition AND its signing key, and keeps the key up to date.
step 3 ${TOTAL} "Add the ROS 2 apt repository"
if [[ ${SKIP_APT_SOURCE} -eq 1 ]]; then
    info "Skipped (--skip-apt-source)."
elif dpkg -s ros2-apt-source >/dev/null 2>&1; then
    info "ros2-apt-source already installed."
else
    # Ask GitHub for the latest release tag of ros-apt-source.
    ROS_APT_SOURCE_VERSION="$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
        | grep -F '"tag_name"' | awk -F'"' '{print $4}')"
    [[ -n "${ROS_APT_SOURCE_VERSION}" ]] || die "Could not determine ros-apt-source version (network?)."
    deb="/tmp/ros2-apt-source.deb"
    curl -L -o "${deb}" \
        "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${VERSION_CODENAME}_all.deb"
    sudo dpkg -i "${deb}"
    rm -f "${deb}"
fi

# ---- Step 4: Install ROS 2, Gazebo and project dependencies ---------------------
# ros-jazzy-ros-gz pulls in Gazebo Harmonic through the gz_*_vendor packages,
# so no separate OSRF Gazebo repository is needed.
step 4 ${TOTAL} "Install ROS 2 ${ROS_DISTRO}, Gazebo Harmonic and dependencies"
sudo apt-get update
sudo apt-get install ${APT_YES} \
    "ros-${ROS_DISTRO}-desktop" \
    "ros-${ROS_DISTRO}-ros-gz" \
    "ros-${ROS_DISTRO}-slam-toolbox" \
    "ros-${ROS_DISTRO}-navigation2" \
    "ros-${ROS_DISTRO}-nav2-bringup" \
    "ros-${ROS_DISTRO}-teleop-twist-keyboard" \
    "ros-${ROS_DISTRO}-xacro" \
    "ros-${ROS_DISTRO}-joint-state-publisher-gui" \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-numpy \
    python3-yaml \
    python3-websockets \
    python3-pytest \
    liburdfdom-tools \
    shellcheck \
    iproute2

# ---- Step 5: rosdep -----------------------------------------------------------
# rosdep installs any remaining system dependencies declared in package.xml files.
# `rosdep init` fails if it was already run, so only call it when needed.
step 5 ${TOTAL} "Initialise rosdep"
if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
    sudo rosdep init
else
    info "rosdep already initialised."
fi
rosdep update

# ---- Step 6: ~/.bashrc ---------------------------------------------------------
# Optional convenience: every new shell gets ROS and (if built) the workspace.
step 6 ${TOTAL} "Configure ~/.bashrc"
if [[ ${ADD_BASHRC} -eq 1 ]]; then
    marker="# >>> robot_splunker >>>"
    if ! grep -qF "${marker}" "${HOME}/.bashrc"; then
        cat >> "${HOME}/.bashrc" <<EOF

${marker}
source /opt/ros/${ROS_DISTRO}/setup.bash
[ -f "${WS_DIR}/install/setup.bash" ] && source "${WS_DIR}/install/setup.bash"
export ROS_DOMAIN_ID=\${ROS_DOMAIN_ID:-42}
# <<< robot_splunker <<<
EOF
        ok "Added ROS sourcing to ~/.bashrc (open a new shell to pick it up)."
    else
        info "~/.bashrc already configured."
    fi
else
    info "Skipped (--no-bashrc)."
fi

ok "Setup complete. Next: ./scripts/bld.sh"
