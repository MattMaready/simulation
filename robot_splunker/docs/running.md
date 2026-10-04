# Running robot_splunker

ROS 2, Gazebo, SLAM and Nav2 run in **WSL2 Ubuntu 24.04**. Unreal runs on **Windows**. Every script in `scripts/` prints its usage with `-h` / `--help`.

## 1. One-time setup (WSL2)

```bash
cd /mnt/c/work/stephan/simulation/robot_splunker
./scripts/setup_wsl.sh -y
cp scripts/.env.example scripts/.env       # then edit UE_ROOT if you use Unreal
```

`setup_wsl.sh` does six things:

1. Checks the OS.
2. Installs the base tools and a UTF-8 locale.
3. Adds the ROS 2 apt repository (the `ros2-apt-source` package).
4. Installs ROS 2 Jazzy desktop, `ros-jazzy-ros-gz` (which brings in Gazebo Harmonic), SLAM Toolbox, Nav2, teleop, xacro, colcon, rosdep, `python3-websockets`, shellcheck and the other tools.
5. Runs `rosdep init` and `rosdep update`.
6. Optionally adds ROS sourcing to `~/.bashrc`.

**Where the files live.** The repo stays on the Windows drive (`C:\work\stephan\simulation\robot_splunker`) because Unreal needs `unreal/` there. `bld.sh` links `src/` into `~/robot_splunker_ws/src/robot_splunker` and builds in `~/robot_splunker_ws`, so `build/`, `install/` and `log/` sit on the fast Linux filesystem.

## 2. Build: `bld.sh`

```bash
./scripts/bld.sh                 # everything: worlds, ROS packages, Unreal (if UE_ROOT is set)
./scripts/bld.sh --ros --test    # ROS packages + unit tests
./scripts/bld.sh --worlds        # only regenerate worlds + validate the URDF
./scripts/bld.sh --clean         # from scratch
```

| Step | What happens |
|---|---|
| 1 Preflight | Sources ROS and checks for `colcon`, `rosdep`, `xacro` and PyYAML |
| 2 Worlds | `generate_world.py` writes the Gazebo SDF, the spawn metadata and the UE layout JSON. Then `xacro` and `check_urdf` validate the robot. |
| 3 ROS 2 | Links `src/`, runs `rosdep install`, then `colcon build --symlink-install` |
| 4 Unreal | Calls `bld_ue.ps1` through `powershell.exe`, which runs UE `Build.bat SplunkerVizEditor Win64 Development`. Skipped if `UE_ROOT` is empty. |
| 5 Tests | `colcon test` and `colcon test-result --verbose` (only with `--test`) |
| 6 Summary | Shows each stage's result and time, plus the log path |

From Windows PowerShell you can also build only the Unreal project:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bld_ue.ps1
```

## 3. Start: `up.sh`

```bash
./scripts/up.sh [explore|mapping|sim|display] [--ue] [--start-ue] [--teleop] [--no-rviz] [--world NAME]
```

| Mode | Starts |
|---|---|
| `explore` (default) | Gazebo + bridge + SLAM + Nav2 + frontier explorer + RViz |
| `mapping` | Gazebo + bridge + SLAM + RViz. You drive (`--teleop` opens a teleop window). |
| `sim` | Gazebo + bridge + robot only |
| `display` | RViz model viewer with joint sliders. No Gazebo. |

| Option | Effect |
|---|---|
| `--ue` | Also starts `ue_bridge` (WebSocket on port `UE_BRIDGE_PORT`, default 9090) |
| `--start-ue` | Also launches Unreal on Windows: the game viewer by default, or the full editor with `--ue-editor` |
| `--no-gazebo-gui` | Runs Gazebo headless. Meant only for CI; the normal workflow shows both Gazebo **and** Unreal. |

What `up.sh` does:

1. Refuses to start if a stack is already running.
2. Sources ROS and the workspace.
3. Starts `ros2 launch` with `setsid` (its own process group) and writes `~/.robot_splunker/run/stack.pid`. Output goes to a log; `logs/latest.log` always points at the newest one.
4. **Waits until the stack is ready:** `/clock`, then `/scan`, then `/map`, then the `navigate_to_pose` action server, then port 9090.
5. Optionally opens a teleop window and starts Unreal.
6. Prints a summary.

## 4. Stop: `dn.sh`

```bash
./scripts/dn.sh              # graceful
./scripts/dn.sh --force --ue # kill now, and close Unreal too
```

`dn.sh` stops things in this order:

1. Sends Ctrl-C (SIGINT) to the whole launch process group and waits up to 10 s.
2. Escalates with SIGTERM, then SIGKILL.
3. Sweeps up stray processes: Gazebo, the bridge, SLAM, Nav2, the explorer, `ue_bridge`, RViz and teleop.
4. Stops `ros2 daemon`.
5. Checks that nothing is left and that port 9090 is free.
6. With `--ue`, closes Unreal.
7. Removes the PID file.

It is safe to run when nothing is running.

## 5. Running launch files by hand

```bash
source /opt/ros/jazzy/setup.bash && source ~/robot_splunker_ws/install/setup.bash
ros2 launch robot_splunker_description display.launch.py           # model check in RViz
ros2 launch robot_splunker_gazebo sim.launch.py world:=empty       # Gazebo + robot + bridges
ros2 launch robot_splunker_bringup mapping.launch.py               # + SLAM, drive with teleop
ros2 launch robot_splunker_bringup explore.launch.py ue:=true      # full autonomy + Unreal bridge
```

`explore.launch.py` arguments:

| Arg | Default | Meaning |
|---|---|---|
| `world` | `splunker_cave` | World name or `.sdf` path |
| `x`, `y`, `yaw` | from `<world>.meta.json` | Spawn pose |
| `gui` | `true` | Gazebo GUI |
| `rviz` | `true` | RViz |
| `slam`, `nav`, `explore` | `true` | Switch each layer on or off |
| `ue`, `ue_port` | `false`, `9090` | Unreal bridge |
| `map_save_path` | `~/robot_splunker_maps/splunker_cave` | Final map file stem (`up.sh` sets `maps/<world>`) |
| `use_sim_time` | `true` | |

## 6. Worlds

Worlds are generated from `worlds/<name>.world.yaml`. Two ship with the repo: `splunker_cave` (four rooms with doorways, pillars and crates) and `empty`. To add one:

1. Copy `worlds/splunker_cave.world.yaml` to `worlds/my_world.world.yaml` and edit the walls and props.
2. Run `./scripts/bld.sh --worlds --ros`.
3. Run `./scripts/up.sh explore --world my_world --ue`. Unreal switches to `my_world_layout.json` automatically.

## WSL notes

- **Networking.** WSL2 forwards `localhost` from Windows into WSL (the default NAT mode), so Unreal reaches `ws://127.0.0.1:9090`. If it can't, run `hostname -I` in WSL and put that IP into the Unreal setting `BridgeUrl`.
- **Graphics.** The Gazebo GUI and RViz render through WSLg. If Gazebo's ogre2 renderer crashes, see [troubleshooting.md](troubleshooting.md).
