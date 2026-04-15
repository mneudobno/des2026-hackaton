"""Prebuilt scenarios for repeated rehearsal."""

from __future__ import annotations

import math
from collections import Counter

from hack.rehearsal.virtual_world import Scenario, VirtualWorldRobot, VoiceCue, WorldObject


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
        description="Follow the blue object as it moves; maintain < 0.2m distance.",
        objects=[
            WorldObject("blue_person", "blue", x=-0.5, y=0.0, is_target=True),
            WorldObject("goal", "bin", x=0.7, y=0.7, is_container=True),
        ],
        cues=[
            VoiceCue(at_tick=1, text="follow me"),
            VoiceCue(at_tick=10, text="keep close"),
        ],
        max_ticks=25,
        success_target="blue_person",
        success_container="goal",
        success_radius=0.2,
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


def load(name: str) -> Scenario:
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario {name!r}; known: {sorted(SCENARIOS)}")
    return SCENARIOS[name]
