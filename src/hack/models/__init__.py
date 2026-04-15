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
from hack.models.openai_compat import OpenAICompatLLM


LLM_ADAPTERS: dict[str, Callable[..., LLMAdapter]] = {
    "ollama": OllamaLLM,
    "gemini": GeminiLLM,
    "openai": OpenAICompatLLM,
    "openai-compat": OpenAICompatLLM,
    # Day-of NIM is OpenAI-compatible; use "openai-compat" with NIM base_url.
    "nim": OpenAICompatLLM,
}

VLM_ADAPTERS: dict[str, Callable[..., VLMAdapter]] = {
    "ollama": OllamaVLM,
    "gemini": GeminiVLM,
}


def make_llm(cfg: dict[str, Any]) -> LLMAdapter:
    name = cfg.get("adapter") or cfg.get("provider") or "ollama"
    if name not in LLM_ADAPTERS:
        raise KeyError(f"unknown LLM adapter {name!r}; known: {sorted(LLM_ADAPTERS)}")
    return LLM_ADAPTERS[name](
        model=cfg["model"],
        base_url=cfg.get("base_url", ""),
        temperature=cfg.get("temperature", 0.3),
        timeout=cfg.get("timeout", 60.0),
        api_key_env=cfg.get("api_key_env", "GEMINI_API_KEY"),
    )


def make_vlm(cfg: dict[str, Any], prompt: str = "") -> VLMAdapter:
    name = cfg.get("adapter") or cfg.get("provider") or "ollama"
    if name not in VLM_ADAPTERS:
        raise KeyError(f"unknown VLM adapter {name!r}; known: {sorted(VLM_ADAPTERS)}")
    return VLM_ADAPTERS[name](
        model=cfg["model"],
        base_url=cfg.get("base_url", ""),
        prompt=prompt or cfg.get("prompt", ""),
        timeout=cfg.get("timeout", 60.0),
        api_key_env=cfg.get("api_key_env", "GEMINI_API_KEY"),
    )


__all__ = ["LLMAdapter", "VLMAdapter", "LLM_ADAPTERS", "VLM_ADAPTERS", "make_llm", "make_vlm"]
