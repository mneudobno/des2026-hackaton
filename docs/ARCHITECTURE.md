# Architecture — where each component runs, how they talk

This doc answers: *"If I open this repo for the first time, what runs on which
machine, and how does a voice cue become a robot action?"*

Scope: production-shape day-of deployment with two HP ZGX Nano boxes, one
robot, and the team's orchestrating laptop. Local Mac-dev deployment
collapses everything onto the laptop — that's called out inline.

---

## 1. Topology — four machines, three network links

```
                          ┌──────────────────┐
                          │   team laptop    │
                          │   (orchestrator) │
                          ├──────────────────┤
                          │  hack agent run  │──► runs/*.jsonl (source of truth)
                          │  hack tui        │       │
                          │  hack ui         │──► http://localhost:8000 (judges)
                          │  Whisper STT*    │
                          │  RobotAdapter    │
                          └────┬─────┬───┬───┘
                   200 Gbps    │     │   │     USB / Ethernet / ROS2 / DDS
                   LAN         │     │   └──────────────────────────────┐
                               ▼     ▼                                  ▼
                ┌──────────────────┐┌──────────────────┐        ┌────────────┐
                │    ZGX Nano A    ││    ZGX Nano B    │        │   robot    │
                │  (inference #1)  ││  (inference #2)  │        │  (hardware)│
                ├──────────────────┤├──────────────────┤        ├────────────┤
                │ LLM planner      ││ VLM observer     │        │ actuators  │
                │ • NIM Nemotron-3 ││ • NIM Nemotron-VL│        │ sensors    │
                │   or Ollama      ││   or Ollama      │        │ (cam, mic, │
                │   qwen2.5:14b    ││   qwen2.5vl:7b   │        │  IMU, enc) │
                │ Router phi3      ││ STT Parakeet     │        │            │
                │ TTS Kokoro       ││  (Riva gRPC)     │        │            │
                └──────────────────┘└──────────────────┘        └────────────┘
                   GB10 Grace Blackwell · 128 GB unified · 1000 TOPS FP4 each
```

*Whisper STT runs on the laptop for Mac-dev. Day-of it moves to ZGX-B (Riva
Parakeet) — same contract (text goes to `runs/live_cues.ndjson`).

**Network links:**
- Laptop ↔ ZGX-A: HTTP (Ollama :11434, NIM :8000) over 200 Gbps LAN.
- Laptop ↔ ZGX-B: HTTP (VLM :8001) + gRPC (Riva :50051).
- Laptop ↔ robot: whichever transport the adapter uses — ROS2 DDS, raw HTTP,
  LeRobot serial, or the Pollen daemon for Reachy Mini.

**Why this split:** every stage has a different latency/memory shape. Planner
(tight tick budget, sequential requests) and TTS (response path) cluster on
one box. VLM (frame-rate bound, batchable) and STT (long streaming) cluster
on the other. Configured in `configs/agent.yaml`:
- `llm.base_url: http://zgx-a:8000/v1` (+ `base_urls: [http://zgx-b:...]` for failover)
- `vlm.base_url: http://zgx-b:8001/v1` (+ `base_urls: [http://zgx-a:...]`)
- `agent.pipeline_parallel: true` → VLM(frame_N) and planner(obs_{N-1}) run
  concurrently across the two boxes.

## 2. What runs on each machine

### Laptop (one per team — orchestrator of everything)

The laptop owns the **clock**. Every event is timestamped here. If the
laptop goes down, everything goes down — this is deliberate, it keeps the
failure story simple.

| Process | CLI | Purpose |
|---|---|---|
| Agent runtime | `uv run hack agent run --robot <name>` | The judged run. Thin wrapper over `rehearse("live")` — same loop that scenarios use. |
| Rehearsal runner | `uv run hack rehearse --scenario <name>` | Pre-event development with virtual world or real robot. |
| Terminal UI | `uv run hack tui` | Keyboard (Ctrl+M → 3 s mic recording → Whisper → `runs/live_cues.ndjson`) + live trace tailer. |
| Dashboard | `uv run hack ui` | FastAPI + SSE. Judges watch this. Reads `runs/last_frame.jpg` + tails `runs/rehearsal-*.jsonl`. |
| RobotAdapter | (in-process library) | Six-method contract to whatever SDK. Runs inside the agent runtime. |
| Camera capture | (in-process library) | OpenCV webcam — used when the robot has no camera or adapter is virtual. |
| JSONL logger | (in-process library) | Every observation, plan, action, alert written to `runs/*.jsonl`. **This file is the demo.** |
| Doctor / recon | `uv run hack doctor`, `hack recon user@<host>` | Pre-flight checks. Recon produces `runs/recon-latest.json` — machine-authoritative. |

### ZGX Nano A — primary inference host

Runs the **hot path** — every tick the planner blocks on a response from
this box. It should be the faster of the two boxes if there's any
asymmetry.

| Process | Port | Source |
|---|---|---|
| Planner LLM | 8000 (NIM) or 11434 (Ollama) | NeMo Inference Microservice or Ollama |
| Router LLM | same Ollama instance (if phi3) | `ollama run phi3:mini`, called only when `router.enabled: true` |
| TTS | 9100 (Kokoro HTTP) or local on laptop (Piper/say) | `hexgrad/Kokoro-82M` |

Bootstrapped by `scripts/bootstrap_zgx.sh --role primary`. Tried in this
order: NIM first (NVIDIA's default on DGX OS) → Ollama fallback if NIM
wedges. See `docs/zgx_notes.md` for the cheatsheet.

### ZGX Nano B — secondary inference host

Runs **frame-rate work** — VLM can run free at its own cadence and the
planner reads its latest output. STT streaming also lives here.

| Process | Port | Source |
|---|---|---|
| VLM | 8000 (vLLM, multimodal Omni — shares LLM endpoint) or 11434 (Ollama fallback) | Nemotron 3 Nano Omni or qwen2.5vl:7b |
| STT | 50051 (gRPC) | Riva Parakeet CTC 1.1B, preinstalled on DGX OS |

Bootstrapped by `scripts/bootstrap_zgx.sh --role secondary`. When either
ZGX drops, the opposite box inherits its load via the `base_urls` failover
list on the adapter (`src/hack/models/base.py::_HostPool`).

### Robot — the actuator

Runs nothing we wrote. We talk to it via `RobotAdapter`, which translates
our six-method contract into the robot's native SDK. Known adapters:

| Adapter | Transport | Lives at |
|---|---|---|
| `reachy_mini` | HTTP+WS to Pollen daemon on port 8000 | `src/hack/robot/reachy_mini.py` |
| `unitree_go2` | Cyclone DDS over wired Ethernet | `src/hack/robot/unitree_go2.py` |
| `lerobot` | whatever the LeRobot driver supplies | `src/hack/robot/lerobot_adapter.py` |
| `http` | generic REST `/command` + `/state` | `src/hack/robot/http.py` |
| `ros2` | `rclpy` topics | `src/hack/robot/ros2.py` |
| `mock` | in-memory | `src/hack/robot/mock.py` |

Some robots expose their own camera/mic — when they do, `RobotAdapter`
surfaces it and the laptop skips its webcam.

## 3. One-tick data flow

What happens in the ~200 ms between the user finishing a sentence and the
robot moving. All of this is driven by `src/hack/rehearsal/runner.py`
(the same loop serves rehearsals and the judged run).

```
 ┌────────┐ 1. Ctrl+M        ┌──────────────┐ 2. wav      ┌──────────────┐
 │  user  │─────────────────▶│  hack tui    │────────────▶│  Whisper STT │
 │ (voice)│                  │   (laptop)   │             │  (laptop/B)  │
 └────────┘                  └──────────────┘             └──────┬───────┘
                                                                 │ 3. text
                                                                 ▼
                                             ┌────────────────────────────────┐
                                             │  runs/live_cues.ndjson         │
                                             └───────────────┬────────────────┘
                                                             │ 4. tail
                                                             ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │   rehearse() tick loop (laptop)                                          │
 │                                                                          │
 │   5. classify_cue_smart(text)  ────────── deterministic? ──── yes ──┐    │
 │       │ no                                                          │    │
 │       ▼                                                             │    │
 │   6. decompose(text) ──► POST /api/generate ─────► ZGX-A planner    │    │
 │       │                                                             │    │
 │       ▼                                                             │    │
 │   7. validate_plan()  ──► POST /api/generate ─────► ZGX-A planner   │    │
 │       │                                                             │    │
 │       └──► 8. plan_memory = PlanMemory(steps) ◄─────────────────────┘    │
 │                 │                                                        │
 │                 ▼                                                        │
 │   9. every tick:                                                         │
 │       a. frame = cam.read()  ◄── robot or laptop webcam                  │
 │       b. obs   = VLM(frame)  ──► POST /api/generate ──► ZGX-B VLM        │
 │                                  (pipelined with step c)                 │
 │       c. plan  = planner.plan(obs, plan_hint) ──► ZGX-A planner          │
 │       d. obstacle_check(obs) → maybe inject avoidance                    │
 │       e. safety_clamp(plan.calls)                                        │
 │       f. for call in calls: tools.call(call)                             │
 │            └──► RobotAdapter.move / emote / speak ──► robot              │
 │       g. trace.log(observation, plan, action)                            │
 │                                                                          │
 │   10. plan_memory.advance() → is_done? → clear                           │
 └──────────────────────────────────────────────────────────────────────────┘
                                                             │
                                                             ▼
                                               ┌───────────────────────────┐
                                               │ runs/rehearsal-*.jsonl    │
                                               │   every event, every tick │
                                               └──────────┬────────────────┘
                                                          │ tail (SSE)
                                                          ▼
                                                   ┌──────────────┐
                                                   │  hack ui     │ ──► judges
                                                   └──────────────┘
```

### Pipelined timing (two boxes)

With `agent.pipeline_parallel: true`, tick N looks like:

```
          t─► time
  ZGX-B:  [VLM(frame_N-1)                    ]
                                              [VLM(frame_N)                  ]
  ZGX-A:                    [planner(obs_N-1)                  ]
                                                                [planner(obs_N)]
          └─ tick N starts                   └─ tick N ends ≈ max(vlm, planner)
```

Serial (single host) would be `vlm_ms + planner_ms`. The code path is gated
by one config flag and a helper (`_pipelined_observe`) in
`src/hack/rehearsal/runner.py`.

### Failover flow (one ZGX dies mid-run)

```
  tick 42: llm.complete(prompt) ──► ZGX-A :8000  ──── 200 OK
  tick 43: (cable unplugged from ZGX-A)
  tick 43: llm.complete(prompt) ──► ZGX-A :8000  ──── httpx.ConnectError
                                 ──► rotate to base_urls[1]
                                 ──► ZGX-B :8000  ──── 200 OK
  tick 44+: llm.complete(prompt) ──► ZGX-B :8000  ──── 200 OK  (sticky)
```

`host_label()` on the adapter updates → the dashboard's "running on" row
visibly shifts to the new host. No restart. Logic lives in
`src/hack/models/base.py::_HostPool._request`. Tested in
`tests/test_adapter_failover.py`.

## 4. Startup sequence (day-of)

```
T+0:00  (all 3) ssh into both ZGX boxes · note IPs
T+0:01  (typist) open docs/DAY_OF_BRIEF.md · start transcribing
T+0:02  (R, parallel) hack recon user@zgx-a  · hack recon user@zgx-b
T+0:05  (R, parallel) bootstrap_zgx.sh --role primary on A, --role secondary on B
T+0:15  ZGX models warm · NIM or Ollama serving
T+0:25  (typist) says "process the brief" · day-of-brief skill emits decisions
T+0:27  (B) commits configs/agent.yaml edits · points LLM at ZGX-A, VLM at ZGX-B
T+0:30  (R) writes/chooses RobotAdapter · hack robot probe --adapter <name>
T+0:45  (all) hack agent run --robot <name> · first end-to-end run
T+1:00  (D) hack ui running · screen recording started
... → judged run @ T+1:55 submit
```

Full minute-by-minute in [`day_of_playbook.md`](./day_of_playbook.md) and
[`DAY_OF_TASKS.md`](./DAY_OF_TASKS.md).

## 5. Code map — where does each responsibility live

Grouped by machine role. All paths relative to repo root.

### Laptop-side, runtime-critical (keep stable day-of)

| Concern | File |
|---|---|
| Event loop, per-tick orchestration | `src/hack/rehearsal/runner.py` |
| Judged-run entry (thin wrapper) | `src/hack/agent/runtime.py` |
| Plan memory, PlanStep, safety clamp | `src/hack/agent/plan_memory.py` |
| Cue classification, deterministic plans | `src/hack/agent/deterministic_plans.py` |
| A* path planning with obstacles | `src/hack/agent/path_planner.py` |
| Planner prompt + JSON parser | `src/hack/agent/planner.py` |
| Intent router (phi3 triage) | `src/hack/agent/router.py` |
| Tool registry (move, speak, emote, …) | `src/hack/agent/tools.py` |
| JSONL trace writer | `src/hack/agent/logger.py` |
| Realtime correctness monitor | `src/hack/observation/correctness_monitor.py` |

### Laptop-side, pluggable (swap freely day-of)

| Concern | File(s) |
|---|---|
| RobotAdapter contract | `src/hack/robot/base.py` |
| Concrete adapters | `src/hack/robot/{mock,http,ros2,lerobot_adapter,reachy_mini,unitree_go2}.py` |
| Adapter registry | `src/hack/robot/__init__.py` |
| Config | `configs/agent.yaml` |
| Prompts (system + observation) | `configs/agent.yaml` `agent.*_prompt` |

### Laptop-side, transport to ZGX

| Concern | File(s) |
|---|---|
| LLM/VLM adapter contract + failover pool | `src/hack/models/base.py` |
| Ollama / OpenAI-compat / Gemini adapters | `src/hack/models/{ollama,openai_compat,gemini}.py` |
| Mock VLM (ground truth from virtual world) | `src/hack/models/mock_vlm.py` |
| VLM client (prompt + Observation parsing) | `src/hack/sensors/vlm.py` |
| Camera capture | `src/hack/sensors/camera.py` |
| CSRT tracker between VLM calls | `src/hack/sensors/tracker.py` |
| Microphone + Whisper | `src/hack/sensors/mic.py` · `src/hack/ui/tui_app.py` (Ctrl+M) |
| TTS | `src/hack/sensors/tts.py` |

### Laptop-side, user interface

| Concern | File(s) |
|---|---|
| CLI entry (Typer) | `src/hack/cli.py` |
| Terminal UI | `src/hack/ui/tui_app.py` · `src/hack/ui/terminal.py` |
| Dashboard (FastAPI + SSE) | `src/hack/ui/app.py` |
| Rehearsal dashboard | `src/hack/rehearsal/dashboard.py` |

### Laptop-side, rehearsal-only (never runs day-of judged)

| Concern | File(s) |
|---|---|
| Virtual world (synthetic frames + mock robot) | `src/hack/rehearsal/virtual_world.py` |
| Scenarios + success criteria | `src/hack/rehearsal/scenarios.py` |
| Regression harness | `src/hack/rehearsal/regression.py` |
| World builder (random obstacle layouts) | `src/hack/rehearsal/world_builder.py` |

### ZGX-side (scripts we ship)

| Concern | File |
|---|---|
| Cold-start both boxes | `scripts/bootstrap_zgx.sh` |
| Recon (snapshot a host's state into JSON) | `scripts/zgx_recon.sh` |

## 6. Mac-dev deployment (for teammate onboarding)

Everything collapses onto the laptop. `configs/agent.yaml` default config
points `llm.base_url` and `vlm.base_url` at `http://localhost:11434` (Ollama
via Homebrew). The flow is identical — same runner, same adapters, same
JSONL output — just running in one process instead of three hosts. This is
why the repo works in `hack rehearse` before any ZGX is reachable.

## 7. Fault model — what fails, what happens

| Failure | Symptom | Mitigation (built-in) |
|---|---|---|
| ZGX-A unreachable | `httpx.ConnectError` on planner | `base_urls` rotates to ZGX-B; dashboard updates host label |
| ZGX-B unreachable | Same, for VLM | Same failover |
| Both ZGX dead | Agent can't plan | Cut-list: drop to MockRobot + pre-recorded demo JSONL (`hack demo play`) |
| Mic flaky (loud venue) | No cues fired | Cut-list: drop audio, type cues into TUI keyboard input |
| Whisper slow (>2 s) | Lag between cue and plan | Cut-list: move STT to ZGX-B Riva (Parakeet — gRPC, ~200 ms) |
| Robot SDK misbehaves | Adapter probe red | Cut-list: MockRobot + scripted demo |
| VLM JSON parse fail | `m.vlm_parse_failures++` | Planner sees an empty observation; behaviour degrades to state-only |
| Planner JSON parse fail | `m.plan_parse_failures++` | Tick idles; next tick retries |
| Infinite plan loop | Same step retried | `plan_memory.retry` → 3-strike → abandon + idle |
| No progress at all | `stall_triggered` | Watchdog re-injects the cue once; second stall terminates the run cleanly |

All of these produce visible events in `runs/*.jsonl` — the dashboard
surfaces them as alerts, and the demo narration has language for each
(see `DEMO_SCRIPT.md` §Recovery script).

---

See also:
- [`day_of_playbook.md`](./day_of_playbook.md) — schedule + cut-list
- [`DEMO_SCRIPT.md`](./DEMO_SCRIPT.md) — 60-second narration per component
- [`zgx_overview.md`](./zgx_overview.md) — hardware conceptual intro
- [`zgx_notes.md`](./zgx_notes.md) — NIM / Ollama / Riva operational cheatsheet
- [`prior_art.md`](./prior_art.md) — references lifted from NVIDIA + HF
