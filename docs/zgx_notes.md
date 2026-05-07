# ZGX Nano operating notes

Hardware: NVIDIA GB10 Grace Blackwell, 128 GB unified RAM, 1000 TOPS FP4, DGX OS, 200 Gbps networking. Two boxes per team, paired to your laptop.

## What it is

The HP ZGX Nano packages an **NVIDIA DGX Spark reference design** into a desktop chassis. Instead of renting a cloud GPU, you put a compact AI box on a desk, SSH in from a laptop over Ethernet, and run the whole ML stack locally. The killer spec is **128 GB unified memory**: GPU addresses it without PCIe copies, so models up to ~200B params (FP4) fit on one box, and you can chain two via the 200 Gbps fabric. The OS is **NVIDIA DGX OS** (Ubuntu-based, NVIDIA AI stack pre-loaded). Each box exposes inference over an OpenAI-compatible HTTP API — `base_url: http://<zgx>:<port>/v1`.

```
 ┌──────────┐   200 Gbps   ┌────────────┐
 │ your Mac │ ───────────▶ │ ZGX Nano A │  ← primary: LLM + VLM (vLLM / NIM / Ollama)
 │ (agent,  │              └────────────┘
 │  TUI,    │   200 Gbps   ┌────────────┐
 │  robot)  │ ───────────▶ │ ZGX Nano B │  ← secondary: STT / TTS / overflow
 └──────────┘              └────────────┘
```

No component runs in the cloud during the judged run. That's both a rule ("local AI hardware") and a design win (no latency tail, no API key juggling).

## First-touch checklist (event day)

1. SSH into box A (primary) and box B (secondary). Note the IPs on a sticky note.
2. `nvidia-smi` on both — confirm GB10 visible, memory free.
3. `podman ps` — list of pre-installed containers (record exact names; substitute below). The ZGX uses **Podman**, not Docker, per the HP ZGX Toolkit's defaults.
4. `ollama list` — see what's already pulled.
5. `df -h` — confirm room for model pulls (Q: 14B ≈ 9 GB, VL 7B ≈ 5 GB).
6. From laptop: `ssh-add` your key, then `hack serve status --host <ip>`.

## Default model set

Two tiers. Day-of (per organizer email 2026-05-05) the ZGX boxes ship with **vLLM + llama.cpp + Nemotron + OpenCode pre-installed** and serve on `:8000/v1`. Try the vLLM endpoint first; fall back to Qwen via Ollama only if it's wedged.

**Tier A — vLLM on ZGX (primary, day-of):**

| Slot | Model | Size | Notes |
|------|-------|------|-------|
| LLM + VLM (one endpoint) | `nvidia/Nemotron-3-Nano-Omni` (vLLM) | ~30 B class | **multimodal** — single `/v1/chat/completions` route fills both planner and vision slots. Confirm the exact tag with `curl http://<zgx>:8000/v1/models` at event start. |
| LLM (alt) | `Qwen/Qwen3-…-A3B` (vLLM) | 35 B params, ~3 B active | MoE; LLM-only. Use if Omni's vision is weak/unavailable. |
| Router | `microsoft/phi-3-mini-128k-instruct` (Ollama) | ~3.8 B | optional triage on the laptop — only enable if challenge is conversational |
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
- Open ports needed: **8000 (vLLM, day-of primary)**, 11434 (Ollama, fallback), 8000 again on the laptop for `hack ui` — collision risk; use `hack ui --port 8080` if the ZGX vLLM is reached on its own host.
- Verify endpoint at event start: `curl http://<zgx>:8000/v1/models` — the response lists exact model tags.

## Pre-installed serving stack (organizer email 2026-05-05)

ZGX boxes ship with: **HP ZGX Toolkit, NVIDIA AI Enterprise, Nemotron, vLLM, llama.cpp, OpenCode**. Two models are pre-loaded:

- **NVIDIA Nemotron 3 Nano Omni** — multimodal (text + vision); fills both LLM and VLM slots from one `/v1/chat/completions` endpoint.
- **Qwen 3.6 35B A3B** — text-only; MoE-style with ~3B active parameters; alternative LLM.

Quick on-site checks:
```bash
curl -s http://localhost:8000/v1/models | jq .          # list served models
podman ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Image}}'   # see container layout (NOT docker — ZGX uses Podman)
```

Then update `configs/agent.yaml` `llm.provider: openai-compat`, `model: <id from above>`, `base_url: http://<zgx-ip>:8000/v1`.

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
