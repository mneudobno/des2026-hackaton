from __future__ import annotations

import json
import os

import httpx

from hack.models.base import LLMAdapter, VLMAdapter, load_dotenv


class OpenAICompatLLM(LLMAdapter):
    """Any `/v1/chat/completions` server — NIM, vLLM, LM Studio, OpenAI itself.

    Day-of: point `base_url` at the ZGX vLLM endpoint (e.g. `http://<zgx>:8000/v1`)
    and set `model` to whatever `curl :8000/v1/models` reports (e.g.
    `nvidia/Nemotron-3-Nano-Omni`). `api_key_env` should be the env var name
    holding the bearer token (NIM usually `NIM_API_KEY`; leave blank for local
    vLLM).
    """

    name = "openai-compat"

    async def complete(self, prompt: str, *, json_mode: bool = True) -> str:
        load_dotenv()
        key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.extra_body:
            body.update(self.extra_body)

        async def _call(base: str) -> str:
            url = f"{base}/chat/completions"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=body, headers=headers)
                r.raise_for_status()
                data = r.json()
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                return json.dumps(data)[:400]

        return await self._request(_call)


class OpenAICompatVLM(VLMAdapter):
    """Multimodal `/v1/chat/completions` server — vLLM serving Nemotron Omni
    or any other model that accepts the OpenAI vision content-parts format.

    Day-of primary path: vLLM at `http://<zgx>:8000/v1` with the multimodal
    Nemotron 3 Nano Omni tag served on the same endpoint as the LLM. Caller
    sends a JPEG (base64) and the standard observation prompt; we wrap it as
    `[{type: text}, {type: image_url, image_url: {url: data:image/jpeg;base64,...}}]`.
    """

    name = "openai-compat"

    async def describe(self, image_b64: str, override_prompt: str | None = None) -> str:
        load_dotenv()
        key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        prompt = override_prompt if override_prompt is not None else self.prompt
        body: dict[str, object] = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                            },
                        },
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
        }
        if self.extra_body:
            body.update(self.extra_body)

        async def _call(base: str) -> str:
            url = f"{base}/chat/completions"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=body, headers=headers)
                r.raise_for_status()
                data = r.json()
            try:
                return data["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, TypeError, AttributeError):
                return json.dumps(data)[:400]

        return await self._request(_call)
