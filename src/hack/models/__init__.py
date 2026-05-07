"""Pluggable model adapters — same pattern as hack.robot.

Every model-facing call (LLM text completion, VLM image-text) routes through
an adapter implementing a tiny interface. Runtime code never mentions providers
directly; it calls `make_llm(cfg)` / `make_vlm(cfg)` and works with the returned
adapter instance.

Day-of swap: edit `configs/agent.*.yaml` `llm.adapter` / `vlm.adapter` — no code
changes. New providers: add a file under this package, register in ADAPTERS.
"""

from __future__ import annotations

from typing import Any, Callable

from hack.models.base import LLMAdapter, VLMAdapter
from hack.models.gemini import GeminiLLM, GeminiVLM
from hack.models.ollama import OllamaLLM, OllamaVLM
from hack.models.openai_compat import OpenAICompatLLM, OpenAICompatVLM


LLM_ADAPTERS: dict[str, Callable[..., LLMAdapter]] = {
    "ollama": OllamaLLM,
    "gemini": GeminiLLM,
    "openai": OpenAICompatLLM,
    "openai-compat": OpenAICompatLLM,
    # Day-of vLLM/NIM are both OpenAI-compatible; use "openai-compat".
    "vllm": OpenAICompatLLM,
    "nim": OpenAICompatLLM,
}

def _make_mock_vlm(**kwargs: object) -> VLMAdapter:
    from hack.models.mock_vlm import MockVLM
    return MockVLM(**{k: v for k, v in kwargs.items() if k in ("model", "base_url", "base_urls", "prompt", "timeout", "api_key_env")})


VLM_ADAPTERS: dict[str, Callable[..., VLMAdapter]] = {
    "ollama": OllamaVLM,
    "gemini": GeminiVLM,
    "openai": OpenAICompatVLM,
    "openai-compat": OpenAICompatVLM,
    "vllm": OpenAICompatVLM,
    "nim": OpenAICompatVLM,
    "mock": _make_mock_vlm,
}


def _resolve_hosts(cfg: dict[str, Any]) -> list[str]:
    """Normalise `base_url` (scalar) + `base_urls` (list) into a single list.
    Order is preserved; duplicates dropped; `base_url` takes precedence as the
    primary when both are provided."""
    urls: list[str] = []
    primary = cfg.get("base_url", "")
    if primary:
        urls.append(primary)
    for u in cfg.get("base_urls", []) or []:
        if u and u not in urls:
            urls.append(u)
    return urls


def make_llm(cfg: dict[str, Any]) -> LLMAdapter:
    name = cfg.get("adapter") or cfg.get("provider") or "ollama"
    if name not in LLM_ADAPTERS:
        raise KeyError(f"unknown LLM adapter {name!r}; known: {sorted(LLM_ADAPTERS)}")
    urls = _resolve_hosts(cfg)
    return LLM_ADAPTERS[name](
        model=cfg["model"],
        base_url=urls[0] if urls else "",
        base_urls=urls,
        temperature=cfg.get("temperature", 0.3),
        timeout=cfg.get("timeout", 60.0),
        api_key_env=cfg.get("api_key_env", "GEMINI_API_KEY"),
    )


def make_vlm(cfg: dict[str, Any], prompt: str = "") -> VLMAdapter:
    name = cfg.get("adapter") or cfg.get("provider") or "ollama"
    if name not in VLM_ADAPTERS:
        raise KeyError(f"unknown VLM adapter {name!r}; known: {sorted(VLM_ADAPTERS)}")
    urls = _resolve_hosts(cfg)
    return VLM_ADAPTERS[name](
        model=cfg["model"],
        base_url=urls[0] if urls else "",
        base_urls=urls,
        prompt=prompt or cfg.get("prompt", ""),
        timeout=cfg.get("timeout", 60.0),
        api_key_env=cfg.get("api_key_env", "GEMINI_API_KEY"),
    )


__all__ = ["LLMAdapter", "VLMAdapter", "LLM_ADAPTERS", "VLM_ADAPTERS", "make_llm", "make_vlm"]
