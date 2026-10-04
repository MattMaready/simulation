"""sim.launch.py: run robot_splunker in Gazebo Harmonic with the ROS 2 bridges in place.

Starts, in order:
  1. GZ_SIM_RESOURCE_PATH set so Gazebo can resolve package:// / model:// URIs
  2. Gazebo (ros_gz_sim/gz_sim.launch.py) with the chosen world, running (-r)
  3. robot_state_publisher with the expanded xacro (publishes /robot_description + TF)
  4. ros_gz_sim `create`: spawns the robot from /robot_description
  5. ros_gz_bridge parameter_bridge with config/parameters.yaml (clock, cmd_vel,
     odom, tf, joint_states, scan, imu, ground-truth odom)

Arguments:
  world         world name or .sdf path            (default: splunker_cave)
  x, y, yaw     spawn pose; empty = read from worlds/<world>.meta.json
  gui           true = Gazebo GUI, false = server only (-s)   (default: true)
  use_sim_time  default: true

Example:
  ros2 launch robot_splunker_gazebo sim.launch.py world:=empty
"""

import json
import os

import xacro
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (AppendEnvironmentVariable, DeclareLaunchArgument,
                            IncludeLaunchDescription, OpaqueFunction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def resolve_world(world_arg):
    """Return the absolute .sdf path for a world name ('splunker_cave') or a path."""
    if os.path.isabs(world_arg) and os.path.exists(world_arg):
        return world_arg
    worlds_dir = os.path.join(get_package_share_directory('robot_splunker_gazebo'), 'worlds')
    name = world_arg if world_arg.endswith('.sdf') else world_arg + '.sdf'
    path = os.path.join(worlds_dir, name)
    if not os.path.exists(path):
        raise RuntimeError(f'World not found: {path} (run ./scripts/bld.sh --worlds?)')
    return path


def resolve_spawn(world_path, x, y, yaw):
    """Spawn pose: explicit launch args win; otherwise <world>.meta.json; otherwise 0,0,0."""
    spawn = {'x': 0.0, 'y': 0.0, 'yaw': 0.0}
    meta = os.path.splitext(world_path)[0] + '.meta.json'
    if os.path.exists(meta):
        with open(meta, 'r', encoding='utf-8') as f:
            spawn.update(json.load(f).get('spawn', {}))
    if x != '':
        spawn['x'] = float(x)
    if y != '':
        spawn['y'] = float(y)
    if yaw != '':
        spawn['yaw'] = float(yaw)
    return spawn


def launch_setup(context, *args, **kwargs):
    desc_pkg = get_package_share_directory('robot_splunker_description')
    gz_pkg = get_package_share_directory('robot_splunker_gazebo')

    world_path = resolve_world(LaunchConfiguration('world').perform(context))
    spawn = resolve_spawn(world_path,
                          LaunchConfiguration('x').perform(context),
                          LaunchConfiguration('y').perform(context),
                          LaunchConfiguration('yaw').perform(context))
    gui = LaunchConfiguration('gui').perform(context).lower() == 'true'
    use_sim_time = LaunchConfiguration('use_sim_time').perform(context).lower() == 'true'

    # ---- 1. Resource path: lets Gazebo find meshes referenced as package://robot_splunker_description/...
    resource_path = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH', os.path.dirname(desc_pkg))

    # ---- 2. Gazebo. -r = start running (not paused); -v 3 = warnings+info; -s = server only (no GUI)
    gz_args = f'-r -v 3 {world_path}' + ('' if gui else ' -s')
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': gz_args, 'on_exit_shutdown': 'true'}.items(),
    )

    # ---- 3. robot_state_publisher: URDF -> /robot_description + static/joint TFs
    robot_description = xacro.process_file(
        os.path.join(desc_pkg, 'urdf', 'robot_splunker.urdf.xacro')).toxml()
    rsp = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{'robot_description': robot_description, 'use_sim_time': use_sim_time}],
        output='screen',
    )

    # ---- 4. Spawn the robot from the /robot_description topic (z slightly above ground)
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=['-topic', 'robot_description',
                   '-name', 'robot_splunker',
                   '-x', str(spawn['x']), '-y', str(spawn['y']), '-z', '0.02',
                   '-Y', str(spawn['yaw'])],
        output='screen',
    )

    # ---- 5. The ROS <-> Gazebo bridge, configured entirely by parameters.yaml
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        parameters=[{'config_file': os.path.join(gz_pkg, 'config', 'parameters.yaml'),
                     'use_sim_time': use_sim_time}],
        output='screen',
    )

    return [resource_path, gazebo, rsp, spawn_robot, bridge]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('world', default_value='splunker_cave',
                              description='World name in robot_splunker_gazebo/worlds or a .sdf path'),
        DeclareLaunchArgument('x', default_value='', description='Spawn x [m] (empty = from world meta)'),
        DeclareLaunchArgument('y', default_value='', description='Spawn y [m] (empty = from world meta)'),
        DeclareLaunchArgument('yaw', default_value='', description='Spawn yaw [rad] (empty = from world meta)'),
        DeclareLaunchArgument('gui', default_value='true', description='Show the Gazebo GUI'),
        DeclareLaunchArgument('use_sim_time', default_value='true', description='Use /clock from Gazebo'),
        OpaqueFunction(function=launch_setup),
    ])
