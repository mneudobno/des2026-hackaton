# Rehearsal log

Append-only record of smoke tests. Every `uv run hack rehearse` run gets **one line** here. The value is in the **Insight** and **Action** columns — treat them as the reason we're running rehearsals.

## Two modes

Rehearsal is the **playground** for developing behaviour + demo script. Two modes, same machinery:

1. **Mac playground** (`--adapter virtual`, default) — runs `VirtualWorldRobot` with synthetic frames on your laptop. Cheap, repeatable, use it for every code/config change.
2. **Real-robot rehearsal** (`--adapter mock|http|ros2|lerobot|<name>`) — swaps the virtual robot for a real adapter and the synthetic frame renderer for the host webcam (or a robot-provided camera). Use this once the physical robot is connected: same scenarios, same success criteria, same UI, same observation report. **Day-of, rehearsing ≠ demoing** — rehearsal lets you iterate; the judged run uses `hack agent run` which has no mic / no scripted cues.

The rehearsal dashboard (`hack ui --rehearsal`) is source-agnostic: it consumes `runs/last_frame.jpg` and tails whatever JSONL is active, so it works identically in both modes.

## Contract (what rehearsal may and may not touch)

- Rehearsal code lives under `src/hack/rehearsal/` and `src/hack/observation/`. It **must not** modify `src/hack/agent/runtime.py`, `src/hack/robot/*`, `src/hack/sensors/*`, or `configs/agent.yaml` semantics.
- Rehearsal dashboard lives under `src/hack/rehearsal/dashboard.py`; day-of `hack.ui.app` stays minimal and trusted.
- Raw JSONL traces live in `runs/rehearsal-*.jsonl` — that's Claude Code's source of truth. The web UI displays human-readable voice / movement / alert views derived from those traces.

Run a rehearsal:

```bash
# Mac playground (synthetic world)
uv run hack rehearse --scenario pick-and-place
uv run hack rehearse --scenario follow
uv run hack rehearse --scenario chit-chat
uv run hack rehearse --scenario dance

# Real-robot rehearsal (once a robot is connected)
uv run hack rehearse --scenario dance --adapter http --delay 0.5
uv run hack rehearse --scenario pick-and-place --adapter lerobot --delay 0.3

# Wrapped in log watcher + observation report
uv run hack observe --scenario dance --delay 0.5
```

A rehearsal is *cheap* on Mac+Ollama — 30 seconds to two minutes. Run it after **any** change to `configs/agent.yaml`, a prompt, or any module in `src/hack/agent/` or `src/hack/sensors/`. Also run them with different model choices to benchmark — that data will decide what we use on ZGX.

### Watching the rehearsal live

Two modes, pick whichever suits the moment:

**A. Standalone OpenCV window** — simplest, one command:

```bash
uv run hack rehearse --scenario dance --display --delay 0.4
```

A 2.5× scaled window opens with the robot, objects, voice cue, tool-call histogram, last action, and current success reason overlaid on each tick. Press `q` to abort early. `--delay 0.4` paces the animation so you can watch — set it to 0 for maximum speed.

**B. Dashboard** — in one shell run `uv run hack ui`, in another run `uv run hack rehearse --scenario <x>` (with or without `--delay`). The dashboard at http://127.0.0.1:8000 streams the same frame (`runs/last_frame.jpg`) and tails the rehearsal JSONL — observation / plan / action events appear as they happen. Good for reviewing multiple runs in sequence or sharing a screen.

Both modes also write `runs/rehearsal-<scenario>-<ts>.jsonl` (full trace) and `runs/rehearsal-<scenario>-<ts>.json` (summary metrics) on exit.

## How to fill this log

After each run, look at the summary table and what `hack rehearse` printed under "vs previous rehearsal". Then write one row:

- **Date/time** — UTC, from the JSON `ts`.
- **Scenario** — `pick-and-place` / `follow` / `chit-chat`.
- **LLM / VLM** — models used (from `configs/agent.yaml`).
- **Success** — ✅ / ❌ / ⚠️ (partial).
- **Latency** — `vlm_ms.mean` / `planner_ms.mean` as `V/P`.
- **Insight** — one sentence. What did this run teach us?
- **Action** — one sentence. What will we change (commit hash if applicable) or "no change".

Keep it terse. The JSONs under `runs/` are the full record; this is the human-readable index.

---

## Log

| Date (UTC) | Scenario | LLM / VLM | Success | V/P (ms) | Insight | Action |
|---|---|---|---|---|---|---|
| *example* | pick-and-place | qwen2.5:1.5b / moondream | ❌ | 620/1090 | moondream ignores JSON-mode → empty observations | changed `vlm.py` to auto-toggle `format:json` per model |
| 2026-04-15 16:27 UTC | pick-and-place | qwen2.5:1.5b / moondream | ❌ | 2036/5399 | 6 ticks, agent oscillates `move` without reaching bin; 1.5B planner too small to commit a multi-step sequence | TODO swap to `qwen2.5:7b` planner (now pulled), re-run |
| 2026-04-15 16:32 UTC | dance | qwen2.5:1.5b / moondream | ❌ | 1810/3442 | 8 ticks; variety is there (`move:7, emote:2`) but wanders off stage 7× and calls stray `grasp`/`release`; 1.5B planner doesn't internalise the "stay near origin" constraint | tune system_prompt to bound motion radius; re-run with `qwen2.5:7b` and compare |
| 2026-04-15 16:36 UTC | dance | qwen2.5:1.5b / moondream | ❌ | 1793/3045 | 3-tick spot-check; confirmed JSONL + annotated `last_frame.jpg` feed the dashboard and OpenCV window; planner 12% faster second time (cache warm) | infra verified; next: real 20-tick run with --display enabled to eyeball dance quality |
| 2026-04-15 18:45 UTC | dance | qwen2.5:1.5b / moondream | ❌ | 2568/3631 | 15-tick full run with mic: "come to the stage" cue at t9 was received (live_cue logged) but 1.5B planner kept issuing dx=3.0 for 6 ticks; `move()` clamped each time | need qwen2.5:7b for spatial reasoning + instrumented clamp events for analyzer |
| 2026-04-15 18:50 UTC | infra | n/a | n/a | — | split dashboard: `hack ui` (day-of, clean) vs `hack ui --rehearsal` (mic + voice/alerts/movement panels). Rehearsal runner now accepts `--adapter <real>` for day-of practice with physical robot. `hack observe` orchestrates rehearsal+watcher+analyzer→md report | next: swap to qwen2.5:7b and re-run dance to see if spatial reasoning improves |
| 2026-04-15 20:30 UTC | infra | n/a | n/a | — | `src/hack/models/` adapter registry (`ollama` / `gemini` / `openai-compat` / `nim`). Planner + VLMClient now consume `LLMAdapter` / `VLMAdapter` via `make_llm(cfg['llm'])` — same code runs against local Ollama, Gemini free tier, or day-of NIM by changing one YAML line | confirms pluggability requirement |
| 2026-04-15 20:45 UTC | infra | n/a | n/a | — | plan-memory in shared core (`src/hack/agent/plan_memory.py`). Decomposer emits `PlanStep(text, tool?)`. Runner takes pre-baked path when `tool` is present — no VLM/planner calls for kinematic steps. No fallback behaviour: unrecognised cues alert + idle | shared by rehearsal runner AND day-of `hack agent run` |
| 2026-04-15 21:05 UTC | dance | qwen2.5:7b / qwen2.5vl | ✅ | — | "spin 360" → 12 pre-baked steps, Σdθ=+7.2 rad (412°). Every step sign-correct. First time a local 7B has delivered a full rotation on cue. No VLM calls during the spin | ships. Next cue to test: compound origin-return |
| 2026-04-15 21:15 UTC | dance | qwen2.5:7b / qwen2.5vl | ✅ | — | "go to random place and back to original position" → decomposer installed remember + walk + grasp/release noise + return. Final pose 0.30 m from origin (on stage). Semantic coverage caught any planner drift; safety clamp never triggered because auto-split already normalised pre-baked steps | compound cues work end-to-end on local |
| 2026-04-15 21:20 UTC | infra | n/a | n/a | — | safety layer: `clamp_call()` hard-caps `move` args to `robot.safety`, `expand_plan_steps()` auto-splits oversized pre-baked moves, `required_tools_for_step()` enforces semantic coverage (move≠remember≠speak). All three wired into both runtimes. Regression harness (`hack regression`) runs curated cue suite and appends row here on each run | `uv run hack regression` now gates prompt/config changes |

---

## Scenario index

- **pick-and-place** — pick the red cube and place it in the bin. Exercises: `move` + `grasp` + `release`, spatial grounding, multi-step plan. Success = target within 0.12 m of the bin and not held.
- **follow** — maintain <0.2 m from a moving blue "person". Exercises: continuous motion, tracker usage. Success = final distance <0.2 m.
- **chit-chat** — user greets; agent should `speak` and stay still. Exercises: router path (if enabled), tool-distribution sanity. Success threshold is generous; really we're looking at the tool-calls histogram.
- **dance** — robot performs a short dance near the stage marker in response to music cues. Exercises: motion variety (both rotation directions), `emote` usage, one voiced acknowledgement. Success = stayed within 0.3 m of origin AND ≥6 `move` calls AND ≥2 distinct rotation directions AND ≥2 `emote` calls AND ≥1 `speak`.

## Adding a new scenario

Open `src/hack/rehearsal/scenarios.py`, add to the `SCENARIOS` dict. A scenario is a `Scenario` with objects, voice cues (tick-scheduled), a `max_ticks` budget, and a success criterion (target object ending near a named container). Commit with a one-line note here under "Log" pointing at why we needed the new scenario.
