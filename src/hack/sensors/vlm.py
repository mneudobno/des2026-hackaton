from __future__ import annotations

import base64
import json

import cv2
import httpx
import numpy as np
from pydantic import BaseModel, Field


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
    """Minimal Ollama-compatible vision client (works with NIM via OpenAI-compat too).

    Returns a structured Observation. If JSON parsing fails, falls back to raw text.
    """

    def __init__(
        self,
        model: str = "qwen2.5vl:7b",
        base_url: str = "http://localhost:11434",
        prompt: str = (
            "List only what is clearly visible. Respond with JSON: "
            '{"objects":[{"label":"...","rough_position":"...","confidence":0..1}],'
            '"scene":"<=15 words","salient_event":"... or null"}'
        ),
        timeout: float = 20.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.prompt = prompt
        self.timeout = timeout

    async def observe(self, image: np.ndarray) -> Observation:
        b64 = _encode_jpeg(image)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": self.prompt,
                    "images": [b64],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1},
                },
            )
            r.raise_for_status()
            text = r.json().get("response", "")
        try:
            parsed = json.loads(text)
            return Observation(**parsed)
        except Exception:
            return Observation(raw=text)
