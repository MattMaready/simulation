"""Unit tests for the ROS -> Unreal conversions (coords.py) and messages (protocol.py).

These pin down the handedness conversion: if these pass, the Unreal twin moves
forward when the Gazebo robot moves forward and turns left when it turns left.
"""

import base64
import json
import math

import pytest

from robot_splunker_ue_bridge import coords, protocol


def approx_seq(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_location_mirrors_y_and_scales_to_cm():
    assert coords.ros_to_ue_location(1.0, 2.0, 3.0) == (100.0, -200.0, 300.0)


def test_yaw_left_turn_is_negative_ue_yaw():
    # ROS +90 deg yaw = facing +y (left). In UE, left is -Y, which is yaw -90.
    pitch, yaw, roll = coords.ros_quat_to_ue_rotator(coords.yaw_to_quat(math.pi / 2))
    assert yaw == pytest.approx(-90.0)
    assert pitch == pytest.approx(0.0, abs=1e-9)
    assert roll == pytest.approx(0.0, abs=1e-9)


def test_forward_vector_matches_after_conversion():
    """Rotate ROS +x by a yaw, convert both the result and the yaw to UE: must agree."""
    for yaw in (0.3, -1.2, 2.5):
        fwd_ros = coords.rotate_vector(coords.yaw_to_quat(yaw), (1.0, 0.0, 0.0))
        fwd_ue = coords.ros_to_ue_location(*fwd_ros)
        _, ue_yaw, _ = coords.ros_rpy_to_ue_rotator(0.0, 0.0, yaw)
        # UE FRotator yaw: forward = (cos(yaw), sin(yaw)) in UE axes, scaled to cm
        expected = (100 * math.cos(math.radians(ue_yaw)), 100 * math.sin(math.radians(ue_yaw)), 0.0)
        assert approx_seq(fwd_ue, expected, 1e-6)


def test_pitch_and_roll_signs():
    # ROS +pitch (about +y) tips the nose DOWN; UE +pitch is nose UP.
    p, _, r = coords.ros_rpy_to_ue_rotator(0.1, 0.2, 0.0)
    assert p == pytest.approx(-math.degrees(0.2))
    assert r == pytest.approx(math.degrees(0.1))


def test_quat_rpy_roundtrip():
    q = coords.quat_multiply(coords.yaw_to_quat(0.7), (math.sin(0.05), 0.0, 0.0, math.cos(0.05)))
    roll, pitch, yaw = coords.quat_to_rpy(q)
    assert yaw == pytest.approx(0.7)
    assert roll == pytest.approx(0.1)
    assert pitch == pytest.approx(0.0, abs=1e-9)


def test_ue_quat_mirror():
    assert coords.ros_quat_to_ue_quat((0.1, 0.2, 0.3, 0.9)) == (-0.1, 0.2, -0.3, 0.9)


def test_map_pose_to_world_uses_spawn_pose():
    # Robot spawned at (-5, -5) facing +90 deg: map origin is there, map +x = world +y.
    pos, q = coords.map_pose_to_world((-5.0, -5.0, math.pi / 2), (1.0, 0.0, 0.0),
                                      (0.0, 0.0, 0.0, 1.0))
    assert approx_seq(pos, (-5.0, -4.0, 0.0))
    assert coords.quat_to_rpy(q)[2] == pytest.approx(math.pi / 2)


def test_scan_projection_skips_invalid_and_decimates():
    ranges = [1.0, float('inf'), 1.0, float('nan'), 0.05, 1.0]
    pts = coords.scan_to_world_points(ranges, 0.0, math.pi / 2, 0.12, 12.0,
                                      (0.0, 0.0, 0.2), (0.0, 0.0, 0.0, 1.0))
    # beams 0 (0 deg), 2 (180 deg), 5 (450 deg = 90 deg) are valid
    assert len(pts) == 3
    assert approx_seq(pts[0], (1.0, 0.0, 0.2))
    assert approx_seq(pts[1], (-1.0, 0.0, 0.2))
    dec = coords.scan_to_world_points([1.0] * 10, 0.0, 0.1, 0.1, 12.0, (0, 0, 0), (0, 0, 0, 1),
                                      decimation=2)
    assert len(dec) == 5


def test_protocol_pose_message():
    msg = json.loads(protocol.pose(1.5, (1.0, 2.0, 0.0), coords.yaw_to_quat(math.pi / 2)))
    assert msg['type'] == 'pose'
    assert msg['loc'] == [100.0, -200.0, 0.0]
    assert msg['rot'][1] == pytest.approx(-90.0)


def test_protocol_map_message_encodes_unknown_as_255():
    msg = json.loads(protocol.occupancy_map(0.0, 2, 1, 0.05, (1.0, 1.0), 0.0, [-1, 100]))
    assert msg['w'] == 2 and msg['h'] == 1 and msg['res_cm'] == pytest.approx(5.0)
    assert list(base64.b64decode(msg['data_b64'])) == [255, 100]
    assert msg['origin'] == [100.0, -100.0, 0.0]
    raw = protocol.occupancy_map(0.0, 2, 1, 0.05, (0.0, 0.0), 0.0, bytes([255, 0]))
    assert list(base64.b64decode(json.loads(raw)['data_b64'])) == [255, 0]
