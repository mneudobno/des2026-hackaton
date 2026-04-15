from __future__ import annotations

import base64
import json

import cv2
import numpy as np
from pydantic import BaseModel, Field

from hack.models import make_vlm
from hack.models.base import VLMAdapter


class ObservedObject(BaseModel):
    label: str
    rough_position: str = Field(description="e.g., 'left foreground', 'top-right', 'center'")
    confidence: float = 0.5


class Observation(BaseModel):
    objects: list[ObservedObject] = Field(default_factory=list)
    scene: str = ""
    salient_event: str | None = None
    raw: str | None = None


def _encode_jpeg(img: np.ndarray, quality: int = 80) -> str:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return base64.b64encode(buf.tobytes()).decode()


class VLMClient:
    """Structured VLM wrapper around a `VLMAdapter` (ollama / gemini / NIM-compat).

    Returns a pydantic `Observation`. If the adapter's output isn't valid JSON,
    falls back to an embedded-object extraction, then to raw text.
    """

    def __init__(
        self,
        adapter: VLMAdapter | None = None,
        # Legacy kwargs — used only when `adapter` is not provided.
        model: str = "qwen2.5vl:7b",
        base_url: str = "http://localhost:11434",
        # DAYOF: B — override this prompt with task-specific grounding (see DAY_OF_DECISIONS.md §8).
        prompt: str = (
            "List only what is clearly visible. Respond with JSON: "
            '{"objects":[{"label":"...","rough_position":"...","confidence":0..1}],'
            '"scene":"<=15 words","salient_event":"... or null"}'
        ),
        timeout: float = 60.0,
        provider: str = "ollama",
        api_key_env: str = "GEMINI_API_KEY",
    ) -> None:
        if adapter is None:
            adapter = make_vlm({
                "adapter": provider,
                "model": model,
                "base_url": base_url,
                "timeout": timeout,
                "api_key_env": api_key_env,
            }, prompt=prompt)
        self.adapter = adapter
        self.prompt = prompt or adapter.prompt

    @property
    def model(self) -> str:
        return self.adapter.model

    @property
    def base_url(self) -> str:
        return self.adapter.base_url

    @property
    def provider(self) -> str:
        return self.adapter.name

    async def observe(self, image: np.ndarray) -> Observation:
        b64 = _encode_jpeg(image)
        text = await self.adapter.describe(b64, override_prompt=self.prompt)
        try:
            return Observation(**json.loads(text))
        except Exception:
            pass
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return Observation(**json.loads(text[start : end + 1]))
            except Exception:
                pass
        return Observation(raw=text, scene=text[:120])
