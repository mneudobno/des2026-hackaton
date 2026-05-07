# REF — your only doc tomorrow

> Print page 1. Pin it next to the laptop. Everything else is in Claude Code, the TUI, or `docs/DAY_OF_BRIEF.md`.

---

## The four tools, in one sentence

1. **Claude Code** — your captain. Tell it the situation; it runs the commands and tells you what to do next.
2. **`hack tui`** — the live dashboard (terminal, no browser). The one thing you launch yourself.
3. **`docs/DAY_OF_BRIEF.md`** — type everything organizers say here. Single file for both pre-event intro AND the 10:30 challenge briefing.
4. **This file** — the cheat sheet. (For deep stack reference: [`docs/TECH_STACK.md`](./TECH_STACK.md) — what each pre-installed tool is, model details, verification punch-list.)

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

## What to say to Claude

You don't type `hack` commands. You tell Claude the situation and it runs the right command(s) for you. Two tables: time-ordered (the spine of the day) and anytime triggers (use as needed).

### Time-ordered — the spine of the day

| When | Say this | Claude runs / does |
|---|---|---|
| 09:30 | "doctor" or "are we good" | `uv run hack doctor` → reports green/red |
| 10:25 | "recon both ZGX" + the two IPs | `hack recon user@<a>` + `-b`, then summarises and proposes config edit |
| T+0:00 | "process the brief" | Reads `DAY_OF_BRIEF.md`, produces config edits + first 3 tasks per role |
| T+0:00 | "boot the ZGX stack" | Runs `bootstrap_zgx.sh`, confirms vLLM is up |
| T+0:05 | "is the stack alive?" | `hack serve status --host <zgx>` |
| T+0:10 | "warm it up" | `hack serve warmup --host <zgx>` |
| T+0:15 | "probe the robot" + adapter name | `hack robot probe --adapter <name>` — **must be green** before anything else |
| T+0:30 | "calibrate the robot" | `hack calibrate --adapter <name>`, commits `linear_scale` / `angular_scale`. **Don't skip.** |
| T+0:30 | (you launch this yourself) | Open `uv run hack tui` in a fresh terminal pane. Leave it running. |
| T+0:45 | "first real-robot run" | `hack agent run --robot <name>` (you may need to launch this yourself in another pane) |
| any | "smoke test" or "rehearse" | `hack rehearse --scenario obstacle-corridor` (~6 s) |
| any | "did the prompt change break anything?" | `hack regression` (~10 s) |
| T+1:30+ | "polish the demo" or "final take" | Invokes the `demo-polish` skill |
| T+1:55 | "tag submit" | `git tag submit` (you push yourself with `git push --tags`) |

### Anytime triggers (no fixed time)

| Say this | What Claude does |
|---|---|
| "where am I" / "what's next" | Reads time + git + runs/, tells you current phase + next 3 actions |
| "make me a runbook" | Reads `DAY_OF_BRIEF.md` → writes `docs/RUNBOOK.md` (full day plan, optional) |
| "swap LLM" / "swap VLM" / "flip to ZGX-B" / "fall back to laptop VLM" | Edits `configs/agent.yaml` + smoke tests |
| "we're behind" / "T+1:00" / "T+1:30" / "drop audio" | Walks the cut-list in order with concrete YAML edits |
| "add adapter for X" | Wires a new robot SDK into `src/hack/robot/` |
| "the agent feels off" / "prompts aren't working" | Replays last trace, proposes prompt edits |
| "what's on the ZGX?" | Summarises `runs/recon-latest.json` + suggests next config edit |

If you're unsure of a phrase, **describe the situation in your own words.** Claude routes to the right skill.

---

## What you launch yourself

Three things Claude can't drive — you start them in their own terminal pane:

| Tool | Command | Why you launch it |
|---|---|---|
| **TUI dashboard** | `uv run hack tui` | Interactive (Ctrl+M / Ctrl+R / Ctrl+O / Ctrl+K). Claude can't send keystrokes. |
| **Live agent loop** (real robot) | `uv run hack agent run --robot <name>` | Long-running; you watch the world map and stop it when needed. |
| **`git push`** | `git push` | Denied to Claude by your project policy — push happens by you. |

Everything else (doctor, recon, bootstrap, serve, probe, calibrate, rehearse, regression, demo record, git tag) — Claude runs them.

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
