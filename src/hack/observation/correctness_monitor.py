"""Continuous correctness monitor — runs alongside a rehearsal and logs every
detected issue with context + a proposed fix.

Reads the active JSONL trace in real-time, applies a set of checkers to each
event, and appends issues to `runs/issues.ndjson`. After the rehearsal
completes, `summarise()` reads that file and produces a markdown digest at
`runs/issues-<ts>.md` grouped by category.

Usage (from `hack observe` or standalone):

    from hack.observation.correctness_monitor import CorrectnessMonitor
    monitor = CorrectnessMonitor(trace_path)
    await monitor.watch()    # blocks until trace has "stop" event
    report = monitor.summarise()
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Issue:
    tick: int | None
    category: str           # "rotation_overshoot" | "sign_flip" | "safety_clamp" | ...
    severity: str           # "error" | "warning" | "info"
    description: str
    context: dict[str, Any] = field(default_factory=dict)
    suggested_fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": time.time(),
            "tick": self.tick,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "context": self.context,
            "suggested_fix": self.suggested_fix,
        }


class CorrectnessMonitor:
    def __init__(self, runs_dir: Path = Path("runs")) -> None:
        self.runs_dir = runs_dir
        self.issues: list[Issue] = []
        self.issues_path = runs_dir / "issues.ndjson"
        # state
        self._plan_cue: str | None = None
        self._plan_steps: list[dict] = []
        self._plan_origin: tuple[float, float] = (0.0, 0.0)
        self._step_idx: int = 0
        self._pose: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._cumulative_dtheta: float = 0.0
        self._cue_target_deg: float | None = None
        self._actions: list[dict] = []
        self._clamp_count: int = 0

    def _log(self, issue: Issue) -> None:
        self.issues.append(issue)
        self.issues_path.parent.mkdir(parents=True, exist_ok=True)
        with self.issues_path.open("a") as f:
            f.write(json.dumps(issue.to_dict(), default=str) + "\n")

    def check_event(self, event: dict[str, Any]) -> None:
        kind = event.get("kind")
        tick = event.get("tick")

        if kind == "plan_installed":
            self._on_plan_installed(event, tick)
        elif kind == "plan_progress":
            self._step_idx = event.get("step_index", 0)
        elif kind == "plan_complete":
            self._on_plan_complete(event, tick)
        elif kind == "action":
            self._on_action(event, tick)
        elif kind == "alert":
            self._on_alert(event, tick)

    def _on_plan_installed(self, ev: dict, tick: int | None) -> None:
        self._plan_cue = ev.get("cue", "")
        self._plan_steps = ev.get("steps", [])
        self._plan_origin = tuple(ev.get("origin", [0, 0]))[:2]
        self._step_idx = 0
        self._cumulative_dtheta = 0.0
        self._cue_target_deg = _extract_degrees(self._plan_cue)
        self._actions = []

        # Check: number of steps vs expected for angular cues
        if self._cue_target_deg is not None:
            target_rad = math.radians(self._cue_target_deg)
            # count pre-baked dtheta
            total_plan_dtheta = 0.0
            for s in self._plan_steps:
                if isinstance(s, dict):
                    tool = s.get("tool")
                    if isinstance(tool, dict) and tool.get("name") == "move":
                        total_plan_dtheta += float((tool.get("args") or {}).get("dtheta") or 0)
            if abs(target_rad) > 0.01:
                ratio = abs(total_plan_dtheta) / abs(target_rad) if abs(target_rad) > 0.01 else 0
                if ratio > 1.5:
                    self._log(Issue(
                        tick=tick, category="rotation_overshoot", severity="warning",
                        description=(
                            f"cue '{self._plan_cue}' implies {self._cue_target_deg:.0f}° "
                            f"({abs(target_rad):.2f} rad) but decomposer planned "
                            f"{abs(total_plan_dtheta):.2f} rad ({math.degrees(abs(total_plan_dtheta)):.0f}°) "
                            f"— {ratio:.1f}× overshoot"
                        ),
                        context={"cue": self._plan_cue, "target_rad": target_rad,
                                 "plan_rad": total_plan_dtheta, "ratio": ratio,
                                 "num_steps": len(self._plan_steps)},
                        suggested_fix=(
                            "decomposer prompt miscomputes step count for angular cues. "
                            "Add explicit worked examples: '90°=1.57rad → ceil(1.57/0.6)=3 steps'. "
                            "Or enforce target_rad / 0.6 = N in decompose()."
                        ),
                    ))
                elif ratio < 0.6:
                    self._log(Issue(
                        tick=tick, category="rotation_undershoot", severity="warning",
                        description=(
                            f"cue '{self._plan_cue}' implies {self._cue_target_deg:.0f}° "
                            f"but decomposer only planned {math.degrees(abs(total_plan_dtheta)):.0f}° "
                            f"— {ratio:.1f}× undershoot"
                        ),
                        context={"cue": self._plan_cue, "target_rad": target_rad,
                                 "plan_rad": total_plan_dtheta},
                        suggested_fix="decomposer dropped steps. Check max_steps budget.",
                    ))

    def _on_plan_complete(self, ev: dict, tick: int | None) -> None:
        # Check: final cumulative rotation vs target
        if self._cue_target_deg is not None:
            target_rad = math.radians(self._cue_target_deg)
            actual_deg = math.degrees(self._cumulative_dtheta)
            if abs(target_rad) > 0.01:
                error_deg = abs(actual_deg) - abs(self._cue_target_deg)
                if abs(error_deg) > 30:
                    self._log(Issue(
                        tick=tick, category="rotation_execution_error", severity="error",
                        description=(
                            f"cue was '{self._plan_cue}' ({self._cue_target_deg:.0f}°) "
                            f"but robot actually rotated {actual_deg:+.0f}° "
                            f"(error {error_deg:+.0f}°)"
                        ),
                        context={"target_deg": self._cue_target_deg,
                                 "actual_deg": actual_deg, "error_deg": error_deg},
                        suggested_fix="check sign flips or missing steps in execution",
                    ))

        # Check: distance from origin after return-to-start cues
        cue_lower = (self._plan_cue or "").lower()
        if any(k in cue_lower for k in ("back", "return", "original", "start", "initial")):
            final_dist = math.hypot(*self._pose[:2])
            if final_dist > 0.5:
                self._log(Issue(
                    tick=tick, category="return_to_origin_failed", severity="warning",
                    description=(
                        f"cue implied return to origin but final distance is {final_dist:.2f}m"
                    ),
                    context={"final_pose": list(self._pose), "final_dist": final_dist},
                    suggested_fix="decomposer return steps are imprecise; consider closing the loop with a computed return vector",
                ))

        self._plan_cue = None
        self._plan_steps = []
        self._cumulative_dtheta = 0.0
        self._cue_target_deg = None

    def _on_action(self, ev: dict, tick: int | None) -> None:
        call = ev.get("call") or {}
        result = ev.get("result") or {}
        source = ev.get("source", "llm")
        self._actions.append(ev)

        if call.get("name") == "move":
            args = call.get("args") or {}
            dt = float(args.get("dtheta") or 0)
            dx = float(args.get("dx") or 0)
            dy = float(args.get("dy") or 0)
            self._cumulative_dtheta += dt

            # Check: sign consistency within a plan (sign flips mid-rotation)
            if len(self._actions) >= 2 and self._plan_cue:
                prev = self._actions[-2].get("call", {})
                if prev.get("name") == "move":
                    prev_dt = float((prev.get("args") or {}).get("dtheta") or 0)
                    if prev_dt != 0 and dt != 0 and (prev_dt > 0) != (dt > 0):
                        self._log(Issue(
                            tick=tick, category="sign_flip", severity="warning",
                            description=(
                                f"dtheta sign flipped: prev={prev_dt:+.2f} → now={dt:+.2f} "
                                f"within cue '{self._plan_cue}'"
                            ),
                            context={"prev_dtheta": prev_dt, "cur_dtheta": dt, "source": source},
                            suggested_fix=(
                                "pre-baked steps should not flip signs. If this is planner-path, "
                                "the direction validator should have caught it — check always_in set."
                            ),
                        ))

            # Update approximate pose
            th = self._pose[2]
            nx = self._pose[0] + dx * math.cos(th) - dy * math.sin(th)
            ny = self._pose[1] + dx * math.sin(th) + dy * math.cos(th)
            self._pose = (nx, ny, th + dt)

        if not result.get("ok"):
            self._log(Issue(
                tick=tick, category="action_failed", severity="error",
                description=f"{call.get('name')} failed: {result.get('error', '?')}",
                context={"call": call, "result": result},
                suggested_fix="check adapter implementation for this tool",
            ))

    def _on_alert(self, ev: dict, tick: int | None) -> None:
        code = ev.get("code", "")
        msg = ev.get("message", "")
        if code == "safety-clamp":
            self._clamp_count += 1
            self._log(Issue(
                tick=tick, category="safety_clamp", severity="warning",
                description=msg,
                context={"total_clamps": self._clamp_count},
                suggested_fix="decomposer or planner emitting oversized move args; tighten decompose prompt or auto-split",
            ))
        elif code in ("step-semantic-mismatch", "step-direction-mismatch", "step-abandoned"):
            self._log(Issue(
                tick=tick, category=code.replace("-", "_"), severity="error",
                description=msg,
                context={},
                suggested_fix="planner cannot execute this step text — consider making it pre-baked",
            ))
        elif code == "cue-decompose-failed":
            self._log(Issue(
                tick=tick, category="decompose_failed", severity="error",
                description=msg,
                context={},
                suggested_fix="check decomposer prompt or model capability for this cue phrasing",
            ))

    def summarise(self) -> str:
        if not self.issues:
            return "# Correctness report\n\nNo issues detected.\n"
        lines = ["# Correctness report", ""]
        by_cat: dict[str, list[Issue]] = {}
        for i in self.issues:
            by_cat.setdefault(i.category, []).append(i)
        errors = sum(1 for i in self.issues if i.severity == "error")
        warnings = sum(1 for i in self.issues if i.severity == "warning")
        lines.append(f"**{len(self.issues)} issues** ({errors} errors, {warnings} warnings)\n")
        for cat, items in sorted(by_cat.items()):
            lines.append(f"## {cat} ({len(items)}×)\n")
            for it in items:
                icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(it.severity, "⚪")
                lines.append(f"- {icon} **t{it.tick}** {it.description}")
                if it.suggested_fix:
                    lines.append(f"  - **fix:** {it.suggested_fix}")
            lines.append("")
        return "\n".join(lines)

    def write_report(self) -> Path:
        ts = int(time.time())
        path = self.runs_dir / f"issues-{ts}.md"
        path.write_text(self.summarise())
        return path


def _extract_degrees(cue: str) -> float | None:
    """Try to extract an angular target from a cue like 'turn left 90 degrees' or 'spin 360'."""
    import re
    m = re.search(r"(\d+)\s*(?:deg|°|degrees?)?", cue or "")
    if not m:
        return None
    val = float(m.group(1))
    if val > 720 or val < 1:
        return None
    return val
