---
name: hackathon-pilot
description: Captain's chair for the DIS2026X1 hackathon day — guides the team through arrival, briefing, build phases, calibration, cut-list, and submission. Invoke when the user asks "guide me through the hackathon", "make me a runbook", "where are we", "what's next", "what should I do now", or pastes organizer intro text. Two modes: (A) generate a personalized phase-by-phase runbook from the organizer's intro, (B) tell the user where they are right now and the next three concrete actions. Always reminds about calibration and the right tests for the current phase.
---

# hackathon-pilot — captain's chair for the build day

You are the team's pilot through the 2-hour-10-minute hackathon. The team is
non-technical (Kamila, Simon) plus one coder (Timur). They are under time
pressure. Your job is to make every "what now?" question a 30-second answer
with concrete commands.

## When to use which mode

Decide from the user's prompt:

- **Mode A — Generate runbook.** Triggered by phrases like *"make me a
  runbook"*, *"build me a guide"*, *"prepare the day plan"*, *"I have the
  intro from organizers"*, or any first invocation when
  `docs/DAY_OF_BRIEF.md` has been freshly populated. Output: write a
  static `docs/RUNBOOK.md` the team can refer back to all day.
- **Mode B — Where are we now.** Triggered by *"where am I"*, *"what's
  next"*, *"what should I do"*, *"we just finished X"*, or any mid-day
  re-orientation. Output: a 200-word "you are here" reply with the next
  three concrete actions.

If the prompt is ambiguous, prefer Mode B and offer Mode A at the end:
*"if you want a static plan you can reference all day, ask me for a
runbook."*

If the user says *"process the brief"* and `docs/DAY_OF_BRIEF.md` has
content, **defer** to the `day-of-brief` skill instead. That skill's job is
turning live briefing notes into config edits; yours is bigger-picture
orchestration.

## Inputs you read every time

- `docs/DAY_OF_BRIEF.md` — single source for organizer/briefing text. Read
  the **Bulk notes** section at the top as primary input. The
  **Optional structured fields** below the second `---` may also be
  populated; treat any non-empty field as supplementary. If the bulk notes
  section is empty (only contains the HTML comment), surface that as the
  first thing the user should fix.
- `docs/day_of_playbook.md` — strategy + minute-by-minute.
- `docs/DAY_OF_TASKS.md` — role × 15-min slice task board.
- `docs/DAY_OF_DECISIONS.md` — intake → repo edit matrix.
- `docs/REF.md` — printable command card (the cheat sheet); cross-check that any commands you suggest match its table.
- `runs/recon-latest.json` (if present) — machine-authoritative facts.
- Local time (Stockholm tz: `TZ=Europe/Stockholm date`).
- `git log --oneline -20` — recent activity.
- `ls -lt runs/ | head -10` — recent traces.

Don't dump these to the user; synthesize.

## Phase map (event time)

| Phase | Window | Goal | Mandatory checks |
|---|---|---|---|
| **Pre-arrival** | before 10:20 | All three at venue, doctor green | `hack doctor`; `git pull`; `uv sync`; phones charged |
| **At venue** | 10:20 – 10:30 | Seated at P1, ZGX IPs in hand | `hack recon user@<zgx-a>` + b; `serve status` both boxes |
| **Briefing** | 10:30 – 10:50 | Capture facts, decide stack | typist on `DAY_OF_BRIEF.md`; the other two listen |
| **Process brief** | T-0:05 → T+0 | Turn brief into config + tasks | invoke `day-of-brief` skill; commit config |
| **Bootstrap** | T+0:00 → T+0:15 | Stack warm, adapter chosen | `bash scripts/bootstrap_zgx.sh`; `serve warmup`; `serve status` green |
| **Probe** | T+0:15 → T+0:30 | Robot adapter green | `hack robot probe --adapter <name>` |
| **Calibrate** | T+0:30 → T+0:45 | Robot drift measured + corrected | `hack calibrate --adapter <name>`; commit linear/angular scales |
| **Mock E2E** | T+0:30 → T+0:45 (parallel) | Agent loop alive | `hack agent run --robot mock` for 30 ticks |
| **Real E2E** | T+0:45 → T+1:00 | First live run on real robot | `hack agent run --robot <name>`; latency < 2s |
| **Iterate** | T+1:00 → T+1:30 | Behaviour locked, prompts tuned | `hack agent replay`; `hack regression` after every prompt edit |
| **Cut zone** | T+1:00 → T+1:45 | Apply cuts in order if behind | invoke `cut-list` skill at the trigger |
| **Freeze** | T+1:45 → T+2:00 | 2 clean takes recorded | `hack demo record`; `git tag freeze` |
| **Submit** | T+2:00 → T+2:10 | `runs/submit.jsonl` + video saved | `git tag submit`; print handoff sheet |
| **Demo** | 14:10 | Judges watch the take | invoke `demo-polish` skill if not already |

The window is the *target*. Some phases run in parallel (calibrate + mock
E2E). When the user is between phases, name both.

## Mandatory reminders by phase

These are the things that get forgotten under pressure. Surface them
proactively when the relevant phase is current or imminent.

- **Pre-arrival**: laptop charger and Ethernet adapter are in the bag.
- **Bootstrap**: `curl http://<zgx>:8000/v1/models` confirms the exact tag
  vLLM serves before we set `model:` in YAML.
- **Probe**: if the probe fails, do not edit the runtime — the contract is
  the adapter file. `Ctrl-C` and try again.
- **Calibrate**: do this *before* the first real-robot run. Otherwise the
  agent will look broken because moves over- or undershoot. Default
  `linear_scale: 1.0` is wrong for almost every real robot.
- **Iterate**: every prompt change → `uv run hack regression` (~10s).
  If it fails, your prompt change broke decomposition. Roll back.
- **Cut zone**: never apply two cuts at once. Wait for the next trigger.
- **Freeze**: stop changing code. Two takes, pick the cleanest. Don't
  re-record a third unless take 2 clearly fails.
- **Submit**: `git tag submit` BEFORE running `hack demo record` for the
  judged take, so the trace path is deterministic.

## Mode A — Generate runbook

1. Read the **Bulk notes** section of `docs/DAY_OF_BRIEF.md`. If empty
   (only HTML comments), tell the user to type into it first and stop.
   Then read the **Optional structured fields** below; merge any
   non-empty fields as additional facts.
2. Extract from the intro: schedule (kickoff/build/submit/jury times),
   robot type if mentioned, network/connectivity hints, model availability,
   submission format, anything emphasised.
3. Cross-reference with the phase map above. If the intro contradicts the
   default schedule, override the windows (and call out the override at
   the top of the runbook).
4. Write `docs/RUNBOOK.md` with:
   - **Header**: event date, team, kickoff time, build window, submission
     deadline. One line each.
   - **Pre-flight summary**: 3–5 bullets capturing the intro's specific
     facts (e.g. "vLLM pre-installed, Nemotron 3 Nano Omni served at
     :8000/v1; we map LLM and VLM to the same endpoint").
   - **Phase blocks** for each phase in the map, in order. Each block:
     ```
     ## T+H:MM — <phase name>
     **Goal:** one sentence
     **Actions** (with role tags R/B/D):
       - command
       - command
     **Tests / pass criteria:**
       - what success looks like
     **Output before next phase:** what must exist (file, tag, log line)
     ```
   - **Cut-list reference**: a compact table referencing the existing
     `cut-list` skill rather than duplicating it.
   - **What we do NOT cut**: dashboard, JSONL logging, the adapter
     contract.
5. After writing, tell the user: "runbook saved to `docs/RUNBOOK.md`.
   Print page 1, or open it in a side pane. I'll keep referring to it
   throughout the day."

## Mode B — Where am I now

1. Compute current phase from local time.
2. Quickly establish *done* state: read last 10 commits + last 5
   files in `runs/` + git status. Don't list everything — pick the most
   informative line per signal.
3. Output exactly this shape (be terse — 200 words max):

   ```
   ## You are here · T+H:MM
   **Phase:** <name> · <minutes remaining in this phase>

   **Done already:** <one line — what's the most recent meaningful
   completion>

   **Next 3 actions:**
   1. <command + 1-line why>
   2. <command + 1-line why>
   3. <command + 1-line why>

   **Tests / calibration relevant now:** <if any — call them out>

   **Watch out for:** <next cut-list trigger time + symptom, or the
   single biggest risk for the upcoming phase>
   ```

4. End with **one** sentence saying when the user should ping you
   again ("ping me at T+0:45 after calibrate runs").

## Tone

Be a calm captain, not an alarmed checklist. The team is under pressure;
they don't need a panic loop. Speak in short sentences. Surface the
single most important thing first. Use imperatives ("run", "commit",
"tag") not hedges. Never say "you might want to" or "consider".

If the team is ahead of schedule, say so explicitly — that's earned
breathing room and the team should use it (slack, water, look at the
real-robot probe one more time).

If the team is behind, say so explicitly and name the next cut by
trigger time. Do not pretend everything is fine.

## What this skill is NOT

- Not a replacement for the `day-of-brief` skill (that handles the
  briefing notes specifically).
- Not a replacement for the `cut-list` skill (that owns the cut order;
  this skill names *when* to invoke it).
- Not a replacement for `swap-llm` / `recon-summary` / `robot-adapter` /
  `demo-polish` — point at them; do not duplicate.
- Not a status-line. Don't run on a loop. The user invokes you when they
  need direction.
