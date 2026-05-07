"""Run every registered scenario end-to-end.

Parametrises over every key in ``SCENARIOS`` except the ones that can't be
evaluated headlessly (`dance` needs a human at the mic, `chit-chat` scores
conversational tool use via the LLM, `live` is the infinite day-of loop).

Each test calls ``rehearse()`` with the mock VLM and asserts
``metrics.success``. A failure surfaces the exact reason so the agent's
limitations stay visible in CI — no xfail masking.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
import yaml

from hack.rehearsal.runner import rehearse
from hack.rehearsal.scenarios import SCENARIOS

# Scenarios we skip because they require something the headless test loop
# can't supply (mic input, LLM-graded chit-chat, or the infinite live loop).
_SKIP = {
    "dance": "requires human mic input",
    "chit-chat": "scores LLM-generated conversational tool use",
    "live": "infinite day-of loop — no terminal state",
    "pick-and-place": "needs planner LLM for grasp/release decomposition",
}

_SCENARIOS = [s for s in sorted(SCENARIOS) if s not in _SKIP]

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
        "calibration": {
            "linear_scale": 1.0,
            "angular_scale": 1.0,
            "prefer_forward_walk": True,
            "robot_radius": 0.08,
            "extra_clearance": 0.03,
            "planner_cell_size": 0.05,
            "reactive_dodge_m": 0.2,
            "reactive_advance_m": 0.25,
        },
    },
}


@pytest.mark.parametrize("scenario", _SCENARIOS)
def test_scenario_passes(scenario):
    async def go():
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg_path = tmp_path / "agent.yaml"
            cfg_path.write_text(yaml.dump(_MIN_CFG))
            metrics = await rehearse(
                scenario_name=scenario,
                config_path=cfg_path,
                runs_dir=tmp_path / "runs",
                display=False,
                delay=0.0,
            )
            assert metrics.success, f"{scenario}: {metrics.success_reason}"

    asyncio.run(go())


@pytest.mark.parametrize("scenario", sorted(_SKIP))
def test_scenario_registered(scenario):
    """Sanity: the skipped scenarios still load. Prevents silent deletion."""
    assert scenario in SCENARIOS
