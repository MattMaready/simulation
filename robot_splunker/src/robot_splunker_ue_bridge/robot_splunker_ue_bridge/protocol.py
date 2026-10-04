"""JSON messages sent from ue_bridge to the Unreal Engine visualizer (protocol v1).

Every message is one WebSocket TEXT frame holding a JSON object with a "type".
All positions are already in Unreal world space (cm, left-handed), all
rotations are [Pitch, Yaw, Roll] in degrees, so the UE side does no maths.

  hello      {"type":"hello","version":1,"world":"splunker_cave"}
  pose       {"type":"pose","stamp":t,"loc":[X,Y,Z],"rot":[P,Y,R]}       ground truth (Gazebo)
  slam_pose  {"type":"slam_pose","stamp":t,"loc":[...],"rot":[...]}      SLAM estimate ("ghost")
  wheels     {"type":"wheels","stamp":t,"left":rad,"right":rad}          joint angles
  scan       {"type":"scan","stamp":t,"origin":[X,Y,Z],"hits":[[X,Y,Z],...]}
  map        {"type":"map","stamp":t,"w":W,"h":H,"res_cm":5.0,
              "origin":[X,Y,Z],"yaw":deg,"data_b64":"..."}               int8 cells, row-major,
                                                                          row 0 = map y-min
  status     {"type":"status","state":"EXPLORING"}

Map placement: cell (col, row) sits at
    origin + R(yaw) * (col * res_cm, -row * res_cm, 0)       (UE frame)
because the map's +y axis becomes UE's -Y.
"""

import base64
import json
import math
from typing import Sequence

from robot_splunker_ue_bridge import coords

PROTOCOL_VERSION = 1


def _dumps(obj) -> str:
    return json.dumps(obj, separators=(',', ':'))


def hello(world: str) -> str:
    return _dumps({'type': 'hello', 'version': PROTOCOL_VERSION, 'world': world})


def pose(stamp: float, pos_ros, quat_ros, kind: str = 'pose') -> str:
    """kind = 'pose' (ground truth) or 'slam_pose'."""
    loc = coords.ros_to_ue_location(*pos_ros)
    rot = coords.ros_quat_to_ue_rotator(quat_ros)
    return _dumps({'type': kind, 'stamp': round(stamp, 3),
                   'loc': coords.round_list(loc, 2), 'rot': coords.round_list(rot, 3)})


def wheels(stamp: float, left: float, right: float) -> str:
    return _dumps({'type': 'wheels', 'stamp': round(stamp, 3),
                   'left': round(left, 4), 'right': round(right, 4)})


def scan(stamp: float, origin_ros, hits_ros) -> str:
    return _dumps({
        'type': 'scan', 'stamp': round(stamp, 3),
        'origin': coords.round_list(coords.ros_to_ue_location(*origin_ros), 1),
        'hits': [coords.round_list(coords.ros_to_ue_location(*h), 1) for h in hits_ros],
    })


def occupancy_map(stamp: float, width: int, height: int, resolution_m: float,
                  origin_world_xy: Sequence[float], origin_world_yaw: float,
                  data: Sequence[int]) -> str:
    """origin_* = pose of cell (0,0)'s corner in the Gazebo WORLD frame (already map->world)."""
    if isinstance(data, (bytes, bytearray)):
        raw = bytes(data)                           # already raw int8 bytes
    else:
        raw = bytes((int(v) & 0xFF) for v in data)  # int8 -> uint8 (two's complement; -1 -> 255)
    return _dumps({
        'type': 'map', 'stamp': round(stamp, 3), 'w': int(width), 'h': int(height),
        'res_cm': round(resolution_m * coords.M_TO_CM, 4),
        'origin': coords.round_list(coords.ros_to_ue_location(
            origin_world_xy[0], origin_world_xy[1], 0.0), 2),
        'yaw': round(-math.degrees(origin_world_yaw), 4),
        'data_b64': base64.b64encode(raw).decode('ascii'),
    })


def status(state: str) -> str:
    return _dumps({'type': 'status', 'state': state})
