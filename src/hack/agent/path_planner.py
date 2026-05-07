"""Grid A* path planner for navigate_to_target with obstacles.

Produces a collision-free polyline from `start` to `goal` on a fine grid.
Cells whose centre falls within any obstacle's clearance zone are blocked.
Returns a list of waypoints (including start and goal) or [] if unreachable.

The planner is deliberately simple — it exists so the deterministic navigate
plan can route around obstacles instead of barrelling through them. The
runtime avoidance system (`check_obstacle_avoidance`) still runs as a safety
net, but good plans reduce the need for reactive dodging.
"""

from __future__ import annotations

import heapq
import math
from typing import Any


def _clearance(obstacle: Any, robot_radius: float, extra: float) -> float:
    return float(obstacle.radius) + robot_radius + extra


def find_path(
    start: tuple[float, float],
    goal: tuple[float, float],
    obstacles: list[Any],
    *,
    # Defaults mirror `robot.calibration` in `configs/agent.yaml`. Callers
    # should always pass explicit kwargs from the live config; these fallbacks
    # exist only so unit tests / direct invocations work without a config.
    robot_radius: float = 0.08,
    extra_clearance: float = 0.03,
    cell_size: float = 0.05,
    margin: float = 1.0,
) -> list[tuple[float, float]]:
    """A* on an axis-aligned grid.

    `obstacles` is a list of objects with `.x`, `.y`, `.radius` attributes.
    Returns waypoints [start, ..., goal] or [] if no path exists.
    The grid is sized around the bounding box of (start, goal, obstacles)
    with a ``margin``-metre border so the planner can route *outside* the
    obstacle cluster (horseshoe trap etc.).
    """
    if not obstacles:
        return [start, goal]

    xs = [start[0], goal[0]] + [o.x for o in obstacles]
    ys = [start[1], goal[1]] + [o.y for o in obstacles]
    min_x = min(xs) - margin
    max_x = max(xs) + margin
    min_y = min(ys) - margin
    max_y = max(ys) + margin

    cols = max(4, int(math.ceil((max_x - min_x) / cell_size)))
    rows = max(4, int(math.ceil((max_y - min_y) / cell_size)))

    def to_cell(p: tuple[float, float]) -> tuple[int, int]:
        cx = int(round((p[0] - min_x) / cell_size))
        cy = int(round((p[1] - min_y) / cell_size))
        return max(0, min(cols - 1, cx)), max(0, min(rows - 1, cy))

    def to_world(c: tuple[int, int]) -> tuple[float, float]:
        return (min_x + c[0] * cell_size, min_y + c[1] * cell_size)

    # Mark blocked cells — any cell whose centre is inside an obstacle's
    # clearance zone. Adjacent-cell corner-cutting is separately prevented in
    # the A* loop below, so we don't need a diagonal cushion here (which can
    # falsely close narrow corridors).
    blocked = [[False] * rows for _ in range(cols)]
    for o in obstacles:
        cl = _clearance(o, robot_radius, extra_clearance)
        cx = (o.x - min_x) / cell_size
        cy = (o.y - min_y) / cell_size
        r_cells = int(math.ceil(cl / cell_size))
        lo_i = max(0, int(cx) - r_cells)
        hi_i = min(cols - 1, int(cx) + r_cells + 1)
        lo_j = max(0, int(cy) - r_cells)
        hi_j = min(rows - 1, int(cy) + r_cells + 1)
        cl2 = cl * cl
        for i in range(lo_i, hi_i + 1):
            for j in range(lo_j, hi_j + 1):
                wx = min_x + i * cell_size
                wy = min_y + j * cell_size
                if (wx - o.x) ** 2 + (wy - o.y) ** 2 <= cl2:
                    blocked[i][j] = True

    start_cell = to_cell(start)
    goal_cell = to_cell(goal)
    # If start/goal cells are blocked (robot spawned inside clearance), relax
    # their block so A* can exit / enter them.
    blocked[start_cell[0]][start_cell[1]] = False
    blocked[goal_cell[0]][goal_cell[1]] = False

    def h(a: tuple[int, int], b: tuple[int, int]) -> float:
        dx = abs(a[0] - b[0])
        dy = abs(a[1] - b[1])
        return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)

    neighbours = [
        (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
        (1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)),
        (-1, 1, math.sqrt(2)), (-1, -1, math.sqrt(2)),
    ]

    open_heap: list[tuple[float, int, tuple[int, int]]] = []
    heapq.heappush(open_heap, (0.0, 0, start_cell))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], float] = {start_cell: 0.0}
    counter = 1
    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal_cell:
            break
        cx, cy = current
        for dx, dy, cost in neighbours:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or nx >= cols or ny < 0 or ny >= rows:
                continue
            if blocked[nx][ny]:
                continue
            # Prevent diagonal corner-cutting through adjacent blocks.
            if dx != 0 and dy != 0 and (blocked[cx + dx][cy] or blocked[cx][cy + dy]):
                continue
            tentative = g_score[current] + cost
            n = (nx, ny)
            if tentative < g_score.get(n, math.inf):
                g_score[n] = tentative
                came_from[n] = current
                f = tentative + h(n, goal_cell)
                heapq.heappush(open_heap, (f, counter, n))
                counter += 1
    if goal_cell not in came_from and start_cell != goal_cell:
        return []
    # Reconstruct.
    path_cells: list[tuple[int, int]] = [goal_cell]
    while path_cells[-1] != start_cell:
        parent = came_from.get(path_cells[-1])
        if parent is None:
            return []
        path_cells.append(parent)
    path_cells.reverse()
    # Collapse collinear segments to reduce waypoint count.
    pts = [to_world(c) for c in path_cells]
    pts[0] = start
    pts[-1] = goal
    if len(pts) <= 2:
        return pts
    simplified: list[tuple[float, float]] = [pts[0]]
    for i in range(1, len(pts) - 1):
        prev = simplified[-1]
        nxt = pts[i + 1]
        dx1, dy1 = pts[i][0] - prev[0], pts[i][1] - prev[1]
        dx2, dy2 = nxt[0] - pts[i][0], nxt[1] - pts[i][1]
        # Same direction (approx) — skip.
        if abs(dx1 * dy2 - dx2 * dy1) < 1e-6:
            continue
        simplified.append(pts[i])
    simplified.append(pts[-1])
    return simplified
