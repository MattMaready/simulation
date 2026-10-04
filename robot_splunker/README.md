# robot_splunker

A ROS 2 workspace for a small differential-drive robot that **maps an unknown environment on its own**.

- **Gazebo Harmonic** simulates the physics, lidar and IMU.
- **SLAM Toolbox** builds the map.
- **Nav2** handles path planning.
- A custom **frontier explorer** decides where to drive next.

The robot keeps exploring until there is nothing left to map. Then it returns home and saves the map.

**Unreal Engine 5** shows a realistic **digital twin** of the same run on Windows. It runs alongside the Gazebo window.

```
 WSL2 Ubuntu 24.04 (ROS 2 Jazzy)                      Windows 11
┌──────────────────────────────────────────┐        ┌──────────────────────────────┐
│ Gazebo Harmonic  ⇄  ros_gz_bridge        │        │ Unreal Engine 5 (SplunkerViz) │
│ SLAM Toolbox · Nav2 · frontier_explorer  │  WS    │ robot twin · lidar · map     │
│ ue_bridge (ROS → UE coordinates, JSON) ──┼──9090──┼▶ HUD + minimap · cameras     │
└──────────────────────────────────────────┘        └──────────────────────────────┘
```

## Quick start (inside WSL2 Ubuntu 24.04)

```bash
cd /mnt/c/work/stephan/simulation/robot_splunker
./scripts/setup_wsl.sh -y                 # one time: ROS 2 Jazzy, Gazebo Harmonic, SLAM, Nav2, tools
cp scripts/.env.example scripts/.env      # optional: set UE_ROOT for the Unreal parts
./scripts/bld.sh --test                   # build worlds + ROS packages (+ Unreal if UE_ROOT set), run tests
./scripts/up.sh explore --ue --start-ue   # Gazebo + RViz + autonomous exploration + Unreal twin
./scripts/dn.sh                           # stop everything
```

Every script supports `-h` / `--help`.

## Repository layout

| Path | What it is |
|---|---|
| `src/robot_splunker_description` | **XACRO** robot model: geometry, inertia, links and joints. It also holds the **Gazebo xacro** (colours, friction, plugins, sensors) and the RViz display launch. |
| `src/robot_splunker_gazebo` | Generated worlds, the **`config/parameters.yaml`** ROS↔Gazebo bridge map, and **`launch/sim.launch.py`**. |
| `src/robot_splunker_bringup` | `explore.launch.py` (main), `mapping.launch.py`, `navigation.launch.py`, and the SLAM, Nav2 and explorer parameters. |
| `src/robot_splunker_exploration` | `frontier_explorer` node: the autonomous exploration logic. |
| `src/robot_splunker_ue_bridge` | `ue_bridge_node`: streams the robot's state to Unreal over a WebSocket. |
| `unreal/SplunkerViz` | UE 5.5+ C++ project. It is the digital-twin viewer and needs no binary assets. |
| `worlds/*.world.yaml` | **Single source of truth** for each world. Both the Gazebo SDF and the Unreal layout are generated from it. |
| `scripts/` | `setup_wsl.sh`, `bld.sh`, `up.sh`, `dn.sh`, `bld_ue.ps1` and `generate_world.py`. |
| `docs/` | Design and usage documentation (below). |
| `maps/` | Where finished maps are saved (`<world>.pgm/.yaml/.posegraph`). |

## Documentation

1. [Architecture](docs/architecture.md): packages, data flow, TF tree, and the design decisions behind them.
2. [Robot model](docs/robot_model.md): dimensions, inertia formulas, and how to change the robot.
3. [Gazebo bridge](docs/gazebo_bridge.md): every `parameters.yaml` entry, and how to add a topic.
4. [Running](docs/running.md): setup, building, the `up.sh`/`dn.sh` modes, and running launch files by hand.
5. [Control](docs/control.md): exploration tuning, teleop, Nav2 goals, and saving and loading maps.
6. [Unreal visualization](docs/unreal_visualization.md): why UE runs on Windows, how to build and run it, the protocol, and realistic materials.
7. [Troubleshooting](docs/troubleshooting.md)
