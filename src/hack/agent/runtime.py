from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from hack.agent.logger import JsonlLogger
from hack.agent.planner import OllamaPlanner, PlannerInput
from hack.agent.tools import ToolBox
from hack.robot import make as make_robot
from hack.sensors.camera import Camera
from hack.sensors.vlm import VLMClient


def _load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


async def run(
    robot_name: str,
    config_path: Path,
    trace_out: Path | None = None,
    video_out: Path | None = None,
) -> None:
    cfg = _load_config(config_path)
    trace = trace_out or Path(f"runs/{int(time.time())}.jsonl")
    log = JsonlLogger(trace)
    log.log("start", config=cfg, robot=robot_name)

    planner = OllamaPlanner(
        model=cfg["llm"]["model"],
        base_url=cfg["llm"]["base_url"],
        system_prompt=cfg["agent"]["system_prompt"],
        temperature=cfg["llm"].get("temperature", 0.3),
        max_tool_calls=cfg["agent"].get("max_tool_calls_per_turn", 4),
    )
    vlm = VLMClient(
        model=cfg["vlm"]["model"],
        base_url=cfg["vlm"]["base_url"],
        prompt=cfg["agent"]["observation_prompt"],
    )
    cam = Camera(fps=cfg["vlm"].get("frame_fps", 2.0), downscale_to=cfg["vlm"].get("downscale_to", 768))

    transcript: list[str] = []

    async with make_robot(robot_name) as robot, cam as camera:
        tools = ToolBox(robot=robot)
        try:
            async for frame in camera.frames():
                obs = await vlm.observe(frame.image)
                state = await robot.get_state()
                inp = PlannerInput(
                    observation=obs.model_dump(),
                    transcript=transcript,
                    robot_state=state.model_dump(),
                    memory=tools.memory,
                )
                log.log("observation", seq=frame.seq, observation=obs.model_dump(), state=state.model_dump())
                plan = await planner.plan(inp)
                log.log("plan", calls=[c.model_dump() for c in plan.calls], note=plan.note)
                for tc in plan.calls[: planner.max_tool_calls]:
                    res = await tools.call(tc)
                    log.log("action", call=tc.model_dump(), result=res.model_dump())
        except KeyboardInterrupt:
            pass
        finally:
            log.log("stop")
            log.close()


async def replay(trace: Path, config_path: Path) -> None:
    cfg = _load_config(config_path)
    out = trace.with_suffix(".replay.jsonl")
    log = JsonlLogger(out)
    planner = OllamaPlanner(
        model=cfg["llm"]["model"],
        base_url=cfg["llm"]["base_url"],
        system_prompt=cfg["agent"]["system_prompt"],
        temperature=cfg["llm"].get("temperature", 0.3),
    )
    for line in trace.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("kind") != "observation":
            continue
        plan = await planner.plan(PlannerInput(observation=rec["observation"], robot_state=rec.get("state", {})))
        log.log("plan", original_seq=rec.get("seq"), calls=[c.model_dump() for c in plan.calls], note=plan.note)
        # synthesize an "action" from the first call so `hack agent diff` works uniformly
        if plan.calls:
            log.log("action", call=plan.calls[0].model_dump())
    log.close()
    print(f"wrote {out}")
