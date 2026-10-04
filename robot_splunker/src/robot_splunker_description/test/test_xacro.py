"""Sanity tests for the robot_splunker xacro model.

Expands urdf/robot_splunker.urdf.xacro and checks the expected links/joints exist,
joint types and axes are right, and every inertial block is physically valid.
Run with:  colcon test --packages-select robot_splunker_description
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import xacro

XACRO_PATH = Path(__file__).resolve().parent.parent / "urdf" / "robot_splunker.urdf.xacro"


@pytest.fixture(scope="module")
def robot():
    doc = xacro.process_file(str(XACRO_PATH))
    return ET.fromstring(doc.toxml())


def _links(robot):
    return {link.get("name"): link for link in robot.findall("link")}


def _joints(robot):
    return {j.get("name"): j for j in robot.findall("joint")}


def test_expected_links(robot):
    expected = {"base_footprint", "base_link", "chassis", "left_wheel", "right_wheel",
                "caster_link", "lidar_link", "imu_link"}
    assert expected <= set(_links(robot))


def test_wheel_joints_are_continuous_about_y(robot):
    joints = _joints(robot)
    for name in ("left_wheel_joint", "right_wheel_joint"):
        j = joints[name]
        assert j.get("type") == "continuous"
        assert [float(v) for v in j.find("axis").get("xyz").split()] == [0.0, 1.0, 0.0]


def test_wheels_are_symmetric(robot):
    joints = _joints(robot)
    yl = float(joints["left_wheel_joint"].find("origin").get("xyz").split()[1])
    yr = float(joints["right_wheel_joint"].find("origin").get("xyz").split()[1])
    assert yl > 0 > yr
    assert yl == pytest.approx(-yr)


def test_caster_is_fixed_and_touches_ground(robot):
    joints = _joints(robot)
    caster = joints["caster_joint"]
    assert caster.get("type") == "fixed"
    # base_link is wheel_radius above ground; caster centre must be caster_radius above ground
    base_z = float(joints["base_joint"].find("origin").get("xyz").split()[2])
    caster_z = float(caster.find("origin").get("xyz").split()[2])
    radius = float(_links(robot)["caster_link"].find("collision/geometry/sphere").get("radius"))
    assert base_z + caster_z == pytest.approx(radius)


def test_inertials_are_valid(robot):
    for name, link in _links(robot).items():
        inertial = link.find("inertial")
        if inertial is None:
            continue  # pure frames (base_footprint, base_link)
        mass = float(inertial.find("mass").get("value"))
        assert mass > 0, name
        i = inertial.find("inertia")
        ixx, iyy, izz = (float(i.get(k)) for k in ("ixx", "iyy", "izz"))
        assert min(ixx, iyy, izz) > 0, name
        # triangle inequality for principal moments of a real rigid body
        assert ixx + iyy >= izz - 1e-12, name
        assert ixx + izz >= iyy - 1e-12, name
        assert iyy + izz >= ixx - 1e-12, name


def test_gazebo_plugins_present(robot):
    plugins = {p.get("filename") for p in robot.iter("plugin")}
    assert {"gz-sim-diff-drive-system", "gz-sim-joint-state-publisher-system",
            "gz-sim-odometry-publisher-system"} <= plugins


def test_sensors_present(robot):
    sensors = {s.get("type") for s in robot.iter("sensor")}
    assert {"gpu_lidar", "imu"} <= sensors
