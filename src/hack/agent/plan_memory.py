"""Plan memory — compound-cue decomposition and per-step execution state.

The planner is called once per tick but many user cues span multiple ticks
("walk around and come back", "go to the red cube then to the bin"). This
module lets the runtime hold a plan across ticks so small models don't have
to re-derive the whole thing every call.

Used by both `hack.agent.runtime.run()` (judged demo) and
`hack.rehearsal.runner.rehearse()` (playground). No fallback behaviour
anywhere: if decomposition fails, caller should raise an alert and stay
idle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hack.agent.planner import OllamaPlanner


MAX_STEP_RETRIES = 3


@dataclass
class PlanStep:
    """One decomposed sub-step.

    - `text`: human description (always present; used for planner fallback + UI).
    - `tool`: optional pre-baked ToolCall dict
      (e.g. {"name":"move","args":{"dtheta":0.6},"rationale":"turn left"}).
      When present, runner executes it directly, bypassing the per-tick planner.
      That's how we keep small/weaker models from flipping signs mid-plan.
    """
    text: str
    tool: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "tool": self.tool}


@dataclass
class PlanMemory:
    cue: str
    steps: list[PlanStep]
    step_index: int = 0
    origin: tuple[float, float] = (0.0, 0.0)
    step_retries: int = 0
    meta: dict[str, object] = field(default_factory=dict)

    def current(self) -> PlanStep | None:
        if self.is_done():
            return None
        return self.steps[self.step_index]

    def advance(self) -> None:
        self.step_index += 1
        self.step_retries = 0

    def retry(self) -> bool:
        self.step_retries += 1
        return self.step_retries >= MAX_STEP_RETRIES

    def is_done(self) -> bool:
        return self.step_index >= len(self.steps)

    def progress_text(self) -> str:
        return f"{self.step_index + 1}/{len(self.steps)}"

    def steps_to_dicts(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.steps]


_DECOMPOSE_SYSTEM_PROMPT = (
    "You decompose a single user instruction for a robot into ordered sub-steps.\n"
    "\n"
    "AVAILABLE TOOLS and their args:\n"
    "  move(dx, dy, dtheta)  — body-frame. dx,dy in metres; dtheta in radians.\n"
    "                          POSITIVE dtheta = turn LEFT (counter-clockwise).\n"
    "                          NEGATIVE dtheta = turn RIGHT (clockwise).\n"
    "                          POSITIVE dx = forward. NEGATIVE dx = backward.\n"
    "  grasp() / release()    — gripper.\n"
    "  speak(text)            — say a short line.\n"
    "  emote(label)           — named expressive motion: spin / wave / bow / pose / sway / clap.\n"
    "  wait(seconds)          — idle.\n"
    "  remember(key, value)   — stash a fact.\n"
    "  set_joint(name, value) — named joint target.\n"
    "\n"
    "PER-TICK SAFETY LIMITS: |dx|,|dy| <= 0.2 m and |dtheta| <= 0.6 rad per step.\n"
    "If the instruction implies larger motion (e.g. 'spin 360 degrees' = 2π ≈ 6.28 rad), "
    "emit MULTIPLE small steps until the target is reached.\n"
    "Example: 'spin 360' → 11 steps of turn-left 0.6 rad.\n"
    "Example: 'walk forward 1 m' → 5 steps of move-forward 0.2 m.\n"
    "\n"
    "For EACH step you emit:\n"
    "  - `text`: short English description (<20 words).\n"
    "  - `tool`: when the step is mechanical (kinematic motion, fixed-label emote, known-text speak),\n"
    "    return a pre-baked tool call: {{\"name\":\"move\",\"args\":{{\"dtheta\":0.6}},\"rationale\":\"...\"}}.\n"
    "    This bypasses the per-tick planner and guarantees correct sign/magnitude.\n"
    "  - Set `tool` to null ONLY when the step genuinely needs vision grounding later\n"
    "    (e.g. 'move toward the red cube' — target unknown at decompose time).\n"
    "\n"
    "Rules:\n"
    "  - Use 1 to {MAX_STEPS} sub-steps total. Prefer granular mechanical steps.\n"
    "  - If a compound instruction genuinely needs more than {MAX_STEPS} steps, use {MAX_STEPS}.\n"
    "  - If the instruction is unintelligible, nonsense, or unsafe, return an empty steps list.\n"
    "  - Do NOT invent instructions the user did not imply.\n"
    "  - If return-to-start is needed, step 1 = remember origin, final = return to remembered origin.\n"
    "\n"
    'Respond JSON only: {{"steps": [{{"text": "...", "tool": {{...}} or null}}, ...]}}.'
)


async def decompose(
    cue: str,
    planner: "OllamaPlanner",
    max_steps: int = 12,
) -> list[PlanStep]:
    """Ask the planner LLM to break `cue` into ordered sub-steps.

    Returns [] on any failure — caller must then alert + idle (no fallback).
    Routes to the same provider (ollama / gemini / openai-compat) as the planner.
    """
    prompt = (
        _DECOMPOSE_SYSTEM_PROMPT.format(MAX_STEPS=max_steps)
        + f"\n\nUSER INSTRUCTION: {cue!r}"
    )
    try:
        text = await planner.adapter.complete(prompt, json_mode=True)
    except Exception as exc:
        import sys
        print(f"[decompose] {planner.provider} call failed: {exc!r}", file=sys.stderr, flush=True)
        return []
    text = (text or "").strip()
    for candidate in (text, _extract_block(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        raw_steps = data.get("steps") if isinstance(data, dict) else None
        if not isinstance(raw_steps, list):
            continue
        cleaned: list[PlanStep] = []
        for item in raw_steps:
            if isinstance(item, str) and item.strip():
                cleaned.append(PlanStep(text=item.strip(), tool=None))
            elif isinstance(item, dict):
                txt = (item.get("text") or item.get("desc") or "").strip()
                if not txt:
                    continue
                tool = item.get("tool")
                if isinstance(tool, dict) and isinstance(tool.get("name"), str):
                    # normalise — ensure args dict, rationale string
                    tool = {
                        "name": tool["name"],
                        "args": tool.get("args") if isinstance(tool.get("args"), dict) else {},
                        "rationale": tool.get("rationale") or "",
                    }
                else:
                    tool = None
                cleaned.append(PlanStep(text=txt, tool=tool))
        if cleaned:
            return cleaned[:max_steps]
    return []


def _extract_block(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return ""
def plan_hint(plan: PlanMemory) -> str:
    """One-line hint to prepend to the planner's transcript."""
    step = plan.current()
    if step is None:
        return ""
    return (
        f"[PLAN] Step {plan.progress_text()}: {step.text!r} — "
        f"origin was ({plan.origin[0]:+.2f},{plan.origin[1]:+.2f}). "
        "Execute ONLY this step; ignore any other scenario guidance."
    )


_DIRECTION_HINTS: list[tuple[tuple[str, ...], str, str]] = [
    # (keywords in step text, arg name, required_sign: "+" / "-")
    (("left", "ccw", "counter-clockwise", "counterclockwise"), "dtheta", "+"),
    (("right", "cw", "clockwise"), "dtheta", "-"),
    (("forward", "ahead"), "dx", "+"),
    (("back", "backward", "backwards", "reverse"), "dx", "-"),
]

# Verbs in step text that demand a specific tool (not just any `move` will do).
# If the step text contains any of these keywords, the plan MUST include the
# paired tool name — `move`/`emote` are NOT considered as "addressing" the step.
SEMANTIC_VERBS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("remember", "recall", "note"), ("remember",)),
    (("wait", "pause", "stand", "stop", "hold", "idle", "ready", "still"), ("wait",)),
    (("say", "speak", "announce", "greet", "tell"), ("speak",)),
    (("grasp", "grip", "grab", "pick", "hold"), ("grasp",)),
    (("release", "drop", "let go", "let-go"), ("release",)),
    (("emote", "gesture", "wave", "bow", "spin", "nod", "sway", "clap", "pose"), ("emote",)),
]


def required_tools_for_step(step_text: str) -> set[str]:
    """Return the set of tool names that satisfy a step; empty = any tool accepted."""
    t = (step_text or "").lower()
    required: set[str] = set()
    for kws, tools in SEMANTIC_VERBS:
        if any(k in t for k in kws):
            required.update(tools)
    return required


def clamp_call(call: dict[str, Any], safety: dict[str, float]) -> tuple[dict[str, Any], list[str]]:
    """Clamp move args to the scenario safety envelope. Returns (clamped_call, notes)."""
    if not isinstance(call, dict) or call.get("name") != "move":
        return call, []
    args = dict(call.get("args") or {})
    notes: list[str] = []
    lin = float(safety.get("max_linear_speed", 0.2))
    ang = float(safety.get("max_angular_speed", 0.6))
    for axis, limit in (("dx", lin), ("dy", lin), ("dtheta", ang)):
        v = args.get(axis)
        if isinstance(v, (int, float)) and abs(v) > limit:
            notes.append(f"{axis} {v:+.2f}→{(limit if v>0 else -limit):+.2f}")
            args[axis] = limit if v > 0 else -limit
    if not notes:
        return call, []
    clamped = dict(call)
    clamped["args"] = args
    return clamped, notes


def split_oversized_move(step: "PlanStep", safety: dict[str, float]) -> list["PlanStep"]:
    """Split a pre-baked `move` step into chunks that respect per-call safety.

    Non-move or non-pre-baked steps are returned unchanged as a single-element list.
    """
    if step.tool is None or step.tool.get("name") != "move":
        return [step]
    args = step.tool.get("args") or {}
    lin = float(safety.get("max_linear_speed", 0.2))
    ang = float(safety.get("max_angular_speed", 0.6))
    dx = float(args.get("dx") or 0.0)
    dy = float(args.get("dy") or 0.0)
    dtheta = float(args.get("dtheta") or 0.0)
    n_lin = max(_chunks_needed(dx, lin), _chunks_needed(dy, lin))
    n_ang = _chunks_needed(dtheta, ang)
    n = max(1, n_lin, n_ang)
    if n == 1:
        return [step]
    rationale = step.tool.get("rationale") or ""
    out: list[PlanStep] = []
    for i in range(n):
        chunk_args = {
            "dx": dx / n,
            "dy": dy / n,
            "dtheta": dtheta / n,
        }
        out.append(PlanStep(
            text=f"{step.text} [{i+1}/{n}]",
            tool={
                "name": "move",
                "args": chunk_args,
                "rationale": rationale or "auto-split safety chunk",
            },
        ))
    return out


def _chunks_needed(value: float, limit: float) -> int:
    import math as _m
    if limit <= 0 or abs(value) <= limit:
        return 1
    return int(_m.ceil(abs(value) / limit))


def expand_plan_steps(steps: list["PlanStep"], safety: dict[str, float]) -> list["PlanStep"]:
    """Apply `split_oversized_move` to every step; returns a fresh list."""
    out: list[PlanStep] = []
    for s in steps:
        out.extend(split_oversized_move(s, safety))
    return out


def validate_call_against_step(step_text: str, call: dict[str, Any]) -> str | None:
    """Return a human reason if the call contradicts the step's directional hint, else None."""
    args = call.get("args") or {}
    if not isinstance(args, dict):
        return None
    t = (step_text or "").lower()
    for kws, arg, sign in _DIRECTION_HINTS:
        if not any(k in t for k in kws):
            continue
        v = args.get(arg)
        if not isinstance(v, (int, float)) or v == 0:
            continue
        if sign == "+" and v < 0:
            return f"step implies {arg}>0 but call has {arg}={v:+g}"
        if sign == "-" and v > 0:
            return f"step implies {arg}<0 but call has {arg}={v:+g}"
    return None
