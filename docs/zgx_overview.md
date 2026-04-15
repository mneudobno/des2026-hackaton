# HP ZGX Nano AI Station — overview

This doc is the **conceptual** intro to the hardware we'll be running on at DIS2026X1. For hands-on commands, latency budgets, and troubleshooting, see `zgx_notes.md`.

## What it is (one paragraph)

The HP ZGX Nano G1n AI Station is a desktop-sized AI workstation that packages an **NVIDIA DGX Spark reference design** into an HP chassis. Instead of renting a cloud GPU, you put a compact AI box on a desk, SSH into it from a laptop over Ethernet, and run the whole ML stack — training, fine-tuning, inference, edge deployment — locally. Think "personal DGX," not "bigger workstation."

## What's inside

| Component | Spec |
|---|---|
| Chip | **NVIDIA GB10 Grace Blackwell Superchip** |
| CPU | 20-core ARM (Grace) |
| GPU | Blackwell generation, unified with CPU via NVLink-C2C |
| Unified memory | **128 GB LPDDR5X** (CPU + GPU share this pool) |
| AI throughput | **~1000 TOPS at FP4** |
| Storage | 1 or 4 TB NVMe M.2, self-encrypting |
| Networking | **ConnectX-7 @ 200 Gbps per port**, 10 GbE RJ45, Wi-Fi 7 |
| OS | **NVIDIA DGX OS** (Ubuntu-based, pre-loaded with the NVIDIA AI stack) |

The killer spec is **128 GB of unified memory**: the GPU can address it without PCIe copies, so models up to ~200B parameters (FP4) fit on one box, and you can chain two via the 200 Gbps fabric to get to ~400B. For comparison, a single H100 has 80 GB discrete VRAM and you pay a PCIe tax on every batch.

## Mental model for hackathon work

Think of each ZGX as a **local inference appliance** you talk to over HTTP:

```
 ┌──────────┐   200 Gbps   ┌────────────┐
 │ your Mac │ ───────────▶ │ ZGX Nano A │  ← primary: LLM + VLM (NIM / Ollama)
 │ (agent   │              └────────────┘
 │  runtime,│   200 Gbps   ┌────────────┐
 │  UI,     │ ───────────▶ │ ZGX Nano B │  ← secondary: STT / TTS / overflow
 │  robot)  │              └────────────┘
 └──────────┘
```

- **Your laptop** owns the clock: it holds the agent runtime (`hack agent run`), the dashboard, the robot connection, sensors. It is the orchestrator.
- **ZGX A** is the brain: large LLM + VLM over an OpenAI-compatible / Ollama API.
- **ZGX B** is the ears and voice: Whisper for STT, Piper/Kokoro for TTS, plus any overflow inference you can't fit on A.

No component runs in the cloud during the judged run. That's both a rule ("local AI hardware") and a design win (no latency tail, no API key juggling).

## Software stack (what's preloaded on DGX OS)

Verified at event time, but DGX OS typically ships with:

- **CUDA** matching the Blackwell driver
- **Docker** with NVIDIA Container Toolkit
- A curated set of **NVIDIA NIM** microservice containers (LLM / VLM / ASR / retrieval). These are OpenAI-API-compatible — `base_url: http://<zgx>:<port>/v1`.
- **Triton Inference Server** for custom models
- The standard Python + PyTorch + Transformers combo in a user venv

Our bootstrap script (`scripts/bootstrap_zgx.sh`) adds **Ollama** as a low-friction fallback so we're never blocked on a NIM container misbehaving.

## Why this matters for "Just Build"

The evaluation rewards **hardware utilization**, **sensor integration**, and **agent quality**. The ZGX shape of the system dictates three practical choices baked into our repo:

1. **Local-only inference.** No cloud fallback. `configs/agent.yaml` points at the ZGX; if that's down, the run is over. So: one `hack serve status` check before every rehearsal, JSONL replay as the safety net.
2. **Structured I/O over HTTP.** Pydantic models serialize at the network edge. We don't share Python objects between laptop and ZGX — the API is the contract.
3. **One brain model, decisively used.** 128 GB is plenty for a single capable model (Qwen2.5 14B, Llama 3.3 70B via NIM). We don't juggle three — the planner is one LLM with tool use, which scores better on "coherence" than an ensemble.

## How we'll actually use it on May 8

| Phase | What happens on ZGX |
|---|---|
| T+0:00 | SSH in, `nvidia-smi`, `docker ps`, note preinstalled NIM containers. |
| T+0:15 | `bash scripts/bootstrap_zgx.sh --role primary` on A, `--role secondary` on B. Pulls models, warms caches. |
| T+0:30 | From laptop: `uv run hack serve status --host <zgx-A-ip>` — must be green. |
| T+0:30–2:00 | ZGX serves every inference call from `hack agent run`. We never touch its shell again unless something wedges. |
| T+1:45 | During demo capture, ZGX is the bottleneck check. If token/s drops, `docker restart <nim>` is the fastest recovery. |

## Gotchas we've planned around

- **ARM CPU.** Some Python wheels (esp. older audio libs) don't ship arm64 builds. `faster-whisper` and `piper` do; verify once in rehearsal.
- **DGX OS ≠ stock Ubuntu.** Don't `apt install` random things — use containers or user venvs. Treat the OS as read-only.
- **Shared memory = shared contention.** Running a 70B LLM and a VLM on the same box fights for bandwidth. Split across A and B.
- **Networking is Ethernet-only for the 200 Gbps path.** Wi-Fi 7 is fine for SSH but will bottleneck inference — plug in.
- **Power.** It's a desktop box with a real PSU. Don't assume it travels in a backpack — at the event it'll be on the provided table.

## Sources

- [HP ZGX Nano AI Station — HP official](https://www.hp.com/us-en/workstations/zgx-nano-ai-station.html)
- [HP ZGX Nano G1n QuickSpecs](https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=c09212373)
- [HP ZGX Nano G1n review — NotebookCheck](https://www.notebookcheck.net/HP-ZGX-Nano-G1n-AI-Station-review-Compact-server-power-with-Nvidia-DGX-Spark.1229276.0.html)
- [HP ZGX Nano datasheet (PDF)](https://h20195.www2.hp.com/v2/GetPDF.aspx/c09208797)
- [NVIDIA DGX Spark — reference platform](https://www.nvidia.com/en-us/products/workstations/dgx-spark/)
