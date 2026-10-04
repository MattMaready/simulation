cmake_minimum_required(VERSION 3.8)
project(robot_splunker_description)

find_package(ament_cmake REQUIRED)

# Install the robot model, RViz config and launch files into share/robot_splunker_description
install(
  DIRECTORY urdf rviz launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  # Expands the xacro and checks links, joints and inertia values.
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_xacro test/test_xacro.py
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  )
endif()

ament_package()
