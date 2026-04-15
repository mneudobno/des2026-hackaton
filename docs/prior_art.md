# Prior art — similar setups, repos to study, lessons to steal

Research dump from 2026-04-15. Focused on: hackathons with the ZGX/DGX Spark, robot-agent builds with local inference, and open repos we can lift patterns from.

## Most relevant: NVIDIA's own DGX Spark + Reachy Mini stack

The ZGX Nano is HP's packaging of the **NVIDIA DGX Spark reference design**. NVIDIA and HuggingFace have already shipped a robot-agent demo on exactly this hardware pair, and published the code. **Study this first.**

- **NVIDIA DGX Spark Playbooks** — step-by-step demos for AI/ML on DGX Spark. The `spark-reachy-photo-booth` playbook is a multi-modal agent (ReAct loop + voice + VLM + image generation) controlling a Reachy Mini. Our hackathon in miniature, blessed by NVIDIA: [`NVIDIA/dgx-spark-playbooks`](https://github.com/NVIDIA/dgx-spark-playbooks) · [photo-booth dir](https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/spark-reachy-photo-booth) · [build.nvidia.com page](https://build.nvidia.com/spark/spark-reachy-photo-booth)
- **HuggingFace blog: NVIDIA + Reachy Mini walk-through** — a full interactive AI assistant running locally on a DGX Spark using Nemotron 3, step by step: [blog post](https://huggingface.co/blog/nvidia-reachy-mini) · [raw markdown](https://github.com/huggingface/blog/blob/main/nvidia-reachy-mini.md)
- **Brev reachy-personal-assistant** — the code backing the tutorial: [`brevdev/reachy-personal-assistant`](https://github.com/brevdev/reachy-personal-assistant)
- **NeMo Agent Toolkit** — NVIDIA's agent framework, works with LangChain / LangGraph / CrewAI. Likely preinstalled in DGX OS containers. Worth one run-through before May 8.

What to lift from these:
- **ReAct loop + voice + VLM** architecture — matches our `agent/runtime.py` design; confirm our tool schema shape against theirs.
- **Nemotron models** are what NVIDIA ships first on DGX Spark; add a Nemotron entry to `configs/agent.yaml` as an alternative to Qwen.
- **Photo-booth demo structure** — sensor → interpret → action → speak → repeat. Same loop we built. Good prompt examples to steal.

## HuggingFace LeRobot — the robotics abstraction we should align with

The AMD Open Robotics Hackathon (Tokyo, 2025) used LeRobot as its "Mission 1 hello world" — 100 people / 36 teams got pick-and-place working in hours. That's a strong signal for the 2-hour window.

- **Repo:** [`huggingface/lerobot`](https://github.com/huggingface/lerobot)
- **Supported hardware:** SO100, LeKiwi, Koch, HopeJR, OMX, EarthRover, **Reachy2**, Unitree G1, plus gamepad/keyboard/phone teleop. If the hackathon robot is any of these, we use LeRobot directly as our adapter backend.
- **SmolVLA (450 M)** — their small VLA model; runs on modest hardware, good fallback if Qwen-VL is unavailable: [blog](https://learnopencv.com/smolvla-lerobot-vision-language-action-model/).
- **Interface:** LeRobot's `Robot` class already decouples control logic from hardware. **Our `RobotAdapter` is a subset of it.** If the event robot has a LeRobot driver, `LeRobotAdapter(RobotAdapter)` → one file, ~40 lines.
- **ROS2 bridge:** [`ycheng517/lerobot-ros`](https://github.com/ycheng517/lerobot-ros) — lightweight LeRobot ↔ ROS2 interface. Good reference for our `ROS2Robot` stub.
- **AMD recap:** [AMD Open Robotics Hackathon](https://www.amd.com/en/developer/resources/technical-articles/2025/amd-open-robotics-hackathon-recap.html).

**Action:** add `lerobot` to `pyproject.toml` `[robot]` optional-extra, and pre-write a `LeRobotAdapter` skeleton. Cost: 30 min. Payoff: if the event robot ships a LeRobot driver, we're done in 5 minutes instead of 30.

## HALO — voice-controlled robot, systems-level lessons

[`andrei-ace/HALO`](https://github.com/andrei-ace/HALO) (also on [Hackster.io](https://www.hackster.io/andrei-ciobanu2/building-halo-d7cd33)) — an operator-speaks-to-robot system. Author explicitly calls out the systems problems we also face.

Lessons to steal:
- **"Keep inference out of the control loop."** The VLM answers at VLM speed; the robot controller runs at controller speed. Don't gate motion on LLM. Our async runtime already does this — validate it under load.
- **VLM-to-tracker handoff.** Use VLM infrequently to ground "what/where", then cheap tracker (OpenCV correlation / SAM2) to follow between VLM calls. Worth adding: a `tracker.py` helper that consumes VLM outputs and emits continuous target poses.

## DGX Spark performance + ops reports

From owners who've been running it for months (these are non-marketing posts):

- [Frank's World: Local LLM Performance on DGX Spark](https://www.franksworld.com/2026/04/10/exploring-local-llm-performance-a-deep-dive-with-nvidia-dgx-spark/) — latency and tok/s numbers.
- [BSwen: Is DGX Spark Worth It for Local LLM Inference?](https://docs.bswen.com/blog/2026-03-27-nvidia-dgx-spark-local-llm/) — honest cost/perf breakdown.
- [Sparktastic Medium: practical local LLM examples](https://medium.com/sparktastic/practical-local-llm-examples-on-dgx-spark-2f8ba384a9d7) — working code snippets.
- [NVIDIA forum: managing local LLM orchestration](https://forums.developer.nvidia.com/t/managing-local-llm-orchestration/363264) — Ollama vs vLLM tradeoffs on Spark.
- [NVIDIA forum: hybrid local + cloud LLMs](https://forums.developer.nvidia.com/t/building-local-hybrid-llms-on-dgx-spark-that-outperform-top-cloud-models/359569) — what works.
- [NVIDIA blog: scaling autonomous AI agents on DGX Spark](https://developer.nvidia.com/blog/scaling-autonomous-ai-agents-and-workloads-with-nvidia-dgx-spark/) — official agent-workload guidance.
- [NVIDIA blog: software optimizations for DGX Spark](https://developer.nvidia.com/blog/new-software-and-model-optimizations-supercharge-nvidia-dgx-spark/).
- [LM Studio on DGX Spark](https://build.nvidia.com/spark/lm-studio) — third alternative to Ollama/NIM if both fail.

Concrete data points to internalize:
- Qwen3-80B ran at ~45 tok/s with <150 ms end-to-end on DGX Spark (user-reported).
- Developers commonly start with Ollama, then graduate to vLLM for throughput — mirrors our plan.
- 122 B models fit and run "genuinely useful for daily work" — well inside our 128 GB budget.

## Agent-hackathon trend lessons (2025–2026)

- [Semgrep: what a hackathon reveals about AI agent trends 2026](https://semgrep.dev/blog/2025/what-a-hackathon-reveals-about-ai-agent-trends-to-expect-2026/) — 250+ devs at AWS Agents Hackathon. Key finding: teams under time pressure gravitate to **multiple LLMs instead of one**, with security checks embedded in dev workflow.
- [Microsoft AI Agents Hackathon 2025](https://microsoft.github.io/AI_Agents_Hackathon/) · [`microsoft/AI_Agents_Hackathon`](https://github.com/microsoft/AI_Agents_Hackathon) — structured "building AI agents" track.
- [Holistic AI × UCL Great Agent Hack](https://hackathon.holisticai.com/), [Ruya AI Self-Improving Agents](https://ruyaai-hackathon-2026.devpost.com/) — agent evaluation focus.
- [`RefiOrDie/Spark`](https://github.com/RefiOrDie/Spark) — an actual NVIDIA hackathon repo. Small but instructive.

**Counter-point to "multiple LLMs":** that trend assumes long-form agentic tasks. We have 2 hours and must commit decisively. **Keep the one-LLM planner.** Don't get clever.

## Repos to look at for patterns

- [`shivamr021/ollama-langchain-agents`](https://github.com/shivamr021/ollama-langchain-agents) — Ollama + LangChain agent patterns with memory + voice + tools. Similar shape to ours.
- [`erkkimon/vllama`](https://github.com/erkkimon/vllama) — hybrid Ollama-mgmt + vLLM-inference server, OpenAI-compatible. Useful if Ollama throughput is too low on ZGX.
- [`vllm-project/vllm`](https://github.com/vllm-project/vllm) — production-grade alternative serving engine.
- [`openvla/openvla`](https://github.com/openvla/openvla) — 7B vision-language-action model. **Too big to integrate in 2 hours**, but worth understanding the interface; our VLM→planner→tools split is a lower-capability but more controllable variant.
- [`OpenMOSS/VLABench`](https://github.com/OpenMOSS/VLABench) — benchmarks for VLA models; has test scenes we could adapt for local rehearsal.

## What this changes in our repo

Small, high-value additions to make before May 8:

1. **Clone `NVIDIA/dgx-spark-playbooks` locally** and walk through `spark-reachy-photo-booth` during the DGX rental rehearsal. Steal any snippets that simplify our bootstrap.
2. **Add `LeRobotAdapter` skeleton** to `src/hack/robot/lerobot.py`. Register in `ADAPTERS`. Guard imports so the base install still works without LeRobot.
3. **Add Nemotron entry to `configs/agent.yaml`** as an alternative LLM, so we can swap to NVIDIA-native models on the ZGX in one line.
4. **Add a `tracker.py` helper** (cheap OpenCV tracker that consumes a VLM bounding box) so continuous motion doesn't block on VLM latency — the HALO lesson.
5. **Skim the NeMo Agent Toolkit** before the event in case it's the preinstalled path of least resistance on DGX OS.

Not doing, deliberately:
- Integrating OpenVLA or SmolVLA — too much time, unclear payoff against our VLM→planner split.
- Swapping to vLLM preemptively — Ollama is enough until we measure a bottleneck.
- Adding LangChain/CrewAI — they buy abstractions we don't need in 2 hours.
