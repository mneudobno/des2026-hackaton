---
name: swap-llm
description: Swap or first-time-adopt the LLM/VLM provider/model/base_url in configs/agent.yaml and smoke-test it. Trigger on "swap LLM", "swap VLM", "switch model", "use Nemotron / Qwen / Ollama", "flip to ZGX-B", "fall back to laptop VLM", "the ZGX endpoint changed", "lock in the config", "adopt the real setup", "first-time adoption". Use for first-time config adoption (placeholders → real ZGX IPs and model tags) AND for mid-build pivots.
---

# swap-llm — adopt or pivot inference without touching runtime

The runtime never references providers directly — `make_llm(cfg['llm'])` and
`make_vlm(cfg['vlm'])` resolve from `configs/agent.yaml`. Your job is to:

1. Decide which mode you're in (see below).
2. Identify what to write (LLM, VLM, or both; provider, model, base_url, extra_body).
3. Edit only `configs/agent.yaml` (or a copy: `configs/agent.local.yaml`, gitignored).
4. Smoke-test with one tiny request and a rehearsal.
5. Tell the user what you changed and what to do if it doesn't work.

## Two modes

### Mode A — First-time adoption ("lock in the config")

Triggered by *"lock in the config"*, *"adopt the real setup"*, *"first-time
adoption"*, or any phrasing that means "we just got the real IPs and model
tags, write them into the YAML now". This is the one moment placeholders
in `configs/agent.yaml` (`<zgx-a>`, `<vllm-tag-from-/v1/models>`, etc.)
become live values.

Procedure:
1. **Read what we know already.** In order:
   - `runs/recon-latest.json` — for `<zgx-a>` / `<zgx-b>` IPs (machine-authoritative).
   - The latest `day-of-brief` skill output (if visible in the conversation) — for the chosen adapter, safety limits, and any audio/video constraints.
   - `docs/DAY_OF_BRIEF.md` — fallback if the brief skill output is gone.
   - `configs/agent.yaml` — current state; you'll write to it, not start fresh.
2. **Probe vLLM live** to learn the actual model id:
   ```
   curl -s http://<zgx-a>:8000/v1/models | jq -r '.data[].id'
   ```
   Use the FIRST id returned (or the multimodal one if both Nemotron and
   Qwen show up — Nemotron's id is preferred because it's the default
   profile).
3. **Pick the profile** from §"Common pivots" below based on what
   `/v1/models` shows. Profile A (Nemotron Omni multimodal) is the default
   if Omni is served; profile C (Qwen LLM-only) if only Qwen; profile D
   (laptop Ollama) if neither answers.
4. **Write `configs/agent.yaml`** end-to-end with:
   - `llm.base_url` and `llm.base_urls` ← real ZGX-A, real ZGX-B
   - `llm.model` ← exact id from `/v1/models`
   - `vlm.base_url` and `vlm.model` ← same endpoint if multimodal, otherwise laptop fallback
   - `robot.adapter` ← from the brief skill output
   - `robot.safety.max_*` ← from the brief if specified
   - For Nemotron LLM, ADD `extra_body: {chat_template_kwargs: {enable_thinking: false}}` to skip CoT on the planner (vision keeps reasoning).
5. **Smoke test** in this exact order:
   ```
   uv run hack doctor                                          # vllm :8000/v1 row green
   uv run hack rehearse --scenario obstacle-corridor          # ~6s; expect grade A
   ```
6. **Report**: what you wrote (4-line diff summary), the rehearsal result,
   and the next thing to do (start `hack tui` and call "where am I").

### Mode B — Mid-build pivot

Triggered by *"swap LLM"*, *"swap VLM"*, *"flip to ZGX-B"*, *"fall back to
laptop VLM"*, etc. The config already has live values — we're swapping one
or two specific fields without rewriting everything.

Procedure: identify what changed (provider? model? base_url? extra_body?),
update only those fields, smoke-test, report.

## Common pivots and their config blocks

**Discover what the vLLM endpoint actually serves first** — the model tag in
the email may not match what's loaded:
```
curl -s http://<zgx-a>:8000/v1/models | jq '.data[].id'
```

### A. Mac dev → ZGX vLLM Nemotron Omni (multimodal, fills BOTH llm + vlm)
```yaml
llm:
  provider: openai-compat
  model: <id from /v1/models — likely "nvidia/Nemotron-3-Nano-Omni" or similar>
  base_url: http://<zgx-a-ip>:8000/v1
  base_urls: [http://<zgx-b-ip>:8000/v1]   # failover
vlm:
  provider: openai-compat
  model: <same Omni id>
  base_url: http://<zgx-a-ip>:8000/v1
```

### B. Same as A but VLM lives on the laptop (Omni vision unusable)
```yaml
vlm:
  provider: ollama
  model: qwen2.5vl:7b
  base_url: http://localhost:11434
```

### C. ZGX vLLM Qwen 3.6 35B A3B (LLM only — Omni endpoint dead)
```yaml
llm:
  provider: openai-compat
  model: <qwen id from /v1/models>
  base_url: http://<zgx-a-ip>:8000/v1
```
(Keep `vlm.provider: ollama` on laptop with qwen2.5vl:7b.)

### D. Total fallback — Mac dev (vLLM down on both ZGX boxes)
```yaml
llm:
  provider: ollama
  model: qwen2.5:7b
  base_url: http://localhost:11434
vlm:
  provider: ollama
  model: qwen2.5vl:7b
  base_url: http://localhost:11434
```

### E. Latency too high → smaller model
- Drop LLM `max_tokens` to 256 (planner won't ramble).
- For Ollama LLM: try `qwen2.5:1.5b` (already on laptop per `ollama list`).
- For vLLM: there's nothing smaller served by default; instead lower `agent.tick_hz` from 5 to 3.

## Smoke test (run after every swap)

1. **Doctor first** — `uv run hack doctor`. The `vllm :8000/v1` row should show served models if you swapped to vLLM; the `ollama :11434` row should show 200 if you fell back to Ollama.
2. **Warmup** — `uv run hack serve warmup --host <host>`. Expect 3× HTTP 200 in under 5s.
3. **End-to-end** — `uv run hack rehearse --scenario obstacle-corridor`. Should complete in ~5 ticks with grade A and 0 collisions on the laptop. On the ZGX, also acceptable but watch latency.
4. **VLM-specific check** if you swapped VLM — observation events in the trace should have non-empty `objects` and `scene` fields. Tail the JSONL: `tail -f runs/rehearsal-*.jsonl | jq -r 'select(.event=="vlm.observation") | .data.scene'`.

## Failure modes and what to do

| Symptom | Likely cause | Fix |
|---|---|---|
| `404 model not found` | Model tag in YAML doesn't match what vLLM serves | Re-run `curl :8000/v1/models`, paste the exact `id` |
| `ConnectError` on first call | Wrong host, wrong port, or vLLM not up | `curl http://<host>:<port>/v1/models` from the laptop; if it fails, the network is the issue, not the config |
| VLM responses are gibberish or one-line | Multimodal model not actually loaded; vLLM running text-only | Switch `vlm` block to profile B (Ollama qwen2.5vl on laptop) |
| Latency spikes after swap | New model is slower; tick budget exceeded | Drop `agent.tick_hz` to 3 OR shrink `vlm.frame_fps` to 1 |
| Both ZGX hosts unreachable | Switch died, IPs reassigned | Flip to profile D (laptop-only) — hackathon mode |

## What to tell the user when done

A 4-line report:
- What changed (file + key + old→new value).
- Result of the smoke test (pass/fail + key metric).
- Latency observed if vLLM (mean/p95 from `hack rehearse` table).
- Next action (commit, or revert, or escalate to cut-list).

Never silently apply a swap if the smoke test fails. Roll back and report.
