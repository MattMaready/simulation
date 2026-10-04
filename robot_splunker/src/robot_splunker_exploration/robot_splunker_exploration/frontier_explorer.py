"""frontier_explorer: autonomous frontier-based exploration for robot_splunker.

Loop (runs every replan_period_s):
    WAIT_FOR_MAP -> EXPLORING: pick best frontier (frontier_utils.select_goal)
                 -> NAVIGATING: Nav2 NavigateToPose; cancel + blacklist on failure,
                    timeout or no progress; cancel early when the frontier is explored
                 -> back to EXPLORING ... until no frontiers are left
                 -> RETURNING_HOME (optional) -> COMPLETE: save map via SLAM Toolbox

Subscribes : /map (nav_msgs/OccupancyGrid), TF map -> base_footprint
Action     : navigate_to_pose (nav2_msgs/action/NavigateToPose)
Publishes  : /explore/frontiers (visualization_msgs/MarkerArray) for RViz
             /explore/status    (std_msgs/String) for the Unreal HUD / monitoring
Services   : /slam_toolbox/save_map, /slam_toolbox/serialize_map (when finished)
Parameters : see robot_splunker_bringup/config/explorer_params.yaml
"""

import math
import os
import time

import numpy as np
import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Point, PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from rclpy.time import Time
from std_msgs.msg import ColorRGBA, String
from tf2_ros import Buffer, TransformException, TransformListener
from visualization_msgs.msg import Marker, MarkerArray

from robot_splunker_exploration import frontier_utils as fu

try:  # slam_toolbox service types (only needed for saving the map at the end)
    from slam_toolbox.srv import SaveMap, SerializePoseGraph
except ImportError:  # pragma: no cover
    SaveMap = SerializePoseGraph = None

# States
WAIT_FOR_MAP = 'WAIT_FOR_MAP'
EXPLORING = 'EXPLORING'
NAVIGATING = 'NAVIGATING'
RETURNING_HOME = 'RETURNING_HOME'
COMPLETE = 'COMPLETE'


def yaw_to_quaternion(yaw):
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


class FrontierExplorer(Node):

    def __init__(self):
        super().__init__('frontier_explorer')

        # ---- parameters (defaults mirror explorer_params.yaml) ----
        p = self.declare_parameter
        self.map_topic = p('map_topic', '/map').value
        self.global_frame = p('global_frame', 'map').value
        self.robot_frame = p('robot_frame', 'base_footprint').value
        self.action_name = p('action_name', 'navigate_to_pose').value
        self.min_frontier_size = int(p('min_frontier_size', 8).value)
        self.occupied_threshold = int(p('occupied_threshold', 50).value)
        self.clearance_radius = float(p('clearance_radius', 0.30).value)
        self.goal_search_radius = float(p('goal_search_radius', 0.8).value)
        self.min_goal_distance = float(p('min_goal_distance', 0.5).value)
        self.size_weight = float(p('size_weight', 1.0).value)
        self.dist_weight = float(p('dist_weight', 1.0).value)
        self.goal_timeout_s = float(p('goal_timeout_s', 90.0).value)
        self.progress_timeout_s = float(p('progress_timeout_s', 20.0).value)
        self.progress_distance = float(p('progress_distance', 0.15).value)
        self.blacklist_radius = float(p('blacklist_radius', 0.6).value)
        self.frontier_cleared_radius = int(p('frontier_cleared_radius', 2).value)
        self.replan_period_s = float(p('replan_period_s', 1.0).value)
        self.empty_checks_to_finish = int(p('empty_checks_to_finish', 3).value)
        self.return_home = bool(p('return_home', True).value)
        self.save_map = bool(p('save_map', True).value)
        self.map_save_path = os.path.expanduser(
            str(p('map_save_path', '~/robot_splunker_maps/splunker_cave').value))

        # ---- state ----
        self.state = WAIT_FOR_MAP
        self.grid = None            # np.ndarray (h, w) int8
        self.info = None            # fu.MapInfo
        self.home = None            # (x, y, yaw) in map frame, recorded at start
        self.blacklist = []         # [(x, y)] failed / finished goals
        self.empty_checks = 0
        self.goal_handle = None
        self.goal = None            # fu.Candidate currently being pursued
        self.goal_target = (0.0, 0.0)   # (x, y) of the goal sent to Nav2
        self.goal_frontier_xy = None    # world (x, y) of the frontier the goal explores
        self.goal_sent_time = 0.0
        self.progress_ref = None    # (x, y, wall time) for the progress check
        self.goal_pending = False   # waiting for the action server to accept
        self.map_saved = False

        # ---- ROS interfaces ----
        # Volatile + reliable works whether SLAM publishes /map transient-local or not;
        # SLAM Toolbox republishes the map every map_update_interval seconds anyway.
        map_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.VOLATILE,
                             history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(OccupancyGrid, self.map_topic, self.on_map, map_qos)
        self.marker_pub = self.create_publisher(MarkerArray, '/explore/frontiers', 1)
        self.status_pub = self.create_publisher(String, '/explore/status', 10)
        self.tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.nav_client = ActionClient(self, NavigateToPose, self.action_name)
        self.timer = self.create_timer(self.replan_period_s, self.step)
        self.status_timer = self.create_timer(2.0, self.publish_status)

        self.get_logger().info(
            f'frontier_explorer ready (min_frontier_size={self.min_frontier_size}, '
            f'map_save_path={self.map_save_path})')

    # ------------------------------------------------------------------ inputs
    def on_map(self, msg: OccupancyGrid):
        info = msg.info
        q = info.origin.orientation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self.info = fu.MapInfo(resolution=info.resolution, width=info.width, height=info.height,
                               origin_x=info.origin.position.x, origin_y=info.origin.position.y,
                               origin_yaw=yaw)
        self.grid = np.asarray(msg.data, dtype=np.int8).reshape(info.height, info.width)

    def robot_pose(self):
        """(x, y, yaw) of the robot in the map frame, or None if TF is not available yet."""
        try:
            t = self.tf_buffer.lookup_transform(self.global_frame, self.robot_frame, Time(),
                                                timeout=Duration(seconds=0.2))
        except TransformException:
            return None
        tr, q = t.transform.translation, t.transform.rotation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        return (tr.x, tr.y, yaw)

    # ------------------------------------------------------------------ state machine
    def set_state(self, state):
        if state != self.state:
            self.get_logger().info(f'state: {self.state} -> {state}')
            self.state = state
            self.publish_status()

    def publish_status(self):
        self.status_pub.publish(String(data=self.state))

    def step(self):
        """Periodic state machine tick."""
        if self.state == COMPLETE:
            return
        pose = self.robot_pose()
        if self.state == WAIT_FOR_MAP:
            if self.grid is None or pose is None:
                return
            if not self.nav_client.server_is_ready():
                self.get_logger().info('waiting for Nav2 navigate_to_pose action server...',
                                       throttle_duration_sec=5.0)
                return
            self.home = pose
            self.get_logger().info(f'home pose recorded at ({pose[0]:.2f}, {pose[1]:.2f})')
            self.set_state(EXPLORING)
            return
        if pose is None or self.grid is None:
            return

        if self.state == EXPLORING:
            self.choose_and_send(pose)
        elif self.state in (NAVIGATING, RETURNING_HOME):
            self.monitor_goal(pose)

    def choose_and_send(self, pose):
        if self.goal_pending:
            return
        best, frontiers = fu.select_goal(
            self.grid, self.info, (pose[0], pose[1]),
            min_frontier_size=self.min_frontier_size,
            occupied_threshold=self.occupied_threshold,
            clearance_m=self.clearance_radius,
            search_radius_m=self.goal_search_radius,
            min_goal_distance=self.min_goal_distance,
            size_weight=self.size_weight, dist_weight=self.dist_weight,
            blacklist=self.blacklist, blacklist_radius=self.blacklist_radius)
        self.publish_markers(frontiers, best)

        if best is None:
            self.empty_checks += 1
            self.get_logger().info(
                f'no reachable frontier ({self.empty_checks}/{self.empty_checks_to_finish})')
            if self.empty_checks >= self.empty_checks_to_finish:
                self.finish_exploration(pose)
            return

        self.empty_checks = 0
        self.goal = best
        # Remember the frontier in WORLD coordinates: SLAM grows the grid (and moves its
        # origin) as it maps, so a stored (row, col) would point somewhere else later.
        self.goal_frontier_xy = fu.grid_to_world(best.frontier_cell, self.info)
        yaw = math.atan2(best.y - pose[1], best.x - pose[0])   # face the frontier
        self.get_logger().info(
            f'goal -> ({best.x:.2f}, {best.y:.2f}) frontier={best.frontier_size} cells '
            f'score={best.score:.2f}')
        self.send_goal(best.x, best.y, yaw, NAVIGATING)

    def finish_exploration(self, pose):
        self.get_logger().info('exploration finished: no frontiers left')
        if self.return_home and self.home is not None and \
                math.hypot(pose[0] - self.home[0], pose[1] - self.home[1]) > 0.5:
            self.goal = None
            self.send_goal(self.home[0], self.home[1], self.home[2], RETURNING_HOME)
        else:
            self.complete()

    def complete(self):
        self.set_state(COMPLETE)
        if self.save_map and not self.map_saved:
            self.save_map_files()
        self.get_logger().info('EXPLORATION COMPLETE')

    # ------------------------------------------------------------------ Nav2 goals
    def send_goal(self, x, y, yaw, new_state):
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = self.global_frame
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(x)
        goal.pose.pose.position.y = float(y)
        qx, qy, qz, qw = yaw_to_quaternion(yaw)
        goal.pose.pose.orientation.z = qz
        goal.pose.pose.orientation.w = qw

        self.goal_pending = True
        self.goal_target = (x, y)
        self.set_state(new_state)
        future = self.nav_client.send_goal_async(goal)
        future.add_done_callback(self.on_goal_response)
        self.goal_sent_time = time.monotonic()
        pose = self.robot_pose()
        self.progress_ref = (pose[0], pose[1], time.monotonic()) if pose else None

    def on_goal_response(self, future):
        self.goal_pending = False
        handle = future.result()
        if handle is None or not handle.accepted:
            self.get_logger().warn('goal rejected by Nav2')
            self.fail_current_goal()
            return
        self.goal_handle = handle
        # Bind THIS handle to its result callback so a late result from an older,
        # cancelled goal can never be mistaken for the current goal's result.
        handle.get_result_async().add_done_callback(
            lambda f, h=handle: self.on_goal_result(f, h))

    def on_goal_result(self, future, handle):
        if handle is not self.goal_handle:
            return  # result of a goal we already cancelled and moved on from
        self.goal_handle = None
        result = future.result()
        status = result.status if result is not None else GoalStatus.STATUS_UNKNOWN
        if self.state == RETURNING_HOME:
            self.complete()
            return
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info('reached frontier goal')
            # Don't pick the exact same spot again if it stays a (tiny) frontier.
            self.blacklist.append(self.goal_target)
            self.set_state(EXPLORING)
        elif status == GoalStatus.STATUS_CANCELED:
            self.set_state(EXPLORING)
        else:
            self.get_logger().warn(f'goal failed (status {status}); blacklisting it')
            self.fail_current_goal()

    def fail_current_goal(self):
        if self.state == RETURNING_HOME:
            self.get_logger().warn('could not return home; finishing here')
            self.complete()
            return
        self.blacklist.append(self.goal_target)
        self.set_state(EXPLORING)

    def cancel_goal(self, reason, blacklist):
        self.get_logger().info(f'cancelling goal: {reason}')
        handle, self.goal_handle = self.goal_handle, None
        if handle is not None:
            handle.cancel_goal_async()
        if blacklist:
            self.blacklist.append(self.goal_target)
        if self.state == RETURNING_HOME:
            self.complete()
        else:
            self.set_state(EXPLORING)

    def monitor_goal(self, pose):
        if self.goal_handle is None:
            return  # still waiting for acceptance
        now = time.monotonic()
        # 1. Overall timeout
        if now - self.goal_sent_time > self.goal_timeout_s:
            self.cancel_goal('timeout', blacklist=True)
            return
        # 2. Progress check: must move progress_distance every progress_timeout_s
        if self.progress_ref is not None:
            px, py, pt = self.progress_ref
            if math.hypot(pose[0] - px, pose[1] - py) >= self.progress_distance:
                self.progress_ref = (pose[0], pose[1], now)
            elif now - pt > self.progress_timeout_s:
                self.cancel_goal('no progress', blacklist=True)
                return
        # 3. Frontier already explored on the way? Move on to the next one early.
        if self.state == NAVIGATING and self.goal_frontier_xy is not None:
            cell = fu.world_to_grid(*self.goal_frontier_xy, self.info)
            if cell is not None and fu.frontier_cleared(self.grid, cell,
                                                        self.frontier_cleared_radius):
                self.cancel_goal('frontier explored', blacklist=False)

    # ------------------------------------------------------------------ map saving
    def save_map_files(self):
        """Ask SLAM Toolbox to write <path>.pgm/.yaml (save_map) and <path>.posegraph/.data."""
        self.map_saved = True
        if SaveMap is None:
            self.get_logger().warn('slam_toolbox python services not available; map not saved')
            return
        os.makedirs(os.path.dirname(self.map_save_path) or '.', exist_ok=True)
        save_cli = self.create_client(SaveMap, '/slam_toolbox/save_map')
        ser_cli = self.create_client(SerializePoseGraph, '/slam_toolbox/serialize_map')
        if save_cli.wait_for_service(timeout_sec=5.0):
            req = SaveMap.Request()
            req.name = String(data=self.map_save_path)
            save_cli.call_async(req).add_done_callback(
                lambda f: self.get_logger().info(f'map saved: {self.map_save_path}.pgm/.yaml'))
        else:
            self.get_logger().warn('/slam_toolbox/save_map not available')
        if ser_cli.wait_for_service(timeout_sec=5.0):
            req = SerializePoseGraph.Request()
            req.filename = self.map_save_path
            ser_cli.call_async(req).add_done_callback(
                lambda f: self.get_logger().info(f'pose graph saved: {self.map_save_path}.posegraph'))

    # ------------------------------------------------------------------ visualisation
    def publish_markers(self, frontiers, best):
        arr = MarkerArray()
        clear = Marker()
        clear.action = Marker.DELETEALL
        arr.markers.append(clear)
        stamp = self.get_clock().now().to_msg()

        pts = Marker()
        pts.header.frame_id = self.global_frame
        pts.header.stamp = stamp
        pts.ns, pts.id, pts.type, pts.action = 'frontiers', 0, Marker.POINTS, Marker.ADD
        pts.scale.x = pts.scale.y = self.info.resolution * 1.5
        pts.color = ColorRGBA(r=0.1, g=0.6, b=1.0, a=0.9)
        pts.pose.orientation.w = 1.0
        for f in frontiers:
            for r, c in f.cells[::2]:      # every 2nd cell is plenty for display
                x, y = fu.grid_to_world((int(r), int(c)), self.info)
                pts.points.append(Point(x=x, y=y, z=0.05))
        arr.markers.append(pts)

        if best is not None:
            g = Marker()
            g.header.frame_id = self.global_frame
            g.header.stamp = stamp
            g.ns, g.id, g.type, g.action = 'goal', 1, Marker.SPHERE, Marker.ADD
            g.pose.position.x, g.pose.position.y, g.pose.position.z = best.x, best.y, 0.1
            g.pose.orientation.w = 1.0
            g.scale.x = g.scale.y = g.scale.z = 0.25
            g.color = ColorRGBA(r=0.1, g=1.0, b=0.2, a=1.0)
            arr.markers.append(g)
        self.marker_pub.publish(arr)


def main(args=None):
    rclpy.init(args=args)
    node = FrontierExplorer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.goal_handle is not None:
            node.goal_handle.cancel_goal_async()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
