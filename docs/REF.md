---
---

# REF — your only doc tomorrow

> Print page 1. Pin it next to the laptop. Everything else is in Claude Code, the TUI, or `docs/DAY_OF_BRIEF.md`.

---

## The four tools, in one sentence

1. **Claude Code** — your captain. Tell it the situation; it runs the commands and tells you what to do next.
2. **`hack tui`** — the live dashboard + mic (terminal, no browser). One of two things you launch yourself day-of (the other is `hack agent run` — see *What you launch yourself* below).
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

## Physical setup — the first 10 minutes

### Topology (mental model)

```
   [Mac mic + webcam]                 [Robot]
           ↓                            ↓ ↑
     ┌────────────┐  Ethernet   ┌──────────────┐
     │  laptop    │ ←─────────→ │  ZGX-A       │
     │ (agent +   │             │  vLLM :8000  │
     │  TUI +     │  Ethernet   ├──────────────┤
     │  adapter)  │ ←─────────→ │  ZGX-B       │
     └────────────┘             │  STT/overflow│
                                └──────────────┘
```

**Laptop is the conductor.** It runs the agent loop, talks HTTP to the ZGX boxes, drives the robot via SDK. The ZGX never touches the robot directly — they're just remote brains.

### In your bag (check before leaving home)

- [ ] Laptop + USB-C charger (≥ 100 W if heavy)
- [ ] **USB-C → Ethernet adapter** (Mac has no RJ45; without this you're WiFi-only)
- [ ] Phone fully charged (video-backup demo if everything dies)
- [ ] Earbuds (loud venue, mic test)
- [ ] Snack + water
- [ ] Optional: USB-C hub (if the desk's only ports are USB-A)

### Steps when you sit down (10:20)

1. **Plug in.** Laptop charger to outlet. Open lid.
2. **Look at the desk.** Note what's there:
   - Power outlets — laptop charger goes here
   - Ethernet cable on the desk? Plug it into laptop (via USB-C → RJ45 adapter)
   - ZGX boxes should be powered on already (organizers boot them) — green/blue LEDs on the front
   - Robot: same desk, separate cage, or different room? Note it.
3. **Note the ZGX IPs.** They're handed out via:
   - Sticky note on the box, OR
   - Sign at the station, OR
   - Verbal handoff during 10:30 briefing
   Write them on the printed copy of this doc so you don't lose them.
4. **Network sanity** (Terminal):
   ```
   ping -c 2 <zgx-a-ip>      # should respond in <5ms on cabled Ethernet
   ssh user@<zgx-a-ip>       # organizer should have pre-loaded your key
   ```
   If `ping` fails: WiFi vs cable issue. Try the other interface. Ask on-site support if both fail.
5. **Hand off to Claude.** From here on, you say things, Claude runs commands. See the next section.

### When the physical setup fights back

| Symptom | First thing to try |
|---|---|
| ZGX power LED is off | Don't touch — ask on-site HP/NVIDIA support. They booted them; they fix them. |
| Ethernet cable on desk but laptop says "no link" | Reseat the USB-C → RJ45 adapter (these die from heat). Try the other ZGX's port. |
| `ping` works but `ssh` rejects key | Organizer didn't load your key yet. Ask. **Don't paste a password into a shared box.** |
| WiFi only, latency feels bad | Live with it for now; cut #1/#2 later if needed. WiFi 7 is OK for SSH but bottlenecks inference. |
| Robot has no network address — it's a USB device | Plug into laptop. The adapter (HTTP / lerobot / serial) determines what to do; the brief tells you which. |
| Robot is in a different room from your desk | Ask: can you see it during the build? You'll need a line-of-sight to debug. |
| Two laptops on the desk (you brought one, they provided one) | Use yours. Theirs may be configured for a different challenge or kicker demo. |

### What NOT to do

- **Don't `apt install` anything on the ZGX.** DGX OS is curated; live in containers or the user venv only.
- **Don't unplug things mid-build.** Network blip = mid-tick failure = lost cycles.
- **Don't trust "the robot is on" if it's not moving when you cycle a probe.** Always run `hack robot probe` before assuming.
- **Don't worry about pretty.** Wires on the desk are fine. Fight wedge problems with `hack`, not zip ties.

---

## What to say to Claude

You don't type `hack` commands. You tell Claude the situation and it runs the right command(s) for you. Two tables: time-ordered (the spine of the day) and anytime triggers (use as needed).

### Time-ordered — the spine of the day

| When | Say this | Claude runs / does |
|---|---|---|
| 09:30 | "doctor" or "are we good" | `uv run hack doctor` → reports green/red |
| 10:25 | "recon both ZGX" *(IPs are read from `DAY_OF_BRIEF.md` — paste them there as you hear them; only include in chat if not yet in the brief)* | `uv run hack recon user@<zgx-a-ip>` then `…@<zgx-b-ip>`, summarises, proposes config edit |
| T+0:00 | "process the brief" | Reads `DAY_OF_BRIEF.md`, produces config edits + first 3 tasks per role |
| T+0:00 | "boot the ZGX stack" | Runs `bootstrap_zgx.sh`, confirms vLLM is up |
| T+0:05 | "is the stack alive?" | `hack serve status --host <zgx>` |
| T+0:10 | "warm it up" | `hack serve warmup --host <zgx>` |
| **T+0:10** | **"lock in the config"** or **"adopt the real setup"** | **Reads recon + `/v1/models` + brief decisions, writes the actual IPs/tags/adapter into `configs/agent.yaml`, runs `hack rehearse --scenario obstacle-corridor`, reports grade. This is the one moment placeholders become real values.** |
| T+0:15 | "probe the robot" + adapter name | `hack robot probe --adapter <name>` — **must be green** before anything else |
| T+0:30 | "/calibrate" or "calibrate the robot" | Invokes the `/calibrate` skill — Claude walks all 10 `robot.safety` + `robot.calibration` knobs, runs `hack calibrate` for motion-scale tests, captures footprint from the tape measure, writes `configs/agent.local.yaml`, smoke-tests with `hack regression`. **Don't skip.** |
| T+0:30 | (you launch this yourself) | Open `uv run hack tui` in a fresh terminal pane. Leave it running. |
| T+0:45 | "first real-robot run" | **You launch** `uv run hack agent run` in a second terminal pane (TUI keeps running in pane 1). Both feed off the same JSONL trace + `runs/live_cues.ndjson`. |
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

Two things Claude truly can't drive (interactive UI / policy-denied) plus one thing **you** own day-of even though Claude can technically smoke-test it:

| Tool | Command | Who runs it |
|---|---|---|
| **TUI dashboard** | `uv run hack tui` | **You only.** Interactive (Ctrl+M / Ctrl+R / Ctrl+O / Ctrl+K) — Claude can't send keystrokes. |
| **Live agent loop** (real robot) | `uv run hack agent run` | **You for the judged take.** You watch the world map / dashboard and stop when a take is clean — Claude can't see the robot or judge "this is the one." Claude *can* boot it briefly in the background to verify the production path is healthy (e.g. before the judged run). Reads `robot.adapter:` from `configs/agent.yaml` (set earlier by the `day-of-brief` skill); valid values `mock` / `http` / `ros2` / `lerobot` / `reachy_mini` / `unitree_go2`; override one-off with `--robot <adapter>`. |
| **`git push`** | `git push` | **You only.** Denied to Claude by project policy. |

Everything else (doctor, recon, bootstrap, serve, probe, calibrate, rehearse, regression, demo record, git tag) — Claude runs them.

For day-to-day dev (today, T-2 days), you don't run `hack agent run` at all — use `hack rehearse <scenario>` (scripted, deterministic, ~6s) or `hack tui` (interactive, mic-driven). `agent run` is only meaningful day-of with a real robot + real cues.

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
| T+1:45 robot crashing | MockRobot + `uv run hack agent replay runs/submit-backup.jsonl` — same dashboard, identical to live. Last resort. |

**Never cut:** dashboard, JSONL logging, the adapter contract.

---

## What goes wrong (and the one-line fix)

| Symptom | Fix |
|---|---|
| `hack doctor` red on Ollama | `brew services start ollama` |
| `hack robot probe` fails | Don't edit runtime — it's the adapter file. Re-read SDK sample. |
| Latency > 2 s | Drop `agent.tick_hz` from 5 to 3. Or smaller LLM via **swap-llm**. |
| Robot moves crooked | You skipped calibrate. Say `/calibrate` to Claude (or run `hack calibrate --adapter <name>` for scales only). |
| Plan has 1 step instead of 6 | LLM too small. Confirm Nemotron / Qwen tag with `curl :8000/v1/models`. |
| Cube doesn't land in bin | Same as above (planner spatial precision). |
| Dashboard blank | TUI auto-tails newest JSONL. Day-of: check `hack agent run` is alive in pane 2 — restart it if not. Dev: `Ctrl+R` in TUI starts a fresh `hack rehearse`. |

---

## One rule

If you don't know what to do, say *"where am I"* to Claude. That's the whole skill.
