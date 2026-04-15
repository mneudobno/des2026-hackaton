# ZGX Nano operating notes

Hardware: NVIDIA GB10 Grace Blackwell, 128 GB unified RAM, 1000 TOPS FP4, DGX OS, 200 Gbps networking. Two boxes per team, paired to your laptop.

## First-touch checklist (event day)

1. SSH into box A (primary) and box B (secondary). Note the IPs on a sticky note.
2. `nvidia-smi` on both — confirm GB10 visible, memory free.
3. `docker ps` — list of pre-installed NIM containers (record exact names; substitute below).
4. `ollama list` — see what's already pulled.
5. `df -h` — confirm room for model pulls (Q: 14B ≈ 9 GB, VL 7B ≈ 5 GB).
6. From laptop: `ssh-add` your key, then `hack serve status --host <ip>`.

## Default model set

| Slot | Model | Size | Notes |
|------|-------|------|-------|
| LLM (primary) | `qwen2.5:14b-instruct` | ~9 GB | fast, good tool-use |
| LLM (large) | `meta/llama-3.3-70b-instruct` (NIM) | ~40 GB | only if NIM container present |
| VLM | `qwen2.5vl:7b` (Ollama tag — no dash) / `qwen2.5-vl:7b` (NIM) | ~5 GB | grounded enough for scene parsing |
| VLM (alt) | `llama-3.2-vision:11b` | ~7 GB | better captions, slower |
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

Then update `configs/agent.yaml` `llm.provider: nim`, `base_url: http://<zgx-ip>:<port>/v1` and use OpenAI-compatible client.

## Latency budget (target)

| Stage | Target | Notes |
|-------|--------|-------|
| Camera → VLM round-trip | <500 ms | downscale to 768 px, FP4 |
| LLM plan | <800 ms | 512 tokens max, JSON mode |
| Tool dispatch | <50 ms | adapter must not block |
| End-to-end perception → action | <1.5 s | everything under this feels alive |

If we miss the budget: drop VLM model size first, then VLM FPS, then LLM max_tokens.
