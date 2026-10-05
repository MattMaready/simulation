# Troubleshooting

Start every investigation with the log: `tail -f ~/.robot_splunker/run/logs/latest.log`.

## Build

| Symptom | Fix |
|---|---|
| `ROS 2 jazzy not found` | Run `./scripts/setup_wsl.sh` |
| `$'\r': command not found` | A script was saved with Windows line endings. Run `sed -i 's/\r$//' scripts/*.sh`. `.gitattributes` prevents this on checkout. |
| xacro error in stage 2 | Read the message. The URDF is expanded on its own at `build_artifacts/robot_splunker.urdf`. |
| `Layout not found` in Unreal | Run `./scripts/bld.sh --worlds`. The layout JSON is generated. |
| Unreal stage skipped | Set `UE_ROOT` in `scripts/.env`, or build from Windows with `scripts\bld_ue.ps1` |
| UE build: missing Windows SDK / MSVC | Install the Visual Studio 2022 "Game development with C++" workload |

## Gazebo / WSLg

| Symptom | Fix |
|---|---|
| Gazebo window is black or crashes (ogre2) | Update the Windows GPU driver and run `wsl --update`. As a last resort, use `export LIBGL_ALWAYS_SOFTWARE=1` before `up.sh`. This is slow, but the gpu_lidar still works. |
| Gazebo **and** Unreal together are slow | Lower Unreal's scalability (Settings → Engine Scalability → High or Medium) and/or shrink the Gazebo window. Close RViz with `--no-rviz` if you don't need it. |
| `up.sh` times out on `/clock` | Gazebo did not start. Look in the log for `gz sim` errors (missing world?). Run `./scripts/bld.sh --worlds --ros`. |
| Robot falls through the floor / jitters | Check that the spawn `z` is just above 0 and that the inertia values are positive (`bld.sh --test`) |

## ROS side

| Symptom | Likely cause / fix |
|---|---|
| Robot doesn't move with teleop | `/cmd_vel` type mismatch. The bridge expects `geometry_msgs/msg/Twist`. Check `gz topic -e -t /cmd_vel` while publishing. |
| No `/map` | No `/scan` (`ros2 topic hz /scan`), or a frame mismatch. `base_frame` must be `base_footprint`. |
| `Lookup would require extrapolation` | A node is missing `use_sim_time: true`, or `/clock` is not bridged |
| Nav2 never becomes active | `/map` or `map → odom` was not ready when Nav2 started. Raise the 5 s `TimerAction` in `explore.launch.py`. Check with `ros2 lifecycle get /bt_navigator`. |
| Explorer keeps saying "waiting for Nav2" | Same as above, or Nav2 crashed. Search the log for `controller_server`. |
| Explorer stops early ("no reachable frontier") | Raise `empty_checks_to_finish`, lower `min_frontier_size` / `clearance_radius` |
| Robot oscillates in doorways | Lower `inflation_radius` (0.45) or `desired_linear_vel` in `nav2_params.yaml` |
| `A stack is already running` | Run `./scripts/dn.sh`. A stale PID file is cleaned up automatically. |
| Leftover processes after a crash | `./scripts/dn.sh --force` |
| Want to start completely fresh / something left over from an earlier run | Follow [Start fresh](running.md#5-start-fresh-ignore-previous-runs) in running.md |

## Unreal twin

| Symptom | Fix |
|---|---|
| HUD says "waiting for ws://127.0.0.1:9090" | Was `up.sh` run with `--ue`? Check `ss -ltn \| grep 9090` in WSL. Test from Windows with `Test-NetConnection 127.0.0.1 -Port 9090`. If WSL localhost forwarding is off, set `BridgeUrl` to the WSL IP from `hostname -I`. |
| Windows Firewall prompt | Allow it for private networks |
| Twin moves mirrored / turns the wrong way | Run the `ue_bridge` tests: `colcon test --packages-select robot_splunker_ue_bridge`. All conversions live in `coords.py`. |
| Twin is offset from the walls | The world layout and the running world differ. Run `bld.sh --worlds`, then check the HUD "World:" line. |
| Map overlay missing | Expected without a `MapOverlayMaterial`; the minimap (top right) still works |
| Very dark scene | Auto-exposure is adapting, so wait a second. Or raise `ASplunkerLightingRig` intensities, or add your own lights. |
