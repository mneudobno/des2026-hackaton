"""OpenAICompatVLM smoke + payload-shape tests.

The runtime calls `describe(image_b64)`, expecting a string back. We don't
spin up a real vLLM server — instead we patch httpx.AsyncClient.post so the
adapter sees a canned `/v1/chat/completions` response and we can assert the
outgoing request shape.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from hack.models import make_vlm
from hack.models.openai_compat import OpenAICompatVLM


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]


class _FakeClient:
    """Stub httpx.AsyncClient that records the last POST and returns a canned reply."""

    captured: dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None) -> _FakeResponse:
        _FakeClient.captured = {"url": url, "json": json, "headers": headers or {}}
        return _FakeResponse(
            {"choices": [{"message": {"content": '{"objects": [], "scene": "ok"}'}}]}
        )


def test_describe_sends_openai_vision_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hack.models.openai_compat.httpx.AsyncClient", _FakeClient)
    adapter = OpenAICompatVLM(
        model="nvidia/Nemotron-3-Nano-Omni",
        base_url="http://zgx-a:8000/v1",
        prompt="describe the scene",
    )
    out = asyncio.run(adapter.describe("BASE64FRAME"))
    assert out == '{"objects": [], "scene": "ok"}'

    cap = _FakeClient.captured
    assert cap["url"] == "http://zgx-a:8000/v1/chat/completions"
    body = cap["json"]
    assert body["model"] == "nvidia/Nemotron-3-Nano-Omni"
    parts = body["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "describe the scene"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"] == "data:image/jpeg;base64,BASE64FRAME"
    assert body["response_format"] == {"type": "json_object"}


def test_describe_uses_override_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hack.models.openai_compat.httpx.AsyncClient", _FakeClient)
    adapter = OpenAICompatVLM(
        model="m",
        base_url="http://h:8000/v1",
        prompt="default prompt",
    )
    asyncio.run(adapter.describe("X", override_prompt="explicit prompt"))
    parts = _FakeClient.captured["json"]["messages"][0]["content"]
    assert parts[0]["text"] == "explicit prompt"


def test_describe_falls_back_when_choices_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed responses become a truncated JSON dump rather than crashing."""

    class _BadClient(_FakeClient):
        async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None) -> _FakeResponse:
            _FakeClient.captured = {"url": url, "json": json, "headers": headers or {}}
            return _FakeResponse({"unexpected": "shape"})

    monkeypatch.setattr("hack.models.openai_compat.httpx.AsyncClient", _BadClient)
    adapter = OpenAICompatVLM(model="m", base_url="http://h:8000/v1", prompt="p")
    out = asyncio.run(adapter.describe("X"))
    assert "unexpected" in out


def test_make_vlm_resolves_openai_compat() -> None:
    adapter = make_vlm({
        "provider": "openai-compat",
        "model": "nvidia/Nemotron-3-Nano-Omni",
        "base_url": "http://zgx-a:8000/v1",
    }, prompt="describe")
    assert isinstance(adapter, OpenAICompatVLM)
    assert adapter.model == "nvidia/Nemotron-3-Nano-Omni"
    assert adapter.base_url == "http://zgx-a:8000/v1"
    assert adapter.prompt == "describe"


def test_make_vlm_resolves_vllm_alias() -> None:
    adapter = make_vlm({
        "provider": "vllm",
        "model": "nvidia/Nemotron-3-Nano-Omni",
        "base_url": "http://zgx-b:8000/v1",
    })
    assert isinstance(adapter, OpenAICompatVLM)


def test_describe_failover_rotates_on_connect_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """First host raises ConnectError; the adapter should rotate to host-2."""
    adapter = OpenAICompatVLM(
        model="m",
        base_urls=["http://dead:8000/v1", "http://live:8000/v1"],
        prompt="p",
    )
    attempts: list[str] = []

    async def fake_call(base: str) -> str:
        attempts.append(base)
        if "dead" in base:
            raise httpx.ConnectError("refused")
        return f"ok from {base}"

    result = asyncio.run(adapter._request(fake_call))
    assert result == "ok from http://live:8000/v1"
    assert attempts == ["http://dead:8000/v1", "http://live:8000/v1"]
