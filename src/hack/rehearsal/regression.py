"""Regression harness — replay curated mic cues against the agent and score each.

The goal is a fast sanity check after every model / prompt / runner change:

    uv run hack regression
    uv run hack regression --config configs/agent.gemini.yaml

Each cue has its own pass criteria (custom checker per cue). The harness runs
one rehearsal per cue, writes a summary table to the terminal, and appends a
row to `docs/REHEARSALS.md`.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from hack.agent.plan_memory import PlanStep, decompose, expand_plan_steps
from hack.agent.planner import OllamaPlanner
from hack.models import make_llm


@dataclass
class CueCase:
    name: str
    cue: str
    # Pre-decompose check — given the decomposed `steps` and the active robot
    # safety dict, return (ok, reason). Safety is passed in so checkers can
    # adapt to the configured per-tick limits (e.g. expected step count for a
    # full spin scales with MAX_ANG).
    check_plan: Callable[[list[PlanStep], dict], tuple[bool, str]] | None = None
    expected_tools: set[str] = field(default_factory=set)  # tools that must appear in the plan
    min_steps: int = 1
    max_steps: int = 20


CASES: list[CueCase] = [
    CueCase(
        name="spin_360",
        cue="spin 360",
        expected_tools={"move"},
        min_steps=3,   # loose floor; precise per-safety count is in _check_spin_360.
        max_steps=15,
        check_plan=lambda steps, safety: _check_spin_360(steps, safety),
    ),
    CueCase(
        name="go_to_random_and_back",
        cue="go to random place and back to initial position",
        expected_tools={"remember", "move"},
        min_steps=3,
        # After auto-split, a 2m walk expands into ~10 chunks; allow up to 30 total.
        max_steps=30,
        check_plan=lambda steps, safety: _check_random_and_back(steps, safety),
    ),
]


def _total_dtheta(steps: list[PlanStep]) -> float:
    total = 0.0
    for s in steps:
        if s.tool and s.tool.get("name") == "move":
            total += float((s.tool.get("args") or {}).get("dtheta") or 0.0)
    return total


def _check_spin_360(steps: list[PlanStep], safety: dict) -> tuple[bool, str]:
    baked = sum(1 for s in steps if s.tool and s.tool.get("name") == "move")
    total_theta = _total_dtheta(steps)
    target = 2 * math.pi
    # Required step count scales with the configured per-tick angular limit:
    # a full 2π spin needs ceil(2π / MAX_ANG) chunks under expand_plan_steps().
    max_ang = float(safety.get("max_angular_speed", 0.6))
    expected_min = math.ceil(target / max_ang) if max_ang > 0 else 6
    if baked < expected_min:
        return False, f"only {baked} pre-baked move steps (need ≥{expected_min} for max_ang={max_ang})"
    if abs(total_theta) < target * 0.8 or abs(total_theta) > target * 1.3:
        return False, f"total dtheta={total_theta:.2f} rad; expected ≈±2π ({target:.2f})"
    return True, f"{baked} baked move steps, Σdtheta={total_theta:+.2f} rad ≈ {math.degrees(total_theta):+.0f}°"


def _check_random_and_back(steps: list[PlanStep], safety: dict) -> tuple[bool, str]:
    tool_names = [s.tool.get("name") if s.tool else None for s in steps]
    texts = " | ".join(s.text.lower() for s in steps)
    has_remember = "remember" in tool_names or any(k in texts for k in ("remember", "recall", "origin"))
    has_return = any(k in texts for k in ("back", "return", "origin", "start", "initial"))
    if not has_remember:
        return False, "no remember/recall step"
    if not has_return:
        return False, "no return-to-origin step"
    return True, f"{len(steps)} steps; includes remember + return"


@dataclass
class CueResult:
    case: CueCase
    steps: list[PlanStep]
    ok: bool
    reason: str
    decompose_ms: float


async def run_one(case: CueCase, config_path: Path) -> CueResult:
    cfg = yaml.safe_load(config_path.read_text())
    planner = OllamaPlanner(
        adapter=make_llm(cfg["llm"]),
        system_prompt=cfg["agent"]["system_prompt"],
        max_tool_calls=cfg["agent"].get("max_tool_calls_per_turn", 4),
    )
    t0 = time.time()
    steps = await decompose(case.cue, planner)
    steps = expand_plan_steps(steps, cfg.get("robot", {}).get("safety", {}))
    decompose_ms = (time.time() - t0) * 1000
    if not steps:
        return CueResult(case, [], False, "decompose returned 0 steps", decompose_ms)
    if not (case.min_steps <= len(steps) <= case.max_steps):
        return CueResult(case, steps, False,
                         f"step count {len(steps)} outside [{case.min_steps}, {case.max_steps}]",
                         decompose_ms)
    tool_names = {s.tool.get("name") for s in steps if s.tool}
    if case.expected_tools and not (case.expected_tools & tool_names):
        text_blob = " ".join(s.text.lower() for s in steps)
        # tools may also appear only in text for llm-path steps
        if not all(t in text_blob or t in tool_names for t in case.expected_tools):
            return CueResult(case, steps, False,
                             f"missing expected tools {sorted(case.expected_tools)}",
                             decompose_ms)
    if case.check_plan:
        ok, reason = case.check_plan(steps, cfg.get("robot", {}).get("safety", {}))
        return CueResult(case, steps, ok, reason, decompose_ms)
    return CueResult(case, steps, True, "passed default checks", decompose_ms)


async def run_all(config_path: Path, names: list[str] | None = None) -> list[CueResult]:
    cases = CASES if not names else [c for c in CASES if c.name in names]
    results: list[CueResult] = []
    for c in cases:
        results.append(await run_one(c, config_path))
    return results


def format_report(config_path: Path, results: list[CueResult]) -> str:
    lines: list[str] = []
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    lines.append(f"regression · {config_path}")
    lines.append(f"  {passed}/{total} passed")
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        lines.append(f"  {status}  {r.case.name:<24}  cue={r.case.cue!r}  ({r.decompose_ms:.0f}ms)")
        lines.append(f"       → {r.reason}  · {len(r.steps)} step(s)")
        for i, s in enumerate(r.steps, 1):
            src = "pre" if s.tool else "llm"
            args = (s.tool or {}).get("args") if s.tool else ""
            lines.append(f"         {i:>2}. [{src}] {s.text}  {args}")
    return "\n".join(lines)


def append_to_log(config_path: Path, results: list[CueResult], log_path: Path = Path("docs/REHEARSALS.md")) -> None:
    if not log_path.exists():
        return
    passed = sum(1 for r in results if r.ok)
    total = len(results)
    per_case = "; ".join(f"{r.case.name}:{'P' if r.ok else 'F'}" for r in results)
    line = (
        f"| {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} "
        f"| regression | {config_path.name} | {passed}/{total} | — | "
        f"{per_case} | — |"
    )
    existing = log_path.read_text()
    log_path.write_text(existing.rstrip() + "\n" + line + "\n")


def summary_json(results: list[CueResult]) -> dict:
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r.ok),
        "cases": [
            {
                "name": r.case.name,
                "cue": r.case.cue,
                "ok": r.ok,
                "reason": r.reason,
                "decompose_ms": round(r.decompose_ms, 1),
                "steps": [{"text": s.text, "tool": s.tool} for s in r.steps],
            }
            for r in results
        ],
    }
