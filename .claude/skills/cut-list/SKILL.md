---
name: cut-list
description: Walk through the day-of cut-list in order with concrete repo edits when the team is behind schedule. Trigger on "we're behind", "cut audio", "drop TTS", "fall back to mock", "freeze and ship", "T+1:30", "T+1:45", or any indication that latency, stability, or behaviour is degrading and the playbook says to start cutting. Owns the order so the team doesn't debate.
---

# cut-list — disciplined retreat under time pressure

The playbook (`docs/day_of_playbook.md`) lists four cuts. Apply them **in
order**. Never skip ahead; never reverse. Every cut is a config or task
change with a concrete commit. Goal: ship a working demo, not the original
plan.

## Trigger thresholds (from playbook)

| At | Symptom | Cut to apply |
|---|---|---|
| Anytime | `hack commentate` pane is slow, wrong, or distracting | **Cut #0: Kill commentator pane** (Ctrl+C in pane 3 — agent and dashboard keep running, demo unaffected) |
| T+1:00 if behind | Audio loop flaky, mic drops cues, STT errors | **Cut #1: Drop audio input** |
| T+1:15 if behind | TTS stutter, voice loop adds latency | **Cut #2: Drop TTS** |
| T+1:30 if behind | Two-host orchestration is brittle, failover noisy | **Cut #3: Drop second ZGX** |
| T+1:45 if behind | Live robot crashes mid-run, adapter unstable | **Cut #4: Drop live robot** |

If the user invokes you, ask which cut they're on (or infer from clock).
Never apply more than one cut in a single invocation — each cut is a commit.

## Cut #1 — Drop audio input

Replace mic-driven cues with text input from the dashboard or TUI.

**Edits:**
```yaml
# configs/agent.yaml
stt:
  provider: none      # was: faster-whisper / riva
```
Ensure `agent.tick_hz` stays at 5; the planner now waits for text cues
typed in the TUI (`Ctrl+M` is moot when STT is off — direct text input via
TUI prompt or `hack agent run` stdin still works).

**Smoke test:** `uv run hack rehearse --scenario chit-chat` — should still
complete because rehearsal cues are scripted, not audio-derived.

**Commit:** `cut #1: drop audio input — rely on dashboard text cues`.

## Cut #2 — Drop TTS

Robot stops talking; logs/dashboard show what it would have said.

**Edits:**
```yaml
# configs/agent.yaml
tts:
  provider: none      # was: piper / kokoro
  barge_in: false
```
Confirm the runtime tolerates `provider: none` — if not, set
`provider: piper` and `voice: ""` to make it a no-op. (Search runtime for
`tts` to verify.)

**Smoke test:** Run a 30-tick agent loop and confirm no TTS errors in the
trace; `speak` tool calls should still appear in the JSONL.

**Commit:** `cut #2: drop TTS — speak events still logged for narration`.

## Cut #3 — Drop second ZGX

Single-host inference. No failover list, no two-host pipeline parallelism.

**Edits:**
```yaml
# configs/agent.yaml
llm:
  base_urls: []                # remove ZGX-B failover
vlm:
  base_urls: []
agent:
  pipeline_parallel: false     # already default; ensure it's not enabled
```
If both LLM and VLM were on the same single host, this is a no-op for
the failover list and just disables parallel mode. If LLM was on
ZGX-A and VLM on ZGX-B, point both at A:
```yaml
vlm:
  base_url: http://<zgx-a-ip>:8000/v1
```

**Smoke test:** `uv run hack rehearse --scenario obstacle-corridor` —
should still hit grade B or better. Note latency in `docs/REHEARSALS.md`.

**Commit:** `cut #3: single-ZGX inference — drop ZGX-B failover`.

## Cut #4 — Drop live robot (last resort)

MockRobot inside the runtime + replay a known-good JSONL trace for the
judge demo.

**Edits:**
```yaml
# configs/agent.yaml
robot:
  adapter: mock                # was: reachy_mini / unitree_go2 / http
```

**Replay artifact, in priority order:**
1. **`runs/submit-backup.jsonl`** — the pre-event canonical fallback trace
   (committed to the repo; not gitignored). Captured T-2 days from a clean
   `obstacle-corridor` rehearsal: grade A, 0 collisions, success ✅.
   This always works. Use first.
2. The most recent successful real-robot trace (only if available):
   ```
   ls -t runs/rehearsal-*.jsonl runs/agent-*.jsonl 2>/dev/null | head -3
   ```

Run replay for the live narration:
```
uv run hack agent replay runs/submit-backup.jsonl
```

Keep one printed video file path on the judge handoff sheet as a
secondary backup if replay also fails.

**Smoke test:** `uv run hack agent run --robot mock --duration 20` should
produce a clean trace with plan + action events.

**Commit:** `cut #4: live robot replaced with MockRobot + recorded take`.
**Tag:** `git tag submit` after this commit if it's the final state.

## After every cut

1. Re-run `uv run hack doctor`.
2. Update `docs/REHEARSALS.md` with one line: `cut N applied at T+H:MM, reason X, smoke test result Y`.
3. Tell the user: "Cut #N applied. Next cut at T+H:MM is <Cut N+1> if <symptom>; otherwise hold."
4. Do **not** preemptively apply the next cut. Wait for the next trigger.

## What never gets cut

- The dashboard (`hack ui`).
- JSONL logging (`logging.jsonl_dir: runs/`).
- The robot adapter contract — never write a parallel adapter mid-build.
- The 60-second narration plan from `docs/DEMO_SCRIPT.md`.

## When to escalate instead of cut

If the symptom doesn't match a cut row (e.g. dashboard crashes), **do not
invent a cut**. Tell the user what you observed and ask for direction. The
cut-list is for predictable failure modes, not improvisation.
