"""End-to-end obstacle-scenario tests — drive the pre-baked scenarios through
the full rehearse() pipeline and assert the robot reaches the goal.

These tests use the MockVLM-backed virtual world (forced when adapter=virtual)
and exercise the grid A* planner in deterministic_plans.py. Each test asserts
success; any failure is surfaced directly (no pytest.xfail masking).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
import yaml

from hack.rehearsal.runner import rehearse
from hack.rehearsal.scenarios import SCENARIOS  # noqa: F401 — ensures registrations run

# Minimal rehearse() config — MockVLM is forced by the runner for adapter=virtual,
# so the VLM block values don't matter operationally.
_MIN_CFG = {
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
        "system_prompt": "You are a robot agent.",
        "observation_prompt": "List what you see.",
        "max_tool_calls_per_turn": 4,
    },
    "robot": {
        "safety": {"max_linear_speed": 0.9, "max_angular_speed": 1.8},
        "calibration": {"linear_scale": 1.0, "angular_scale": 1.0, "prefer_forward_walk": True},
    },
}


def _run_scenario(name: str):
    async def go():
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg_path = tmp_path / "agent.yaml"
            cfg_path.write_text(yaml.dump(_MIN_CFG))
            metrics = await rehearse(
                scenario_name=name,
                config_path=cfg_path,
                runs_dir=tmp_path / "runs",
                display=False,
                delay=0.0,
            )
            assert metrics.success, f"{name}: {metrics.success_reason}"
            return metrics

    return asyncio.run(go())


@pytest.mark.parametrize("scenario", [
    "obstacle-course",
    "obstacle-hard",
    "obstacle-wall",
    "obstacle-corridor",
    "obstacle-horseshoe",
])
def test_obstacle_scenario_reaches_goal(scenario):
    """Every curated obstacle scenario must reach the goal without collisions
    and within its per-scenario min_efficiency threshold."""
    metrics = _run_scenario(scenario)
    # Sanity: something must have moved.
    assert metrics.tool_calls.get("move", 0) >= 1, (
        f"{scenario}: no move tool calls emitted"
    )
