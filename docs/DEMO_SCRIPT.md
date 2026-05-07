---
---

# Demo script — judged run (DIS2026X1, 2026-05-08)

Target duration: **60 seconds spoken + ~30 seconds live demo**. Everything
below is supported by today's implementation — no aspirational features.

Hardware assumption: two ZGX Nano boxes, one robot, one laptop. Setup:
`configs/agent.yaml` with `llm.base_url=zgx-a`, `vlm.base_url=zgx-b`,
`llm.base_urls=[zgx-b]`, `vlm.base_urls=[zgx-a]`, `agent.pipeline_parallel: true`.

Run one terminal with `hack tui`, one browser tab with `hack world --display`,
one browser tab with the JSONL trace visible (`watch -n 0.5 'tail -5 runs/rehearsal-live-*.jsonl'`).

## The 60 seconds (demo lead reads verbatim)

Bold = what the narrator says. *Italic* = what's happening on screen. The time
column is a guide; hit the 60-second mark by trimming the stretch beat.

| T | Narration (demo lead) | On-screen / robot | Backing evidence |
|---|---|---|---|
| 0:00 | **"Meet our agent. Two ZGX boxes, one robot, one laptop."** | TUI boot splash; `hack doctor` green. | `hack doctor` output (green rows). |
| 0:05 | **"The big planner runs on ZGX-A. The vision model runs on ZGX-B. They talk in parallel — pipelined."** | Dashboard "running on" row shows both hosts + `pipelined=true` in trace. | `trace.log('model_info')` + `status: vlm_done pipelined=true`. |
| 0:15 | **"I give it a voice cue."** *(speak into mic)* **"Go to the red cup and come back."** | TUI mic indicator lights. Live cue appears in voice panel. | `live_cue` JSONL event; TUI voice panel. |
| 0:22 | **"No LLM round-trip for known-shape cues — it classifies, computes the path, and installs a plan."** | Alert panel: `deterministic-plan` event. Plan decomposition panel lists steps. | `alert code=deterministic-plan`; `plan_installed` event with `origin` + `steps[]`. |
| 0:30 | **"Vision runs every tick for obstacle avoidance. When it sees something, the planner injects a detour."** | OpenCV world window shows the robot reroute around a red obstacle. | `alert code=obstacle-detected`; `plan_installed cue=obstacle-avoidance`. |
| 0:40 | **"If either ZGX drops mid-run, the adapter fails over to the other box automatically — no restart."** | Pull the ZGX-A Ethernet cable live (or show a pre-recorded clip). Trace continues; `host_label` in dashboard updates. | `base_urls` failover path in `models/base.py`; unit tests 7/7 in `tests/test_adapter_failover.py`. |
| 0:50 | **"Round trip back to start. The plan origin is remembered from the first step — the agent can return home without a second cue."** | Robot reaches target, turns, returns. TUI step counter advances; `plan_complete` event. | `plan_memory.origin`; `PlanStep`; `return_to_origin` deterministic case. |
| 0:58 | **"Every tick — observation, plan, action — is in one JSONL file. We can replay any run bit-exact for debugging. That file IS the demo."** | Shell: `uv run hack agent replay runs/submit.jsonl` runs in sidebar. | `JsonlLogger`; `replay()` in `agent/runtime.py`; CLI `hack agent replay`. |
| 1:00 | **"Two hours. Three teammates. One pluggable adapter surface."** | `git log --oneline --since="2 hours ago"` briefly on screen. | Git history. |

## What to show the judges (in priority order)

All three advertised axes get a named moment:

1. **Hardware utilization** — T+0:05 pipelined dual-host + T+0:40 failover.
   Backed by: `agent.pipeline_parallel`, `base_urls`, `host_label(+N failover)`.
2. **Sensor / input integration** — T+0:15 mic cue drives everything;
   T+0:30 camera → VLM → obstacle avoidance. Backed by: `hack tui` Ctrl+M →
   Whisper → `runs/live_cues.ndjson`; `VLMClient.observe()`; `check_obstacle_avoidance()`.
3. **Agent quality** — T+0:22 deterministic plan (no LLM waste);
   T+0:50 `return_to_origin` round trip. Backed by: `classify_cue_smart`,
   `plan_memory.PlanMemory`, `generate_plan`.

## Recovery script (if something breaks mid-demo)

Cut to `MockRobot` + a pre-recorded `runs/submit.jsonl`:

```
uv run hack agent replay runs/submit.jsonl configs/agent.yaml
```

Narration: **"Every run is logged — this is last rehearsal, bit-exact."**
The replay produces `plan` + `action` events identical to the live run.

## One-line pitch (if a judge asks "what's novel?")

> "Everything that can be deterministic — is. The planner only runs when the
> cue is genuinely open-ended. That's why it's fast on small hardware and
> why it fails over cleanly when a box dies."

## Hand-off sheet (one printed page, give to judges at T+1:55)

Leave `runs/submit.jsonl` open on the dashboard. Include:

- Team: **Just Build** — Timur · Kamila · Simon
- Robot adapter: `<name>` (one of: reachy_mini · unitree_go2 · http · ros2 · lerobot · mock)
- Models: planner `<cfg.llm.model>` @ `<zgx-a>`, VLM `<cfg.vlm.model>` @ `<zgx-b>`
- Pipelined: `true`, failover configured
- Trace: `runs/submit.jsonl` — every tick recorded
- Rehearsals run during the 2 hours: see `runs/rehearsal-*.json`
- Regression suite: `uv run hack regression` — PASS

## Rehearsal drill (do this 3× before leaving for Stockholm)

1. `uv run hack rehearse --scenario obstacle-corridor --display`
2. Open OBS or QuickTime — record the TUI + world window side-by-side
3. Speak the narration over the recording, timing each beat
4. If the beat slips past 60 seconds, cut the T+0:40 failover live pull and
   run a pre-recorded clip of it instead — saves 6–8 seconds

## What is *not* in this demo (deliberately)

- Fine-grained manipulation (no gripper scenario yet).
- Multi-turn conversation (we have the stack; it's not a scored axis here).
- Novel ML — the planner is Qwen/Nemotron; the VLM is whatever NIM is on the box.
  The story is the *agent architecture*, not the model.
