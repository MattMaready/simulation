from setuptools import setup

package_name = 'robot_splunker_exploration'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='robot_splunker maintainers',
    maintainer_email='matt.maready@gmail.com',
    description='Frontier-based autonomous exploration (SLAM Toolbox + Nav2) for robot_splunker.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'frontier_explorer = robot_splunker_exploration.frontier_explorer:main',
        ],
    },
)
