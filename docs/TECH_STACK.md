---
---

# Tech stack reference — DIS2026X1, 2026-05-08

> **Purpose.** Single reference for every tool and model the organizer
> said is pre-installed. Use it day-of to: (a) confirm what's actually on
> the box, (b) configure our adapters correctly, (c) recover when
> something is missing or different than promised.
>
> **Tone.** Reference, not narrative. Skim for the section you need; ignore
> the rest.

## What the organizer said

From the email received 2026-05-05:

- Hardware: **HP ZGX Nano AI Station** (× 2, on-site).
- Software: **HP ZGX Toolkit**, **NVIDIA AI Enterprise**, **Nemotron**, **vLLM**, **llama.cpp**, **OpenCode** — all pre-installed.
- Models: **NVIDIA Nemotron 3 Nano Omni**, **Qwen 3.6 35B A3B**.
- Schedule: 10:30 kickoff & briefing → 10:50 build → 13:00 submission → 14:00 jury → 14:10 winner.
- Bring: laptop, charger, IDE/SSH/browser.

The exact model tags are not promised; we have to read them from the
box (`curl :8000/v1/models`) on day-of and update our config. The list
above is otherwise authoritative.

---

## 1. Hardware

| Spec | Value |
|---|---|
| Chip | NVIDIA GB10 Grace Blackwell |
| CPU | 20-core ARM (Grace) |
| Unified memory | **128 GB LPDDR5X** (CPU + GPU share, no PCIe copies) |
| AI throughput | ~1000 TOPS @ FP4 |
| Networking | ConnectX-7 200 Gbps + 10 GbE + Wi-Fi 7 |
| OS | NVIDIA DGX OS (Ubuntu-based) |

128 GB unified means a 30B-param multimodal model in NVFP4 (~21 GB) has
**massive headroom** — we'll never be memory-bound on a single box.
For ops detail (recon checklist, port assignments, latency budget), see
[`zgx_notes.md`](./zgx_notes.md).

---

## 2. Software stack — one table

| Tool | Day-of disposition | Why |
|---|---|---|
| **vLLM** | ✅ primary inference engine | Serves Nemotron + Qwen on `:8000/v1`. Our `OpenAICompatLLM` / `OpenAICompatVLM` are the consumers. |
| **NVIDIA AI Enterprise / NIM** | ✅ supplementary (if vLLM is the only thing running, this is moot; if separate NIM containers exist, we can pivot to them) | OpenAI-compatible HTTP. Same adapter works. |
| **Nemotron 3 Nano Omni** | ✅ default LLM **and** VLM | Multimodal (text + image + audio + video → text). Single endpoint. |
| **Qwen 3.6 35B A3B** | ⚠ verify; LLM-only fallback | Text + image only, no audio. Sampling-sensitive. |
| **llama.cpp `llama-server`** | 🟡 fallback (not auto-detected by us) | Speaks `/v1/chat/completions` on `:8080` by default. Manual config swap if needed. |
| **HP ZGX Toolkit** | ⚪ ignore (forced) | VS Code extension. **x86-only** (Windows 11 / Ubuntu 24.04 — not Mac). Decision is structural, not preferential. We use SSH + our own bootstrap. |
| **OpenCode** (`sst/opencode`) | ⚪ ignore | TUI coding agent. We use Claude Code. |
| **Ollama** (laptop AND ZGX) | ✅ multi-tier fallback | Pre-installed on Timur's laptop AND **also pre-installed on the ZGX** by the HP ZGX Toolkit defaults (per HP's onboard docs). Tertiary fallback if both vLLM and llama-server are down on the ZGX. |

---

## 3. Inference engines

### 3.1 vLLM (primary)

- **Default port**: `8000`. All models served via OpenAI-compatible API.
- **Endpoints we use**:
  - `GET /v1/models` — list of served model `id`s. Source of truth for what to put in `model:` field.
  - `POST /v1/chat/completions` — text completion + multimodal.
- **Payload shape** (text):
  ```json
  {"model":"<id>","messages":[{"role":"user","content":"…"}],
   "temperature":0.3,"max_tokens":512,"response_format":{"type":"json_object"}}
  ```
- **Payload shape** (multimodal — what `OpenAICompatVLM` sends):
  ```json
  {"model":"<id>","messages":[{"role":"user","content":[
    {"type":"text","text":"describe this scene"},
    {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,…"}}
  ]}],"max_tokens":256,"response_format":{"type":"json_object"}}
  ```
- **Adapter in our repo**: `src/hack/models/openai_compat.py` →
  `OpenAICompatLLM` and `OpenAICompatVLM`.
- **Bootstrap probe**: `scripts/bootstrap_zgx.sh` curls `:8000/v1/models`
  before doing anything else; if vLLM responds, Ollama install is skipped.

### 3.2 llama.cpp `llama-server` (fallback)

- **Default port**: `8080` — collides with our `hack ui` default; if we
  pivot to llama-server, run `hack ui --port 8081`.
- **OpenAI-compatible**: yes — same `/v1/chat/completions` shape, so
  `OpenAICompatLLM`/`OpenAICompatVLM` work unchanged.
- **Throughput note**: single-threaded sequential request handling. If
  the agent fires concurrent VLM + LLM calls on the same llama-server,
  they queue. vLLM batches them. Latency hit is real — assume +30-50%
  per tick.
- **Quantisation**: GGUF only. Day-of, the model files (`.gguf`) live
  somewhere on the ZGX; if vLLM is dead and llama-server is the
  fallback, find them with `find / -name '*.gguf' 2>/dev/null | head`.
- **Pivot config**: see `configs/agent.llama-server.yaml` (just a base_url
  swap from `:8000/v1` to `:8080/v1`).

### 3.3 Ollama (laptop AND ZGX)

- **Default port**: `11434`. Pre-installed on Timur's laptop (Mac dev) **and** on the ZGX (per HP ZGX Toolkit defaults).
- **Endpoints**: `/api/generate` (text), `/api/generate` with `images: []`
  (multimodal). Different shape from OpenAI; `OllamaLLM`/`OllamaVLM`
  handle it.
- **When we use it**:
  - **Laptop** — rehearsals + ultimate fallback if both ZGX boxes are unreachable.
  - **ZGX** — tertiary fallback if both vLLM (`:8000/v1`) and llama-server (`:8080/v1`) are down on the ZGX. Probe with `curl http://<zgx>:11434/api/tags`.
- **Models on the laptop**: `qwen2.5:7b`, `qwen2.5vl:7b`, `phi3:mini`,
  `qwen2.5:1.5b` (verify with `ollama list`).
- **Models on the ZGX**: unknown until day-of — run `curl http://<zgx>:11434/api/tags | jq -r '.models[].name'` to enumerate.

---

## 4. Models

### 4.1 NVIDIA Nemotron 3 Nano Omni

| Property | Value |
|---|---|
| HF tag (most likely served) | `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4` |
| Alternative quants on HF | `…-BF16` (62 GB), `…-FP8` (33 GB), `…-NVFP4` (21 GB) |
| Architecture | 30B-param MoE (~3B active, A3B); Mamba2 + attention hybrid |
| Modalities (in) | Text, image, audio, video |
| Modalities (out) | Text only |
| Context window | 256k native (extensible to ~1M via YaRN) |
| Tool calling / JSON mode | ✅ both supported |
| **Reasoning** | **ON by default** — adds CoT tokens; toggle with `extra_body: {chat_template_kwargs: {enable_thinking: false}}` |
| vLLM flags worth knowing | `--trust-remote-code`, `--reasoning-parser nemotron_v3`, `--tool-call-parser qwen3_coder` |
| Endpoint sharing | All modalities share `/v1/chat/completions` — no separate vision endpoint |

**Our config (in `configs/agent.zgx-nim.yaml`)**: both LLM and VLM point
at the same Omni endpoint. Update the model tag to whatever
`/v1/models` reports.

**Multimodal payload shape**: standard OpenAI vision content array
(`{type:text, text:…}` + `{type:image_url, image_url:{url:"data:image/jpeg;base64,…"}}`).
Our `OpenAICompatVLM.describe()` already does this.
For audio: `{type:audio_url, audio_url:{url:"file://…"}}`. We don't ship
an audio adapter today — would need 50 lines if the challenge demands it.

**Sampling defaults that work**: temperature 0.2–0.4, top_p 0.95.
Our planner default of 0.3 is fine.

**Known weaknesses**:
1. **Reasoning latency**: with thinking on, simple tool dispatch ("move
   forward 0.5m") takes 2-3× longer than necessary. Disable for the
   planner via `extra_body` (see Optional fix A below) when latency
   matters.
2. **Vision-prefill VRAM** with dense video (≥ 64 frames) can blow up.
   Stick to ≤ 64 frames at ≤ 2 fps for any multi-frame VLM call.
3. **No audio out** — pipe TTS through Piper/Kokoro on the laptop.

### 4.2 Qwen 3.6 35B A3B

| Property | Value |
|---|---|
| HF tag (most likely served) | `Qwen/Qwen3.6-35B-A3B-FP8` (or unquantised BF16) |
| Architecture | 35B-param MoE; ~8B effective active (8 experts + 1 shared per token) |
| Modalities (in) | Text, image |
| Modalities (out) | Text only |
| Context window | 262k native |
| Tool calling / JSON mode | ✅ both supported, but tool calling is **fragile** under MoE routing — prefer plain JSON-mode |
| Sampling **(important — don't use 0.3)** | Instruct: `temperature: 0.7, top_p: 0.8, presence_penalty: 1.5`. Thinking: `temperature: 1.0, top_p: 0.95, presence_penalty: 0.0` |
| vLLM flags | `--reasoning-parser qwen3`, `--tool-call-parser qwen3_coder`, `--dtype bfloat16 --kv-cache-dtype fp8` if FP8 |

**When we'd use it**: Nemotron Omni is the default. Qwen is the fallback
if Nemotron's vision is broken or if the served endpoint only has Qwen.
For text-only tasks (planning, dialogue) Qwen is competitive; for vision
it's weaker than Omni's C-RADIOv4 encoder.

**Our config**: not currently a primary profile. To swap mid-build, ask
Claude *"swap LLM to Qwen"* — the `swap-llm` skill knows the right block
(see `configs/agent.yaml` profile C).

**Known weaknesses**:
1. **Sampling sensitivity** — see table. Default `temperature: 0.3` will
   produce safe, generic answers. Override per-mode.
2. **No audio/video** — if vision is the only modality available, plus
   Qwen, plan for it. If audio is essential, fall back to laptop Ollama.
3. **Tool-call instability under MoE** — for our planner, use
   `response_format: {"type": "json_object"}` and parse JSON, don't rely
   on OpenAI-style function calling.

---

## 5. NVIDIA AI Enterprise / NIM containers

If vLLM isn't the front door, the same models may be served via NIM
containers — different process, same OpenAI-compatible HTTP shape.

**Enumerate on the box**:
```
podman ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Image}}'   # docker is NOT installed on the ZGX (Podman is the container engine, per HP defaults)
```

NIMs we'd care about:
- LLM/VLM NIM (Nemotron) — usually `:8000/v1` or `:8001/v1`.
- Riva Parakeet (STT) — gRPC `:50051`. Our STT path defaults to
  `faster-whisper` on the laptop; switch only if Riva is a clear win.
- Kokoro / Piper TTS — sometimes containerised. Day-of we'd just keep
  Piper on the laptop; less to configure.

**Adapter mapping**: same adapter (`OpenAICompatLLM` / `OpenAICompatVLM`).
Just point `base_url` at whatever port the NIM exposes.

**Auth**: NIM usually wants a bearer token in `NIM_API_KEY`. Local-only
hackathon NIMs may not enforce auth. Either way our adapter accepts
`api_key_env: NIM_API_KEY` and sends `Authorization: Bearer …` only if
the env var is set.

---

## 6. Tools we ignore (and why)

### HP ZGX Toolkit

A VS Code extension that automates Python venv setup, Ollama install,
PyTorch, JupyterLab, MLFlow, etc. on Windows 11 / Ubuntu 24.04 client
laptops (per HP's onboard docs). It runs on the **client**, not the
server, and explicitly **does not support macOS** — so even if we
wanted it, we couldn't use it. Side-effect of the ZGX shipping with the
toolkit's defaults pre-installed: **the ZGX itself has Ollama, Podman,
PyTorch, uv, MLFlow, JupyterLab, Streamlit, Gradio, OpenWebUI** ready
to go. We don't need any of those for our flow, but Ollama-on-ZGX is
the tertiary fallback noted in §3.

### OpenCode (`sst/opencode`)

Open-source TUI coding agent (Go-based, provider-agnostic). Could in
principle hit the ZGX vLLM as its backend and act as a Claude Code
substitute on the box itself. We don't need this — Claude Code on the
laptop talks to the ZGX over SSH/HTTP just fine, and we have skills,
hooks, and permissions invested in it. Ignore.

If a teammate genuinely wants to play with OpenCode (e.g., as an SSH
pair-programming session on the ZGX), the install is one line:
`curl -fsSL https://opencode.ai/install | bash`. Configure backend to
`http://localhost:8000/v1` and pick whatever model `/v1/models` reports.

---

## 7. Day-of verification punch-list

Run these in the **first 5 minutes** on the ZGX. Replace `<zgx>` with
the actual host or IP from organizer-provided sticky notes.

```bash
# 1. GPU + driver visible
nvidia-smi

# 2. What's running
podman ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Image}}'   # docker is NOT installed on the ZGX (Podman is the container engine, per HP defaults)

# 3. vLLM endpoint up + models served (THE most important check)
curl -s http://<zgx>:8000/v1/models | jq '.data[].id'

# 4. Nemotron text + JSON sanity
curl -s -X POST http://<zgx>:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"<paste exact id from step 3>",
       "messages":[{"role":"user","content":"Return JSON: {\"ok\":true}"}],
       "response_format":{"type":"json_object"},
       "max_tokens":32}' \
  | jq '.choices[0].message.content'

# 5. Nemotron vision sanity (use a tiny test image)
B64=$(base64 -i /tmp/test.jpg | tr -d '\n')
curl -s -X POST http://<zgx>:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d "{\"model\":\"<id>\",\"messages\":[{\"role\":\"user\",\"content\":[
        {\"type\":\"text\",\"text\":\"Describe in 10 words.\"},
        {\"type\":\"image_url\",\"image_url\":{\"url\":\"data:image/jpeg;base64,$B64\"}}]}],
        \"max_tokens\":64}" | jq '.choices[0].message.content'

# 6. (If only Qwen is served) — JSON sanity with the right temperature
curl -s -X POST http://<zgx>:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"<qwen id>",
       "messages":[{"role":"user","content":"Return JSON: {\"ok\":true}"}],
       "response_format":{"type":"json_object"},
       "temperature":0.7,"max_tokens":32}' \
  | jq '.choices[0].message.content'

# 7. First-token latency baseline (single quick prompt; eye the wall-clock)
time curl -s -X POST http://<zgx>:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"<id>","messages":[{"role":"user","content":"hi"}],"max_tokens":4}' \
  >/dev/null

# 8. Disk + memory headroom
df -h / && free -h
```

If step 3 fails: vLLM is down or on a different port. Try `:8080`
(llama-server) and `:8001`. If both fail, ask on-site support before
touching anything.

If step 5 returns garbage but step 4 is fine: Nemotron vision is broken
(or the model loaded is text-only). Pivot: keep LLM on Nemotron, swap
VLM to laptop Ollama (`provider: ollama`, `model: qwen2.5vl:7b`,
`base_url: http://localhost:11434`).

If step 7 latency > 1.5s for 4 tokens: reasoning is hurting us. See
known weakness #1 above; disable thinking via `extra_body`.

---

## 8. Known weaknesses + mitigations

| Risk | Symptom | Mitigation |
|---|---|---|
| Nemotron reasoning latency | Tool dispatch takes 2-3× longer than expected | Disable thinking for the planner: `extra_body: {chat_template_kwargs: {enable_thinking: false}}` (needs adapter support — see Optional A) |
| Qwen sampling defaults wrong | Generic, safe-but-wrong answers; planner picks wrong tool | Override `temperature` per-mode: 0.7 instruct, 1.0 thinking. The `swap-llm` skill knows. |
| llama-server queueing | VLM and LLM calls block each other; latency tail | Avoid in concurrent paths; if you must use it, set `agent.tick_hz: 3` to widen the budget |
| Wrong model tag in YAML | `404 model not found` from vLLM | Always paste from `/v1/models` step 3, never from this doc verbatim |
| Vision endpoint missing | Step 5 fails | Fall back to laptop Ollama VLM (see Pivot block above) |
| Both ZGX boxes unreachable | All steps fail from laptop | Run everything on Ollama laptop — `provider: ollama` for both LLM and VLM. Single rehearsal proves it. |

---

## 9. Cross-references

- **[`REF.md`](./REF.md)** — printable command card for the day.
- **[`zgx_notes.md`](./zgx_notes.md)** — hardware ops detail, network, latency budget.
- **[`day_of_playbook.md`](./day_of_playbook.md)** — minute-by-minute strategy.
- **[`DAY_OF_DECISIONS.md`](./DAY_OF_DECISIONS.md)** — brief → repo edits matrix.
- **[`scripts/bootstrap_zgx.sh`](../scripts/bootstrap_zgx.sh)** — what we run first on the ZGX.
- **[`configs/agent.yaml`](../configs/agent.yaml)** — Mac dev profile + commented day-of profiles.
- **[`configs/agent.zgx-nim.yaml`](../configs/agent.zgx-nim.yaml)** — ZGX vLLM/NIM profile.
- **[`configs/agent.llama-server.yaml`](../configs/agent.llama-server.yaml)** — llama-server fallback profile.
- **[`src/hack/models/openai_compat.py`](../src/hack/models/openai_compat.py)** — adapter source.
- **`/swap-llm`** skill — pivot LLM/VLM mid-build with a smoke test.
- **`/recon-summary`** skill — turn `hack recon` JSON into a config decision.
