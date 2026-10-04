# Controlling robot_splunker

There are three ways to move the robot, from fully autonomous to fully manual. Unreal never sends commands; it only displays.

## 1. Autonomous exploration (default)

```bash
./scripts/up.sh explore --ue
```

`frontier_explorer` runs as a state machine:

```
WAIT_FOR_MAP ─► EXPLORING ─► NAVIGATING ─┐
                    ▲                    │ goal reached / cancelled / failed
                    └────────────────────┘
EXPLORING with no frontiers (3 checks in a row) ─► RETURNING_HOME ─► COMPLETE (map saved)
```

Each cycle (every `replan_period_s`):

1. **Find frontiers.** These are free cells next to unknown cells on `/map`. Neighbouring cells (8-connected) are grouped into clusters, and clusters smaller than `min_frontier_size` are dropped.
2. **Choose a goal for each frontier.** Start from the frontier cell nearest the cluster centroid, then snap it to the nearest free cell with no obstacle within `clearance_radius`, searching up to `goal_search_radius`. Skip goals closer than `min_goal_distance` or inside `blacklist_radius` of an earlier goal.
3. **Score** each goal as `size_weight × frontier length (m) − dist_weight × distance (m)` and send the best one to Nav2.
4. **While driving,** cancel the goal and blacklist it if any of these happen:
   - it takes longer than `goal_timeout_s`
   - the robot moves less than `progress_distance` within `progress_timeout_s`
   - Nav2 aborts it

   If the frontier gets explored on the way (no unknown cells left nearby), cancel it **without** blacklisting and pick the next one.
5. **When no frontiers remain,** drive back to the start pose (`return_home`), then call SLAM Toolbox's `save_map` and `serialize_map`. This writes `maps/<world>.pgm`, `.yaml`, `.posegraph` and `.data`.

You can watch it in RViz: frontiers are blue dots, the chosen goal is a green sphere, and the path is a green line. The current state is on `/explore/status` and on the Unreal HUD.

```bash
ros2 topic echo /explore/status
```

### Tuning (`src/robot_splunker_bringup/config/explorer_params.yaml`)

| Symptom | Change |
|---|---|
| Robot chases tiny gaps or noise | Raise `min_frontier_size` |
| Zig-zags between far-apart frontiers | Raise `dist_weight` |
| Leaves big areas for later | Raise `size_weight` |
| Gives up on reachable goals | Raise `goal_timeout_s` / `progress_timeout_s` |
| Goals too close to walls | Raise `clearance_radius` |
| Declares "done" too early | Raise `empty_checks_to_finish` |

Parameter files are installed as symlinks (`--symlink-install`), so after editing you only need to restart: `dn.sh` then `up.sh`.

### Stop or restart exploring

```bash
# Stop exploring but keep Gazebo, SLAM and Nav2 running. On Ctrl-C/SIGINT the
# explorer cancels its current Nav2 goal, so the robot stops.
pkill -INT -f frontier_explorer

# Start it again (it continues on the existing map):
ros2 run robot_splunker_exploration frontier_explorer --ros-args \
  --params-file ~/robot_splunker_ws/install/robot_splunker_bringup/share/robot_splunker_bringup/config/explorer_params.yaml \
  -p use_sim_time:=true
```

## 2. Point-and-click goals (Nav2)

In mapping or explore mode, click **2D Goal Pose** in RViz and then click-drag on the map. This publishes `/goal_pose`, which `bt_navigator` follows. In explore mode the explorer will send its own goal again on its next cycle, so for manual goals stop the explorer first, or use `up.sh sim` plus your own Nav2.

From the command line:

```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: map}, pose: {position: {x: 2.0, y: 1.0}, orientation: {w: 1.0}}}}"
```

## 3. Manual driving (teleop)

```bash
./scripts/up.sh mapping --teleop        # opens teleop in a new terminal window
# or, in any ROS-sourced terminal:
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

The keys are `i` forward, `,` back, `j`/`l` turn, `k` stop, and `q`/`z` change speed. Teleop publishes `/cmd_vel` directly to the bridge.

Raw command for a quick test:

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.2}, angular: {z: 0.3}}"
```

## Maps

| Action | Command |
|---|---|
| Save at any time (image + yaml) | `ros2 run nav2_map_server map_saver_cli -f maps/my_map` |
| Save via SLAM Toolbox | `ros2 service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap "{name: {data: 'maps/my_map'}}"` |
| Save the pose graph (to continue later) | `ros2 service call /slam_toolbox/serialize_map slam_toolbox/srv/SerializePoseGraph "{filename: 'maps/my_map'}"` |
| View a saved map | `ros2 run nav2_map_server map_server --ros-args -p yaml_filename:=maps/my_map.yaml` (then activate it and view `/map` in RViz) |

With `up.sh`, finished maps go to `<repo>/maps/<world>.*`. When launching by hand, they go to `~/robot_splunker_maps/` unless you pass `map_save_path:=...`.
