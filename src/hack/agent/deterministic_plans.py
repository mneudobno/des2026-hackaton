"""Deterministic plan generators — bypass the LLM decomposer entirely when the
cue maps to a computable motion.

The LLM's only job is to **classify** the cue into one of these cases. If it
matches, the runner uses the programmatic plan. If not, it falls through to the
LLM decomposer as before.

Add new cases here as pure functions; register them in `DETERMINISTIC_CASES`.
"""

from __future__ import annotations

import math
import re
from typing import Any

from hack.agent.plan_memory import DEFAULT_SAFETY, PlanStep  # noqa: F401 — re-exported for callers


_CLASSIFY_PROMPT = (
    "You classify a user's robot command into exactly ONE category.\n"
    "Categories:\n"
    "  single_action   — one atomic instruction (e.g. 'move forward', 'turn right', 'spin 360', 'go to stage')\n"
    "  compound         — two or more sequential instructions (e.g. 'walk forward then come back', 'turn left and wave')\n"
    "  unclear          — unintelligible or ambiguous\n"
    'Respond JSON only: {{"type": "single_action" | "compound" | "unclear"}}'
)


def classify_cue(cue: str) -> str | None:
    """Return the case name if the cue matches a deterministic pattern, else None.

    Keyword check only — no LLM. For compound detection use `classify_cue_with_llm`.
    """
    c = cue.lower().strip()
    # Personality intro — pre-baked greeting (must precede other matchers).
    if _is_personality_intro(c):
        return "personality_intro"
    # Navigate to a named target (goal, cube, bin, etc.)
    if _is_navigate_to_target(c):
        return "navigate_to_target"
    # Return-to-origin first when the cue mentions a destination (start/stage/origin).
    if _is_return_cue(c):
        return "return_to_origin"
    # Numbered walk: "10 steps forward", "5 steps left", etc.
    if _is_numbered_walk(c):
        return "numbered_walk"
    # Simple move only fires when there's NO destination keyword.
    if _is_simple_move(c):
        return "single_move"
    m = re.search(r"(?:turn|spin|rotate)\b.*?(\d+)", c)
    if m:
        deg = float(m.group(1))
        if 1 <= deg <= 720:
            return "rotate_degrees"
    if any(k in c for k in ("circle", "arc", "orbit")):
        return "walk_circle"
    return None


async def classify_cue_smart(cue: str, planner: Any = None) -> str | None:
    """Two-pass classification:
    1. If the cue contains compound connectors ('and then', 'after that', 'and', 'then'),
       it's compound → return None (fall through to LLM decomposer).
    2. Short cues (≤4 words) → keyword classifier directly.
    3. Longer single-action cues → LLM classifies, then keyword classifier.
    On any LLM failure → return None (safe: decomposer handles it).
    """
    c = cue.lower().strip()

    # Compound connectors — almost always multi-step instructions.
    compound_markers = (" and then ", " after that ", " then ", " afterwards ",
                        " followed by ", " and after ", " and also ")
    if any(m in f" {c} " for m in compound_markers):
        return None

    # Comma-separated sub-cues (e.g. "10 steps forward, 10 steps left").
    if "," in c:
        return None

    # Simple "and" between two verb phrases: "walk forward and come back"
    if " and " in c:
        parts = c.split(" and ")
        if len(parts) >= 2 and all(len(p.strip().split()) >= 2 for p in parts):
            return None

    # Fast path: very short cues (≤4 words) are always single-action.
    words = cue.strip().split()
    if len(words) <= 4:
        return classify_cue(cue)

    # LLM classification for longer cues.
    if planner is not None:
        try:
            import json as _json
            prompt = _CLASSIFY_PROMPT + f"\n\nUser command: {cue!r}"
            text = await planner.adapter.complete(prompt, json_mode=True)
            text = (text or "").strip()
            for candidate in (text, _extract_json(text)):
                if not candidate:
                    continue
                try:
                    data = _json.loads(candidate)
                except _json.JSONDecodeError:
                    continue
                ctype = data.get("type", "").lower().strip()
                if ctype in ("compound", "unclear"):
                    return None
                if ctype == "single_action":
                    return classify_cue(cue)
        except Exception:
            pass
        # LLM failed (429, timeout, parse error) → safe fallback is decomposer, not keyword.
        return None

    # No LLM available at all — keyword classifier.
    return classify_cue(cue)


def _extract_json(text: str) -> str:
    s = text.find("{")
    e = text.rfind("}")
    return text[s : e + 1] if s >= 0 and e > s else ""


def generate_plan(
    case: str,
    cue: str,
    pose: tuple[float, float, float],
    safety: dict[str, float],
    calibration: dict[str, float] | None = None,
    world_objects: dict[str, Any] | None = None,
) -> list[PlanStep]:
    """Generate a deterministic plan for the given case. Never calls an LLM.

    `calibration` keys: `linear_scale`, `angular_scale` (default 1.0),
    `prefer_forward_walk` (default false).
    """
    gen = _GENERATORS.get(case)
    if gen is None:
        return []
    # Merge calibration preferences into safety so generators can read them.
    merged_safety = dict(safety)
    if calibration:
        # Pass the whole calibration block through (path planner, dodge sizes,
        # robot footprint, etc.) and keep the old single-key back-compat.
        merged_safety["_calibration"] = dict(calibration)
        merged_safety["prefer_forward_walk"] = calibration.get("prefer_forward_walk", False)
    if world_objects:
        merged_safety["_world_objects"] = world_objects
    steps = gen(cue, pose, merged_safety)
    cal = calibration or {}
    lin_s = float(cal.get("linear_scale", 1.0))
    ang_s = float(cal.get("angular_scale", 1.0))
    if lin_s == 1.0 and ang_s == 1.0:
        return steps
    for s in steps:
        if s.tool and s.tool.get("name") == "move":
            args = s.tool.get("args") or {}
            if "dx" in args:
                args["dx"] = round(float(args["dx"]) * lin_s, 6)
            if "dy" in args:
                args["dy"] = round(float(args["dy"]) * lin_s, 6)
            if "dtheta" in args:
                args["dtheta"] = round(float(args["dtheta"]) * ang_s, 6)
    return steps


# ---------------------------------------------------------------------------
# Internal generators
# ---------------------------------------------------------------------------

def _is_return_cue(c: str) -> bool:
    # Verbs that mean "navigate to origin/start/stage/home".
    # Keep this list broad — false positives are caught by the smart classifier
    # for compound cues (5+ words go through LLM classification first).
    return_kws = (
        "go to start", "go to stage", "go to origin",
        "goto start", "goto stage", "goto origin",
        "walk to start", "walk to stage", "walk to origin",
        "move to start", "move to stage", "move to origin",
        "run to start", "run to stage", "run to origin",
        "return to", "go back", "come back",
        "back to start", "back to stage", "back to origin",
        "return home", "go home", "walk home",
        "to initial position", "to original position", "to starting position",
    )
    return any(k in c for k in return_kws)


def _is_personality_intro(c: str) -> bool:
    """Match canonical greeting phrasings only — keep narrow to avoid colliding
    with navigation cues like 'go to the cube and say hi'."""
    canon = (
        "introduce yourself", "introduce yourselves",
        "say hi", "say hello", "say hey",
        "who are you", "what's your name", "whats your name",
        "wave hello", "wave hi",
    )
    return any(k in c for k in canon)


def _is_navigate_to_target(c: str) -> bool:
    """Cues like 'go to the goal', 'navigate to the green goal', 'move to the bin'."""
    nav_verbs = ("go to the", "navigate to the", "move to the", "walk to the", "reach the")
    target_kws = (
        "goal", "target", "cube", "bin", "marker", "object",
        "person", "human", "blue", "red", "green", "yellow",
    )
    if not any(v in c for v in nav_verbs):
        return False
    return any(t in c for t in target_kws)


def _is_numbered_walk(c: str) -> bool:
    """Match patterns like '10 steps forward', '5 step left', 'walk 3 steps right'."""
    return bool(re.search(r"\d+\s*steps?\s*(forward|left|right|back|backward|backwards|ahead)", c))


def _is_simple_move(c: str) -> bool:
    # No number in the cue + a motion verb + NO destination keyword.
    if re.search(r"\d", c):
        return False
    # If the cue mentions a destination, it's navigation, not a simple move.
    destinations = ("start", "stage", "origin", "home", "initial", "original", "position")
    if any(d in c for d in destinations):
        return False
    verbs = ("move forward", "move back", "step forward", "step back",
             "walk forward", "walk back", "go forward", "go back",
             "move left", "move right", "step left", "step right",
             "go left", "go right",
             "walk backward", "walk backwards", "go backward", "go backwards",
             "move backward", "move backwards")
    return any(k in c for k in verbs)


def _gen_return_to_origin(
    cue: str, pose: tuple[float, float, float], safety: dict[str, float],
) -> list[PlanStep]:
    x, y, th = pose
    dist = math.hypot(x, y)
    if dist < 0.05:
        return [PlanStep(text="Already at origin.", tool={"name": "wait", "args": {"seconds": 0.5}, "rationale": "already at origin"})]

    lin = float(safety.get("max_linear_speed", DEFAULT_SAFETY["max_linear_speed"]))
    ang = float(safety.get("max_angular_speed", DEFAULT_SAFETY["max_angular_speed"]))

    # Check if the caller wants turn-walk-turn (real robots) or body-frame (sim).
    # `safety` dict also carries calibration keys when passed from the runner.
    prefer_fwd = bool(safety.get("prefer_forward_walk", False))

    if prefer_fwd:
        return _return_via_forward_walk(x, y, th, dist, lin, ang)

    # Body-frame (omnidirectional / sim): direct dx/dy toward origin.
    cos_t, sin_t = math.cos(th), math.sin(th)
    body_dx = (-x) * cos_t + (-y) * sin_t
    body_dy = (-x) * (-sin_t) + (-y) * cos_t

    n = max(1, math.ceil(max(abs(body_dx), abs(body_dy)) / lin))
    chunk_dx = body_dx / n
    chunk_dy = body_dy / n

    steps: list[PlanStep] = []
    for i in range(n):
        steps.append(PlanStep(
            text=f"Return to origin [{i+1}/{n}]",
            tool={
                "name": "move",
                "args": {"dx": round(chunk_dx, 4), "dy": round(chunk_dy, 4), "dtheta": 0.0},
                "rationale": f"computed return step {i+1}/{n}",
            },
        ))
    return steps


def _return_via_forward_walk(
    x: float, y: float, th: float, dist: float, lin: float, ang: float,
) -> list[PlanStep]:
    """Turn toward origin → walk forward → optionally turn back to original heading."""
    steps: list[PlanStep] = []

    # Angle from robot to origin in world frame.
    target_angle = math.atan2(-y, -x)
    # Delta to turn the robot to face origin.
    turn_needed = (target_angle - th + math.pi) % (2 * math.pi) - math.pi

    # 1. Turn to face origin (if needed).
    if abs(turn_needed) > 0.05:
        n_turn = max(1, math.ceil(abs(turn_needed) / ang))
        per_turn = turn_needed / n_turn
        for i in range(n_turn):
            steps.append(PlanStep(
                text=f"Turn toward origin [{i+1}/{n_turn}]",
                tool={
                    "name": "move",
                    "args": {"dx": 0.0, "dy": 0.0, "dtheta": round(per_turn, 6)},
                    "rationale": f"face origin step {i+1}/{n_turn}",
                },
            ))

    # 2. Walk forward to origin.
    n_walk = max(1, math.ceil(dist / lin))
    per_walk = dist / n_walk
    for i in range(n_walk):
        steps.append(PlanStep(
            text=f"Walk to origin [{i+1}/{n_walk}]",
            tool={
                "name": "move",
                "args": {"dx": round(per_walk, 4), "dy": 0.0, "dtheta": 0.0},
                "rationale": f"forward walk step {i+1}/{n_walk}",
            },
        ))

    # 3. Turn back to original heading (so the robot faces where it was facing before).
    turn_back = -turn_needed
    if abs(turn_back) > 0.05:
        n_back = max(1, math.ceil(abs(turn_back) / ang))
        per_back = turn_back / n_back
        for i in range(n_back):
            steps.append(PlanStep(
                text=f"Restore heading [{i+1}/{n_back}]",
                tool={
                    "name": "move",
                    "args": {"dx": 0.0, "dy": 0.0, "dtheta": round(per_back, 6)},
                    "rationale": f"restore heading step {i+1}/{n_back}",
                },
            ))

    return steps


def _gen_rotate_degrees(
    cue: str, pose: tuple[float, float, float], safety: dict[str, float],
) -> list[PlanStep]:
    c = cue.lower()
    m = re.search(r"(\d+)", c)
    if not m:
        return []
    deg = float(m.group(1))
    rad = math.radians(deg)

    # Direction: default left (positive dtheta) unless cue says right/clockwise
    if any(k in c for k in ("right", "clockwise", "cw")):
        rad = -rad

    ang = float(safety.get("max_angular_speed", DEFAULT_SAFETY["max_angular_speed"]))
    n = max(1, math.ceil(abs(rad) / ang))
    per_step = rad / n

    steps: list[PlanStep] = []
    for i in range(n):
        steps.append(PlanStep(
            text=f"Turn {math.degrees(per_step):+.0f}° [{i+1}/{n}]",
            tool={
                "name": "move",
                "args": {"dx": 0.0, "dy": 0.0, "dtheta": round(per_step, 6)},
                "rationale": f"computed rotation step {i+1}/{n}",
            },
        ))
    return steps


def _gen_single_move(
    cue: str, pose: tuple[float, float, float], safety: dict[str, float],
) -> list[PlanStep]:
    c = cue.lower()
    lin = float(safety.get("max_linear_speed", DEFAULT_SAFETY["max_linear_speed"]))
    dx = dy = 0.0

    if any(k in c for k in ("forward", "ahead")):
        dx = lin
    elif any(k in c for k in ("back", "backward", "backwards", "reverse")):
        dx = -lin
    elif "left" in c:
        dy = lin
    elif "right" in c:
        dy = -lin
    else:
        dx = lin  # default forward

    return [PlanStep(
        text=cue,
        tool={
            "name": "move",
            "args": {"dx": round(dx, 4), "dy": round(dy, 4), "dtheta": 0.0},
            "rationale": "single step, default magnitude",
        },
    )]


def _gen_numbered_walk(
    cue: str, pose: tuple[float, float, float], safety: dict[str, float],
) -> list[PlanStep]:
    """Handle 'N steps forward/left/right/back'.

    'left'/'right' means turn 90° then walk forward N steps (square-walk semantics).
    """
    c = cue.lower()
    m = re.search(r"(\d+)\s*steps?\s*(forward|left|right|back|backward|backwards|ahead)", c)
    if not m:
        return []
    n = int(m.group(1))
    direction = m.group(2)
    lin = float(safety.get("max_linear_speed", DEFAULT_SAFETY["max_linear_speed"]))
    ang = float(safety.get("max_angular_speed", DEFAULT_SAFETY["max_angular_speed"]))
    steps: list[PlanStep] = []

    # For left/right/back: turn first, then walk forward.
    turn_rad = 0.0
    if direction in ("left",):
        turn_rad = math.pi / 2  # +90° left
    elif direction in ("right",):
        turn_rad = -math.pi / 2  # -90° right
    elif direction in ("back", "backward", "backwards"):
        turn_rad = math.pi  # 180°

    if abs(turn_rad) > 0.05:
        n_turn = max(1, math.ceil(abs(turn_rad) / ang))
        per_turn = turn_rad / n_turn
        for i in range(n_turn):
            steps.append(PlanStep(
                text=f"Turn {'left' if turn_rad > 0 else 'right'} [{i+1}/{n_turn}]",
                tool={
                    "name": "move",
                    "args": {"dx": 0.0, "dy": 0.0, "dtheta": round(per_turn, 6)},
                    "rationale": f"turn step {i+1}/{n_turn}",
                },
            ))

    # Walk forward N steps (each step = max_linear_speed).
    for i in range(n):
        steps.append(PlanStep(
            text=f"Walk forward [{i+1}/{n}]",
            tool={
                "name": "move",
                "args": {"dx": round(lin, 4), "dy": 0.0, "dtheta": 0.0},
                "rationale": f"walk step {i+1}/{n}",
            },
        ))
    return steps


def _gen_walk_circle(
    cue: str, pose: tuple[float, float, float], safety: dict[str, float],
) -> list[PlanStep]:
    """8-step circle: each step advances forward + turns 45° = 360° total arc."""
    lin = float(safety.get("max_linear_speed", DEFAULT_SAFETY["max_linear_speed"]))
    ang = float(safety.get("max_angular_speed", DEFAULT_SAFETY["max_angular_speed"]))
    n = 8
    per_theta = (2 * math.pi) / n  # 0.785 rad = 45°
    per_dx = min(lin, 0.15)  # keep radius small

    # Clamp angular if needed
    if abs(per_theta) > ang:
        n = math.ceil(2 * math.pi / ang)
        per_theta = (2 * math.pi) / n
        per_dx = min(lin, 0.15)

    steps: list[PlanStep] = []
    for i in range(n):
        steps.append(PlanStep(
            text=f"Circle arc [{i+1}/{n}]",
            tool={
                "name": "move",
                "args": {"dx": round(per_dx, 4), "dy": 0.0, "dtheta": round(per_theta, 6)},
                "rationale": f"arc step {i+1}/{n}",
            },
        ))
    return steps


def check_obstacle_avoidance(
    observation: dict[str, Any],
    pose: tuple[float, float, float],
    safety: dict[str, float],
) -> list[PlanStep] | None:
    """Check if the observation reports an obstacle ahead and generate avoidance steps.

    Returns a list of PlanStep if avoidance is needed, else None.
    Called by the runner AFTER each VLM observation, BEFORE the planner.
    Works identically whether the observation came from MockVLM or a real VLM.
    """
    objects = observation.get("objects") or []
    ahead_obstacles = [
        o for o in objects
        if o.get("label") == "obstacle"
        and "ahead" in (o.get("rough_position") or "")
        and float(o.get("confidence", 0)) > 0.4
    ]
    if not ahead_obstacles:
        return None
    # Pick the nearest ahead obstacle.
    nearest = ahead_obstacles[0]
    pos = nearest.get("rough_position", "ahead")
    lin = float(safety.get("max_linear_speed", DEFAULT_SAFETY["max_linear_speed"]))
    # Dodge magnitude from calibration (so different robots size correctly);
    # still capped at max_linear_speed so safety wins.
    cal = safety.get("_calibration") or {}
    dodge = min(lin, float(cal.get("reactive_dodge_m", 0.2)))
    advance = min(lin, float(cal.get("reactive_advance_m", 0.25)))
    # direction: +dy = left, -dy = right. If obstacle is ahead-left, dodge right.
    dy_sign = -1.0 if "left" in pos else +1.0
    return [
        PlanStep(
            text=f"Sidestep {'right' if dy_sign < 0 else 'left'} to dodge obstacle",
            tool={"name": "move", "args": {"dx": 0.0, "dy": round(dy_sign * dodge, 4), "dtheta": 0.0},
                  "rationale": "lateral dodge"},
        ),
        PlanStep(
            text="Advance past obstacle",
            tool={"name": "move", "args": {"dx": round(advance, 4), "dy": 0.0, "dtheta": 0.0},
                  "rationale": "clear obstacle"},
        ),
    ]


def inject_avoidance(
    plan_memory: Any,
    avoidance_steps: list[PlanStep],
    robot_pose: tuple[float, float, float] | None = None,
    world_objects: dict[str, Any] | None = None,
    safety: dict[str, float] | None = None,
) -> Any:
    """Prepend avoidance steps into the current plan.

    If plan_memory is None, creates a temporary plan from avoidance_steps alone.
    If plan_memory is active, inserts avoidance steps then recomputes remaining
    navigation steps toward the original target (if navigating).
    """
    from hack.agent.plan_memory import PlanMemory

    if plan_memory is None:
        return PlanMemory(
            cue="obstacle-avoidance",
            steps=avoidance_steps,
            origin=robot_pose[:2] if robot_pose else (0.0, 0.0),
            meta={"auto_injected": True},
        )
    # Preserve the ORIGINAL cue so re-convergence works on subsequent dodges.
    cue = plan_memory.meta.get("original_cue") or plan_memory.cue or ""
    recomputed: list[PlanStep] = []
    if robot_pose and world_objects and safety and _is_navigate_to_target(cue.lower()):
        # Simulate post-avoidance pose: apply each avoidance step to the current pose.
        sim_x, sim_y, sim_th = robot_pose
        for s in avoidance_steps:
            if s.tool and s.tool.get("name") == "move":
                a = s.tool.get("args", {})
                dx = float(a.get("dx", 0))
                dy = float(a.get("dy", 0))
                dt = float(a.get("dtheta", 0))
                sim_x += dx * math.cos(sim_th) - dy * math.sin(sim_th)
                sim_y += dx * math.sin(sim_th) + dy * math.cos(sim_th)
                sim_th += dt
        # Generate fresh steps from the simulated post-dodge pose.
        # Merge world_objects into safety so the generator can find the goal.
        merged = dict(safety or {})
        merged["_world_objects"] = world_objects
        recomputed = _gen_navigate_to_target(cue, (sim_x, sim_y, sim_th), merged)
    if not recomputed:
        # Fallback: keep remaining steps from the old plan.
        recomputed = plan_memory.steps[plan_memory.step_index:]
    new_steps = avoidance_steps + recomputed
    plan_memory.steps = new_steps
    plan_memory.step_index = 0
    plan_memory.step_retries = 0
    plan_memory.meta["original_cue"] = cue
    plan_memory.cue = cue  # keep the original cue, not "obstacle-avoidance"
    return plan_memory


def _gen_navigate_to_target(
    cue: str, pose: tuple[float, float, float], safety: dict[str, float],
) -> list[PlanStep]:
    """Navigate to a named world object (goal, bin, cube, etc.).

    When obstacles are present in ``safety["_world_objects"]`` the plan is
    computed by grid A* so it routes around them. Otherwise we fall back to
    the simple body-frame / forward-walk straight-line generators.
    """
    world_objects = safety.get("_world_objects") or {}
    # Find the target object by matching cue keywords. Prefer containers /
    # marked targets first (usually named "goal" / "bin") so a wall cell whose
    # name happens to share a letter with the cue doesn't hijack navigation.
    c = cue.lower()
    target = None
    # 1. Exact-name match over containers and marked targets.
    for obj in world_objects.values():
        nm = obj.name.lower()
        if (getattr(obj, "is_container", False) or getattr(obj, "is_target", False)) \
                and nm in c:
            target = obj
            break
    # 2. Token match (>=3-char words only) over containers/targets.
    if target is None:
        for obj in world_objects.values():
            if not (getattr(obj, "is_container", False) or getattr(obj, "is_target", False)):
                continue
            tokens = [t for t in obj.name.lower().split("_") if len(t) >= 3]
            if any(t in c for t in tokens):
                target = obj
                break
    # 3. Last resort — take any container we find.
    if target is None:
        for obj in world_objects.values():
            if getattr(obj, "is_container", False):
                target = obj
                break
    if target is None:
        return []  # can't find target; fall through to LLM
    tx, ty = target.x, target.y
    x, y, th = pose
    dist = math.hypot(tx - x, ty - y)
    if dist < 0.05:
        return [PlanStep(text="Already at target.", tool={"name": "wait", "args": {"seconds": 0.5}, "rationale": "already there"})]
    lin = float(safety.get("max_linear_speed", DEFAULT_SAFETY["max_linear_speed"]))
    ang = float(safety.get("max_angular_speed", DEFAULT_SAFETY["max_angular_speed"]))
    prefer_fwd = bool(safety.get("prefer_forward_walk", False))

    # If there are obstacles in the world, plan a polyline around them via A*.
    cal = safety.get("_calibration") or {}
    robot_radius = float(cal.get("robot_radius", 0.08))
    extra_clearance = float(cal.get("extra_clearance", 0.03))
    cell_size = float(cal.get("planner_cell_size", 0.05))
    obstacles = [o for o in world_objects.values()
                 if getattr(o, "is_obstacle", False)]
    waypoints: list[tuple[float, float]] = []
    if obstacles:
        from hack.agent.path_planner import find_path
        waypoints = find_path(
            (x, y), (tx, ty), obstacles,
            robot_radius=robot_radius,
            extra_clearance=extra_clearance,
            cell_size=cell_size,
        )
    if waypoints and len(waypoints) >= 2:
        steps = _plan_along_waypoints(waypoints, pose, lin, ang, prefer_fwd)
        # Flag these steps so the runner knows they already avoid obstacles
        # and can skip reactive sidestep injection.
        for s in steps:
            if s.tool is not None:
                s.tool.setdefault("meta", {})
                s.tool["meta"]["from_astar"] = True
        return steps

    # No obstacles (or planner failed) — straight-line fall-through.
    if prefer_fwd:
        return _navigate_forward_walk(x, y, th, tx, ty, dist, lin, ang)
    cos_t, sin_t = math.cos(th), math.sin(th)
    body_dx = (tx - x) * cos_t + (ty - y) * sin_t
    body_dy = -(tx - x) * sin_t + (ty - y) * cos_t
    n = max(1, math.ceil(max(abs(body_dx), abs(body_dy)) / lin))
    steps: list[PlanStep] = []
    for i in range(n):
        steps.append(PlanStep(
            text=f"Navigate to target [{i+1}/{n}]",
            tool={"name": "move", "args": {"dx": round(body_dx / n, 4), "dy": round(body_dy / n, 4), "dtheta": 0.0},
                  "rationale": f"step {i+1}/{n} toward target"},
        ))
    return steps


def _plan_along_waypoints(
    waypoints: list[tuple[float, float]],
    pose: tuple[float, float, float],
    lin: float, ang: float, prefer_fwd: bool,
) -> list[PlanStep]:
    """Turn a polyline into a sequence of PlanStep move calls.

    ``prefer_fwd`` — real-robot style: turn to face each waypoint, walk forward.
    Otherwise emit body-frame (dx,dy) steps suitable for the sim / omni mock.
    """
    steps: list[PlanStep] = []
    x, y, th = pose
    for idx, (wx, wy) in enumerate(waypoints[1:], start=1):
        seg_dx, seg_dy = wx - x, wy - y
        seg_len = math.hypot(seg_dx, seg_dy)
        if seg_len < 1e-4:
            continue
        if prefer_fwd:
            target_angle = math.atan2(seg_dy, seg_dx)
            turn_needed = (target_angle - th + math.pi) % (2 * math.pi) - math.pi
            if abs(turn_needed) > 0.05:
                n_turn = max(1, math.ceil(abs(turn_needed) / ang))
                per_turn = turn_needed / n_turn
                for i in range(n_turn):
                    steps.append(PlanStep(
                        text=f"Turn toward wp {idx} [{i+1}/{n_turn}]",
                        tool={"name": "move", "args": {"dx": 0.0, "dy": 0.0, "dtheta": round(per_turn, 6)},
                              "rationale": f"face wp{idx}"},
                    ))
                th = target_angle
            n_walk = max(1, math.ceil(seg_len / lin))
            per_walk = seg_len / n_walk
            for i in range(n_walk):
                steps.append(PlanStep(
                    text=f"Walk to wp {idx} [{i+1}/{n_walk}]",
                    tool={"name": "move", "args": {"dx": round(per_walk, 4), "dy": 0.0, "dtheta": 0.0},
                          "rationale": f"walk wp{idx}"},
                ))
            x, y = wx, wy
        else:
            # Body-frame step. For omnidirectional sim: split into chunks of lin.
            cos_t, sin_t = math.cos(th), math.sin(th)
            bdx = seg_dx * cos_t + seg_dy * sin_t
            bdy = -seg_dx * sin_t + seg_dy * cos_t
            n = max(1, math.ceil(max(abs(bdx), abs(bdy)) / lin))
            for i in range(n):
                steps.append(PlanStep(
                    text=f"Path wp {idx} [{i+1}/{n}]",
                    tool={"name": "move",
                          "args": {"dx": round(bdx / n, 4), "dy": round(bdy / n, 4), "dtheta": 0.0},
                          "rationale": f"waypoint {idx}"},
                ))
            x, y = wx, wy
    return steps


def _navigate_forward_walk(
    x: float, y: float, th: float, tx: float, ty: float,
    dist: float, lin: float, ang: float,
) -> list[PlanStep]:
    """Turn toward target → walk forward → no heading restore (we want to face the target)."""
    steps: list[PlanStep] = []
    target_angle = math.atan2(ty - y, tx - x)
    turn_needed = (target_angle - th + math.pi) % (2 * math.pi) - math.pi
    if abs(turn_needed) > 0.05:
        n_turn = max(1, math.ceil(abs(turn_needed) / ang))
        per_turn = turn_needed / n_turn
        for i in range(n_turn):
            steps.append(PlanStep(
                text=f"Turn toward target [{i+1}/{n_turn}]",
                tool={"name": "move", "args": {"dx": 0.0, "dy": 0.0, "dtheta": round(per_turn, 6)},
                      "rationale": f"face target step {i+1}/{n_turn}"},
            ))
    n_walk = max(1, math.ceil(dist / lin))
    per_walk = dist / n_walk
    for i in range(n_walk):
        steps.append(PlanStep(
            text=f"Walk to target [{i+1}/{n_walk}]",
            tool={"name": "move", "args": {"dx": round(per_walk, 4), "dy": 0.0, "dtheta": 0.0},
                  "rationale": f"forward step {i+1}/{n_walk}"},
        ))
    return steps


def _gen_personality_intro(
    cue: str,
    pose: tuple[float, float, float],
    safety: dict[str, float],
) -> list[PlanStep]:
    """Theatrical opener: anchor origin, wave, speak team name, nod.

    Used as the first cue of the judged demo so the audience hears a
    person-shaped intro before any task logic. No motion budget consumed —
    only `remember`, `emote`, `speak` tools.
    """
    return [
        PlanStep(
            text="remember starting pose as origin",
            tool={
                "name": "remember",
                "args": {"key": "origin", "value": "current_pose"},
                "rationale": "anchor return target",
            },
        ),
        PlanStep(
            text="wave to the audience",
            tool={
                "name": "emote",
                "args": {"label": "wave"},
                "rationale": "greeting gesture",
            },
        ),
        PlanStep(
            text="introduce the team",
            tool={
                "name": "speak",
                "args": {
                    "text": "Hi, I'm a robot agent. I'm here with team Just Build at the DIS hackathon.",
                },
                "rationale": "verbal team intro",
            },
        ),
        PlanStep(
            text="acknowledge with a nod",
            tool={
                "name": "emote",
                "args": {"label": "nod"},
                "rationale": "punctuation gesture",
            },
        ),
    ]


_GENERATORS: dict[str, Any] = {
    "return_to_origin": _gen_return_to_origin,
    "rotate_degrees": _gen_rotate_degrees,
    "single_move": _gen_single_move,
    "numbered_walk": _gen_numbered_walk,
    "walk_circle": _gen_walk_circle,
    "navigate_to_target": _gen_navigate_to_target,
    "personality_intro": _gen_personality_intro,
}


def split_compound_cue(
    cue: str,
    pose: tuple[float, float, float],
    safety: dict[str, float],
    calibration: dict[str, float] | None = None,
    world_objects: dict[str, Any] | None = None,
) -> list[PlanStep] | None:
    """Split a compound cue on commas / 'then' / 'and then' and handle each
    sub-cue deterministically. Returns None if any sub-cue can't be handled
    (caller should fall through to LLM decomposer).
    """
    c = cue.strip()
    # Split on commas, ' then ', ' and then '.
    parts = re.split(r"\s*,\s*|\s+and then\s+|\s+then\s+", c)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 2:
        return None

    all_steps: list[PlanStep] = []
    sim_x, sim_y, sim_th = pose
    for part in parts:
        case = classify_cue(part)
        if case is None:
            return None  # can't handle this sub-cue deterministically
        steps = generate_plan(case, part, (sim_x, sim_y, sim_th), safety, calibration, world_objects)
        if not steps:
            return None
        # Simulate the effect of these steps on the pose for subsequent sub-cues.
        for s in steps:
            if s.tool and s.tool.get("name") == "move":
                a = s.tool.get("args", {})
                dx = float(a.get("dx", 0))
                dy = float(a.get("dy", 0))
                dt = float(a.get("dtheta", 0))
                sim_x += dx * math.cos(sim_th) - dy * math.sin(sim_th)
                sim_y += dx * math.sin(sim_th) + dy * math.cos(sim_th)
                sim_th += dt
        all_steps.extend(steps)
    return all_steps
