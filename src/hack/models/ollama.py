from __future__ import annotations

import httpx

from hack.models.base import LLMAdapter, VLMAdapter


class OllamaLLM(LLMAdapter):
    name = "ollama"

    async def complete(self, prompt: str, *, json_mode: bool = True) -> str:
        base = self.base_url or "http://localhost:11434"
        body: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        if json_mode:
            body["format"] = "json"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{base.rstrip('/')}/api/generate", json=body)
            r.raise_for_status()
            return r.json().get("response", "")


class OllamaVLM(VLMAdapter):
    name = "ollama"
    # Small VLMs (moondream, phi-vision) don't respect json-mode reliably;
    # the adapter still sends it — caller's parser handles fallback.
    JSON_MODE_MODELS = ("qwen2.5vl", "qwen2.5-vl", "llama3.2-vision", "llava", "nemotron")

    async def describe(self, image_b64: str, override_prompt: str | None = None) -> str:
        base = self.base_url or "http://localhost:11434"
        prompt = override_prompt if override_prompt is not None else self.prompt
        json_mode = any(tag in self.model.lower() for tag in self.JSON_MODE_MODELS)
        body: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 180},
        }
        if json_mode:
            body["format"] = "json"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{base.rstrip('/')}/api/generate", json=body)
            r.raise_for_status()
            return r.json().get("response", "").strip()
