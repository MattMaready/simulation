# Unreal Engine 5 visualization (digital twin)

`unreal/SplunkerViz` is a UE 5.5+ C++ project. It shows the robot exploring a realistic version of the same world Gazebo simulates, **at the same time** as the Gazebo window. Gazebo stays the simulator: physics and sensors happen there. Unreal only displays, and never sends commands.

## Why Unreal runs on Windows, not in WSL2/Ubuntu

| | Windows (chosen) | Ubuntu in WSL2 |
|---|---|---|
| GPU | Native DirectX 12 driver, so Lumen, Nanite and virtual shadow maps run at full speed | Only through WSLg's D3D12-to-Mesa translation: far too slow and unstable for the UE editor |
| Install | Binary from the Epic Games Launcher | Must be built from source (100+ GB, hours of compiling) |
| Tooling and assets | Visual Studio 2022, Fab/Quixel Megascans | Less polished Linux editor |

ROS 2 and Gazebo stay in WSL2. They talk to Unreal over **one WebSocket** (`ue_bridge`, port 9090). WSL2 forwards `localhost`, so no DDS traffic has to cross the Windows/WSL boundary.

## Requirements

- Unreal Engine **5.5 or newer**, from the Epic Games Launcher. The `.uproject` is set to 5.5; newer versions offer to convert it, and the code uses only stable engine APIs.
- **Visual Studio 2022** with the "Game development with C++" workload, plus the Windows SDK that your UE version asks for.

## Build

Pick one:

- **From WSL:** set `UE_ROOT` in `scripts/.env`, then run `./scripts/bld.sh --ue`.
- **From PowerShell:** `powershell -ExecutionPolicy Bypass -File scripts\bld_ue.ps1 [-UeRoot "C:\Program Files\Epic Games\UE_5.5"]`
- **By hand:** right-click `SplunkerViz.uproject` and choose *Generate Visual Studio project files*. Open `SplunkerViz.sln` and build **Development Editor | Win64**.

## Run

1. In WSL, start the stack with the bridge: `./scripts/up.sh explore --ue`
2. Start Unreal, either way:
   - automatically: add `--start-ue` to the `up.sh` command (opens the viewer window with `-game`, or the full editor with `--ue-editor`), or
   - manually: open `unreal/SplunkerViz/SplunkerViz.uproject` and press **Play**.
3. Put the Gazebo window and the Unreal window side by side. The Unreal HUD should show **ROS bridge: CONNECTED**.

**No binary assets are needed.** The project opens on the engine's empty `Entry` map. `ASplunkerGameMode` (the global default GameMode) then spawns everything that is missing:

| Actor | Role |
|---|---|
| `ASplunkerWorldBuilder` | Reads `Content/Splunker/Data/<world>_layout.json`, which `generate_world.py` writes, and builds the floor, walls and props. |
| `ASplunkerRobot` | The robot twin: chassis, two wheels, caster and lidar puck, sized from `properties.xacro`, plus a headlight. It follows the ground-truth pose and spins its wheels. |
| `ALidarVisualizer` | The last few lidar scans, drawn as red points on the walls. |
| `AOccupancyMapActor` | The SLAM map as a texture (minimap), plus an optional floor overlay. |
| `ASplunkerLightingRig` | Low sun, sky atmosphere, real-time sky light and height fog, for a Lumen "dusk cave" look. |
| `ASplunkerCameraPawn` + `ASplunkerHUD` | Camera modes, status text and the minimap. |

To make a hand-built level, create a level, place any of these actors yourself and set them up in the Details panel. The GameMode only spawns the ones that are missing.

## Controls (in the Unreal window)

| Key | Action |
|---|---|
| `1` | Chase camera (behind the robot) |
| `2` | Orbit camera (mouse to orbit) |
| `3` | Top-down camera (ROS +x is up the screen, +y to the left) |
| `4` | Free-fly: WASD to move, Q/E for down/up, mouse to look, Shift for speed |
| Mouse wheel | Zoom |
| `H` | Toggle the floor map overlay (needs an overlay material, see below) |
| `G` | Toggle the SLAM ghost: a blue plate where SLAM *thinks* the robot is |
| `L` | Toggle the lidar points |
| `F1` | Show or hide the help |
| `Esc` | Quit |

## Settings (Project Settings → Game → Splunker Viz, or `Config/DefaultGame.ini`)

| Setting | Default | Meaning |
|---|---|---|
| `BridgeUrl` | `ws://127.0.0.1:9090` | `ue_bridge` address. Use the WSL IP (`hostname -I`) if localhost forwarding is off. |
| `ReconnectIntervalSeconds` | 2 | How often to retry while ROS is not running |
| `LayoutFile` | `Splunker/Data/splunker_cave_layout.json` | Starting layout. It switches automatically to whatever world ROS reports. |
| `MaterialOverrides` | empty | Tag → material, for realistic surfaces (see below) |
| `FallbackColors` | Gazebo colours | Used for tags without an override |
| `MapOverlayMaterial`, `MapOverlayTextureParameter` | none, `MapTexture` | Floor overlay material |
| `LidarScansToKeep`, `LidarPointSizeCm`, `LidarColor` | 3, 3, red | Lidar look |
| `PoseInterpSpeed` | 15 | How smoothly the robot moves between 30 Hz pose updates |
| `bAutoSpawnActors`, `bAutoSpawnLighting` | true | The GameMode's auto-spawning |

## Making it realistic

1. In the Fab / Quixel Bridge plugin, add a few surfaces to the project, such as concrete, rock, brick, metal and wood. For walls that are scaled boxes, *world-aligned* materials look best because they don't stretch.
2. Under **Project Settings → Game → Splunker Viz → Material Overrides**, map each tag to a material. The tags are `concrete`, `rock`, `brick`, `metal`, `wood` and `floor`, the same ones used in `worlds/*.world.yaml`.
3. Optional floor overlay: create a translucent, unlit material with a `Texture2D` parameter named `MapTexture`. Opacity around 0.5 works; multiply by the texture's alpha. Set it as `MapOverlayMaterial`. If it appears mirrored, apply `1 - V` to its texture coordinate.
4. Optional mood: place your own `DirectionalLight` / `SkyLight` / fog in a level. The lighting rig is then not spawned.

## Protocol (WSL → Unreal)

The bridge sends one JSON object per WebSocket text frame. Positions are already in **Unreal space** (cm, left-handed) and rotations are `[Pitch, Yaw, Roll]` in degrees. The definition is in `src/robot_splunker_ue_bridge/robot_splunker_ue_bridge/protocol.py`.

| type | Fields | Rate |
|---|---|---|
| `hello` | `version`, `world` | on connect |
| `pose` | `stamp`, `loc`, `rot`: Gazebo ground truth | 30 Hz |
| `slam_pose` | `stamp`, `loc`, `rot`: SLAM estimate | 10 Hz |
| `wheels` | `left`, `right`: wheel angles in rad | 30 Hz |
| `scan` | `origin`, `hits`: lidar hit points in world space | 10 Hz |
| `map` | `w`, `h`, `res_cm`, `origin`, `yaw`, `data_b64`: int8 cells, 255 = unknown | ≤1 Hz, and on connect |
| `status` | `state`: explorer state | on change, and on connect |

### Coordinate conversion (ROS → Unreal)

| | ROS / Gazebo | Unreal | Conversion |
|---|---|---|---|
| Handedness | right-handed | left-handed | mirror Y |
| Axes | x fwd, y **left**, z up | X fwd, Y **right**, Z up | |
| Position | metres | centimetres | `X = 100x, Y = −100y, Z = 100z` |
| Yaw | rad, counter-clockwise + | deg, clockwise + (from above) | `Yaw = −deg(yaw)` |
| Pitch | +pitch = nose down | +pitch = nose up | `Pitch = −deg(pitch)` |
| Roll | | | `Roll = deg(roll)` |
| Quaternion | (x, y, z, w) | | `(−x, y, −z, w)` |
| Map frame | starts at the robot spawn pose | | `ue_bridge` applies `map_to_world` (from `<world>.meta.json`) |

All of this lives in `coords.py` and is covered by `test/test_coords.py`.

## Extending

- **New message type.** Add a builder in `protocol.py` and publish it from `ue_bridge_node.py`. Then add a branch in `USplunkerBridgeSubsystem::HandleMessage`, store the data in a struct in `SplunkerTypes.h`, and read it from an actor's `Tick`.
- **Future: control from Unreal.** The socket is already two-way. `ue_bridge` currently ignores incoming frames; it could map them to `/cmd_vel` or `/goal_pose`.
- **Future: photoreal sensors.** Render a UE camera and send the frames back to ROS as `sensor_msgs/Image`, for perception experiments.
