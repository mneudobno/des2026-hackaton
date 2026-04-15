from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel

from hack.agent.tools import TOOL_SCHEMAS, ToolCall


class PlannerInput(BaseModel):
    observation: dict[str, Any]
    transcript: list[str] = []
    robot_state: dict[str, Any] = {}
    memory: dict[str, str] = {}


class Plan(BaseModel):
    calls: list[ToolCall]
    note: str = ""


class OllamaPlanner:
    """Ollama JSON-mode planner. Works with any OpenAI-compatible /api/generate too.

    Day-of: swap base_url to the NIM-compat endpoint and adjust the model name.
    """

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434",
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tool_calls: int = 4,
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tool_calls = max_tool_calls
        self.timeout = timeout

    def _build_prompt(self, inp: PlannerInput) -> str:
        return (
            f"SYSTEM:\n{self.system_prompt}\n\n"
            f"TOOLS (choose 1-{self.max_tool_calls}):\n{json.dumps(TOOL_SCHEMAS, indent=2)}\n\n"
            f"OBSERVATION:\n{json.dumps(inp.observation, indent=2)}\n\n"
            f"RECENT TRANSCRIPT:\n{json.dumps(inp.transcript[-5:])}\n\n"
            f"ROBOT STATE:\n{json.dumps(inp.robot_state)}\n\n"
            f"MEMORY:\n{json.dumps(inp.memory)}\n\n"
            "Respond with JSON: "
            '{"calls":[{"name":"...","args":{...},"rationale":"<=12 words"}], "note":"<=15 words"}'
            " — prefer one decisive call."
        )

    async def plan(self, inp: PlannerInput) -> Plan:
        prompt = self._build_prompt(inp)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": self.temperature},
                },
            )
            r.raise_for_status()
            text = r.json().get("response", "")
        try:
            data = json.loads(text)
            return Plan(**data)
        except Exception:
            return Plan(calls=[], note=f"parse_failed: {text[:120]}")
