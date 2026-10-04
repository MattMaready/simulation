"""navigation.launch.py: the Nav2 navigation servers for exploring with SLAM.

Starts the Nav2 servers needed for NavigateToPose plus a lifecycle manager that
configures and activates them. AMCL and map_server are NOT started: SLAM Toolbox
supplies /map and map -> odom.

We start the nodes directly (instead of including nav2_bringup/navigation_launch.py)
so the node list and cmd_vel wiring are explicit and do not change between Nav2
releases:

    controller_server  --cmd_vel_nav-->  velocity_smoother  --cmd_vel-->  Gazebo (bridge)
    behavior_server    --cmd_vel_nav--^

Arguments: use_sim_time (default true), params_file, autostart (default true)
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# Lifecycle-managed Nav2 nodes, in start-up order.
LIFECYCLE_NODES = [
    'controller_server',
    'smoother_server',
    'planner_server',
    'behavior_server',
    'velocity_smoother',
    'bt_navigator',
    'waypoint_follower',
]


def launch_setup(context, *args, **kwargs):
    params_file = LaunchConfiguration('params_file').perform(context)
    use_sim_time = LaunchConfiguration('use_sim_time').perform(context).lower() == 'true'
    autostart = LaunchConfiguration('autostart').perform(context).lower() == 'true'
    params = [params_file, {'use_sim_time': use_sim_time}]

    def nav_node(package, executable, remappings=None):
        return Node(package=package, executable=executable, name=executable,
                    parameters=params, remappings=remappings or [], output='screen')

    return [
        # The controller follows the path; its raw command goes to the smoother.
        nav_node('nav2_controller', 'controller_server', [('cmd_vel', 'cmd_vel_nav')]),
        nav_node('nav2_smoother', 'smoother_server'),
        nav_node('nav2_planner', 'planner_server'),
        # Recovery behaviours (spin, back up, ...) also publish on cmd_vel_nav.
        nav_node('nav2_behaviors', 'behavior_server', [('cmd_vel', 'cmd_vel_nav')]),
        # Smoother: reads cmd_vel_nav, limits accel, publishes the final /cmd_vel.
        nav_node('nav2_velocity_smoother', 'velocity_smoother',
                 [('cmd_vel', 'cmd_vel_nav'), ('cmd_vel_smoothed', 'cmd_vel')]),
        nav_node('nav2_bt_navigator', 'bt_navigator'),
        nav_node('nav2_waypoint_follower', 'waypoint_follower'),
        Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='lifecycle_manager_navigation',
            output='screen',
            parameters=[{'use_sim_time': use_sim_time,
                         'autostart': autostart,
                         'node_names': LIFECYCLE_NODES,
                         'bond_timeout': 4.0}],
        ),
    ]


def generate_launch_description():
    bringup = get_package_share_directory('robot_splunker_bringup')
    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('autostart', default_value='true',
                              description='Configure + activate the Nav2 nodes automatically'),
        DeclareLaunchArgument('params_file',
                              default_value=os.path.join(bringup, 'config', 'nav2_params.yaml'),
                              description='Nav2 parameters'),
        OpaqueFunction(function=launch_setup),
    ])
