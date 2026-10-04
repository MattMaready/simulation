"""mapping.launch.py: manual mapping. Gazebo + bridge + SLAM Toolbox + RViz, no Nav2/explorer.

Drive the robot yourself while SLAM builds the map:
    ros2 launch robot_splunker_bringup mapping.launch.py
    ros2 run teleop_twist_keyboard teleop_twist_keyboard       # in another terminal
Save the map:
    ros2 run nav2_map_server map_saver_cli -f ~/robot_splunker_maps/my_map

This is a thin wrapper around explore.launch.py with nav:=false explore:=false;
all other arguments (world, rviz, gui, ue, ue_port, x, y, yaw) are forwarded.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

FORWARDED = {
    'world': 'splunker_cave', 'x': '', 'y': '', 'yaw': '', 'use_sim_time': 'true',
    'gui': 'true', 'rviz': 'true', 'ue': 'false', 'ue_port': '9090',
    'map_save_path': os.path.join(os.path.expanduser('~'), 'robot_splunker_maps', 'splunker_cave'),
}


def generate_launch_description():
    explore = os.path.join(get_package_share_directory('robot_splunker_bringup'),
                           'launch', 'explore.launch.py')
    args = [DeclareLaunchArgument(k, default_value=v) for k, v in FORWARDED.items()]
    launch_args = {k: LaunchConfiguration(k) for k in FORWARDED}
    launch_args.update({'slam': 'true', 'nav': 'false', 'explore': 'false'})
    return LaunchDescription(args + [
        IncludeLaunchDescription(PythonLaunchDescriptionSource(explore),
                                 launch_arguments=launch_args.items()),
    ])
