"""Coordinate conversion between ROS / Gazebo and Unreal Engine (pure Python, unit-tested).

ROS / Gazebo (REP-103)            Unreal Engine
  right-handed                      left-handed
  x forward, y LEFT, z up           X forward, Y RIGHT, Z up
  metres                            centimetres
  radians, CCW-positive yaw         degrees, FRotator(Pitch, Yaw, Roll)

Position:   X =  100 x      Y = -100 y      Z = 100 z
Rotation:   Roll_ue  =  roll          (degrees)
            Pitch_ue = -pitch
            Yaw_ue   = -yaw
Quaternion: (x, y, z, w)_ros  ->  (-x, y, -z, w)_ue
            (mirroring the y axis flips the rotation sense about x and z)

Every ROS -> UE conversion in the project goes through this module (the UE side
does no maths), so getting the twin to move the right way only needs these tests
to pass.
"""

import math
from typing import Iterable, List, Sequence, Tuple

M_TO_CM = 100.0

Vec3 = Tuple[float, float, float]
Quat = Tuple[float, float, float, float]  # (x, y, z, w)


def ros_to_ue_location(x: float, y: float, z: float) -> Vec3:
    """ROS metres -> UE centimetres (mirror Y)."""
    return (x * M_TO_CM, -y * M_TO_CM, z * M_TO_CM)


def quat_to_rpy(q: Quat) -> Vec3:
    """Quaternion (x, y, z, w) -> (roll, pitch, yaw) in radians, ZYX convention."""
    x, y, z, w = q
    sinr = 2.0 * (w * x + y * z)
    cosr = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr, cosr)
    sinp = 2.0 * (w * y - z * x)
    pitch = math.copysign(math.pi / 2, sinp) if abs(sinp) >= 1 else math.asin(sinp)
    siny = 2.0 * (w * z + x * y)
    cosy = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny, cosy)
    return (roll, pitch, yaw)


def ros_rpy_to_ue_rotator(roll: float, pitch: float, yaw: float) -> Vec3:
    """ROS roll/pitch/yaw (rad) -> UE FRotator order [Pitch, Yaw, Roll] in degrees."""
    return (-math.degrees(pitch), -math.degrees(yaw), math.degrees(roll))


def ros_quat_to_ue_rotator(q: Quat) -> Vec3:
    """ROS quaternion -> UE [Pitch, Yaw, Roll] degrees."""
    return ros_rpy_to_ue_rotator(*quat_to_rpy(q))


def ros_quat_to_ue_quat(q: Quat) -> Quat:
    """ROS quaternion -> UE FQuat components (x, y, z, w)."""
    x, y, z, w = q
    return (-x, y, -z, w)


def yaw_to_quat(yaw: float) -> Quat:
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def quat_multiply(a: Quat, b: Quat) -> Quat:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def rotate_vector(q: Quat, v: Vec3) -> Vec3:
    """Rotate vector v by unit quaternion q."""
    x, y, z, w = q
    vx, vy, vz = v
    # t = 2 * cross(q.xyz, v)
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    # v' = v + w * t + cross(q.xyz, t)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


def compose(parent_pos: Vec3, parent_q: Quat, child_pos: Vec3, child_q: Quat) -> Tuple[Vec3, Quat]:
    """Pose composition parent * child (both in ROS frames)."""
    r = rotate_vector(parent_q, child_pos)
    pos = (parent_pos[0] + r[0], parent_pos[1] + r[1], parent_pos[2] + r[2])
    return pos, quat_multiply(parent_q, child_q)


def map_pose_to_world(map_to_world: Sequence[float], pos: Vec3, q: Quat) -> Tuple[Vec3, Quat]:
    """Transform a pose from SLAM's map frame to the Gazebo world frame.

    map_to_world = (x0, y0, yaw0): the robot's spawn pose, which is where SLAM
    Toolbox puts the map frame origin (odom starts at the spawn pose, map == odom
    at start-up).
    """
    x0, y0, yaw0 = map_to_world
    return compose((x0, y0, 0.0), yaw_to_quat(yaw0), pos, q)


def scan_to_world_points(ranges: Sequence[float], angle_min: float, angle_increment: float,
                         range_min: float, range_max: float, sensor_pos: Vec3, sensor_q: Quat,
                         decimation: int = 1) -> List[Vec3]:
    """Project LaserScan beams into world-frame hit points (ROS metres).

    Beams that hit nothing (inf / NaN / out of range) are skipped.
    """
    pts: List[Vec3] = []
    step = max(1, int(decimation))
    for i in range(0, len(ranges), step):
        r = ranges[i]
        if not math.isfinite(r) or r < range_min or r >= range_max:
            continue
        a = angle_min + i * angle_increment
        local = (r * math.cos(a), r * math.sin(a), 0.0)
        w = rotate_vector(sensor_q, local)
        pts.append((sensor_pos[0] + w[0], sensor_pos[1] + w[1], sensor_pos[2] + w[2]))
    return pts


def round_list(values: Iterable[float], ndigits: int = 2) -> List[float]:
    return [round(float(v), ndigits) for v in values]
