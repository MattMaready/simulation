cmake_minimum_required(VERSION 3.8)
project(robot_splunker_bringup)

find_package(ament_cmake REQUIRED)

# launch/ : explore (main), mapping, navigation
# config/ : slam_toolbox, nav2 and explorer parameters
# rviz/   : mapping.rviz
install(
  DIRECTORY launch config rviz
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
