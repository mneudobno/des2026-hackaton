---
name: zgx-bootstrap
description: Bring up the local LLM/VLM serving stack on an HP ZGX Nano AI Station (DGX OS, Grace Blackwell). Use when the ZGX is cold, models aren't loaded, or `hack serve status` is red.
---

# Bootstrapping serving on a ZGX Nano

Two ZGX Nanos are networked; treat node A as primary (LLM + VLM), node B as secondary (STT/TTS + overflow).

## Steps

1. **SSH into the ZGX** (IP from the event sheet). Confirm: `nvidia-smi`, `docker ps`.
2. **Run** `bash scripts/bootstrap_zgx.sh --role primary` on node A, `--role secondary` on node B. The script:
   - pulls required NIM containers / Ollama models from the local mirror first, registry second
   - starts Ollama on `:11434` and NIM endpoints on the configured ports
   - warms each model with a tiny prompt
3. **From the laptop:** `hack serve status --host <zgx-ip>` — expect all green, tokens/sec reported.
4. **Warm the cache:** `hack serve warmup` fires 3 canned prompts; first-real-request latency drops to steady state.
5. **If a pull fails:** check `docs/zgx_notes.md` for the manual `docker pull` / `ollama pull` fallback list.

## Models (default set)

- **LLM:** `qwen2.5:14b-instruct` (Ollama) or `meta/llama-3.3-70b-instruct` (NIM) if it fits.
- **VLM:** `qwen2.5-vl:7b` or `llama-3.2-vision:11b`.
- **STT:** `faster-whisper large-v3-turbo` on node B.
- **TTS:** `piper` (CPU, low latency).

## If serving is flaky

- Kill everything: `hack serve stop --force`. Restart only the primary node. Run agent with `--llm ollama --vlm ollama` as a fallback.
- If a NIM container wedges, `docker restart <name>` beats rebooting the box.
