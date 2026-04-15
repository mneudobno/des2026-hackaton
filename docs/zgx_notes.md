# ZGX Nano operating notes

Hardware: NVIDIA GB10 Grace Blackwell, 128 GB unified RAM, 1000 TOPS FP4, DGX OS, 200 Gbps networking. Two boxes per team, paired to your laptop.

> For the conceptual overview (what it is, why we designed the repo this way, sources), see [`zgx_overview.md`](./zgx_overview.md). This doc is the operational cheatsheet.

## First-touch checklist (event day)

1. SSH into box A (primary) and box B (secondary). Note the IPs on a sticky note.
2. `nvidia-smi` on both — confirm GB10 visible, memory free.
3. `docker ps` — list of pre-installed NIM containers (record exact names; substitute below).
4. `ollama list` — see what's already pulled.
5. `df -h` — confirm room for model pulls (Q: 14B ≈ 9 GB, VL 7B ≈ 5 GB).
6. From laptop: `ssh-add` your key, then `hack serve status --host <ip>`.

## Default model set

Two tiers. Try Nemotron via NIM first (it's what NVIDIA ships on DGX OS); fall back to Qwen via Ollama if a container wedges.

**Tier A — NVIDIA-native (primary on ZGX):**

| Slot | Model | Size | Notes |
|------|-------|------|-------|
| Router | `microsoft/phi-3-mini-128k-instruct` (NIM) | ~3.8 B | triage — saves planner invocations |
| LLM (planner) | `nvidia/Nemotron-3-Nano-30B-A3B` (NIM) | ~65 GB | NVIDIA-tuned reasoning, ReAct-friendly |
| VLM | `nvidia/Nemotron-Nano-12B-v2-VL` (NIM) | ~28 GB | matches Reachy playbook |
| STT | `nvidia/riva-parakeet-ctc-1.1B` (Riva) | ~1 GB | gRPC, preinstalled on DGX OS |
| TTS | `hexgrad/Kokoro-82M` | ~400 MB | fast, fluent; what NVIDIA's photo-booth uses |

**Tier B — Ollama fallback (also works on Mac):**

| Slot | Model | Size | Notes |
|------|-------|------|-------|
| LLM | `qwen2.5:14b-instruct` | ~9 GB | ZGX; `qwen2.5:7b` on Mac dev |
| VLM | `qwen2.5vl:7b` (Ollama) / `qwen2.5-vl:7b` (NIM) | ~5 GB | grounded enough for scene parsing |
| STT | `faster-whisper large-v3-turbo` | ~1.5 GB | streaming, multilingual |
| TTS | `piper en_US-amy-medium` | ~60 MB | CPU-only is fine |

## Manual fallbacks (when bootstrap fails)

```bash
# Ollama daemon
nohup ollama serve >/tmp/ollama.log 2>&1 &

# Pull
ollama pull qwen2.5:14b-instruct
ollama pull qwen2.5-vl:7b

# Smoke test LLM
curl -s http://127.0.0.1:11434/api/generate \
  -d '{"model":"qwen2.5:14b-instruct","prompt":"Say hi","stream":false}'

# Smoke test VLM (base64 image)
curl -s http://127.0.0.1:11434/api/generate \
  -d "{\"model\":\"qwen2.5-vl:7b\",\"prompt\":\"What is in this image?\",\"images\":[\"$(base64 -i test.jpg)\"],\"stream\":false}"
```

## Networking

- Laptop ↔ ZGX over Ethernet (200 Gbps per port). Use IPs, not mDNS.
- Open ports needed: 11434 (Ollama), 8000 (hack ui), plus any NIM ports (typically 8000–8001 — verify and remap).
- If NIM port collides with `hack ui`, change with `hack ui --port 8080`.

## NIM container reference (placeholder)

Fill in once we see what's actually preinstalled at the event:

```
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Image}}'
```

Then update `configs/agent.yaml` `llm.provider: openai-compat`, `base_url: http://<zgx-ip>:<port>/v1`.

Expected NIM containers on DGX OS (based on NVIDIA's published playbooks):
- Nemotron-3-Nano-30B-A3B (reasoning LLM)
- Nemotron-Nano-12B-v2-VL (VLM)
- Phi-3-Mini-128K (router)
- Riva Parakeet ASR (STT)
- Kokoro TTS
- FLUX.1-Kontext-dev (image gen — optional, only if the challenge involves visuals)

## NeMo Agent Toolkit (NAT)

If `nat` is on `$PATH` on DGX OS, it's NVIDIA's official agent framework with built-in ReAct, router, and tool-use primitives. Reference config lives at `nat/src/ces_tutorial/config.yml` in the Reachy playbook.

We do **not** rely on NAT — our `hack.agent.runtime` is the source of truth. But if the event environment has NAT preinstalled and a compatible router config for Nemotron, we can crib prompts from it.

Quick check on day-of:
```bash
which nat && nat --help
ls /opt/nvidia/nemo-agent-toolkit 2>/dev/null || true
```

## Latency budget (target)

| Stage | Target | Notes |
|-------|--------|-------|
| Camera → VLM round-trip | <500 ms | downscale to 768 px, FP4 |
| LLM plan | <800 ms | 512 tokens max, JSON mode |
| Tool dispatch | <50 ms | adapter must not block |
| End-to-end perception → action | <1.5 s | everything under this feels alive |

If we miss the budget: drop VLM model size first, then VLM FPS, then LLM max_tokens.
