# Robot model

Files: `src/robot_splunker_description/urdf/`

| File | Contents |
|---|---|
| `robot_splunker.urdf.xacro` | Top level: links and joints, the wheel macro, and the includes |
| `properties.xacro` | **Every dimension and mass.** Edit the robot here. |
| `inertial_macros.xacro` | `box_inertia`, `cylinder_inertia`, `sphere_inertia` |
| `robot_splunker.gazebo.xacro` | Colours, friction, Gazebo plugins (DiffDrive, JointStatePublisher, OdometryPublisher) and the sensors |
| `sensors.xacro` | Lidar and IMU links and joints |

## Geometry

```
            top view (x forward, y left)              side view
                 ┌──────────────────┐ ← chassis 0.40 × 0.30 × 0.10
   left wheel ▐█▌│      ◯ lidar     │                 ◯ lidar (z 0.155)
   (y +0.18)     │  ●base_link      │ ○ caster     ┌───────────┐
   right wheel▐█▌│                  │  (x +0.25)   └─█───────○─┘  ground clearance 0.03
                 └──────────────────┘                ↑ wheels r 0.05
```

| Part | Shape | Size (m) | Mass (kg) | Position relative to `base_link` (m) |
|---|---|---|---|---|
| chassis | box | 0.40 × 0.30 × 0.10 | 2.0 | (0.10, 0, 0.03) |
| left / right wheel | cylinder (axis y) | r 0.05, width 0.04 | 0.2 each | (0, ±0.18, 0) |
| caster | sphere | r 0.025 | 0.05 | (0.25, 0, −0.025) |
| lidar | cylinder | r 0.04, h 0.05 | 0.1 | (0.12, 0, 0.105) |
| imu | box | 0.02 cube | 0.01 | (0.10, 0, 0.03) |

The total mass is 2.56 kg. `base_link` sits 0.05 m above `base_footprint` (one wheel radius).

### Joints

| Joint | Type | Parent → child | Notes |
|---|---|---|---|
| `base_joint` | fixed | base_footprint → base_link | z = wheel radius |
| `chassis_joint` | fixed | base_link → chassis | |
| `left_wheel_joint`, `right_wheel_joint` | **continuous**, axis +y | base_link → wheel | A positive angle rolls the robot forward |
| `caster_joint` | fixed | base_link → caster_link | Frictionless sphere (see architecture.md) |
| `lidar_joint`, `imu_joint` | fixed | base_link → sensor | |

## Inertia

All parts are treated as uniform solids. Inertia is taken about the centre of mass:

| Shape | Formula |
|---|---|
| Box (x, y, z) | Ixx = m(y²+z²)/12, Iyy = m(x²+z²)/12, Izz = m(x²+y²)/12 |
| Cylinder (r, h), axis z | Ixx = Iyy = m(3r²+h²)/12, Izz = mr²/2 |
| Sphere (r) | I = 2mr²/5 |

Resulting values:

| Link | Ixx | Iyy | Izz |
|---|---|---|---|
| chassis | 0.016667 | 0.028333 | 0.041667 |
| wheel (axis along y after rotation) | 0.000152 | 0.000152 | 0.000250 |
| caster | 0.0000125 | 0.0000125 | 0.0000125 |
| lidar | 0.0000608 | 0.0000608 | 0.0000800 |

The wheel's inertial block uses the same `rpy = (-π/2, 0, 0)` as its visual and collision, so the tensor lines up with the wheel's real axis.

## Gazebo properties (`robot_splunker.gazebo.xacro`)

- **Colours.** Each colour is defined once as an RGBA property. It is exported both as a URDF `<material>` (for RViz) and as a Gazebo `<visual><material>` with ambient, diffuse and specular values. Harmonic ignores the old `Gazebo/Orange` style names.
- **Friction.** The wheels have μ = 1.0 and are stiff (kp = 1e6). The caster has μ = 0.
- **DiffDrive.**
  - It uses wheel separation 0.36 and wheel radius 0.05, taken from `properties.xacro`.
  - It listens on `cmd_vel`, publishes `odom`, and publishes `odom → base_footprint` on `tf`.
  - Limits are 0.6 m/s and 2 rad/s.
- **JointStatePublisher.** Publishes `joint_states` for the two wheel joints.
- **OdometryPublisher.** Publishes `ground_truth/odom`, the true world pose. Only the Unreal twin uses it.
- **gpu_lidar.** 360 samples over 360°, range 0.12–12 m, 10 Hz, σ = 1 cm noise, on topic `scan`.
- **imu.** 100 Hz on topic `imu`.

Fixed joints are merged into their parent link when Gazebo loads the URDF. The sensors therefore set `<gz_frame_id>`, so their messages still say `lidar_link` and `imu_link`.

## Changing the robot

1. Edit `properties.xacro`. If you change wheel separation or radius, the DiffDrive plugin picks the new values up automatically.
2. Run `./scripts/bld.sh --worlds`. This expands the xacro and runs `check_urdf`.
3. Check the result in `./scripts/up.sh display` (RViz only) and then in `./scripts/up.sh sim`.
4. If the footprint changed, update `robot_radius` in `nav2_params.yaml`.
5. Optionally, update the Unreal twin's sizes. They are the `ASplunkerRobot` properties in centimetres (Details panel or `SplunkerRobot.h`).
