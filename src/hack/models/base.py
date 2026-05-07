"""Model adapter contracts — tiny, provider-agnostic.

An LLMAdapter takes a prompt string and returns a text response (ideally JSON).
A VLMAdapter takes a JPEG base64 + prompt and returns a text response.
That's it. Everything else (prompt construction, JSON parsing, plan memory,
cue routing) is orchestrated above the adapter layer.

Adapters support a list of `base_urls` for failover across multiple inference
hosts (e.g. ZGX-A and ZGX-B). On transient network errors the active host
rotates to the next entry; transports call `self._request(fn)` to inherit this.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")


class _HostPool:
    """Ordered list of base URLs with a rotating active index.

    Shared by LLMAdapter and VLMAdapter. Mixed-in rather than inherited so a
    stub subclass can override behaviour without fighting the ABC.
    """

    def _init_hosts(self, base_url: str, base_urls: list[str] | None) -> None:
        if base_urls:
            urls = [u.rstrip("/") for u in base_urls if u]
        elif base_url:
            urls = [base_url.rstrip("/")]
        else:
            urls = []
        self.base_urls: list[str] = urls
        self._url_idx: int = 0

    @property
    def base_url(self) -> str:
        return self.base_urls[self._url_idx] if self.base_urls else ""

    def _rotate_host(self) -> bool:
        """Promote the next base_url; return True if a rotation happened."""
        if self._url_idx + 1 < len(self.base_urls):
            self._url_idx += 1
            return True
        return False

    async def _request(self, do_call: "Callable[[str], Awaitable[T]]") -> T:
        """Call do_call(base) with failover across self.base_urls.

        Retries on httpx connect/read/pool timeouts and remote protocol errors —
        i.e. the kinds of failures that mean "this host is dead, try the next
        one." Non-transient failures (4xx/5xx HTTPStatusError, parse errors)
        propagate immediately so real bugs aren't masked.
        """
        import httpx  # imported here so base.py has no hard httpx dep
        transient: tuple[type[BaseException], ...] = (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
        )
        last_exc: BaseException | None = None
        # +1 so the loop still executes once when base_urls is empty (lets
        # provider defaults like Ollama's localhost kick in).
        attempts = max(1, len(self.base_urls))
        for _ in range(attempts):
            try:
                return await do_call(self.base_url)
            except transient as exc:
                last_exc = exc
                if not self._rotate_host():
                    break
        assert last_exc is not None
        raise last_exc


class LLMAdapter(_HostPool, ABC):
    name: str = "abstract"

    def __init__(
        self,
        model: str,
        base_url: str = "",
        temperature: float = 0.3,
        timeout: float = 60.0,
        api_key_env: str = "",
        base_urls: list[str] | None = None,
    ) -> None:
        self.model = model
        self._init_hosts(base_url, base_urls)
        self.temperature = temperature
        self.timeout = timeout
        self.api_key_env = api_key_env

    @abstractmethod
    async def complete(self, prompt: str, *, json_mode: bool = True) -> str:
        """Return the raw text response. Caller parses."""

    def host_label(self) -> str:
        """Short 'local (Mac)' / '<host>' descriptor for the dashboard."""
        url = self.base_url
        if not url:
            return "(default)"
        from urllib.parse import urlparse
        try:
            h = urlparse(url).hostname or url
        except Exception:
            h = url
        label = "local (Mac)" if h in ("localhost", "127.0.0.1", "::1") else h
        if len(self.base_urls) > 1:
            label += f" (+{len(self.base_urls) - 1} failover)"
        return label


class VLMAdapter(_HostPool, ABC):
    name: str = "abstract"

    def __init__(
        self,
        model: str,
        base_url: str = "",
        prompt: str = "",
        timeout: float = 60.0,
        api_key_env: str = "",
        base_urls: list[str] | None = None,
    ) -> None:
        self.model = model
        self._init_hosts(base_url, base_urls)
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
