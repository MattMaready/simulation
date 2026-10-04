"""ue_bridge_node: streams robot_splunker state to the Unreal Engine 5 twin over WebSocket.

ROS 2 (WSL2)                                   Unreal Engine (Windows)
  /ground_truth/odom  --pose @30 Hz-->  \
  /joint_states       --wheels @30 Hz->  \
  /scan + lidar TF    --scan @10 Hz--->   >  ws://0.0.0.0:<port>  -->  SplunkerBridgeSubsystem
  /map                --map  @<=1 Hz->   /
  TF map->base_footprint --slam_pose-> /
  /explore/status     --status------->/

All conversions to Unreal coordinates happen here (coords.py / protocol.py).
The WebSocket server runs on its own asyncio thread; ROS callbacks hand
messages to it with call_soon_threadsafe. Unreal only listens (view-only).
"""

import asyncio
import threading
import time

import numpy as np
import rclpy
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import JointState, LaserScan
from std_msgs.msg import String
from tf2_ros import Buffer, TransformException, TransformListener

import websockets

from robot_splunker_ue_bridge import coords, protocol


class WsBroadcaster:
    """Minimal WebSocket broadcast server running in a background asyncio thread."""

    def __init__(self, host, port, logger, on_connect=None):
        self._host, self._port, self._log = host, port, logger
        self._on_connect = on_connect or (lambda: [])
        self._clients = set()
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._error = None
        self._server = None
        self._thread = threading.Thread(target=self._run, name='ue_ws', daemon=True)

    # -- lifecycle -----------------------------------------------------------
    def start(self, timeout=5.0):
        self._thread.start()
        self._ready.wait(timeout)
        if self._error is not None:
            raise RuntimeError(f'cannot listen on {self._host}:{self._port}: {self._error}')

    def stop(self):
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._server = self._loop.run_until_complete(
                websockets.serve(self._handler, self._host, self._port,
                                 max_size=2 ** 20, ping_interval=20, ping_timeout=20))
        except OSError as exc:      # port in use, permission denied, ...
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        self._loop.run_forever()

    # -- connections ---------------------------------------------------------
    async def _handler(self, ws, *_):        # (ws) on websockets>=10.1, (ws, path) before
        peer = getattr(ws, 'remote_address', None)
        self._clients.add(ws)
        self._log.info(f'Unreal client connected: {peer} ({len(self._clients)} total)')
        try:
            for text in self._on_connect():  # latest map/status so a late client catches up
                await ws.send(text)
            async for _ in ws:               # UE is view-only; ignore anything it sends
                pass
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            self._log.info(f'Unreal client disconnected: {peer}')

    # -- sending (called from ROS threads) ------------------------------------
    @property
    def has_clients(self):
        return bool(self._clients)

    def broadcast(self, text):
        if self._clients:
            # websockets.broadcast() never blocks: slow clients just drop frames.
            self._loop.call_soon_threadsafe(websockets.broadcast, set(self._clients), text)


class UeBridge(Node):

    def __init__(self):
        super().__init__('ue_bridge')
        p = self.declare_parameter
        self.host = p('host', '0.0.0.0').value
        self.port = int(p('port', 9090).value)
        self.world_name = p('world_name', 'splunker_cave').value
        self.pose_rate = float(p('pose_rate_hz', 30.0).value)
        self.wheel_rate = float(p('wheel_rate_hz', 30.0).value)
        self.map_period = 1.0 / max(0.05, float(p('map_rate_hz', 1.0).value))
        self.slam_rate = float(p('slam_pose_rate_hz', 10.0).value)
        self.scan_decimation = int(p('scan_decimation', 2).value)
        self.robot_frame = p('robot_frame', 'base_footprint').value
        self.lidar_frame = p('lidar_frame', 'lidar_link').value
        self.map_frame = p('map_frame', 'map').value
        self.left_joint = p('left_wheel_joint', 'left_wheel_joint').value
        self.right_joint = p('right_wheel_joint', 'right_wheel_joint').value
        # Fallback lidar offset in base_footprint (m) if TF is not available yet.
        self.lidar_offset = tuple(float(v) for v in p('lidar_offset', [0.12, 0.0, 0.155]).value)
        # Pose of SLAM's map frame in the Gazebo world = robot spawn pose (x, y, yaw).
        self.map_to_world = tuple(float(v) for v in p('map_to_world', [0.0, 0.0, 0.0]).value)

        # Latest state
        self.gt_pos = None          # ground truth position (ROS world, m)
        self.gt_q = None
        self.last_pose_sent = 0.0
        self.last_wheels_sent = 0.0
        self.last_map_sent = 0.0
        self.latest_map_text = None
        self.latest_status_text = None
        self.lidar_tf = None        # (pos, quat) of lidar in base_footprint

        self.ws = WsBroadcaster(self.host, self.port, self.get_logger(), self._on_connect)
        self.ws.start()
        self.get_logger().info(
            f'ue_bridge listening on ws://{self.host}:{self.port} '
            f'(map_to_world={self.map_to_world})')

        self.tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self.tf_listener = TransformListener(self.tf_buffer, self)

        map_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.VOLATILE, history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(Odometry, '/ground_truth/odom', self.on_ground_truth, 10)
        self.create_subscription(JointState, '/joint_states', self.on_joints, 10)
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
        self.create_subscription(OccupancyGrid, '/map', self.on_map, map_qos)
        self.create_subscription(String, '/explore/status', self.on_status, 10)
        self.create_timer(1.0 / max(1.0, self.slam_rate), self.send_slam_pose)

    # ------------------------------------------------------------------ helpers
    def _stamp(self, header=None):
        if header is not None:
            return header.stamp.sec + header.stamp.nanosec * 1e-9
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_connect(self):
        msgs = [protocol.hello(self.world_name)]
        if self.latest_map_text:
            msgs.append(self.latest_map_text)
        if self.latest_status_text:
            msgs.append(self.latest_status_text)
        return msgs

    # ------------------------------------------------------------------ callbacks
    def on_ground_truth(self, msg: Odometry):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        self.gt_pos = (p.x, p.y, p.z)
        self.gt_q = (q.x, q.y, q.z, q.w)
        now = time.monotonic()
        if self.ws.has_clients and now - self.last_pose_sent >= 1.0 / self.pose_rate:
            self.last_pose_sent = now
            self.ws.broadcast(protocol.pose(self._stamp(msg.header), self.gt_pos, self.gt_q))

    def on_joints(self, msg: JointState):
        now = time.monotonic()
        if not self.ws.has_clients or now - self.last_wheels_sent < 1.0 / self.wheel_rate:
            return
        pos = dict(zip(msg.name, msg.position))
        if self.left_joint in pos and self.right_joint in pos:
            self.last_wheels_sent = now
            self.ws.broadcast(protocol.wheels(self._stamp(msg.header),
                                              pos[self.left_joint], pos[self.right_joint]))

    def _lidar_in_base(self):
        """Lidar pose in base_footprint from TF (static, so cache it once found)."""
        if self.lidar_tf is None:
            try:
                t = self.tf_buffer.lookup_transform(self.robot_frame, self.lidar_frame, Time())
                tr, r = t.transform.translation, t.transform.rotation
                self.lidar_tf = ((tr.x, tr.y, tr.z), (r.x, r.y, r.z, r.w))
            except TransformException:
                return self.lidar_offset, (0.0, 0.0, 0.0, 1.0)
        return self.lidar_tf

    def on_scan(self, msg: LaserScan):
        if not self.ws.has_clients or self.gt_pos is None:
            return
        # Lidar pose in the world = ground-truth robot pose * lidar offset.
        l_pos, l_q = self._lidar_in_base()
        s_pos, s_q = coords.compose(self.gt_pos, self.gt_q, l_pos, l_q)
        hits = coords.scan_to_world_points(msg.ranges, msg.angle_min, msg.angle_increment,
                                           msg.range_min, msg.range_max, s_pos, s_q,
                                           decimation=self.scan_decimation)
        self.ws.broadcast(protocol.scan(self._stamp(msg.header), s_pos, hits))

    def on_map(self, msg: OccupancyGrid):
        now = time.monotonic()
        if now - self.last_map_sent < self.map_period:
            return
        self.last_map_sent = now
        info = msg.info
        o, oq = info.origin.position, info.origin.orientation
        # Map origin (map frame) -> Gazebo world frame using the spawn pose.
        w_pos, w_q = coords.map_pose_to_world(self.map_to_world, (o.x, o.y, o.z),
                                              (oq.x, oq.y, oq.z, oq.w))
        w_yaw = coords.quat_to_rpy(w_q)[2]
        data = np.asarray(msg.data, dtype=np.int8).tobytes()   # fast path: raw int8 bytes
        text = protocol.occupancy_map(self._stamp(msg.header), info.width, info.height,
                                      info.resolution, w_pos[:2], w_yaw, data)
        self.latest_map_text = text
        self.ws.broadcast(text)

    def on_status(self, msg: String):
        self.latest_status_text = protocol.status(msg.data)
        self.ws.broadcast(self.latest_status_text)

    def send_slam_pose(self):
        """SLAM's estimate of the robot (map -> base_footprint), shown as a 'ghost' in UE."""
        if not self.ws.has_clients:
            return
        try:
            t = self.tf_buffer.lookup_transform(self.map_frame, self.robot_frame, Time())
        except TransformException:
            return
        tr, r = t.transform.translation, t.transform.rotation
        pos, q = coords.map_pose_to_world(self.map_to_world, (tr.x, tr.y, tr.z),
                                          (r.x, r.y, r.z, r.w))
        self.ws.broadcast(protocol.pose(self._stamp(t.header), pos, q, kind='slam_pose'))


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = UeBridge()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.ws.stop()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
