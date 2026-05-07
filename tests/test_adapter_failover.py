"""Failover across multiple base_urls on transient network errors.

Scope: the pool rotation + _request helper on LLMAdapter/VLMAdapter. We don't
start real HTTP servers — we monkey-patch each attempt to raise ConnectError
until the desired host is reached, then return successfully.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from hack.models import make_llm
from hack.models.ollama import OllamaLLM


def test_base_url_property_reflects_active_host() -> None:
    adapter = OllamaLLM(
        model="mock",
        base_urls=["http://zgx-a:11434", "http://zgx-b:11434"],
    )
    assert adapter.base_url == "http://zgx-a:11434"
    assert adapter.base_urls == ["http://zgx-a:11434", "http://zgx-b:11434"]
    assert adapter._rotate_host() is True
    assert adapter.base_url == "http://zgx-b:11434"
    assert adapter._rotate_host() is False  # exhausted


def test_failover_rotates_on_connect_error() -> None:
    """First host raises ConnectError, adapter moves to second host which
    returns successfully. The final result comes from host-2."""
    adapter = OllamaLLM(
        model="mock",
        base_urls=["http://dead-host:11434", "http://live-host:11434"],
    )

    attempts: list[str] = []

    async def fake_call(base: str) -> str:
        attempts.append(base)
        if "dead-host" in base:
            raise httpx.ConnectError("connection refused")
        return f"response from {base}"

    result = asyncio.run(adapter._request(fake_call))
    assert result == "response from http://live-host:11434"
    assert attempts == ["http://dead-host:11434", "http://live-host:11434"]
    # After rotation the pool remembers the working host.
    assert adapter.base_url == "http://live-host:11434"


def test_failover_reraises_when_all_hosts_fail() -> None:
    adapter = OllamaLLM(
        model="mock",
        base_urls=["http://a:11434", "http://b:11434"],
    )

    async def fake_call(base: str) -> str:
        raise httpx.ConnectError(f"refused: {base}")

    with pytest.raises(httpx.ConnectError):
        asyncio.run(adapter._request(fake_call))


def test_non_transient_error_does_not_fail_over() -> None:
    """4xx/5xx and ValueError etc. are real bugs — must propagate without
    burning the failover list on a host that's actually reachable."""
    adapter = OllamaLLM(
        model="mock",
        base_urls=["http://a:11434", "http://b:11434"],
    )

    attempts: list[str] = []

    async def fake_call(base: str) -> str:
        attempts.append(base)
        raise ValueError("bad json from model")

    with pytest.raises(ValueError):
        asyncio.run(adapter._request(fake_call))
    # Only one attempt — we did not walk the failover list.
    assert attempts == ["http://a:11434"]
    assert adapter.base_url == "http://a:11434"


def test_make_llm_accepts_base_urls_list() -> None:
    adapter = make_llm({
        "provider": "ollama",
        "model": "qwen2.5:7b",
        "base_url": "http://zgx-a:11434",
        "base_urls": ["http://zgx-b:11434"],
    })
    # Primary + one failover, order preserved.
    assert adapter.base_urls == ["http://zgx-a:11434", "http://zgx-b:11434"]
    assert adapter.base_url == "http://zgx-a:11434"


def test_make_llm_back_compat_scalar_base_url() -> None:
    adapter = make_llm({
        "provider": "ollama",
        "model": "qwen2.5:7b",
        "base_url": "http://localhost:11434",
    })
    assert adapter.base_urls == ["http://localhost:11434"]
    assert adapter.base_url == "http://localhost:11434"
    assert adapter._rotate_host() is False


def test_host_label_shows_failover_count() -> None:
    multi = OllamaLLM(
        model="mock",
        base_urls=["http://zgx-a:11434", "http://zgx-b:11434"],
    )
    assert multi.host_label() == "zgx-a (+1 failover)"
    single = OllamaLLM(model="mock", base_url="http://zgx-a:11434")
    assert single.host_label() == "zgx-a"
