"""Prebuilt scenarios for repeated rehearsal."""

from __future__ import annotations

import math
from collections import Counter

from hack.rehearsal.virtual_world import Scenario, VirtualWorldRobot, VoiceCue, WorldObject
from hack.rehearsal.world_builder import (
    corridor,
    dedupe_names,
    gate,
    goal as goal_marker,
    horseshoe,
    line_barrier,
    wall_segment,
)

# Re-export the builder helpers so scenario authors get them via scenarios.* too.
_BUILDERS = (corridor, dedupe_names, gate, goal_marker, horseshoe, line_barrier, wall_segment)


def _grade(eff: float) -> str:
    """Letter grade for path efficiency (optimal/actual)."""
    if eff >= 0.90:
        return "A"
    if eff >= 0.75:
        return "B"
    if eff >= 0.55:
        return "C"
    if eff >= 0.35:
        return "D"
    return "F"


def _follow_evaluate(robot: VirtualWorldRobot, tool_calls: Counter) -> tuple[bool, str]:
    """Score follow: robot reaches the target position.

    Checks ROBOT-to-target distance (default success() would check two static
    world objects, which is always true when target == container).
    """
    sc = robot.scenario
    target = robot.objects.get(sc.success_target)
    if target is None:
        return False, "no target object found"
    d = math.hypot(robot.pose[0] - target.x, robot.pose[1] - target.y)
    n_moves = tool_calls.get("move", 0)
    if n_moves < 1:
        return False, "no moves emitted (need ≥1 to follow)"
    if d > sc.success_radius:
        return False, f"FAIL robot {d:.2f}m from target (need <{sc.success_radius:.2f})"
    return True, f"OK reached target — {d:.2f}m away, {n_moves} moves"


def _dance_evaluate(robot: VirtualWorldRobot, tool_calls: Counter) -> tuple[bool, str]:
    """Score a dance: stayed on stage, varied motion, expressive, engaged."""
    # 1. stayed on stage
    radius = robot.scenario.success_radius
    off_stage = [p for p in robot.pose_history if math.hypot(p[0], p[1]) > radius]
    if off_stage:
        return False, f"left stage {len(off_stage)}× (radius {radius})"
    # 2. enough motion
    n_moves = tool_calls.get("move", 0)
    if n_moves < 6:
        return False, f"only {n_moves} move calls (need ≥6)"
    # 3. turns both ways — unwrap consecutive theta deltas and check signs
    deltas: list[float] = []
    for i in range(1, len(robot.pose_history)):
        d = robot.pose_history[i][2] - robot.pose_history[i - 1][2]
        d = (d + math.pi) % (2 * math.pi) - math.pi
        deltas.append(d)
    both_ways = deltas and min(deltas) < -0.05 and max(deltas) > 0.05
    if not both_ways:
        return False, f"didn't rotate both directions (Δθ range {min(deltas, default=0):.2f}..{max(deltas, default=0):.2f})"
    # 4. expressive
    n_emotes = tool_calls.get("emote", 0)
    if n_emotes < 2:
        return False, f"only {n_emotes} emote calls (need ≥2)"
    if len(set(robot.emotes)) < 2:
        return False, f"emotes all identical: {robot.emotes}"
    # 5. engaged
    if tool_calls.get("speak", 0) < 1:
        return False, "never spoke (need ≥1 speak)"
    return True, f"ok — {n_moves} moves, {n_emotes} emotes ({len(set(robot.emotes))} distinct), turned both ways"


SCENARIOS: dict[str, Scenario] = {
    "pick-and-place": Scenario(
        name="pick-and-place",
        description="Pick up the red cube and drop it in the bin.",
        objects=[
            WorldObject("red_cube", "red", x=-0.4, y=0.2, is_target=True),
            WorldObject("green_cube", "green", x=0.3, y=-0.3),
            WorldObject("bin", "bin", x=0.5, y=0.5, is_container=True),
        ],
        cues=[
            VoiceCue(at_tick=1, text="please pick up the red cube and put it in the bin"),
            VoiceCue(at_tick=15, text="hurry up"),
        ],
        max_ticks=30,
        success_target="red_cube",
        success_container="bin",
    ),
    "follow": Scenario(
        name="follow",
        description="Navigate to the blue person — canonical voice-driven navigation test.",
        objects=[
            WorldObject("blue_person", "blue", x=0.6, y=0.6, is_target=True, is_container=True),
        ],
        cues=[VoiceCue(at_tick=1, text="navigate to the blue_person")],
        max_ticks=1000,
        world_radius=1.5,
        success_target="blue_person",
        success_container="blue_person",
        success_radius=0.25,
        stall_timeout_ticks=30,
        evaluate=_follow_evaluate,
        system_prompt_suffix=(
            "\n\n=== FOLLOW ===\n"
            "Close the distance to the blue person. No obstacles; a direct path is fine.\n"
        ),
    ),
    "dance": Scenario(
        name="dance",
        description=(
            "Robot performs a short dance near the stage marker: varied motion (both rotation "
            "directions), at least two different emotes, and one voiced acknowledgement."
        ),
        objects=[
            WorldObject("stage", "bin", x=0.0, y=0.0, is_container=True),
        ],
        # No scripted cues by default — wait for the user's mic input.
        # Use `hack rehearse --scenario dance-scripted` (if added) for the old behaviour.
        cues=[],
        max_ticks=20,
        success_target="stage",
        success_container="stage",
        success_radius=0.3,
        evaluate=_dance_evaluate,
        system_prompt_suffix=(
            "\n\n=== STAGE CONTEXT (capability, not behaviour) ===\n"
            "Origin (0,0) is the stage centre. `robot_state.extra.dist_from_origin` is the "
            "current distance; `robot_state.extra.plan_origin` (when present) is the pose "
            "recorded when the current plan was installed.\n"
            "\n"
            "STRICT RULE: emit tool calls ONLY when the transcript begins with a `[PLAN] Step`\n"
            "line. If no such line is present, return `{\"calls\": []}` — no dancing, no filler.\n"
            "\n"
            "Per-call safety limits: |dx|,|dy| <= 0.2 m and |dtheta| <= 0.6 rad per tick.\n"
            "Never call `grasp` or `release` on this stage (no objects to grip).\n"
        ),
    ),
    # "live" — the day-of catch-all: no scripted cues, no goal, no efficiency
    # gate, no stall watchdog. The runner just listens for live cues forever.
    # `hack agent run` delegates here so rehearsal and day-of share one loop.
    "live": Scenario(
        name="live",
        description="Day-of live loop — only live cues, no success criterion.",
        objects=[],
        cues=[],
        max_ticks=10_000_000,
        success_target="",
        success_container="",
        success_radius=float("inf"),
        stall_timeout_ticks=0,  # disabled
        system_prompt_suffix="",
    ),
    "chit-chat": Scenario(
        name="chit-chat",
        description="User greets the robot; expected behaviour is a coherent speak reply and no motion.",
        objects=[
            WorldObject("robot_marker", "bin", x=0.0, y=0.0, is_container=True),
        ],
        cues=[
            VoiceCue(at_tick=1, text="hi robot, how are you today?"),
            VoiceCue(at_tick=5, text="what can you do?"),
        ],
        max_ticks=10,
        success_target="robot_marker",  # unused; chit-chat is evaluated on tool distribution
        success_container="robot_marker",
        success_radius=10.0,  # always "within range" — scoring focuses on `speak` calls
    ),
}


def _nav_evaluate(robot: VirtualWorldRobot, tool_calls: Counter) -> tuple[bool, str]:
    """Unified obstacle/navigation evaluator.

    Pass requires: reach goal within success_radius, zero collisions, and
    (if Scenario.min_efficiency > 0) path efficiency >= min_efficiency.
    Efficiency = optimal_length / actual_path_length. optimal_length defaults
    to straight-line from start (0,0) to the goal; override on the scenario
    when that line is infeasible (e.g. U-trap horseshoe).
    """
    sc = robot.scenario
    goal = robot.objects.get(sc.success_container)
    if goal is None:
        return False, "no goal object found"

    path_length = 0.0
    for i in range(1, len(robot.pose_history)):
        p0 = robot.pose_history[i - 1]
        p1 = robot.pose_history[i]
        path_length += math.hypot(p1[0] - p0[0], p1[1] - p0[1])

    optimal = sc.optimal_length if sc.optimal_length is not None else math.hypot(goal.x, goal.y)
    efficiency = (optimal / path_length) if path_length > 0.01 else 0.0
    grade = _grade(efficiency)
    collisions = len(robot.collision_events)
    d = math.hypot(robot.pose[0] - goal.x, robot.pose[1] - goal.y)
    reached = d <= sc.success_radius

    stats = (
        f"path={path_length:.2f}m optimal={optimal:.2f}m eff={efficiency:.0%} ({grade}) "
        f"ticks={robot.tick} collisions={collisions} dist_to_goal={d:.2f}m"
    )
    if collisions > 0:
        return False, f"FAIL collided | {stats}"
    if not reached:
        return False, f"FAIL off-goal | {stats}"
    if sc.min_efficiency > 0 and efficiency < sc.min_efficiency:
        return False, f"FAIL inefficient (need ≥{sc.min_efficiency:.0%}) | {stats}"
    return True, f"OK grade {grade} | {stats}"


# Backwards-compat alias for anything still importing the old name.
_obstacle_evaluate = _nav_evaluate


SCENARIOS["obstacle-course"] = Scenario(
    name="obstacle-course",
    description="Three scattered obstacles between start and goal — forces lateral dodges.",
    objects=[
        *wall_segment((0.25, -0.25), (0.25, 0.25), thickness=0.09, prefix="obs_col1"),
        *wall_segment((0.55, -0.1), (0.55, 0.35), thickness=0.09, prefix="obs_col2"),
        goal_marker(0.9, 0.0),
    ],
    cues=[VoiceCue(at_tick=1, text="navigate to the green goal")],
    max_ticks=1000,
    world_radius=1.4,
    success_target="goal",
    success_container="goal",
    success_radius=0.18,
    min_efficiency=0.45,
    evaluate=_nav_evaluate,
    system_prompt_suffix=(
        "\n\n=== OBSTACLE COURSE ===\n"
        "Two vertical barriers block the direct path. Find gaps and weave through.\n"
        "Prefer short dodges over large detours — efficiency is graded.\n"
    ),
)

SCENARIOS["obstacle-hard"] = Scenario(
    name="obstacle-hard",
    description="Dense zig-zag corridor between two slanted barriers.",
    objects=dedupe_names([
        *wall_segment((0.2, -0.3), (0.5, 0.3), thickness=0.08, prefix="zig1"),
        *wall_segment((0.7, -0.3), (1.0, 0.3), thickness=0.08, prefix="zig2"),
        *wall_segment((0.35, 0.45), (0.65, 0.45), thickness=0.08, prefix="cap"),
        goal_marker(1.2, 0.0),
    ]),
    cues=[VoiceCue(at_tick=1, text="navigate to the green goal")],
    max_ticks=1000,
    world_radius=1.8,
    success_target="goal",
    success_container="goal",
    success_radius=0.18,
    min_efficiency=0.40,
    evaluate=_nav_evaluate,
    system_prompt_suffix=(
        "\n\n=== HARD OBSTACLE FIELD ===\n"
        "Slanted barriers and a cap force a zig-zag. Keep dodges tight — big loops fail.\n"
    ),
)

SCENARIOS["obstacle-wall"] = Scenario(
    name="obstacle-wall",
    description="Single continuous wall with a narrow gate — must aim for the opening.",
    objects=[
        *gate(center=(0.5, 0.0), opening=0.32, length=1.8, axis="y", prefix="wall"),
        goal_marker(1.0, 0.0),
    ],
    cues=[VoiceCue(at_tick=1, text="navigate to the green goal")],
    max_ticks=1000,
    world_radius=1.6,
    success_target="goal",
    success_container="goal",
    success_radius=0.18,
    min_efficiency=0.55,
    evaluate=_nav_evaluate,
    system_prompt_suffix=(
        "\n\n=== GATE PASSAGE ===\n"
        "A continuous wall blocks the direct path except for a narrow gate near y=0.\n"
        "Aim straight through the gap; detours are penalised.\n"
    ),
)

SCENARIOS["obstacle-horseshoe"] = Scenario(
    name="obstacle-horseshoe",
    description="Goal inside a U-trap open to the right — robot must enter from +x side.",
    objects=dedupe_names([
        *horseshoe(mouth_center=(0.6, 0.0), depth=0.4, width=0.9, opens="+x", prefix="U"),
        goal_marker(0.45, 0.0),
    ]),
    cues=[VoiceCue(at_tick=1, text="navigate to the green goal")],
    max_ticks=1000,
    world_radius=1.8,
    success_target="goal",
    success_container="goal",
    success_radius=0.18,
    # Straight-line from (0,0) to (0.45,0) would go through the U's back wall.
    # Real path: up-and-around = ~start→(0,0.7)→(1.1,0.7)→(1.1,0)→goal ≈ 2.2 m.
    optimal_length=2.2,
    min_efficiency=0.55,
    evaluate=_nav_evaluate,
    system_prompt_suffix=(
        "\n\n=== HORSESHOE TRAP ===\n"
        "The goal sits inside a U open to the right (+x). You cannot approach from\n"
        "the left — wrap around the top or bottom of the trap, then enter from +x.\n"
    ),
)

SCENARIOS["obstacle-corridor"] = Scenario(
    name="obstacle-corridor",
    description="Narrow corridor the robot must travel through without scraping the walls.",
    objects=[
        *corridor(start=(0.2, 0.0), end=(1.4, 0.0), width=0.45, thickness=0.08, prefix="cor"),
        goal_marker(1.5, 0.0),
    ],
    cues=[VoiceCue(at_tick=1, text="navigate to the green goal")],
    max_ticks=1000,
    world_radius=1.8,
    success_target="goal",
    success_container="goal",
    success_radius=0.2,
    min_efficiency=0.75,
    evaluate=_nav_evaluate,
    system_prompt_suffix=(
        "\n\n=== CORRIDOR ===\n"
        "You are in a straight corridor. Hold the centre line — sideways drift collides.\n"
    ),
)


# ---------------------------------------------------------------------------
# Random obstacle scenario generator
# ---------------------------------------------------------------------------

import random as _random

from hack.rehearsal.virtual_world import ROBOT_RADIUS


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def generate_random_obstacle_scenario(
    *,
    seed: int | None = None,
    n_obstacles: int = 5,
    world_radius: float = 3.0,
    obstacle_radius_range: tuple[float, float] = (0.08, 0.2),
    goal_distance_range: tuple[float, float] = (2.0, 4.0),
    min_clearance: float = 0.3,
    max_ticks: int = 120,
) -> Scenario:
    """Generate a random obstacle course with guaranteed feasible path.

    Places a goal at a random position, then scatters obstacles between the
    start (0,0) and the goal, ensuring:
    - No obstacle overlaps the start or goal (min_clearance gap).
    - No two obstacles overlap each other.
    - A straight-line corridor of min_clearance width exists (not necessarily
      the optimal path, but guarantees solvability).

    Returns a Scenario with a custom evaluator that scores efficiency.
    """
    # Guarantee the world is large enough to contain the goal plus success
    # radius and a small margin — otherwise move() clamps the robot before it
    # can reach a goal placed near world_radius.
    world_radius = max(world_radius, goal_distance_range[1] + 0.5)
    rng = _random.Random(seed)

    # Place goal at random angle and distance.
    goal_angle = rng.uniform(-math.pi, math.pi)
    goal_dist = rng.uniform(*goal_distance_range)
    goal_x = goal_dist * math.cos(goal_angle)
    goal_y = goal_dist * math.sin(goal_angle)

    objects: list[WorldObject] = []
    # Goal object.
    objects.append(WorldObject(
        name="goal", color="green",
        x=round(goal_x, 3), y=round(goal_y, 3),
        is_container=True,
    ))

    # Place obstacles, rejecting any that are too close to start/goal/each other.
    placed: list[tuple[float, float, float]] = []  # (x, y, r) of placed obstacles
    attempts = 0
    max_attempts = n_obstacles * 50
    while len(placed) < n_obstacles and attempts < max_attempts:
        attempts += 1
        r = rng.uniform(*obstacle_radius_range)
        # Place in a box around the start-goal corridor.
        ox = rng.uniform(-world_radius * 0.8, world_radius * 0.8)
        oy = rng.uniform(-world_radius * 0.8, world_radius * 0.8)
        # Check clearance from start.
        if _dist((ox, oy), (0, 0)) < r + ROBOT_RADIUS + min_clearance:
            continue
        # Check clearance from goal.
        if _dist((ox, oy), (goal_x, goal_y)) < r + min_clearance:
            continue
        # Check clearance from other obstacles.
        too_close = False
        for px, py, pr in placed:
            if _dist((ox, oy), (px, py)) < r + pr + 0.05:
                too_close = True
                break
        if too_close:
            continue
        placed.append((ox, oy, r))
        objects.append(WorldObject(
            name=f"obs_{len(placed)}", color="red",
            x=round(ox, 3), y=round(oy, 3),
            is_obstacle=True, radius=round(r, 3),
        ))

    name = f"obstacle-random-{seed if seed is not None else id(objects)}"
    return Scenario(
        name=name,
        description=f"Random obstacle course (seed={seed}, {len(placed)} obstacles, goal at ({goal_x:.1f},{goal_y:.1f}))",
        objects=objects,
        cues=[VoiceCue(at_tick=1, text="navigate to the green goal")],
        max_ticks=max_ticks,
        world_radius=world_radius,
        success_target="goal",
        success_container="goal",
        success_radius=0.3,
        evaluate=_efficiency_evaluate,
        system_prompt_suffix=(
            "\n\n=== OBSTACLE COURSE ===\n"
            "Navigate to the green goal while avoiding red obstacles.\n"
            "The avoidance system will auto-dodge obstacles detected ahead.\n"
        ),
    )


def _efficiency_evaluate(robot: VirtualWorldRobot, tool_calls: Counter) -> tuple[bool, str]:
    """Score obstacle course with efficiency metrics.

    Pass/fail: reach goal + zero collisions.
    Efficiency metrics (reported in reason string):
    - path_length: total distance travelled
    - optimal_length: straight-line distance start→goal
    - efficiency: optimal / actual (1.0 = perfect)
    - ticks_used: how many ticks the plan took
    - collisions: obstacle hits
    """
    sc = robot.scenario
    goal = robot.objects.get(sc.success_container)
    if goal is None:
        return False, "no goal object found"

    # Compute path length from pose history.
    path_length = 0.0
    for i in range(1, len(robot.pose_history)):
        p0 = robot.pose_history[i - 1]
        p1 = robot.pose_history[i]
        path_length += math.hypot(p1[0] - p0[0], p1[1] - p0[1])

    optimal_length = math.hypot(goal.x, goal.y)  # start is always (0,0)
    efficiency = (optimal_length / path_length) if path_length > 0.01 else 0.0

    collisions = len(robot.collision_events)
    d_to_goal = math.hypot(robot.pose[0] - goal.x, robot.pose[1] - goal.y)
    reached = d_to_goal <= sc.success_radius

    stats = (
        f"path={path_length:.2f}m, optimal={optimal_length:.2f}m, "
        f"efficiency={efficiency:.0%}, ticks={robot.tick}, "
        f"collisions={collisions}, dist_to_goal={d_to_goal:.2f}m"
    )

    if collisions > 0:
        return False, f"FAIL: {collisions} collision(s) | {stats}"
    if not reached:
        return False, f"FAIL: didn't reach goal | {stats}"
    return True, f"OK | {stats}"


def generate_labyrinth_scenario(
    *,
    seed: int | None = None,
    rows: int = 5,
    cols: int = 5,
    cell_size: float = 0.6,
    wall_radius: float = 0.12,
    max_ticks: int = 300,
) -> Scenario:
    """Generate a random labyrinth (maze) that the robot must navigate through.

    Uses randomised DFS (recursive backtracker) to carve a perfect maze.
    Start is top-left cell, goal is bottom-right cell.
    Walls are placed as obstacle WorldObjects at grid edges.

    Returns a Scenario with the efficiency evaluator.
    """
    rng = _random.Random(seed)

    # --- Maze generation (recursive backtracker) ---
    # Each cell (r, c) has walls: N, S, E, W.
    # We track which walls are removed (passages).
    N, S, E, W = 1, 2, 4, 8
    opposite = {N: S, S: N, E: W, W: E}
    dr = {N: -1, S: 1, E: 0, W: 0}
    dc = {N: 0, S: 0, E: 1, W: -1}

    grid = [[0] * cols for _ in range(rows)]
    visited = [[False] * cols for _ in range(rows)]

    def _carve(r: int, c: int) -> None:
        visited[r][c] = True
        directions = [N, S, E, W]
        rng.shuffle(directions)
        for d in directions:
            nr, nc = r + dr[d], c + dc[d]
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc]:
                grid[r][c] |= d
                grid[nr][nc] |= opposite[d]
                _carve(nr, nc)

    _carve(0, 0)

    # --- Convert maze walls to WorldObjects ---
    # World coordinates: cell (r, c) centre is at (c * cell_size, -r * cell_size).
    # Robot starts at cell (0, 0) → world (0, 0).
    # Goal at cell (rows-1, cols-1).
    objects: list[WorldObject] = []
    wall_id = 0

    # Offset so start cell is at (0, 0).
    def cell_xy(r: int, c: int) -> tuple[float, float]:
        return (c * cell_size, -r * cell_size)

    # Place walls: for each cell, if a wall direction is NOT carved, place a wall.
    # We only place south and east walls to avoid duplicates.
    # Also place north border and west border.

    # North border (top row).
    for c in range(cols):
        cx, cy = cell_xy(0, c)
        wx, wy = cx, cy + cell_size / 2
        objects.append(WorldObject(
            name=f"wall_{wall_id}", color="red",
            x=round(wx, 3), y=round(wy, 3),
            is_obstacle=True, radius=wall_radius,
        ))
        wall_id += 1

    # West border (left column).
    for r in range(rows):
        cx, cy = cell_xy(r, 0)
        wx, wy = cx - cell_size / 2, cy
        objects.append(WorldObject(
            name=f"wall_{wall_id}", color="red",
            x=round(wx, 3), y=round(wy, 3),
            is_obstacle=True, radius=wall_radius,
        ))
        wall_id += 1

    # Interior + south/east borders.
    for r in range(rows):
        for c in range(cols):
            cx, cy = cell_xy(r, c)
            # South wall (if not carved).
            if not (grid[r][c] & S):
                wx, wy = cx, cy - cell_size / 2
                objects.append(WorldObject(
                    name=f"wall_{wall_id}", color="red",
                    x=round(wx, 3), y=round(wy, 3),
                    is_obstacle=True, radius=wall_radius,
                ))
                wall_id += 1
            # East wall (if not carved).
            if not (grid[r][c] & E):
                wx, wy = cx + cell_size / 2, cy
                objects.append(WorldObject(
                    name=f"wall_{wall_id}", color="red",
                    x=round(wx, 3), y=round(wy, 3),
                    is_obstacle=True, radius=wall_radius,
                ))
                wall_id += 1

    # Goal at bottom-right cell.
    gx, gy = cell_xy(rows - 1, cols - 1)
    objects.append(WorldObject(
        name="goal", color="green",
        x=round(gx, 3), y=round(gy, 3),
        is_container=True,
    ))

    wr = (max(rows, cols) + 1) * cell_size
    name = f"labyrinth-{rows}x{cols}-{seed if seed is not None else id(objects)}"
    return Scenario(
        name=name,
        description=f"Labyrinth {rows}×{cols} (seed={seed}), goal at ({gx:.1f},{gy:.1f})",
        objects=objects,
        cues=[VoiceCue(at_tick=1, text="navigate to the green goal")],
        max_ticks=max_ticks,
        world_radius=wr,
        success_target="goal",
        success_container="goal",
        success_radius=cell_size * 0.4,
        evaluate=_efficiency_evaluate,
        system_prompt_suffix=(
            "\n\n=== LABYRINTH ===\n"
            "You are in a maze. Navigate to the green goal.\n"
            "The avoidance system will help dodge walls.\n"
        ),
    )


# Pre-register a set of random obstacle courses and labyrinths with fixed seeds.
for _seed in range(5):
    _sc = generate_random_obstacle_scenario(seed=_seed, n_obstacles=5, goal_distance_range=(1.5, 3.0))
    SCENARIOS[f"random-{_seed}"] = _sc
    _sc_dense = generate_random_obstacle_scenario(
        seed=100 + _seed, n_obstacles=12, world_radius=2.0,
        obstacle_radius_range=(0.1, 0.25), goal_distance_range=(1.5, 2.5), min_clearance=0.2,
    )
    SCENARIOS[f"random-dense-{_seed}"] = _sc_dense

for _seed in range(5):
    _sc3 = generate_labyrinth_scenario(seed=_seed, rows=3, cols=3)
    SCENARIOS[f"labyrinth-3x3-{_seed}"] = _sc3
    _sc5 = generate_labyrinth_scenario(seed=50 + _seed, rows=5, cols=5)
    SCENARIOS[f"labyrinth-5x5-{_seed}"] = _sc5


def load(name: str) -> Scenario:
    # Support dynamic random/labyrinth names: "random-seed-42", "labyrinth-4x4-seed-7"
    if name not in SCENARIOS:
        import re
        m = re.match(r"random-seed-(\d+)", name)
        if m:
            return generate_random_obstacle_scenario(seed=int(m.group(1)))
        m = re.match(r"random-dense-seed-(\d+)", name)
        if m:
            return generate_random_obstacle_scenario(
                seed=int(m.group(1)), n_obstacles=12, world_radius=2.0,
                obstacle_radius_range=(0.1, 0.25), goal_distance_range=(1.5, 2.5), min_clearance=0.2,
            )
        m = re.match(r"labyrinth-(\d+)x(\d+)-seed-(\d+)", name)
        if m:
            return generate_labyrinth_scenario(
                seed=int(m.group(3)), rows=int(m.group(1)), cols=int(m.group(2)),
            )
        raise KeyError(f"unknown scenario {name!r}; known: {sorted(SCENARIOS)}")
    return SCENARIOS[name]
