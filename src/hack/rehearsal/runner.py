"""Rehearsal runner: executes the agent against a VirtualWorldRobot and collects metrics."""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from hack.agent.logger import JsonlLogger
from hack.observation.correctness_monitor import CorrectnessMonitor
from hack.agent.plan_memory import (
    PlanMemory,
    clamp_call,
    decompose,
    expand_plan_steps,
    plan_hint,
    required_tools_for_step,
    validate_call_against_step,
    validate_plan,
)
from hack.agent.deterministic_plans import (  # noqa: F401
    check_obstacle_avoidance,
    classify_cue_smart,
    generate_plan,
    inject_avoidance,
)
from hack.agent.planner import OllamaPlanner, PlannerInput
from hack.agent.tools import ToolBox, ToolCall
from hack.rehearsal.scenarios import load as load_scenario
from hack.rehearsal.virtual_world import VirtualWorldRobot
from hack.sensors.vlm import VLMClient


def _annotate_frame(frame: np.ndarray, tick: int, total: int, cue: str | None, tool_calls: Counter,
                    last_action: str | None, success: str | None, scenario_name: str = "") -> np.ndarray:
    """Overlay scenario status on a world-rendered frame.

    Layout:
      top bar    (44 px) — two rows:
                  row 1: tick N/M | scenario=<name>
                  row 2: tool histogram
      world      (middle)
      bottom bar (58 px) — three rows:
                  row 1: voice cue
                  row 2: last action
                  row 3: success status
    A coloured frame border pulses when a voice cue fires.
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    out = frame.copy()
    h, w = out.shape[:2]
    TOP_H, BOT_H = 44, 58

    # Voice-cue border pulse (blue)
    if cue:
        cv2.rectangle(out, (0, TOP_H), (w, h - BOT_H), (255, 160, 60), 4)

    # Top bar (two rows)
    cv2.rectangle(out, (0, 0), (w, TOP_H), (30, 30, 30), -1)
    line1 = f"tick {tick}/{total}"
    if scenario_name:
        line1 += f"  |  scenario={scenario_name}"
    cv2.putText(out, line1, (8, 17), font, 0.46, (240, 240, 240), 1, cv2.LINE_AA)
    hist = _fmt_counter(tool_calls) or "(no calls yet)"
    cv2.putText(out, hist, (8, 36), font, 0.44, (180, 255, 180), 1, cv2.LINE_AA)

    # Bottom bar (three rows)
    cv2.rectangle(out, (0, h - BOT_H), (w, h), (30, 30, 30), -1)
    cue_row_y = h - BOT_H + 17
    act_row_y = h - BOT_H + 35
    suc_row_y = h - BOT_H + 53

    if cue:
        cv2.putText(out, f'cue: "{cue[: max(1, (w - 80)//9)]}"', (8, cue_row_y),
                    font, 0.44, (180, 220, 255), 1, cv2.LINE_AA)
    else:
        cv2.putText(out, "cue: -", (8, cue_row_y), font, 0.44, (140, 140, 140), 1, cv2.LINE_AA)

    act_text = (last_action or "(awaiting planner)")[: max(1, (w - 80)//9)]
    cv2.putText(out, f"-> {act_text}", (8, act_row_y), font, 0.44, (180, 255, 180), 1, cv2.LINE_AA)

    if success:
        if success.startswith("ok"):
            color, tag = (0, 200, 0), "PASS"
        elif success.startswith("FAIL"):
            color, tag = (60, 60, 230), "FAIL"
        else:
            # mid-run "checking — …" or anything else: neutral gray.
            color, tag = (170, 170, 170), "status"
        cv2.putText(out, f"{tag}: {success[:70]}", (8, suc_row_y),
                    font, 0.44, color, 1, cv2.LINE_AA)
    else:
        cv2.putText(out, "status: running", (8, suc_row_y), font, 0.44, (170, 170, 170), 1, cv2.LINE_AA)
    return out


def _fmt_counter(c: Counter) -> str:
    if not c:
        return ""
    return "  ".join(f"{k}={v}" for k, v in sorted(c.items()))


@dataclass
class RehearsalMetrics:
    scenario: str
    ticks_run: int
    success: bool
    success_reason: str
    vlm_ms: list[float] = field(default_factory=list)
    planner_ms: list[float] = field(default_factory=list)
    tool_calls: Counter = field(default_factory=Counter)
    vlm_parse_failures: int = 0
    plan_parse_failures: int = 0

    def summary(self) -> dict[str, Any]:
        def stats(xs: list[float]) -> dict[str, float]:
            if not xs:
                return {"n": 0}
            return {
                "n": len(xs),
                "mean": statistics.mean(xs),
                "p50": statistics.median(xs),
                "p95": sorted(xs)[int(0.95 * (len(xs) - 1))],
                "max": max(xs),
            }
        return {
            "scenario": self.scenario,
            "ticks_run": self.ticks_run,
            "success": self.success,
            "success_reason": self.success_reason,
            "vlm_ms": stats(self.vlm_ms),
            "planner_ms": stats(self.planner_ms),
            "tool_calls": dict(self.tool_calls),
            "vlm_parse_failures": self.vlm_parse_failures,
            "plan_parse_failures": self.plan_parse_failures,
        }


async def rehearse(
    scenario_name: str,
    config_path: Path,
    max_ticks: int | None = None,
    image_save_dir: Path | None = None,
    display: bool = False,
    delay: float = 0.0,
    runs_dir: Path = Path("runs"),
    adapter: str = "virtual",
) -> RehearsalMetrics:
    """Run a rehearsal.

    adapter:
        "virtual" — use VirtualWorldRobot (Mac playground; renders frames itself).
        "mock"/"http"/"ros2"/"lerobot"/<name> — use a real adapter from hack.robot.ADAPTERS.
            Frames then come from hack.sensors.camera.Camera (webcam or robot-provided).
            The scenario's success criterion still applies but object positions in the
            world are meaningless (only the robot's pose is tracked).
    """
    cfg = yaml.safe_load(config_path.read_text())
    scenario = load_scenario(scenario_name)
    real_mode = adapter != "virtual"
    real_robot = None
    if real_mode:
        from hack.robot import make as _make_robot
        real_robot = _make_robot(adapter)
        await real_robot.connect()
        robot = VirtualWorldRobot(scenario)  # keeps history + scoring consistent
        robot.tick = 0
    else:
        robot = VirtualWorldRobot(scenario)
    tools = ToolBox(robot=real_robot or robot)

    # Per-run JSONL trace (what `hack ui` tails) and a shared "last frame" path.
    runs_dir.mkdir(parents=True, exist_ok=True)
    trace_path = runs_dir / f"rehearsal-{scenario.name}-{int(time.time())}.jsonl"
    last_frame_path = runs_dir / "last_frame.jpg"
    live_cues_path = runs_dir / "live_cues.ndjson"
    # Skip any pre-existing cues so we only consume new ones for this rehearsal.
    live_cues_cursor = live_cues_path.stat().st_size if live_cues_path.exists() else 0
    trace = JsonlLogger(trace_path)
    correctness = CorrectnessMonitor(runs_dir)
    trace.add_listener(correctness)  # every trace.log() feeds the monitor in real-time
    trace.log("start", scenario=scenario.name, config=cfg, adapter=adapter)
    # Model identity so the dashboard can show "running on: <model> @ <host>"
    def _host_label(url: str) -> str:
        from urllib.parse import urlparse
        try:
            h = urlparse(url).hostname or url
        except Exception:
            h = url
        return "local (Mac)" if h in ("localhost", "127.0.0.1", "::1") else h

    trace.log(
        "model_info",
        llm_model=cfg["llm"]["model"],
        llm_host=_host_label(cfg["llm"]["base_url"]),
        vlm_model=cfg["vlm"]["model"],
        vlm_host=_host_label(cfg["vlm"]["base_url"]),
    )

    # Camera source for real-robot rehearsals
    real_cam = None
    if real_mode:
        from hack.sensors.camera import Camera
        real_cam = Camera(
            device=cfg["vlm"].get("device", 0),
            fps=cfg["vlm"].get("frame_fps", 2.0),
            downscale_to=cfg["vlm"].get("downscale_to", 768),
        )
        await real_cam.__aenter__()
        real_cam_iter = real_cam.frames().__aiter__()

    from hack.models import make_llm as _make_llm, make_vlm as _make_vlm
    system_prompt = cfg["agent"]["system_prompt"] + (scenario.system_prompt_suffix or "")
    planner = OllamaPlanner(
        adapter=_make_llm(cfg["llm"]),
        system_prompt=system_prompt,
        max_tool_calls=cfg["agent"].get("max_tool_calls_per_turn", 4),
    )
    # Mock VLM: use ground-truth from virtual world (no API call).
    vlm_provider = cfg["vlm"].get("provider") or cfg["vlm"].get("adapter") or "ollama"
    if vlm_provider == "mock" and not real_mode:
        from hack.models.mock_vlm import MockVLM
        vlm = VLMClient(adapter=MockVLM(world_robot=robot))
    else:
        vlm = VLMClient(adapter=_make_vlm(cfg["vlm"], prompt=cfg["agent"]["observation_prompt"]))

    m = RehearsalMetrics(scenario=scenario.name, ticks_run=0, success=False, success_reason="not run")
    cue_by_tick = {c.at_tick: c.text for c in scenario.cues}
    transcript: list[str] = []
    total_ticks = max_ticks or scenario.max_ticks
    last_action_label: str | None = None
    cur_success: str | None = None
    # Voice-driven plan memory. No plan → idle. No fallback anywhere.
    plan_memory: PlanMemory | None = None

    win_name = f"hack rehearse | {scenario.name}"
    if display:
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, 640, 640)

    for tick in range(1, total_ticks + 1):
        robot.tick = tick
        scripted_cue = cue_by_tick.get(tick)
        live_text, live_cues_cursor = _drain_live_cues(live_cues_path, live_cues_cursor)
        # Merge scripted + live cues.
        new_cue_text = ""
        if scripted_cue:
            new_cue_text = scripted_cue
            trace.log("scripted_cue", tick=tick, text=scripted_cue)
        if live_text:
            new_cue_text = (new_cue_text + " | " if new_cue_text else "") + live_text
            trace.log("live_cue", tick=tick, text=live_text)
        cue = new_cue_text or None
        if cue:
            transcript.append(cue)

        # --- Cue → plan installation (scripted OR live) ---
        if new_cue_text:
            pose = (await (real_robot or robot).get_state()).pose
            # Deterministic path first — no LLM if the cue is computable.
            det_case = await classify_cue_smart(new_cue_text, planner)
            safety = cfg.get("robot", {}).get("safety", {})
            if det_case:
                calibration = cfg.get("robot", {}).get("calibration")
                world_objs = {n: o for n, o in robot.objects.items()} if hasattr(robot, "objects") else None
                steps = generate_plan(det_case, new_cue_text, pose, safety, calibration, world_objects=world_objs)
                trace.log("alert", tick=tick, code="deterministic-plan",
                          message=f"classified as '{det_case}' — {len(steps)} computed step(s), no LLM")
            else:
                steps = await decompose(new_cue_text, planner, pose=pose)
            if steps:
                if not det_case:
                    # Validate LLM-generated plan via a second LLM call.
                    ok, corrected, reason = await validate_plan(new_cue_text, steps, planner, pose=pose)
                    if not ok and corrected:
                        trace.log("alert", tick=tick, code="plan-corrected",
                                  message=f"validator corrected plan: {reason}")
                        steps = corrected
                    elif not ok:
                        trace.log("alert", tick=tick, code="plan-rejected",
                                  message=f"validator rejected plan: {reason} — robot stays idle")
                        continue
                steps = expand_plan_steps(steps, safety)
                plan_memory = PlanMemory(
                    cue=new_cue_text, steps=steps,
                    origin=(pose[0], pose[1]),
                    meta={"installed_tick": tick},
                )
                trace.log("plan_installed", tick=tick, cue=new_cue_text,
                          steps=plan_memory.steps_to_dicts(),
                          origin=list(plan_memory.origin))
            else:
                trace.log("alert", tick=tick, code="cue-decompose-failed",
                          message=f"could not decompose cue {new_cue_text!r} — robot stays idle")

        # --- Idle rule: no plan, no action ---
        if plan_memory is None or plan_memory.is_done():
            if plan_memory is not None and plan_memory.is_done():
                trace.log("plan_complete", tick=tick, cue=plan_memory.cue)
                plan_memory = None
            still = _annotate_frame(robot.render_frame(), tick, total_ticks, cue, m.tool_calls,
                                    last_action_label, "idle — awaiting voice cue", scenario.name)
            cv2.imwrite(str(last_frame_path), still)
            if display:
                big = cv2.resize(still, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_NEAREST)
                cv2.imshow(win_name, big)
                if cv2.waitKey(max(1, int(delay * 1000))) & 0xFF == ord("q"):
                    break
            elif delay > 0:
                await asyncio.sleep(delay)
            _emit_world_state(trace, tick, robot)
            trace.log("idle", tick=tick)
            m.ticks_run = tick
            continue

        if real_mode and real_cam is not None:
            # Pull the next real camera frame (waits on FPS budget).
            try:
                real_frame = await real_cam_iter.__anext__()
                frame = real_frame.image
            except StopAsyncIteration:
                break
        else:
            frame = robot.render_frame()
        annotated = _annotate_frame(frame, tick, total_ticks, cue, m.tool_calls,
                                    last_action_label, cur_success, scenario.name)
        cv2.imwrite(str(last_frame_path), annotated)
        if image_save_dir is not None:
            image_save_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(image_save_dir / f"tick-{tick:03d}.jpg"), annotated)
        if display:
            big = cv2.resize(annotated, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_NEAREST)
            cv2.imshow(win_name, big)
            cv2.waitKey(1)

        # Pre-baked direct-execute path: if the current plan step has a tool, execute it
        # verbatim — no VLM, no planner call. Deterministic for kinematic motion.
        # EXCEPTION: if vlm is running every_tick (e.g. obstacle-course with mock VLM),
        # run the VLM observation + obstacle check BEFORE executing the pre-baked step.
        # This lets the avoidance system interrupt a pre-baked plan when obstacles appear.
        current_step = plan_memory.current() if plan_memory else None
        if current_step is not None and current_step.tool is not None:
            # Obstacle check before pre-baked execution (if VLM runs every tick).
            vlm_mode = cfg["vlm"].get("run_mode", "every_tick")
            if vlm_mode == "every_tick":
                obs = await vlm.observe(frame)
                obs_dict = obs.model_dump() if hasattr(obs, "model_dump") else {}
                state = await (real_robot or robot).get_state()
                avoidance_steps = check_obstacle_avoidance(
                    obs_dict, state.pose, cfg.get("robot", {}).get("safety", {}))
                if avoidance_steps:
                    trace.log("alert", tick=tick, code="obstacle-detected",
                              message=f"obstacle ahead during pre-baked plan — injecting {len(avoidance_steps)}-step avoidance")
                    world_objs = {n: o for n, o in robot.objects.items()} if hasattr(robot, "objects") else None
                    plan_memory = inject_avoidance(
                        plan_memory, avoidance_steps,
                        robot_pose=state.pose if hasattr(state, "pose") else None,
                        world_objects=world_objs,
                        safety=cfg.get("robot", {}).get("safety"),
                    )
                    trace.log("plan_installed", tick=tick, cue="obstacle-avoidance",
                              steps=[s.to_dict() for s in plan_memory.steps],
                              origin=list(plan_memory.origin))
                    current_step = plan_memory.current()
            # Safety clamp — even pre-baked steps get capped.
            clamped, notes = clamp_call(current_step.tool, cfg.get("robot", {}).get("safety", {}))
            if notes:
                trace.log("alert", tick=tick, code="safety-clamp",
                          message=f"pre-baked step clamped: {', '.join(notes)}")
            tc = ToolCall(**clamped)
            m.tool_calls[tc.name] += 1
            res = await tools.call(tc)
            trace.log("action", tick=tick, call=tc.model_dump(),
                      result=res.model_dump(), source="pre-baked")
            last_action_label = f"{tc.name} {tc.args}"[:60]
            plan_memory.advance()
            trace.log("plan_progress", tick=tick,
                      step_index=plan_memory.step_index,
                      total=len(plan_memory.steps))
            if plan_memory.is_done():
                trace.log("plan_complete", tick=tick, cue=plan_memory.cue)
                plan_memory = None
            m.ticks_run = tick
            post = _annotate_frame(robot.render_frame(), tick, total_ticks, cue, m.tool_calls,
                                   last_action_label, cur_success, scenario.name)
            cv2.imwrite(str(last_frame_path), post)
            if display:
                big = cv2.resize(post, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_NEAREST)
                cv2.imshow(win_name, big)
                if cv2.waitKey(max(1, int(delay * 1000))) & 0xFF == ord("q"):
                    break
            elif delay > 0:
                await asyncio.sleep(delay)
            _emit_world_state(trace, tick, robot)
            ok, why = _evaluate(scenario, robot, m.tool_calls)
            cur_success = why if ok else f"checking — {why}"
            if ok:
                break
            continue

        # VLM call rate management — if `vlm.run_mode == "on_cue"` only run VLM on the
        # tick that installed a fresh plan (to ground it). Otherwise skip and give the
        # planner an empty observation. Cuts API pressure ~2× on free-tier providers.
        vlm_mode = cfg["vlm"].get("run_mode", "every_tick")
        run_vlm = (vlm_mode == "every_tick") or bool(live_text)
        if run_vlm:
            t0 = time.time()
            trace.log("status", tick=tick, state="vlm_thinking")
            try:
                obs = await vlm.observe(frame)
                _elapsed = (time.time() - t0) * 1000
                m.vlm_ms.append(_elapsed)
                trace.log("status", tick=tick, state="vlm_done", ms=round(_elapsed))
            except Exception as exc:
                m.vlm_parse_failures += 1
                err = str(exc)
                obs = type("O", (), {"model_dump": lambda self, _e=err: {"error": _e}})()
                trace.log("status", tick=tick, state="vlm_error", error=err)
        else:
            obs = type("O", (), {"model_dump": lambda self: {"scene": "(skipped; plan executing)"}})()

        state = await (real_robot or robot).get_state()

        # Obstacle avoidance check — runs after every observation (mock or real VLM).
        obs_dict = obs.model_dump() if hasattr(obs, "model_dump") else obs.model_dump()
        avoidance_steps = check_obstacle_avoidance(obs_dict, state.pose, cfg.get("robot", {}).get("safety", {}))
        if avoidance_steps:
            trace.log("alert", tick=tick, code="obstacle-detected",
                      message=f"obstacle ahead — injecting {len(avoidance_steps)}-step avoidance")
            world_objs = {n: o for n, o in robot.objects.items()} if hasattr(robot, "objects") else None
            plan_memory = inject_avoidance(
                plan_memory, avoidance_steps,
                robot_pose=state.pose if hasattr(state, "pose") else None,
                world_objects=world_objs,
                safety=cfg.get("robot", {}).get("safety"),
            )
            trace.log("plan_installed", tick=tick, cue="obstacle-avoidance",
                      steps=[s.to_dict() for s in plan_memory.steps],
                      origin=list(plan_memory.origin))
            # Re-enter the pre-baked path on the next tick.
            m.ticks_run = tick
            post = _annotate_frame(robot.render_frame(), tick, total_ticks, cue, m.tool_calls,
                                   last_action_label, cur_success, scenario.name)
            cv2.imwrite(str(last_frame_path), post)
            if delay > 0:
                await asyncio.sleep(delay)
            continue

        # Expose plan_origin to planner via robot_state.extra if a plan is active.
        state_dump = state.model_dump()
        if plan_memory is not None:
            state_dump.setdefault("extra", {})
            state_dump["extra"]["plan_origin"] = list(plan_memory.origin)
            state_dump["extra"]["plan_step"] = plan_memory.progress_text()
        # Prepend the current plan-step hint so the planner targets it exclusively.
        hint = plan_hint(plan_memory) if plan_memory else ""
        turn_transcript = ([hint] if hint else []) + transcript
        t0 = time.time()
        trace.log("status", tick=tick, state="planner_thinking")
        try:
            plan = await planner.plan(PlannerInput(
                observation=obs.model_dump(),
                transcript=turn_transcript,
                robot_state=state_dump,
                memory=tools.memory,
            ))
            _elapsed = (time.time() - t0) * 1000
            m.planner_ms.append(_elapsed)
            trace.log("status", tick=tick, state="planner_done", ms=round(_elapsed))
            if "parse_failed" in plan.note:
                m.plan_parse_failures += 1
        except Exception:
            m.plan_parse_failures += 1
            plan = None
            trace.log("status", tick=tick, state="planner_error")

        trace.log("observation", tick=tick, cue=cue, observation=getattr(obs, "model_dump", dict)())
        suppress_plan = False
        if plan:
            trace.log("plan", tick=tick, calls=[c.model_dump() for c in plan.calls], note=plan.note)
            # Step-coverage + direction validation + semantic requirement.
            current_step = plan_memory.current() if plan_memory else None
            if current_step:
                step_text = current_step.text
                plan_blob = json.dumps([c.model_dump() for c in plan.calls]).lower() + " " + (plan.note or "").lower()
                # Semantic: if step text implies a specific tool, plan must use it.
                required_tools = required_tools_for_step(step_text)
                plan_tool_names = {c.name for c in plan.calls}
                semantic_error: str | None = None
                if required_tools and not (required_tools & plan_tool_names):
                    semantic_error = (
                        f"step requires tool(s) {sorted(required_tools)} but plan used "
                        f"{sorted(plan_tool_names) or '∅'}"
                    )
                # Loose keyword / always-in-scope fallback.
                kws = [w.lower() for w in step_text.split() if len(w) > 3]
                always_in = {"move", "turn", "forward", "back", "left", "right", "speak"}
                matched = (not kws) or any(k in plan_blob for k in kws) or any(
                    k in plan_blob for k in always_in)
                # Directional validator — catches sign flips.
                direction_error: str | None = None
                for c in plan.calls:
                    err = validate_call_against_step(step_text, c.model_dump())
                    if err:
                        direction_error = err
                        break
                if semantic_error or direction_error or not matched:
                    abandoned = plan_memory.retry() if plan_memory else True
                    suppress_plan = True
                    if abandoned:
                        code, msg = "step-abandoned", f"abandoned step {step_text!r} after 3 retries; plan cleared"
                    elif semantic_error:
                        code, msg = "step-semantic-mismatch", f"{semantic_error} — suppressed (retry {plan_memory.step_retries}/3)"
                    elif direction_error:
                        code, msg = "step-direction-mismatch", f"{direction_error} — suppressed (retry {plan_memory.step_retries}/3)"
                    else:
                        code, msg = "step-not-executed", f"planner did not address step {step_text!r} (retry {plan_memory.step_retries}/3)"
                    trace.log("alert", tick=tick, code=code, message=msg)
                    last_action_label = f"[SUPPRESSED — {step_text[:40]!r}]"
                    if abandoned:
                        plan_memory = None
            if not suppress_plan:
                safety = cfg.get("robot", {}).get("safety", {})
                for tc in plan.calls[: planner.max_tool_calls]:
                    # Safety clamp on planner-emitted calls too.
                    clamped, notes = clamp_call(tc.model_dump(), safety)
                    if notes:
                        trace.log("alert", tick=tick, code="safety-clamp",
                                  message=f"planner call clamped: {', '.join(notes)}")
                        tc = ToolCall(**clamped)
                    m.tool_calls[tc.name] += 1
                    res = await tools.call(tc)
                    trace.log("action", tick=tick, call=tc.model_dump(), result=res.model_dump())
                    last_action_label = f"{tc.name} {tc.args}"[:60]
                # Step executed → advance plan (one step per successful tick).
                if plan_memory is not None:
                    plan_memory.advance()
                    trace.log("plan_progress", tick=tick,
                              step_index=plan_memory.step_index,
                              total=len(plan_memory.steps))
                    if plan_memory.is_done():
                        trace.log("plan_complete", tick=tick, cue=plan_memory.cue)
                        plan_memory = None

        _emit_world_state(trace, tick, robot)
        m.ticks_run = tick
        # Render again after actions so the post-tick state is what's shown + saved.
        post = _annotate_frame(robot.render_frame(), tick, total_ticks, cue, m.tool_calls,
                               last_action_label, cur_success, scenario.name)
        cv2.imwrite(str(last_frame_path), post)
        if display:
            big = cv2.resize(post, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_NEAREST)
            cv2.imshow(win_name, big)
            # Quit-on-q; allow a small inter-tick pause.
            pause_ms = max(1, int(delay * 1000))
            if cv2.waitKey(pause_ms) & 0xFF == ord("q"):
                break
        elif delay > 0:
            await asyncio.sleep(delay)

        ok, why = _evaluate(scenario, robot, m.tool_calls)
        # Mid-run: show a neutral "checking" state so the UI doesn't flash FAIL every tick.
        cur_success = why if ok else f"checking — {why}"
        if ok:
            break

    ok, why = _evaluate(scenario, robot, m.tool_calls)
    m.success = ok
    m.success_reason = why
    # Final frame annotation — either PASS (green) or a terminal FAIL (red).
    cur_success = why if ok else f"FAIL — {why}"
    final = _annotate_frame(robot.render_frame(), m.ticks_run, total_ticks, None, m.tool_calls,
                            last_action_label, cur_success, scenario.name)
    cv2.imwrite(str(last_frame_path), final)
    if robot.clamp_events:
        trace.log("clamp_summary", count=len(robot.clamp_events), events=robot.clamp_events)
    trace.log("stop", success=ok, reason=why)
    trace.close()
    # Write correctness report for this rehearsal.
    if correctness.issues:
        report_path = correctness.write_report()
        import sys
        print(f"[correctness] {len(correctness.issues)} issue(s) logged → {report_path}", file=sys.stderr, flush=True)
    if real_mode:
        if real_cam is not None:
            await real_cam.__aexit__(None, None, None)
        if real_robot is not None:
            await real_robot.disconnect()
    if display:
        # leave the final frame visible for 1.5s then close
        cv2.waitKey(1500)
        cv2.destroyWindow(win_name)
    return m


def _compute_hints(scenario_name: str, state, tool_calls) -> list[str]:
    """Produce explicit per-tick corrections based on ground truth.

    These are injected into the transcript as `[SYSTEM HINT]` lines so the planner
    cannot ignore them without noticing. Kept scenario-aware so hints are relevant.
    """
    hints: list[str] = []
    pose = state.pose if hasattr(state, "pose") else state.get("pose", (0, 0, 0))
    x, y, _ = pose
    dist = (x * x + y * y) ** 0.5
    tick = state.extra.get("tick", 0) if hasattr(state, "extra") else 0
    if scenario_name == "dance":
        if dist > 0.3:
            sx = "NEGATIVE" if x > 0 else "POSITIVE"
            sy = "NEGATIVE" if y > 0 else "POSITIVE"
            hints.append(
                f"OFF STAGE dist={dist:.2f}m (x={x:+.2f}, y={y:+.2f}). "
                f"Your NEXT move MUST have dx {sx} (|dx|=0.15) and dy {sy} (|dy|=0.15). "
                f"Do NOT emit an emote this tick — return home first."
            )
        # `speak` nudge — escalates if it keeps being ignored.
        speaks = tool_calls.get("speak", 0)
        if speaks == 0:
            if tick >= 4:
                hints.append(
                    "MANDATORY THIS TICK: emit a `speak` tool call with a short original line "
                    "in `args.text` that fits the current moment (react to any recent user "
                    "cue; do NOT copy example phrases verbatim). This is non-negotiable — "
                    "the scenario fails without it. Include `speak` FIRST in your calls array."
                )
            else:
                hints.append("You have not yet called `speak`. Include one short original line this tick.")
        emote_labels = tool_calls.get("emote", 0)
        if emote_labels >= 2:
            hints.append("You have used emotes. Vary the LABEL (spin/wave/bow/pose/sway).")
    return hints


def _emit_world_state(trace: JsonlLogger, tick: int, robot: VirtualWorldRobot) -> None:
    """Emit a world_state event with robot pose + all object positions for the TUI map."""
    objects = []
    for name, obj in robot.objects.items():
        objects.append({
            "name": name, "x": round(obj.x, 3), "y": round(obj.y, 3),
            "color": obj.color, "is_obstacle": obj.is_obstacle,
            "is_container": obj.is_container, "is_target": obj.is_target,
            "radius": obj.radius if obj.is_obstacle else 0,
        })
    trace.log("world_state", tick=tick,
              pose=list(robot.pose),
              objects=objects,
              collisions=len(robot.collision_events))


def _drain_live_cues(path: Path, cursor: int) -> tuple[str, int]:
    """Read new NDJSON lines from `path` starting at byte `cursor`; return joined text + new cursor."""
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


def _evaluate(scenario, robot, tool_calls):
    if scenario.evaluate is not None:
        return scenario.evaluate(robot, tool_calls)
    return robot.success()


def write_summary(m: RehearsalMetrics, out_dir: Path, config_snapshot: Path | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = out_dir / f"rehearsal-{m.scenario}-{ts}.json"
    payload: dict[str, Any] = {"ts": ts, **m.summary()}
    if config_snapshot and config_snapshot.exists():
        payload["config"] = yaml.safe_load(config_snapshot.read_text())
    path.write_text(json.dumps(payload, indent=2, default=str))
    # maintain a "latest" pointer
    (out_dir / f"rehearsal-{m.scenario}-latest.json").write_text(path.read_text())
    return path


def compare_to_previous(scenario: str, current: RehearsalMetrics, runs_dir: Path) -> list[str]:
    """Return human-readable regressions/improvements vs the last rehearsal of this scenario."""
    candidates = sorted(runs_dir.glob(f"rehearsal-{scenario}-*.json"))
    # Drop the "latest" pointer; keep timestamped files.
    candidates = [p for p in candidates if "-latest" not in p.name]
    if len(candidates) < 2:
        return ["(no previous rehearsal of this scenario to compare against)"]
    prev = json.loads(candidates[-2].read_text())
    out: list[str] = []
    cur = current.summary()
    # success transitions
    if prev.get("success") != cur["success"]:
        arrow = "↗" if cur["success"] else "↘"
        out.append(f"{arrow} success: {prev.get('success')} → {cur['success']}")
    # latency deltas
    for key in ("vlm_ms", "planner_ms"):
        pp = prev.get(key, {}).get("mean")
        cc = cur.get(key, {}).get("mean")
        if pp and cc:
            dlt = (cc - pp) / pp * 100
            if abs(dlt) > 10:
                arrow = "↗ slower" if dlt > 0 else "↘ faster"
                out.append(f"{arrow} {key} mean {pp:.0f}ms → {cc:.0f}ms ({dlt:+.0f}%)")
    # parse failures
    for key in ("vlm_parse_failures", "plan_parse_failures"):
        pp, cc = prev.get(key, 0), cur.get(key, 0)
        if cc != pp:
            out.append(f"{'↘' if cc < pp else '↗'} {key}: {pp} → {cc}")
    return out or ["no notable changes vs previous rehearsal"]
