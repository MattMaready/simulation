"""Unit tests for frontier_utils on small synthetic occupancy grids (no ROS needed)."""

import math

import numpy as np
import pytest

from robot_splunker_exploration import frontier_utils as fu

U, F, O = -1, 0, 100   # unknown, free, occupied


def make_grid(rows):
    return np.array(rows, dtype=np.int8)


def test_frontier_cells_border_between_free_and_unknown():
    g = make_grid([
        [F, F, U, U],
        [F, F, U, U],
        [F, F, U, U],
    ])
    mask = fu.find_frontier_cells(g)
    # Column 1 free cells touch unknown column 2; column 0 does not.
    assert mask[:, 1].all()
    assert not mask[:, 0].any()
    assert not mask[:, 2:].any()          # unknown cells are never frontier cells


def test_occupied_cells_are_not_frontiers():
    g = make_grid([
        [F, O, U],
        [F, O, U],
    ])
    mask = fu.find_frontier_cells(g)
    assert not mask.any()                 # the wall separates free space from unknown


def test_map_edge_is_not_a_frontier():
    g = np.zeros((5, 5), dtype=np.int8)   # fully known, free map
    assert not fu.find_frontier_cells(g).any()


def test_clustering_separates_two_frontiers_and_filters_small():
    g = np.full((10, 10), F, dtype=np.int8)
    g[0:4, 9] = U        # frontier A (4 cells in column 8)
    g[9, 0] = U          # frontier B: tiny corner
    mask = fu.find_frontier_cells(g)
    clusters = fu.cluster_frontiers(mask, min_size=1)
    assert len(clusters) == 2
    big = fu.cluster_frontiers(mask, min_size=4)
    assert len(big) == 1 and big[0].size >= 4


def test_grid_world_roundtrip_with_rotation():
    info = fu.MapInfo(resolution=0.05, width=200, height=100,
                      origin_x=-3.0, origin_y=2.0, origin_yaw=0.4)
    for cell in [(0, 0), (10, 20), (99, 199)]:
        x, y = fu.grid_to_world(cell, info)
        assert fu.world_to_grid(x, y, info) == cell
    assert fu.world_to_grid(1000.0, 1000.0, info) is None


def test_clearance_and_snap():
    g = np.full((21, 21), F, dtype=np.int8)
    g[10, 10] = O
    assert not fu.has_clearance(g, (10, 12), radius_cells=3)
    assert fu.has_clearance(g, (10, 15), radius_cells=3)
    snapped = fu.snap_to_safe_cell(g, (10, 11), clearance_cells=3, search_radius_cells=6)
    assert snapped is not None
    assert fu.has_clearance(g, snapped, 3)
    assert math.hypot(snapped[0] - 10, snapped[1] - 10) > 3


def test_frontier_cleared():
    g = np.full((9, 9), F, dtype=np.int8)
    assert fu.frontier_cleared(g, (4, 4), 2)
    g[4, 6] = U
    assert not fu.frontier_cleared(g, (4, 4), 2)


def _corridor_world():
    """Known free corridor on the left, unknown on the right half."""
    g = np.full((40, 80), U, dtype=np.int8)
    g[5:35, 0:40] = F
    g[4, 0:40] = O
    g[35, 0:40] = O
    info = fu.MapInfo(resolution=0.05, width=80, height=40)
    return g, info


def test_select_goal_finds_frontier_and_respects_blacklist():
    g, info = _corridor_world()
    robot = (0.3, 1.0)
    best, frontiers = fu.select_goal(g, info, robot, min_frontier_size=5, clearance_m=0.15,
                                     search_radius_m=0.5, min_goal_distance=0.2)
    assert best is not None and frontiers
    # Goal is near the free/unknown border at x ~= 2.0 m, inside the corridor.
    assert 1.4 < best.x < 2.05
    assert 0.25 < best.y < 1.75

    # Blacklist that spot: there is only one frontier, so nothing else is selectable.
    best2, _ = fu.select_goal(g, info, robot, min_frontier_size=5, clearance_m=0.15,
                              search_radius_m=0.5, min_goal_distance=0.2,
                              blacklist=[(best.x, best.y)], blacklist_radius=0.6)
    assert best2 is None


def test_select_goal_none_when_fully_explored():
    g = np.zeros((30, 30), dtype=np.int8)
    g[0, :] = g[-1, :] = g[:, 0] = g[:, -1] = O
    info = fu.MapInfo(resolution=0.05, width=30, height=30)
    best, frontiers = fu.select_goal(g, info, (0.75, 0.75))
    assert best is None and frontiers == []


@pytest.mark.parametrize('size_m,dist,expected_sign', [(2.0, 1.0, 1), (0.5, 3.0, -1)])
def test_score(size_m, dist, expected_sign):
    assert math.copysign(1, fu.score_frontier(size_m, dist, 1.0, 1.0)) == expected_sign
