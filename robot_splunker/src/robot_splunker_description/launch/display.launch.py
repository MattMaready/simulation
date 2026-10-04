"""display.launch.py: view the robot_splunker model in RViz without Gazebo.

Starts:
  * robot_state_publisher      - publishes /robot_description and the link TFs
  * joint_state_publisher_gui  - sliders to rotate the wheel joints
  * rviz2                      - with rviz/display.rviz

Use it to check geometry, colours and frames after editing the xacro:
    ros2 launch robot_splunker_description display.launch.py
"""

import os

import xacro
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory('robot_splunker_description')
    xacro_file = os.path.join(pkg, 'urdf', 'robot_splunker.urdf.xacro')
    rviz_config = os.path.join(pkg, 'rviz', 'display.rviz')

    # Expand the xacro once at launch time into a URDF string.
    robot_description = xacro.process_file(xacro_file).toxml()

    rviz_arg = DeclareLaunchArgument('rviz', default_value='true', description='Start RViz')

    return LaunchDescription([
        rviz_arg,
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{'robot_description': robot_description}],
            output='screen',
        ),
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            output='screen',
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', rviz_config],
            condition=IfCondition(LaunchConfiguration('rviz')),
            output='screen',
        ),
    ])
