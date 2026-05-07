"""End-to-end motion tests — voice cue → rehearsal runner → final pose assertion.

Each test registers a temporary scenario with scripted voice cues and a custom
evaluator that checks the robot's final pose. The full rehearsal pipeline runs:
  voice cue → classify_cue_smart → compound split / LLM decompose →
  plan installation → step execution on VirtualWorldRobot → evaluator.

No LLM calls for deterministic cues — the classifier routes them to
precomputed plans. Tests that exercise LLM paths are in test_regression.
"""

from __future__ import annotations

import asyncio
import math
import tempfile
from collections import Counter
from pathlib import Path

import pytest
import yaml

from hack.rehearsal.runner import rehearse
from hack.rehearsal.scenarios import (
    SCENARIOS,
    generate_labyrinth_scenario,
    generate_random_obstacle_scenario,
)
from hack.rehearsal.virtual_world import Scenario, VirtualWorldRobot, VoiceCue, WorldObject

# ---- Config -----------------------------------------------------------------

# Read safety limits from the main config so tests stay in sync.
_MAIN_CFG = yaml.safe_load(Path("configs/agent.yaml").read_text())
_SAFETY = _MAIN_CFG.get("robot", {}).get("safety", {})
LIN = float(_SAFETY.get("max_linear_speed", 0.2))  # step size in metres
ANG = float(_SAFETY.get("max_angular_speed", 0.6))  # step size in radians

# Minimal config — mock VLM (no API calls), deterministic cues bypass LLM entirely.
_MINIMAL_CONFIG = {
    "llm": {
        "provider": "ollama",
        "model": "qwen2.5:7b",
        "base_url": "http://127.0.0.1:11434",
    },
    "vlm": {
        "provider": "mock",
        "model": "mock",
        "base_url": "http://127.0.0.1:11434",
    },
    "agent": {
        "system_prompt": "You are a robot assistant.",
        "observation_prompt": "Describe what you see.",
        "max_tool_calls_per_turn": 4,
    },
    "robot": {
        "safety": {
            "max_linear_speed": LIN,
            "max_angular_speed": ANG,
        },
    },
}


def _write_config(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "agent.yaml"
    cfg_path.write_text(yaml.dump(_MINIMAL_CONFIG))
    return cfg_path


# ---- Pose evaluator factory --------------------------------------------------

def _pose_evaluator(
    expected_x: float,
    expected_y: float,
    tol_pos: float = 0.1,
    expected_heading_deg: float | None = None,
    tol_deg: float = 15.0,
    check_collisions: bool = True,
):
    """Return an evaluator function that checks final pose."""

    def evaluate(robot: VirtualWorldRobot, tool_calls: Counter) -> tuple[bool, str]:
        rx, ry, rth = robot.pose
        dist = math.hypot(rx - expected_x, ry - expected_y)
        if dist > tol_pos:
            return False, (
                f"position ({rx:.3f},{ry:.3f}) too far from "
                f"expected ({expected_x:.3f},{expected_y:.3f}), dist={dist:.4f}"
            )
        if check_collisions and robot.collision_events:
            return False, f"{len(robot.collision_events)} collision(s)"
        if expected_heading_deg is not None:
            angle_err = abs(((math.degrees(rth) - expected_heading_deg + 180) % 360) - 180)
            if angle_err > tol_deg:
                return False, (
                    f"heading {math.degrees(rth):.1f}° too far from "
                    f"expected {expected_heading_deg:.1f}°, error={angle_err:.1f}°"
                )
        return True, f"pose ok: ({rx:.3f},{ry:.3f}) heading={math.degrees(rth):.0f}°"

    return evaluate


# ---- Scenario builders -------------------------------------------------------

def _motion_scenario(
    name: str,
    cue: str,
    expected_x: float,
    expected_y: float,
    tol_pos: float = 0.1,
    expected_heading_deg: float | None = None,
    tol_deg: float = 15.0,
    max_ticks: int = 80,
    objects: list[WorldObject] | None = None,
    check_collisions: bool = True,
) -> Scenario:
    return Scenario(
        name=name,
        description=f"motion test: {cue}",
        objects=objects or [],
        cues=[VoiceCue(at_tick=1, text=cue)],
        max_ticks=max_ticks,
        world_radius=50.0,  # large enough for any step count
        evaluate=_pose_evaluator(
            expected_x, expected_y, tol_pos,
            expected_heading_deg, tol_deg, check_collisions,
        ),
    )


# ---- Test runner helper -------------------------------------------------------

def _run_motion_test(scenario: Scenario):
    """Register scenario, run rehearsal, assert success."""

    async def go():
        # Register scenario temporarily.
        SCENARIOS[scenario.name] = scenario
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                cfg_path = _write_config(tmp_path)
                runs_dir = tmp_path / "runs"
                metrics = await rehearse(
                    scenario_name=scenario.name,
                    config_path=cfg_path,
                    runs_dir=runs_dir,
                    display=False,
                    delay=0.0,
                )
                assert metrics.success, (
                    f"scenario '{scenario.name}' failed: {metrics.success_reason}"
                )
        finally:
            SCENARIOS.pop(scenario.name, None)

    asyncio.run(go())


# ---- Tests: basic moves -------------------------------------------------------

class TestBasicMovesE2E:
    """Single-step motions through the full pipeline."""

    def test_forward(self):
        _run_motion_test(_motion_scenario(
            "e2e-forward", "move forward",
            expected_x=LIN, expected_y=0.0, tol_pos=0.05,
            expected_heading_deg=0.0,
        ))

    def test_backward(self):
        _run_motion_test(_motion_scenario(
            "e2e-backward", "step back",
            expected_x=-LIN, expected_y=0.0, tol_pos=0.05,
            expected_heading_deg=0.0,
        ))

    def test_step_left(self):
        _run_motion_test(_motion_scenario(
            "e2e-step-left", "step left",
            expected_x=0.0, expected_y=LIN, tol_pos=0.05,
            expected_heading_deg=0.0,
        ))

    def test_step_right(self):
        _run_motion_test(_motion_scenario(
            "e2e-step-right", "step right",
            expected_x=0.0, expected_y=-LIN, tol_pos=0.05,
            expected_heading_deg=0.0,
        ))


# ---- Tests: numbered walks ---------------------------------------------------

class TestNumberedWalksE2E:

    def test_10_steps_forward(self):
        _run_motion_test(_motion_scenario(
            "e2e-10-fwd", "10 steps forward",
            expected_x=10 * LIN, expected_y=0.0, tol_pos=0.1,
            expected_heading_deg=0.0,
        ))

    def test_5_steps_left(self):
        _run_motion_test(_motion_scenario(
            "e2e-5-left", "5 steps left",
            expected_x=0.0, expected_y=5 * LIN, tol_pos=0.2,
            expected_heading_deg=90.0,
        ))

    def test_3_steps_right(self):
        _run_motion_test(_motion_scenario(
            "e2e-3-right", "3 steps right",
            expected_x=0.0, expected_y=-3 * LIN, tol_pos=0.2,
            expected_heading_deg=-90.0,
        ))


# ---- Tests: rotations --------------------------------------------------------

class TestRotationsE2E:

    def test_turn_left_90(self):
        _run_motion_test(_motion_scenario(
            "e2e-turn-left-90", "turn left 90 degrees",
            expected_x=0.0, expected_y=0.0, tol_pos=0.01,
            expected_heading_deg=90.0,
        ))

    def test_turn_right_90(self):
        _run_motion_test(_motion_scenario(
            "e2e-turn-right-90", "turn right 90 degrees",
            expected_x=0.0, expected_y=0.0, tol_pos=0.01,
            expected_heading_deg=-90.0,
        ))

    def test_spin_360(self):
        _run_motion_test(_motion_scenario(
            "e2e-spin-360", "spin 360 degrees",
            expected_x=0.0, expected_y=0.0, tol_pos=0.01,
            expected_heading_deg=0.0, tol_deg=15.0,
        ))


# ---- Tests: compound squares -------------------------------------------------

class TestCompoundSquareE2E:
    """All squares/polygons return to origin — independent of step size."""

    def test_square_ccw_returns_to_start(self):
        _run_motion_test(_motion_scenario(
            "e2e-square-ccw",
            "4 steps forward, 4 steps left, 4 steps left, 4 steps left",
            expected_x=0.0, expected_y=0.0, tol_pos=0.1,
            max_ticks=60,
        ))

    def test_square_cw_returns_to_start(self):
        _run_motion_test(_motion_scenario(
            "e2e-square-cw",
            "4 steps forward, 4 steps right, 4 steps right, 4 steps right",
            expected_x=0.0, expected_y=0.0, tol_pos=0.1,
            max_ticks=60,
        ))

    def test_forward_and_back(self):
        _run_motion_test(_motion_scenario(
            "e2e-fwd-back",
            "5 steps forward, 5 steps back",
            expected_x=0.0, expected_y=0.0, tol_pos=0.2,
            expected_heading_deg=180.0, tol_deg=15.0,
            max_ticks=40,
        ))

    def test_triangle(self):
        _run_motion_test(_motion_scenario(
            "e2e-triangle",
            "4 steps forward, turn left 120, 4 steps forward, turn left 120, 4 steps forward",
            expected_x=0.0, expected_y=0.0, tol_pos=0.2,
            max_ticks=50,
        ))

    def test_big_square(self):
        """The original user cue that exposed the bug."""
        _run_motion_test(_motion_scenario(
            "e2e-big-square",
            "walk 10 steps forward, 10 steps left, 10 steps left, 10 steps left",
            expected_x=0.0, expected_y=0.0, tol_pos=0.2,
            max_ticks=80,
        ))


# ---- Tests: return to origin -------------------------------------------------

class TestReturnToOriginE2E:

    def test_return_after_walk(self):
        """Walk forward then return — two separate cues via scripted sequence."""

        async def go():
            sc = Scenario(
                name="e2e-return",
                description="walk then return",
                objects=[],
                cues=[
                    VoiceCue(at_tick=1, text="3 steps forward"),
                    VoiceCue(at_tick=15, text="go back to start"),
                ],
                max_ticks=40,
                world_radius=50.0,
                evaluate=_pose_evaluator(0.0, 0.0, tol_pos=0.2),
            )
            SCENARIOS[sc.name] = sc
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    tmp_path = Path(tmp)
                    cfg_path = _write_config(tmp_path)
                    metrics = await rehearse(
                        scenario_name=sc.name,
                        config_path=cfg_path,
                        runs_dir=tmp_path / "runs",
                        display=False,
                    )
                    assert metrics.success, f"failed: {metrics.success_reason}"
            finally:
                SCENARIOS.pop(sc.name, None)

        asyncio.run(go())


# ---- Tests: circle ------------------------------------------------------------

class TestCircleE2E:

    def test_circle_returns_near_start(self):
        _run_motion_test(_motion_scenario(
            "e2e-circle", "walk a circle",
            expected_x=0.0, expected_y=0.0, tol_pos=0.4,
            max_ticks=20,
        ))


# ---- Tests: collisions -------------------------------------------------------

class TestCollisionsE2E:

    def test_walk_into_obstacle(self):
        """Walking into an obstacle should fail the collision check."""
        sc = _motion_scenario(
            "e2e-collision",
            "10 steps forward",
            expected_x=10 * LIN, expected_y=0.0, tol_pos=1.0,
            check_collisions=True,
            objects=[
                WorldObject("wall", "red", x=2.0, y=0.0, is_obstacle=True, radius=0.3),
            ],
        )
        with pytest.raises(AssertionError, match="collision"):
            _run_motion_test(sc)


# ---- Tests: random obstacle courses ------------------------------------------

class TestRandomObstaclesE2E:
    """Run the agent through randomly generated obstacle fields.

    Each test uses a fixed seed for reproducibility. The evaluator checks:
    - Reached the goal
    - Zero collisions
    - Reports efficiency (path_length / optimal_length)
    """

    @pytest.mark.parametrize("seed", range(10))
    def test_random_sparse(self, seed):
        """Sparse random obstacles — mostly clear paths."""

        async def go():
            sc = generate_random_obstacle_scenario(
                seed=seed,
                n_obstacles=5,
                world_radius=3.0,
                goal_distance_range=(1.5, 3.0),
                max_ticks=150,
            )
            SCENARIOS[sc.name] = sc
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    tmp_path = Path(tmp)
                    cfg_path = _write_config(tmp_path)
                    metrics = await rehearse(
                        scenario_name=sc.name,
                        config_path=cfg_path,
                        runs_dir=tmp_path / "runs",
                        display=False,
                        delay=0.0,
                    )
                    # Print efficiency stats for visibility.
                    print(f"\n  seed={seed}: {metrics.success_reason}")
                    assert metrics.success, (
                        f"seed={seed} failed: {metrics.success_reason}"
                    )
            finally:
                SCENARIOS.pop(sc.name, None)

        asyncio.run(go())

    @pytest.mark.parametrize("seed", range(10))
    def test_random_dense(self, seed):
        """Dense random obstacles — stress test. Reports efficiency, soft-fails."""

        async def go():
            sc = generate_random_obstacle_scenario(
                seed=100 + seed,
                n_obstacles=12,
                world_radius=2.0,
                obstacle_radius_range=(0.1, 0.25),
                goal_distance_range=(1.5, 2.5),
                min_clearance=0.2,
                max_ticks=200,
            )
            SCENARIOS[sc.name] = sc
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    tmp_path = Path(tmp)
                    cfg_path = _write_config(tmp_path)
                    metrics = await rehearse(
                        scenario_name=sc.name,
                        config_path=cfg_path,
                        runs_dir=tmp_path / "runs",
                        display=False,
                        delay=0.0,
                    )
                    print(f"\n  seed={100+seed}: {metrics.success_reason}")
                    assert metrics.success, (
                        f"seed={100+seed} failed: {metrics.success_reason}"
                    )
            finally:
                SCENARIOS.pop(sc.name, None)

        asyncio.run(go())


# ---- Tests: labyrinth ---------------------------------------------------------

class TestLabyrinthE2E:
    """Random maze navigation — robot must find path to goal."""

    @pytest.mark.parametrize("seed", range(5))
    def test_labyrinth_3x3(self, seed):
        """Small 3×3 labyrinth."""

        async def go():
            sc = generate_labyrinth_scenario(
                seed=seed, rows=3, cols=3, max_ticks=200,
            )
            SCENARIOS[sc.name] = sc
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    tmp_path = Path(tmp)
                    cfg_path = _write_config(tmp_path)
                    metrics = await rehearse(
                        scenario_name=sc.name,
                        config_path=cfg_path,
                        runs_dir=tmp_path / "runs",
                        display=False,
                        delay=0.0,
                    )
                    print(f"\n  labyrinth 3x3 seed={seed}: {metrics.success_reason}")
                    assert metrics.success, (
                        f"labyrinth 3x3 seed={seed} failed: {metrics.success_reason}"
                    )
            finally:
                SCENARIOS.pop(sc.name, None)

        asyncio.run(go())

    @pytest.mark.parametrize("seed", range(5))
    def test_labyrinth_5x5(self, seed):
        """Medium 5×5 labyrinth."""

        async def go():
            sc = generate_labyrinth_scenario(
                seed=50 + seed, rows=5, cols=5, max_ticks=400,
            )
            SCENARIOS[sc.name] = sc
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    tmp_path = Path(tmp)
                    cfg_path = _write_config(tmp_path)
                    metrics = await rehearse(
                        scenario_name=sc.name,
                        config_path=cfg_path,
                        runs_dir=tmp_path / "runs",
                        display=False,
                        delay=0.0,
                    )
                    print(f"\n  labyrinth 5x5 seed={50+seed}: {metrics.success_reason}")
                    assert metrics.success, (
                        f"labyrinth 5x5 seed={50+seed} failed: {metrics.success_reason}"
                    )
            finally:
                SCENARIOS.pop(sc.name, None)

        asyncio.run(go())
