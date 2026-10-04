from glob import glob

from setuptools import setup

package_name = 'robot_splunker_ue_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='robot_splunker maintainers',
    maintainer_email='matt.maready@gmail.com',
    description='Streams robot_splunker pose, wheels, lidar and map to Unreal Engine 5 over WebSocket.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'ue_bridge_node = robot_splunker_ue_bridge.ue_bridge_node:main',
        ],
    },
)
