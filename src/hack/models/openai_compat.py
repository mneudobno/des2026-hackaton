from __future__ import annotations

import json
import os

import httpx

from hack.models.base import LLMAdapter, load_dotenv


class OpenAICompatLLM(LLMAdapter):
    """Any `/v1/chat/completions` server — NIM, vLLM, LM Studio, OpenAI itself.

    Day-of: point `base_url` at the ZGX NIM endpoint (e.g. `http://<zgx>:8000/v1`)
    and set `model` to `nvidia/Nemotron-3-Nano-30B-A3B`. `api_key_env` should be
    the env var name holding the bearer token (NIM usually `NIM_API_KEY`; leave
    blank for local vLLM).
    """

    name = "openai-compat"

    async def complete(self, prompt: str, *, json_mode: bool = True) -> str:
        load_dotenv()
        key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        url = f"{self.base_url}/chat/completions"
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return json.dumps(data)[:400]
