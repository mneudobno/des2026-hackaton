"""Model adapter contracts — tiny, provider-agnostic.

An LLMAdapter takes a prompt string and returns a text response (ideally JSON).
A VLMAdapter takes a JPEG base64 + prompt and returns a text response.
That's it. Everything else (prompt construction, JSON parsing, plan memory,
cue routing) is orchestrated above the adapter layer.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


class LLMAdapter(ABC):
    name: str = "abstract"

    def __init__(
        self,
        model: str,
        base_url: str = "",
        temperature: float = 0.3,
        timeout: float = 60.0,
        api_key_env: str = "",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.api_key_env = api_key_env

    @abstractmethod
    async def complete(self, prompt: str, *, json_mode: bool = True) -> str:
        """Return the raw text response. Caller parses."""

    def host_label(self) -> str:
        """Short 'local (Mac)' / '<host>' descriptor for the dashboard."""
        if not self.base_url:
            return "(default)"
        from urllib.parse import urlparse
        try:
            h = urlparse(self.base_url).hostname or self.base_url
        except Exception:
            h = self.base_url
        return "local (Mac)" if h in ("localhost", "127.0.0.1", "::1") else h


class VLMAdapter(ABC):
    name: str = "abstract"

    def __init__(
        self,
        model: str,
        base_url: str = "",
        prompt: str = "",
        timeout: float = 60.0,
        api_key_env: str = "",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.prompt = prompt
        self.timeout = timeout
        self.api_key_env = api_key_env

    @abstractmethod
    async def describe(self, image_b64: str, override_prompt: str | None = None) -> str:
        """Return raw text response for the given JPEG (base64) image."""


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader — only sets vars not already present in os.environ."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                if k and k not in os.environ:
                    os.environ[k] = v
    except OSError:
        pass
