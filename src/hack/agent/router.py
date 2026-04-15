"""Intent router — tiny LLM classifies input into a route before the big planner fires.

Pattern from NVIDIA's Reachy Mini playbook: a 3.8B Phi-3 (or similar) LLM
returns one of {chit_chat, image_understanding, other}. "other" triggers the
full ReAct/tool-use planner; the other two shortcut to much cheaper paths.

On our hardware this saves the 30B planner forward-pass when the user just says
"hello". On a 2-hour hackathon where latency is a scoring axis, this is cheap
insurance.

Configure in `configs/agent.yaml` under `router:`. If no router is configured,
the runtime falls through directly to the planner (current behavior).
"""

from __future__ import annotations

import json
from typing import Literal

import httpx
from pydantic import BaseModel

Route = Literal["chit_chat", "image_understanding", "other"]


class RouteDecision(BaseModel):
    route: Route
    reason: str = ""


class OllamaRouter:
    """Small-LLM router over the Ollama JSON-mode API."""

    def __init__(
        self,
        model: str = "phi3:mini",  # ~3.8B, very fast. qwen2.5:1.5b also good.
        base_url: str = "http://localhost:11434",
        timeout: float = 5.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def route(self, user_text: str, has_image: bool) -> RouteDecision:
        prompt = (
            "Classify the user's message into exactly one route. "
            "Routes: "
            "`chit_chat` (greetings, small talk), "
            "`image_understanding` (questions about what is seen / the scene / user's appearance), "
            "`other` (tool use, robot action, reasoning, external info). "
            f"Image available: {has_image}. "
            f"User: {user_text!r}. "
            'Respond JSON: {"route":"...", "reason":"<=8 words"}.'
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0},
                },
            )
            r.raise_for_status()
            text = r.json().get("response", "")
        try:
            return RouteDecision(**json.loads(text))
        except Exception:
            # On any failure, fall back to the most capable path — never drop actions.
            return RouteDecision(route="other", reason=f"router_parse_failed:{text[:40]}")
