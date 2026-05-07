from __future__ import annotations

import json
import os

import httpx

from hack.models.base import LLMAdapter, VLMAdapter, load_dotenv

_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiLLM(LLMAdapter):
    name = "gemini"

    async def complete(self, prompt: str, *, json_mode: bool = True) -> str:
        load_dotenv()
        key = os.environ.get(self.api_key_env or "GEMINI_API_KEY", "")
        if not key:
            return f'{{"error":"{self.api_key_env or "GEMINI_API_KEY"} not set"}}'
        body: dict[str, object] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": self.temperature},
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"

        async def _call(base: str) -> str:
            base = base or _DEFAULT_BASE
            url = f"{base.rstrip('/')}/models/{self.model}:generateContent"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=body, headers={"X-goog-api-key": key})
                r.raise_for_status()
                data = r.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError):
                return json.dumps(data)[:400]

        return await self._request(_call)


class GeminiVLM(VLMAdapter):
    name = "gemini"

    async def describe(self, image_b64: str, override_prompt: str | None = None) -> str:
        load_dotenv()
        key = os.environ.get(self.api_key_env or "GEMINI_API_KEY", "")
        if not key:
            return f'{{"error":"{self.api_key_env or "GEMINI_API_KEY"} not set","scene":""}}'
        prompt = override_prompt if override_prompt is not None else self.prompt
        body = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
                ],
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        async def _call(base: str) -> str:
            base = base or _DEFAULT_BASE
            url = f"{base.rstrip('/')}/models/{self.model}:generateContent"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=body, headers={"X-goog-api-key": key})
                r.raise_for_status()
                data = r.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError):
                return json.dumps(data)[:400]

        return await self._request(_call)
