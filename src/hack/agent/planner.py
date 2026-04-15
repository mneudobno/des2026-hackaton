from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from hack.agent.tools import TOOL_SCHEMAS, ToolCall
from hack.models import make_llm
from hack.models.base import LLMAdapter, load_dotenv as _load_dotenv  # re-export for legacy callers


class PlannerInput(BaseModel):
    observation: dict[str, Any]
    transcript: list[str] = []
    robot_state: dict[str, Any] = {}
    memory: dict[str, str] = {}


class Plan(BaseModel):
    calls: list[ToolCall]
    note: str = ""


class OllamaPlanner:
    """Prompt builder + JSON parser. Transport is delegated to an `LLMAdapter`.

    The historical name is kept for backwards compatibility; the class now works
    with any adapter in `hack.models.LLM_ADAPTERS` (ollama, gemini, openai-compat, nim).
    """

    def __init__(
        self,
        adapter: LLMAdapter | None = None,
        system_prompt: str = "",
        max_tool_calls: int = 4,
        # Legacy kwargs — used only when `adapter` is not provided.
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.3,
        timeout: float = 60.0,
        provider: str = "ollama",
        api_key_env: str = "GEMINI_API_KEY",
    ) -> None:
        if adapter is None:
            adapter = make_llm({
                "adapter": provider,
                "model": model,
                "base_url": base_url,
                "temperature": temperature,
                "timeout": timeout,
                "api_key_env": api_key_env,
            })
        self.adapter = adapter
        self.system_prompt = system_prompt
        self.max_tool_calls = max_tool_calls

    # --- introspection helpers used by runtime/dashboard ---
    @property
    def model(self) -> str:
        return self.adapter.model

    @property
    def base_url(self) -> str:
        return self.adapter.base_url

    @property
    def provider(self) -> str:
        return self.adapter.name

    @property
    def timeout(self) -> float:
        return self.adapter.timeout

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
        text = await self.adapter.complete(prompt, json_mode=True)
        for candidate in (text, _extract_json_object(text)):
            if not candidate:
                continue
            try:
                return Plan(**json.loads(candidate))
            except Exception:
                continue
        return Plan(calls=[], note=f"parse_failed: {text[:120]}")


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return ""


__all__ = ["OllamaPlanner", "PlannerInput", "Plan", "_load_dotenv"]
