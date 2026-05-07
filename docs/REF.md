# REF — your only doc tomorrow

> Print page 1. Pin it next to the laptop. Everything else is in Claude Code, the TUI, or `docs/HACKATHON_INTRO.md`.

---

## The four tools, in one sentence

1. **Claude Code** — your captain. Tell it where you are; it tells you what to do.
2. **`hack tui`** — the live dashboard (terminal, no browser).
3. **`docs/DAY_OF_BRIEF.md`** — type everything organizers say here. Single file for both pre-event intro AND the 10:30 challenge briefing.
4. **This file** — the cheat sheet.

---

## Day-of file flow (memorize this)

```
       Organizer / briefing speaks
                  ↓
       [type into DAY_OF_BRIEF.md]
                  ↓
        ┌─────────┴──────────┐
        ↓                    ↓
"make me a runbook"   "process the brief"
        ↓                    ↓
   docs/RUNBOOK.md      config edits + first 3 tasks
   (full day plan,      (immediate next actions —
    refer all day)       run before build starts)
                  ↓
              Build starts (10:50)
```

Same file in, two outputs. Run *"process the brief"* first (gives you immediate next actions), then *"make me a runbook"* if you want the static all-day reference.

---

## When to talk to Claude (trigger phrases)

| Say this | What happens |
|---|---|
| **"process the brief"** | After typing organizer/briefing into `DAY_OF_BRIEF.md` — produces config edits + first 3 tasks. Run this **first**. |
| **"make me a runbook"** | Reads same `DAY_OF_BRIEF.md` → writes `RUNBOOK.md` with the full day plan. Optional, once. |
| **"where am I"** / **"what's next"** | Tells you current phase + next 3 actions. Use any time you're stuck during the build. |
| **"recon"** / **"what's on the ZGX"** | Summarises `runs/recon-latest.json` + suggests next config edit. |
| **"swap LLM"** / **"flip to ZGX-B"** / **"fall back to laptop VLM"** | Edits `configs/agent.yaml` + smoke tests the swap. |
| **"we're behind"** / **"T+1:30"** / **"drop audio"** | Walks the cut-list in order with concrete YAML edits. |
| **"polish the demo"** / **"final take"** | Last-20-min submission prep. |
| **"add adapter for X"** | Wires a new robot SDK into `src/hack/robot/`. |
| **"the agent feels off"** / **"prompts aren't working"** | Replays last trace, proposes prompt edits. |

If you're not sure what phrase to use — just describe the situation. Claude routes to the right skill.

---

## `hack` CLI — the only commands you need

Order matches the day. Run from the repo root.

| When | Command | Why |
|---|---|---|
| 09:30 | `uv run hack doctor` | Sanity. Must be all green except `nvidia-smi`. |
| 10:25 | `uv run hack recon user@<zgx-a>` (and `-b`) | Snapshot ZGX state into `runs/recon-latest.json`. |
| T+0:00 | `bash scripts/bootstrap_zgx.sh --role primary` | Detects vLLM at `:8000/v1` first; falls back to Ollama. |
| T+0:05 | `uv run hack serve status --host <zgx>` | Confirm vLLM or Ollama is responding. |
| T+0:10 | `uv run hack serve warmup --host <zgx>` | Three tiny prompts to warm caches. |
| T+0:15 | `uv run hack robot probe --adapter <name>` | Cycles all 6 adapter methods. **Must be green** before any other build work. |
| T+0:30 | `uv run hack calibrate --adapter <name>` | Measures drift, writes `linear_scale` / `angular_scale`. **Don't skip.** |
| T+0:30 | `uv run hack tui` | Open the dashboard. Leave it running. |
| T+0:45 | `uv run hack agent run --robot <name>` | First live run. Latency target: <2 s/tick. |
| any | `uv run hack rehearse --scenario obstacle-corridor` | Quick agent-loop sanity (5 ticks, ~6 s). |
| any | `uv run hack regression` | Gate after every prompt change. ~10 s. |
| T+1:45 | `uv run hack demo record` | Capture submission run + video. |
| T+1:55 | `git tag submit && git push --tags` | Mark the final state. |

---

## TUI keyboard (inside `hack tui`)

| Key | Action |
|---|---|
| **Ctrl+M** | Hold while speaking → 3s record → Whisper transcribe → send as cue. **The headline feature.** |
| **Ctrl+R** | Restart rehearsal (current scenario). |
| **Ctrl+O** | Cycle to next scenario (dance → obstacle-course → pick-and-place → …). |
| **Ctrl+K** | Kill running rehearsal. |
| **Ctrl+C** | Quit TUI. |

Type a free-text command at the bottom prompt to send it directly to the agent. World map shows robot (`↑`), obstacles (`●`), goal (`◆`).

---

## The clock (Stockholm time)

```
10:20  ──  At main stage P1. All three.
10:30  ──  Briefing starts. Typist on DAY_OF_BRIEF.md.
10:50  ──  Build window opens (T+0:00).
T+0:15  ──  Robot probe green
T+0:30  ──  Calibrate done. Mock E2E running.
T+0:45  ──  First real-robot run.
T+1:00  ──  CUT #1 if audio flaky → drop mic input
T+1:15  ──  CUT #2 if TTS lags → drop robot voice
T+1:30  ──  CUT #3 if 2-host brittle → single ZGX
T+1:45  ──  CUT #4 if robot crashes → MockRobot + recorded video
T+1:45  ──  Freeze. Two takes recorded.
13:00  ──  SUBMIT (= T+2:10, 10 min cushion past freeze)
14:00  ──  Jury deliberation
14:10  ──  Winner announced.
```

If the clock and your progress disagree, **say "we're behind"** to Claude — don't argue. The cut-list runs itself once you say it.

---

## Cut-list (don't read live, just say "T+1:00" and Claude applies it)

| Trigger | Cut |
|---|---|
| T+1:00 mic flaky | Drop audio in. Type cues into TUI instead. |
| T+1:15 TTS laggy | Drop robot voice. Show subtitles. |
| T+1:30 two-host brittle | Single ZGX. Drop failover list. |
| T+1:45 robot crashing | MockRobot + recorded video. Last resort. |

**Never cut:** dashboard, JSONL logging, the adapter contract.

---

## What goes wrong (and the one-line fix)

| Symptom | Fix |
|---|---|
| `hack doctor` red on Ollama | `brew services start ollama` |
| `hack robot probe` fails | Don't edit runtime — it's the adapter file. Re-read SDK sample. |
| Latency > 2 s | Drop `agent.tick_hz` from 5 to 3. Or smaller LLM via **swap-llm**. |
| Robot moves crooked | You skipped calibrate. Run `hack calibrate --adapter <name>`. |
| Plan has 1 step instead of 6 | LLM too small. Confirm Nemotron / Qwen tag with `curl :8000/v1/models`. |
| Cube doesn't land in bin | Same as above (planner spatial precision). |
| Dashboard blank | TUI auto-tails newest JSONL — restart with `Ctrl+R` to start a fresh trace. |

---

## One rule

If you don't know what to do, say *"where am I"* to Claude. That's the whole skill.
