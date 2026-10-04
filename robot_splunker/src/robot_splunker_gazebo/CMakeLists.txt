cmake_minimum_required(VERSION 3.8)
project(robot_splunker_gazebo)

find_package(ament_cmake REQUIRED)

# worlds/  : generated .sdf + .meta.json (from ../../worlds/*.world.yaml)
# config/  : parameters.yaml (ROS <-> Gazebo bridge)
# launch/  : sim.launch.py
install(
  DIRECTORY worlds config launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
