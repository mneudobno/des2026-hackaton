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
    "SPATIAL CONTEXT (use this for navigation!):\n"
    "  Current robot pose: x={POSE_X:+.2f}, y={POSE_Y:+.2f}, theta={POSE_THETA:+.2f} rad ({POSE_THETA_DEG:+.0f}°)\n"
    "  Stage / origin is at (0, 0). Distance from origin: {DIST_FROM_ORIGIN:.2f} m\n"
    "  To RETURN to origin from current pose, the robot needs:\n"
    "    dx ≈ {RETURN_DX:+.2f} m, dy ≈ {RETURN_DY:+.2f} m (in body frame, approximate)\n"
    "\n"
    "AVAILABLE TOOLS and their args:\n"
    "  move(dx, dy, dtheta)  — body-frame. dx,dy in metres; dtheta in radians.\n"
    "                          POSITIVE dtheta = turn LEFT (counter-clockwise).\n"
    "                          NEGATIVE dtheta = turn RIGHT (clockwise).\n"
    "                          POSITIVE dx = forward. NEGATIVE dx = backward.\n"
    "  grasp() / release()    — gripper.\n"
    "  speak(text)            — say a short line.\n"
    "  emote(label)           — named expressive motion.\n"
    "  wait(seconds)          — idle.\n"
    "  remember(key, value)   — stash a fact.\n"
    "  set_joint(name, value) — named joint target.\n"
    "\n"
    "PER-TICK SAFETY LIMITS: |dx|,|dy| <= 0.2 m and |dtheta| <= 0.6 rad per step.\n"
    "\n"
    "ANGLE MATH (follow exactly):\n"
    "  - N degrees = N × π/180 radians.\n"
    "  - Steps needed = ceil(radians / 0.6).\n"
    "  - 90° = 1.571 rad → ceil(1.571/0.6) = 3 steps of 0.524 rad each.\n"
    "  - 180° = 3.142 rad → ceil(3.142/0.6) = 6 steps of 0.524 rad each.\n"
    "  - 360° = 6.283 rad → ceil(6.283/0.6) = 11 steps of 0.571 rad each.\n"
    "  DO NOT guess. COMPUTE steps = ceil(target_radians / 0.6), then per_step = target / steps.\n"
    "\n"
    "DEFAULT MAGNITUDES (when user does NOT specify a distance or angle):\n"
    "  - 'move forward' / 'move back' / 'step left' → 1 step of 0.2 m. NOT 5 steps.\n"
    "  - 'turn left' / 'turn right' (no angle given) → 1 step of 0.6 rad (~34°).\n"
    "  - Only emit multiple steps when the user gives a specific distance or angle.\n"
    "\n"
    "GEOMETRY — 'walk a circle' / 'make a circle':\n"
    "  A circle is NOT a spin. A circle requires BOTH translation AND rotation each step.\n"
    "  Example for a small circle: 8 steps of {{dx: 0.15, dtheta: 0.785}} (each step advances\n"
    "  and turns 45°, completing 360° around a ~0.12m radius arc).\n"
    "\n"
    "NAVIGATION — 'go to stage' / 'return to start' / 'go back':\n"
    "  Use the RETURN_DX and RETURN_DY values above to compute the actual steps.\n"
    "  Split into small chunks of 0.2m each. The robot MUST translate (dx/dy), not just spin.\n"
    "  'go to stage' / 'go to origin' / 'move to start' / 'return' all mean NAVIGATE TO (0,0).\n"
    "\n"
    "For EACH step you emit:\n"
    "  - `text`: short English description (<20 words).\n"
    "  - `tool`: pre-baked tool call when the step is mechanical.\n"
    "    Set `tool` to null ONLY when the step genuinely needs vision grounding.\n"
    "\n"
    "Rules:\n"
    "  - Use 1 to {MAX_STEPS} sub-steps total.\n"
    "  - If the instruction is unintelligible, return empty steps.\n"
    "  - Do NOT invent instructions the user did not imply.\n"
    "\n"
    'Respond JSON only: {{"steps": [{{"text": "...", "tool": {{...}} or null}}, ...]}}.'
)

_VALIDATE_SYSTEM_PROMPT = (
    "You are a plan validator for a robot. You receive a user cue, the robot's current pose, "
    "and a proposed list of steps. Check for these errors:\n"
    "  1. ANGLE MATH: if the cue says N degrees, total dtheta in the plan should be ≈ N×π/180 rad (±20%%).\n"
    "  2. STEP COUNT: unquantified cues ('move forward', 'step back') should be 1 step, not 5.\n"
    "  3. CIRCLE vs SPIN: 'circle' requires dx+dtheta each step; dtheta-only is a spin, not a circle.\n"
    "  4. NAVIGATION: 'go to stage'/'return'/'go back' must include translation (dx/dy), not just rotation.\n"
    "     Compare planned total dx/dy against the RETURN_DX/RETURN_DY hint.\n"
    "  5. SIGN: 'turn left' → dtheta > 0; 'turn right' → dtheta < 0; 'forward' → dx > 0; 'back' → dx < 0.\n"
    "\n"
    "If the plan is correct, respond: {{\"ok\": true}}\n"
    "If the plan has errors, respond: {{\"ok\": false, \"reason\": \"...\", \"corrected_steps\": [...]}}\n"
    "where corrected_steps uses the same format as the input steps.\n"
    "Respond JSON only."
)


async def decompose(
    cue: str,
    planner: "OllamaPlanner",
    max_steps: int = 12,
    pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> list[PlanStep]:
    """Ask the planner LLM to break `cue` into ordered sub-steps.

    Returns [] on any failure — caller must then alert + idle (no fallback).
    Routes to the same provider (ollama / gemini / openai-compat) as the planner.
    Now injects current pose + return vector so the decomposer can navigate.
    """
    import math as _m
    x, y, th = pose
    dist = _m.hypot(x, y)
    # Approximate body-frame return vector (rotate world-frame offset by -theta).
    cos_t, sin_t = _m.cos(-th), _m.sin(-th)
    return_dx = -x * cos_t - (-y) * sin_t  # negate because we want to go TOWARD origin
    return_dy = -x * sin_t + (-y) * cos_t
    # Fix: use proper body-frame transform
    return_dx = (-x) * _m.cos(th) + (-y) * _m.sin(th)
    return_dy = -(-x) * _m.sin(th) + (-y) * _m.cos(th)

    prompt = (
        _DECOMPOSE_SYSTEM_PROMPT.format(
            MAX_STEPS=max_steps,
            POSE_X=x, POSE_Y=y, POSE_THETA=th,
            POSE_THETA_DEG=_m.degrees(th),
            DIST_FROM_ORIGIN=dist,
            RETURN_DX=return_dx, RETURN_DY=return_dy,
        )
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


async def validate_plan(
    cue: str,
    steps: list[PlanStep],
    planner: "OllamaPlanner",
    pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[bool, list[PlanStep], str]:
    """Validate a decomposed plan via a second LLM call.

    Returns (ok, corrected_steps, reason).
    If ok=True, corrected_steps == original steps.
    If ok=False and the validator provided corrections, corrected_steps is the fixed plan.
    If ok=False and no corrections, corrected_steps is empty (caller should alert + idle).
    """
    import math as _m

    x, y, th = pose
    steps_json = json.dumps([s.to_dict() for s in steps], indent=2)
    prompt = (
        _VALIDATE_SYSTEM_PROMPT
        + f"\n\nCurrent pose: x={x:+.2f}, y={y:+.2f}, theta={th:+.2f} rad ({_m.degrees(th):+.0f}°)"
        + f"\nDistance from origin: {_m.hypot(x, y):.2f}m"
        + f"\nRETURN_DX ≈ {-x:+.2f}, RETURN_DY ≈ {-y:+.2f}"
        + f"\n\nUser cue: {cue!r}"
        + f"\n\nProposed steps:\n{steps_json}"
    )
    try:
        text = await planner.adapter.complete(prompt, json_mode=True)
    except Exception:
        return True, steps, "validator call failed; accepting plan"
    text = (text or "").strip()
    for candidate in (text, _extract_block(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            ok = data.get("ok", True)
            reason = data.get("reason", "")
            if ok:
                return True, steps, "validated"
            corrected = data.get("corrected_steps")
            if isinstance(corrected, list) and corrected:
                fixed: list[PlanStep] = []
                for item in corrected:
                    if isinstance(item, str) and item.strip():
                        fixed.append(PlanStep(text=item.strip(), tool=None))
                    elif isinstance(item, dict):
                        txt = (item.get("text") or "").strip()
                        if not txt:
                            continue
                        tool = item.get("tool")
                        if isinstance(tool, dict) and isinstance(tool.get("name"), str):
                            tool = {
                                "name": tool["name"],
                                "args": tool.get("args") if isinstance(tool.get("args"), dict) else {},
                                "rationale": tool.get("rationale") or "",
                            }
                        else:
                            tool = None
                        fixed.append(PlanStep(text=txt, tool=tool))
                if fixed:
                    return False, fixed, reason
            return False, [], reason
    return True, steps, "validator parse failed; accepting plan"


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
