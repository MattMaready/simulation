# ROS 2 ↔ Gazebo bridge

ROS 2 (DDS) and Gazebo (gz-transport) are separate middlewares. `ros_gz_bridge`'s `parameter_bridge` copies messages between them. It is set up entirely by
`src/robot_splunker_gazebo/config/parameters.yaml`, which `sim.launch.py` loads:

```python
Node(package='ros_gz_bridge', executable='parameter_bridge',
     parameters=[{'config_file': '<share>/config/parameters.yaml', 'use_sim_time': True}])
```

## Entry format

```yaml
- ros_topic_name: "/scan"                 # name on the ROS 2 side
  gz_topic_name: "/scan"                  # name on the Gazebo side (= <topic> in the gazebo xacro)
  ros_type_name: "sensor_msgs/msg/LaserScan"
  gz_type_name: "gz.msgs.LaserScan"
  direction: GZ_TO_ROS                    # GZ_TO_ROS | ROS_TO_GZ | BIDIRECTIONAL
```

## Topics bridged

| ROS topic | Gazebo topic | ROS type | Gazebo type | Direction | Produced by | Used by |
|---|---|---|---|---|---|---|
| `/clock` | `/clock` | rosgraph_msgs/msg/Clock | gz.msgs.Clock | GZ→ROS | Gazebo world | every node (`use_sim_time`) |
| `/cmd_vel` | `/cmd_vel` | geometry_msgs/msg/Twist | gz.msgs.Twist | ROS→GZ | Nav2 / teleop | DiffDrive plugin |
| `/odom` | `/odom` | nav_msgs/msg/Odometry | gz.msgs.Odometry | GZ→ROS | DiffDrive | Nav2 |
| `/tf` | `/tf` | tf2_msgs/msg/TFMessage | gz.msgs.Pose_V | GZ→ROS | DiffDrive (odom→base_footprint) | everyone |
| `/joint_states` | `/joint_states` | sensor_msgs/msg/JointState | gz.msgs.Model | GZ→ROS | JointStatePublisher | robot_state_publisher, ue_bridge |
| `/scan` | `/scan` | sensor_msgs/msg/LaserScan | gz.msgs.LaserScan | GZ→ROS | gpu_lidar | SLAM, Nav2 costmaps, ue_bridge |
| `/imu` | `/imu` | sensor_msgs/msg/Imu | gz.msgs.IMU | GZ→ROS | imu sensor | (spare: for an EKF) |
| `/ground_truth/odom` | `/ground_truth/odom` | nav_msgs/msg/Odometry | gz.msgs.Odometry | GZ→ROS | OdometryPublisher | ue_bridge only |

Why each entry exists:

- **`/clock`.** Simulated time. All nodes run with `use_sim_time: true`, so timestamps, TF lookups and timeouts all follow Gazebo's clock, even when it runs slower than real time.
- **`/cmd_vel`.** The only ROS→Gazebo entry. Nav2 is set to `enable_stamped_cmd_vel: false`, so it sends a plain `Twist`. If you switch Nav2 to `TwistStamped`, change both type names here as well.
- **`/tf`.** DiffDrive publishes the odometry transform as a `Pose_V`, and the bridge turns it into a `TFMessage`. The fixed-joint transforms come from `robot_state_publisher` instead, not from Gazebo.

## Adding a topic

1. Make Gazebo publish it. For example, add a camera `<sensor>` with `<topic>camera/image</topic>` to the gazebo xacro.
2. Look up the matching message pair in the [ros_gz_bridge README](https://github.com/gazebosim/ros_gz/tree/jazzy/ros_gz_bridge). For example, `sensor_msgs/msg/Image` pairs with `gz.msgs.Image`.
3. Add an entry to `parameters.yaml` and rebuild with `./scripts/bld.sh --ros`.

   For images, `ros_gz_image`'s `image_bridge` is more efficient. It is optional.

## Debugging

```bash
gz topic -l                      # topics on the Gazebo side
gz topic -e -t /scan             # echo a Gazebo topic
ros2 topic list                  # topics on the ROS side
ros2 topic echo /scan --once
ros2 topic hz /clock             # is time flowing?
ros2 run tf2_tools view_frames   # TF tree as PDF
```

If a topic shows up on the Gazebo side but not in ROS, compare the topic name and the `gz_type_name` in `parameters.yaml` with what `gz topic -i -t <topic>` reports.
