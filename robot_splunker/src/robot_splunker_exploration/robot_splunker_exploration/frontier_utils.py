"""Pure frontier-exploration helpers (numpy only, no ROS) so they can be unit-tested.

Occupancy grid conventions (nav_msgs/OccupancyGrid):
    -1        unknown
    0..100    probability of occupancy (SLAM Toolbox publishes 0 = free, 100 = occupied)
Grids are numpy arrays of shape (height, width) indexed [row, col]; row = y, col = x.

A *frontier cell* is a known-free cell with at least one unknown 8-neighbour: the
edge of the explored area. Neighbouring frontier cells are grouped into *frontiers*;
the explorer drives to a safe point near the best-scoring frontier.
"""

from collections import deque
from dataclasses import dataclass, field
import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

UNKNOWN = -1
Cell = Tuple[int, int]  # (row, col)

# 8-connected neighbourhood offsets (row, col)
NEIGHBOURS_8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


@dataclass
class MapInfo:
    """Geometry of an occupancy grid (subset of nav_msgs/MapMetaData)."""

    resolution: float          # metres per cell
    width: int                 # cells (x / columns)
    height: int                # cells (y / rows)
    origin_x: float = 0.0      # world position of cell (0, 0)'s corner [m]
    origin_y: float = 0.0
    origin_yaw: float = 0.0    # rotation of the grid in the world [rad] (normally 0)


@dataclass
class Frontier:
    """A connected group of frontier cells."""

    cells: np.ndarray                      # (N, 2) int array of (row, col)
    centroid: Tuple[float, float] = field(default=(0.0, 0.0))  # (row, col), fractional

    @property
    def size(self) -> int:
        return int(self.cells.shape[0])


# --------------------------------------------------------------------------- coordinates
def grid_to_world(cell: Cell, info: MapInfo) -> Tuple[float, float]:
    """Centre of a (row, col) cell in world coordinates (metres)."""
    r, c = cell
    lx = (c + 0.5) * info.resolution
    ly = (r + 0.5) * info.resolution
    cy, sy = math.cos(info.origin_yaw), math.sin(info.origin_yaw)
    return (info.origin_x + cy * lx - sy * ly, info.origin_y + sy * lx + cy * ly)


def world_to_grid(x: float, y: float, info: MapInfo) -> Optional[Cell]:
    """World (x, y) -> (row, col), or None if outside the grid."""
    dx, dy = x - info.origin_x, y - info.origin_y
    cy, sy = math.cos(info.origin_yaw), math.sin(info.origin_yaw)
    lx = cy * dx + sy * dy
    ly = -sy * dx + cy * dy
    c = int(math.floor(lx / info.resolution))
    r = int(math.floor(ly / info.resolution))
    if 0 <= r < info.height and 0 <= c < info.width:
        return (r, c)
    return None


# --------------------------------------------------------------------------- detection
def free_mask(grid: np.ndarray, occupied_threshold: int = 50) -> np.ndarray:
    """Known and below the occupancy threshold."""
    return (grid >= 0) & (grid < occupied_threshold)


def find_frontier_cells(grid: np.ndarray, occupied_threshold: int = 50) -> np.ndarray:
    """Boolean mask of frontier cells: free cells with >= 1 unknown 8-neighbour."""
    free = free_mask(grid, occupied_threshold)
    unknown = grid == UNKNOWN
    # Pad with "not unknown" so the map border itself is not treated as a frontier.
    padded = np.pad(unknown, 1, mode='constant', constant_values=False)
    h, w = grid.shape
    near_unknown = np.zeros_like(unknown)
    for dr, dc in NEIGHBOURS_8:
        near_unknown |= padded[1 + dr:1 + dr + h, 1 + dc:1 + dc + w]
    return free & near_unknown


def cluster_frontiers(mask: np.ndarray, min_size: int = 1) -> List[Frontier]:
    """Group 8-connected frontier cells (BFS) and drop clusters smaller than min_size."""
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    frontiers: List[Frontier] = []
    for r0, c0 in zip(*np.nonzero(mask)):
        if visited[r0, c0]:
            continue
        queue = deque([(int(r0), int(c0))])
        visited[r0, c0] = True
        cells = []
        while queue:
            r, c = queue.popleft()
            cells.append((r, c))
            for dr, dc in NEIGHBOURS_8:
                nr, nc = r + dr, c + dc
                if 0 <= nr < h and 0 <= nc < w and mask[nr, nc] and not visited[nr, nc]:
                    visited[nr, nc] = True
                    queue.append((nr, nc))
        if len(cells) >= min_size:
            arr = np.array(cells, dtype=int)
            centroid = (float(arr[:, 0].mean()), float(arr[:, 1].mean()))
            frontiers.append(Frontier(cells=arr, centroid=centroid))
    return frontiers


def representative_cell(frontier: Frontier) -> Cell:
    """The frontier cell closest to the cluster centroid.

    The centroid of a curved frontier can lie inside an obstacle or unknown space;
    a member cell is always on the frontier itself.
    """
    d2 = ((frontier.cells[:, 0] - frontier.centroid[0]) ** 2
          + (frontier.cells[:, 1] - frontier.centroid[1]) ** 2)
    r, c = frontier.cells[int(np.argmin(d2))]
    return (int(r), int(c))


# --------------------------------------------------------------------------- safety
def has_clearance(grid: np.ndarray, cell: Cell, radius_cells: int,
                  occupied_threshold: int = 50) -> bool:
    """True when no occupied cell lies within radius_cells (circular) of cell."""
    h, w = grid.shape
    r, c = cell
    r0, r1 = max(0, r - radius_cells), min(h, r + radius_cells + 1)
    c0, c1 = max(0, c - radius_cells), min(w, c + radius_cells + 1)
    window = grid[r0:r1, c0:c1]
    rr, cc = np.ogrid[r0:r1, c0:c1]
    inside = (rr - r) ** 2 + (cc - c) ** 2 <= radius_cells ** 2
    return not np.any((window >= occupied_threshold) & inside)


def snap_to_safe_cell(grid: np.ndarray, cell: Cell, clearance_cells: int,
                      search_radius_cells: int, occupied_threshold: int = 50) -> Optional[Cell]:
    """Nearest known-free cell (within search radius) that has the required clearance."""
    h, w = grid.shape
    r, c = cell
    candidates = []
    for dr in range(-search_radius_cells, search_radius_cells + 1):
        for dc in range(-search_radius_cells, search_radius_cells + 1):
            d2 = dr * dr + dc * dc
            if d2 <= search_radius_cells ** 2:
                candidates.append((d2, r + dr, c + dc))
    candidates.sort()
    for _, nr, nc in candidates:
        if not (0 <= nr < h and 0 <= nc < w):
            continue
        v = grid[nr, nc]
        if 0 <= v < occupied_threshold and has_clearance(grid, (nr, nc), clearance_cells,
                                                         occupied_threshold):
            return (nr, nc)
    return None


def frontier_cleared(grid: np.ndarray, cell: Cell, radius_cells: int) -> bool:
    """True when no unknown cell remains within radius_cells of cell (frontier explored)."""
    h, w = grid.shape
    r, c = cell
    window = grid[max(0, r - radius_cells):min(h, r + radius_cells + 1),
                  max(0, c - radius_cells):min(w, c + radius_cells + 1)]
    return not np.any(window == UNKNOWN)


# --------------------------------------------------------------------------- selection
def score_frontier(size_m: float, distance_m: float, size_weight: float,
                   dist_weight: float) -> float:
    """Bigger frontiers are more informative; nearer ones are cheaper to reach."""
    return size_weight * size_m - dist_weight * distance_m


def is_blacklisted(xy: Tuple[float, float], blacklist: Sequence[Tuple[float, float]],
                   radius: float) -> bool:
    return any(math.hypot(xy[0] - bx, xy[1] - by) < radius for bx, by in blacklist)


@dataclass
class Candidate:
    """A goal the explorer could drive to."""

    x: float
    y: float
    score: float
    frontier_size: int
    frontier_cell: Cell


def select_goal(grid: np.ndarray, info: MapInfo, robot_xy: Tuple[float, float], *,
                min_frontier_size: int = 8, occupied_threshold: int = 50,
                clearance_m: float = 0.3, search_radius_m: float = 0.8,
                min_goal_distance: float = 0.5, size_weight: float = 1.0,
                dist_weight: float = 1.0, blacklist: Sequence[Tuple[float, float]] = (),
                blacklist_radius: float = 0.6) -> Tuple[Optional[Candidate], List[Frontier]]:
    """Pick the best reachable-looking frontier goal.

    Returns (best candidate or None, all frontiers found) - the frontier list is
    returned so the caller can visualise it.
    """
    mask = find_frontier_cells(grid, occupied_threshold)
    frontiers = cluster_frontiers(mask, min_frontier_size)
    clearance_cells = max(1, int(round(clearance_m / info.resolution)))
    search_cells = max(1, int(round(search_radius_m / info.resolution)))

    best: Optional[Candidate] = None
    for f in frontiers:
        rep = representative_cell(f)
        goal_cell = snap_to_safe_cell(grid, rep, clearance_cells, search_cells, occupied_threshold)
        if goal_cell is None:
            continue
        gx, gy = grid_to_world(goal_cell, info)
        dist = math.hypot(gx - robot_xy[0], gy - robot_xy[1])
        if dist < min_goal_distance:
            continue
        if is_blacklisted((gx, gy), blacklist, blacklist_radius):
            continue
        s = score_frontier(f.size * info.resolution, dist, size_weight, dist_weight)
        if best is None or s > best.score:
            best = Candidate(x=gx, y=gy, score=s, frontier_size=f.size, frontier_cell=rep)
    return best, frontiers
