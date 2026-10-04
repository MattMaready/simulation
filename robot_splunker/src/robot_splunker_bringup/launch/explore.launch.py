"""explore.launch.py: MAIN ENTRY POINT. Autonomous mapping of an unknown world.

Starts (each part can be switched off with a launch argument):
  1. sim.launch.py          Gazebo + robot + ROS<->Gazebo bridge          (always)
  2. SLAM Toolbox           /scan + odom -> /map and map -> odom          (slam:=true)
  3. Nav2 (navigation.launch.py), 5 s later, once SLAM publishes TF   (nav:=true)
  4. frontier_explorer, 10 s later, drives to frontiers via Nav2      (explore:=true)
  5. ue_bridge              WebSocket feed for the Unreal twin            (ue:=false)
  6. RViz                   mapping.rviz                                  (rviz:=true)

Examples:
  ros2 launch robot_splunker_bringup explore.launch.py
  ros2 launch robot_splunker_bringup explore.launch.py ue:=true
  ros2 launch robot_splunker_bringup explore.launch.py slam:=false nav:=false explore:=false   # sim only
"""

import json
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription, LogInfo,
                            OpaqueFunction, TimerAction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _flag(context, name):
    return LaunchConfiguration(name).perform(context).lower() == 'true'


def resolve_spawn(world, x, y, yaw):
    """Same rule as sim.launch.py: explicit args > worlds/<world>.meta.json > 0,0,0.

    The spawn pose matters here because SLAM's map frame starts at the robot's
    spawn pose; ue_bridge needs it to place the map in the Gazebo/Unreal world.
    """
    spawn = {'x': 0.0, 'y': 0.0, 'yaw': 0.0}
    if os.path.isabs(world):
        meta = os.path.splitext(world)[0] + '.meta.json'
    else:
        name = world[:-4] if world.endswith('.sdf') else world
        meta = os.path.join(get_package_share_directory('robot_splunker_gazebo'),
                            'worlds', name + '.meta.json')
    if os.path.exists(meta):
        with open(meta, 'r', encoding='utf-8') as f:
            spawn.update(json.load(f).get('spawn', {}))
    for key, val in (('x', x), ('y', y), ('yaw', yaw)):
        if val != '':
            spawn[key] = float(val)
    return spawn


def launch_setup(context, *args, **kwargs):
    bringup = get_package_share_directory('robot_splunker_bringup')
    gazebo_pkg = get_package_share_directory('robot_splunker_gazebo')

    world = LaunchConfiguration('world').perform(context)
    spawn = resolve_spawn(world,
                          LaunchConfiguration('x').perform(context),
                          LaunchConfiguration('y').perform(context),
                          LaunchConfiguration('yaw').perform(context))
    use_sim_time = _flag(context, 'use_sim_time')
    sim_time_str = 'true' if use_sim_time else 'false'
    actions = [LogInfo(msg=f"robot_splunker: world={world} spawn=({spawn['x']}, "
                           f"{spawn['y']}, yaw {spawn['yaw']})")]

    # ---- 1. Simulation: Gazebo + spawn + robot_state_publisher + bridge
    actions.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(gazebo_pkg, 'launch', 'sim.launch.py')),
        launch_arguments={
            'world': world,
            'x': str(spawn['x']), 'y': str(spawn['y']), 'yaw': str(spawn['yaw']),
            'gui': LaunchConfiguration('gui').perform(context),
            'use_sim_time': sim_time_str,
        }.items(),
    ))

    # ---- 2. SLAM Toolbox (online async): builds /map, publishes map -> odom
    if _flag(context, 'slam'):
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                get_package_share_directory('slam_toolbox'), 'launch', 'online_async_launch.py')),
            launch_arguments={
                'slam_params_file': os.path.join(bringup, 'config', 'slam_toolbox_params.yaml'),
                'use_sim_time': sim_time_str,
            }.items(),
        ))

    # ---- 3. Nav2, delayed so /map and the map -> odom transform exist first
    if _flag(context, 'nav'):
        actions.append(TimerAction(period=5.0, actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(bringup, 'launch', 'navigation.launch.py')),
            launch_arguments={
                'use_sim_time': sim_time_str,
                'params_file': os.path.join(bringup, 'config', 'nav2_params.yaml'),
            }.items(),
        )]))

    # ---- 4. Frontier explorer, delayed until Nav2 is (nearly) active
    if _flag(context, 'explore'):
        if not _flag(context, 'nav'):
            actions.append(LogInfo(msg='WARNING: explore:=true needs nav:=true; explorer not started.'))
        else:
            actions.append(TimerAction(period=10.0, actions=[Node(
                package='robot_splunker_exploration',
                executable='frontier_explorer',
                name='frontier_explorer',
                output='screen',
                parameters=[
                    os.path.join(bringup, 'config', 'explorer_params.yaml'),
                    {'use_sim_time': use_sim_time,
                     'map_save_path': LaunchConfiguration('map_save_path').perform(context)},
                ],
            )]))

    # ---- 5. Unreal Engine bridge (WebSocket server for the UE5 digital twin)
    if _flag(context, 'ue'):
        actions.append(Node(
            package='robot_splunker_ue_bridge',
            executable='ue_bridge_node',
            name='ue_bridge',
            output='screen',
            parameters=[
                os.path.join(get_package_share_directory('robot_splunker_ue_bridge'),
                             'config', 'ue_bridge_params.yaml'),
                {'use_sim_time': use_sim_time,
                 'port': int(LaunchConfiguration('ue_port').perform(context)),
                 # map frame == robot spawn pose in the world (SLAM starts there)
                 'map_to_world': [float(spawn['x']), float(spawn['y']), float(spawn['yaw'])]},
            ],
        ))

    # ---- 6. RViz
    if _flag(context, 'rviz'):
        actions.append(Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', os.path.join(bringup, 'rviz', 'mapping.rviz')],
            parameters=[{'use_sim_time': use_sim_time}],
            output='screen',
        ))

    return actions


def generate_launch_description():
    default_map_path = os.path.join(os.path.expanduser('~'), 'robot_splunker_maps', 'splunker_cave')
    return LaunchDescription([
        DeclareLaunchArgument('world', default_value='splunker_cave',
                              description='World in robot_splunker_gazebo/worlds (or .sdf path)'),
        DeclareLaunchArgument('x', default_value='', description='Spawn x (empty = world meta)'),
        DeclareLaunchArgument('y', default_value='', description='Spawn y (empty = world meta)'),
        DeclareLaunchArgument('yaw', default_value='', description='Spawn yaw (empty = world meta)'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('gui', default_value='true', description='Gazebo GUI'),
        DeclareLaunchArgument('rviz', default_value='true', description='Start RViz'),
        DeclareLaunchArgument('slam', default_value='true', description='Start SLAM Toolbox'),
        DeclareLaunchArgument('nav', default_value='true', description='Start Nav2'),
        DeclareLaunchArgument('explore', default_value='true', description='Start frontier_explorer'),
        DeclareLaunchArgument('ue', default_value='false', description='Start the Unreal bridge'),
        DeclareLaunchArgument('ue_port', default_value='9090', description='Unreal bridge port'),
        DeclareLaunchArgument('map_save_path', default_value=default_map_path,
                              description='Where the explorer saves the final map (no extension)'),
        OpaqueFunction(function=launch_setup),
    ])
