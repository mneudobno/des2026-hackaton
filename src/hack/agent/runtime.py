from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from hack.agent.logger import JsonlLogger
from hack.agent.planner import OllamaPlanner, PlannerInput


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

    Thin wrapper over ``hack.rehearsal.runner.rehearse`` with the built-in
    "live" scenario. The rehearsal runner is the single source of truth for the
    control loop — obstacle-avoidance, A* path planning, stall watchdog,
    cue re-inject, safety clamp, plan memory — so day-of automatically inherits
    every advancement made in rehearsal. The only inputs that change day-of are:
      * ``robot_name``  → pluggable RobotAdapter (http / ros2 / lerobot / mock)
      * real VLM        → picked up from ``configs/agent.yaml``
      * real Camera     → picked up by the runner when adapter != "virtual"
      * live_cues only  → the "live" scenario ships with no scripted cues
    """
    import shutil

    from hack.rehearsal.runner import rehearse
    runs_dir = trace_out.parent if trace_out else Path("runs")
    await rehearse(
        scenario_name="live",
        config_path=config_path,
        runs_dir=runs_dir,
        display=False,
        adapter=robot_name,
    )
    # If the caller requested a specific trace path, mirror the rehearsal
    # output there (keeps `demo record --out runs/submit.jsonl` working).
    if trace_out is not None:
        candidates = sorted(runs_dir.glob("rehearsal-live-*.jsonl"))
        if candidates:
            shutil.copy2(candidates[-1], trace_out)


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
