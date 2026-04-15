from __future__ import annotations

from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from hack.robot.base import RobotAdapter


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class ToolResult(BaseModel):
    name: str
    ok: bool
    output: Any = None
    error: str | None = None


# Tool schemas exposed to the planner. Keep small and committal — one tool per intent.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "move", "args": {"dx": "float meters", "dy": "float meters", "dtheta": "float radians"}, "desc": "Move the robot in body frame."},
    {"name": "grasp", "args": {}, "desc": "Close gripper."},
    {"name": "release", "args": {}, "desc": "Open gripper."},
    {"name": "set_joint", "args": {"name": "str", "value": "float"}, "desc": "Set a named joint."},
    {"name": "emote", "args": {"label": "str (e.g. 'wave', 'nod', 'confused')"}, "desc": "Express via LEDs/sound/canned pose."},
    {"name": "speak", "args": {"text": "str"}, "desc": "Say something to the human via TTS."},
    {"name": "wait", "args": {"seconds": "float"}, "desc": "Pause and observe."},
    {"name": "remember", "args": {"key": "str", "value": "str"}, "desc": "Persist a fact across turns."},
    {"name": "think", "args": {"thought": "str"}, "desc": "Internal note. Do not overuse."},
]


class ToolBox:
    """Dispatches ToolCalls to the robot adapter or built-in handlers."""

    def __init__(self, robot: RobotAdapter, speak: Callable[[str], Awaitable[None]] | None = None) -> None:
        self.robot = robot
        self._speak = speak
        self.memory: dict[str, str] = {}

    async def call(self, tc: ToolCall) -> ToolResult:
        try:
            match tc.name:
                case "move":
                    await self.robot.move(float(tc.args.get("dx", 0)), float(tc.args.get("dy", 0)), float(tc.args.get("dtheta", 0)))
                case "grasp":
                    await self.robot.grasp()
                case "release":
                    await self.robot.release()
                case "set_joint":
                    await self.robot.set_joint(str(tc.args["name"]), float(tc.args["value"]))
                case "emote":
                    await self.robot.emote(str(tc.args.get("label", "neutral")))
                case "speak":
                    text = str(tc.args.get("text", ""))
                    if self._speak:
                        await self._speak(text)
                    return ToolResult(name=tc.name, ok=True, output=text)
                case "wait":
                    import asyncio
                    await asyncio.sleep(float(tc.args.get("seconds", 0.5)))
                case "remember":
                    self.memory[str(tc.args["key"])] = str(tc.args["value"])
                case "think":
                    return ToolResult(name=tc.name, ok=True, output=str(tc.args.get("thought", "")))
                case _:
                    return ToolResult(name=tc.name, ok=False, error=f"unknown tool: {tc.name}")
            return ToolResult(name=tc.name, ok=True)
        except Exception as e:
            return ToolResult(name=tc.name, ok=False, error=str(e))
