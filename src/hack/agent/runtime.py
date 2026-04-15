from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from hack.agent.logger import JsonlLogger
from hack.agent.plan_memory import (
    PlanMemory,
    clamp_call,
    decompose,
    expand_plan_steps,
    plan_hint,
    required_tools_for_step,
    validate_call_against_step,
)
from hack.agent.planner import OllamaPlanner, PlannerInput
from hack.agent.tools import ToolBox, ToolCall
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
    live_cues_path: Path = Path("runs/live_cues.ndjson"),
) -> None:
    """Day-of agent loop.

    Strictly voice-driven: the agent emits no tool calls unless a plan step is
    active. Plans are installed by `hack.agent.plan_memory.decompose()` when a
    new live cue arrives via `runs/live_cues.ndjson`. No fallback behaviour.
    """
    cfg = _load_config(config_path)
    trace = trace_out or Path(f"runs/{int(time.time())}.jsonl")
    log = JsonlLogger(trace)
    log.log("start", config=cfg, robot=robot_name)

    from hack.models import make_llm as _make_llm, make_vlm as _make_vlm
    planner = OllamaPlanner(
        adapter=_make_llm(cfg["llm"]),
        system_prompt=cfg["agent"]["system_prompt"],
        max_tool_calls=cfg["agent"].get("max_tool_calls_per_turn", 4),
    )
    vlm = VLMClient(adapter=_make_vlm(cfg["vlm"], prompt=cfg["agent"]["observation_prompt"]))
    cam = Camera(fps=cfg["vlm"].get("frame_fps", 2.0), downscale_to=cfg["vlm"].get("downscale_to", 768))

    transcript: list[str] = []
    plan_memory: PlanMemory | None = None
    live_cues_cursor = live_cues_path.stat().st_size if live_cues_path.exists() else 0

    async with make_robot(robot_name) as robot, cam as camera:
        tools = ToolBox(robot=robot)
        try:
            async for frame in camera.frames():
                # DAYOF: B — if cfg["router"]["enabled"], route first and skip planner for shortcut_routes.
                # DAYOF: B — if cfg["robot"]["tracker"]["enabled"], reinit BBoxTracker from last VLM bbox.
                live_text, live_cues_cursor = _drain_live_cues(live_cues_path, live_cues_cursor)
                if live_text:
                    transcript.append(live_text)
                    log.log("live_cue", text=live_text)
                    pose = (await robot.get_state()).pose
                    steps = await decompose(live_text, planner)
                    if steps:
                        safety = cfg.get("robot", {}).get("safety", {})
                        steps = expand_plan_steps(steps, safety)
                        plan_memory = PlanMemory(cue=live_text, steps=steps, origin=(pose[0], pose[1]))
                        log.log("plan_installed", cue=live_text, steps=plan_memory.steps_to_dicts(),
                                origin=list(plan_memory.origin))
                    else:
                        log.log("alert", code="cue-decompose-failed",
                                message=f"could not decompose cue {live_text!r} — robot idle")

                if plan_memory is None or plan_memory.is_done():
                    if plan_memory is not None and plan_memory.is_done():
                        log.log("plan_complete", cue=plan_memory.cue)
                        plan_memory = None
                    log.log("idle", seq=frame.seq)
                    continue

                # Pre-baked direct-execute: skip VLM+planner for mechanical steps.
                current_step = plan_memory.current()
                if current_step is not None and current_step.tool is not None:
                    clamped, notes = clamp_call(current_step.tool, cfg.get("robot", {}).get("safety", {}))
                    if notes:
                        log.log("alert", code="safety-clamp",
                                message=f"pre-baked step clamped: {', '.join(notes)}")
                    tc = ToolCall(**clamped)
                    res = await tools.call(tc)
                    log.log("action", call=tc.model_dump(), result=res.model_dump(),
                            source="pre-baked")
                    plan_memory.advance()
                    log.log("plan_progress", step_index=plan_memory.step_index,
                            total=len(plan_memory.steps))
                    if plan_memory.is_done():
                        log.log("plan_complete", cue=plan_memory.cue)
                        plan_memory = None
                    continue

                obs = await vlm.observe(frame.image)
                state = await robot.get_state()
                state_dump = state.model_dump()
                state_dump.setdefault("extra", {})
                state_dump["extra"]["plan_origin"] = list(plan_memory.origin)
                state_dump["extra"]["plan_step"] = plan_memory.progress_text()

                hint = plan_hint(plan_memory)
                inp = PlannerInput(
                    observation=obs.model_dump(),
                    transcript=([hint] if hint else []) + transcript,
                    robot_state=state_dump,
                    memory=tools.memory,
                )
                log.log("observation", seq=frame.seq, observation=obs.model_dump(), state=state_dump)
                plan = await planner.plan(inp)
                log.log("plan", calls=[c.model_dump() for c in plan.calls], note=plan.note)

                # Step-coverage: semantic requirement + keyword/always-in + direction.
                step_obj = plan_memory.current()
                step_text = step_obj.text if step_obj else ""
                plan_blob = json.dumps([c.model_dump() for c in plan.calls]).lower() + " " + (plan.note or "").lower()
                required_tools = required_tools_for_step(step_text)
                plan_tool_names = {c.name for c in plan.calls}
                semantic_error: str | None = None
                if required_tools and not (required_tools & plan_tool_names):
                    semantic_error = (
                        f"step requires tool(s) {sorted(required_tools)} but plan used "
                        f"{sorted(plan_tool_names) or '∅'}"
                    )
                kws = [w.lower() for w in step_text.split() if len(w) > 3]
                always_in = {"move", "turn", "forward", "back", "left", "right", "speak"}
                matched = (not kws) or any(k in plan_blob for k in kws) or any(k in plan_blob for k in always_in)
                direction_error: str | None = None
                for c in plan.calls:
                    err = validate_call_against_step(step_text, c.model_dump())
                    if err:
                        direction_error = err
                        break
                if semantic_error or direction_error or not matched:
                    abandoned = plan_memory.retry()
                    if abandoned:
                        code, msg = "step-abandoned", f"abandoned step {step_text!r} after 3 retries"
                    elif semantic_error:
                        code, msg = "step-semantic-mismatch", f"{semantic_error} — suppressed"
                    elif direction_error:
                        code, msg = "step-direction-mismatch", f"{direction_error} — suppressed"
                    else:
                        code, msg = "step-not-executed", f"planner did not address step {step_text!r} (retry {plan_memory.step_retries}/3)"
                    log.log("alert", code=code, message=msg)
                    if abandoned:
                        plan_memory = None
                    continue

                safety = cfg.get("robot", {}).get("safety", {})
                for tc in plan.calls[: planner.max_tool_calls]:
                    clamped, notes = clamp_call(tc.model_dump(), safety)
                    if notes:
                        log.log("alert", code="safety-clamp",
                                message=f"planner call clamped: {', '.join(notes)}")
                        tc = ToolCall(**clamped)
                    res = await tools.call(tc)
                    log.log("action", call=tc.model_dump(), result=res.model_dump())
                plan_memory.advance()
                log.log("plan_progress", step_index=plan_memory.step_index, total=len(plan_memory.steps))
                if plan_memory.is_done():
                    log.log("plan_complete", cue=plan_memory.cue)
                    plan_memory = None
        except KeyboardInterrupt:
            pass
        finally:
            log.log("stop")
            log.close()


def _drain_live_cues(path: Path, cursor: int) -> tuple[str, int]:
    """Read new NDJSON cues since `cursor`; return concatenated text + new cursor."""
    if not path.exists():
        return "", cursor
    size = path.stat().st_size
    if size <= cursor:
        return "", size
    with path.open("rb") as f:
        f.seek(cursor)
        chunk = f.read().decode("utf-8", errors="replace")
    texts: list[str] = []
    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line).get("text", "").strip()
            if t:
                texts.append(t)
        except json.JSONDecodeError:
            continue
    return " | ".join(texts), size


async def replay(trace: Path, config_path: Path) -> None:
    cfg = _load_config(config_path)
    out = trace.with_suffix(".replay.jsonl")
    log = JsonlLogger(out)
    from hack.models import make_llm as _make_llm
    planner = OllamaPlanner(
        adapter=_make_llm(cfg["llm"]),
        system_prompt=cfg["agent"]["system_prompt"],
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
