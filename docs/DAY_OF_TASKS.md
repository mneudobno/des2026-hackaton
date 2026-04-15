# Day-of live task board — team "Just Build", 2026-05-08

**Ticking this file is the source of truth during the build window.** The playbook (`day_of_playbook.md`) is strategy; this is tactics. Update on every commit. If a task isn't ticking in the time column it belongs to, invoke the cut-list.

Legend: **R** = Robot lead · **B** = Brain lead · **D** = Demo lead · **(all)** = sync everyone.

Roles are assigned in `docs/DAY_OF_INTAKE.md` §11 at T+0:25 and do not change after.

---

## T+0:00 — Reconnaissance (all together, 30 min)

- [ ] (all) Fill `docs/DAY_OF_INTAKE.md` live during the challenge intro
- [ ] (all) `uv run hack recon user@<zgx-a-ip>` and `uv run hack recon user@<zgx-b-ip>` — populates intake §6 automatically and saves `runs/recon-latest.json`
- [ ] (all) 5 min silent re-read of the intake, 5 min discuss
- [ ] (all) Assign roles (intake §11) and commit one-sentence primary behaviour (intake §8)
- [ ] (all) Walk `docs/DAY_OF_DECISIONS.md` top to bottom; commit the edits it produces

## T+0:15 — Parallel setup

- [ ] (R) `bash scripts/bootstrap_zgx.sh --role primary` on ZGX A · `--role secondary` on ZGX B
- [ ] (R) Read the robot SDK sample / README — note connection handshake and units
- [ ] (B) `uv run hack serve status --host <zgx-a-ip>` — must be green before touching agent code
- [ ] (B) Confirm `configs/agent.yaml` reflects Decisions §1–§5; `uv run hack agent run --robot mock` still works end-to-end
- [ ] (D) `uv run hack ui` on the demo laptop; browser open on `http://localhost:8000`
- [ ] (D) Start screen+audio recording (QuickTime or OBS) — demo backup starts now, not at the end
- [ ] (D) `du -h runs/` — confirm disk space for JSONL + video

## T+0:30 — First adapter probe

- [ ] (R) Create `src/hack/robot/<robot>.py` subclassing `RobotAdapter` per Decisions §1
- [ ] (R) Register in `src/hack/robot/__init__.py` `ADAPTERS[...]`
- [ ] (R) `uv run hack robot probe --adapter <robot>` — all 6 methods cycle without error (or `NotImplementedError` with a reason)
- [ ] (R) Commit with message "adapter: first probe green"
- [ ] (B) In parallel: draft task-specific prompts in `configs/agent.yaml` per Decisions §8
- [ ] (D) Verify dashboard sees JSONL events from `hack agent run --robot mock`

## T+0:45 — First real end-to-end

- [ ] (all) Confirm adapter probe is green before proceeding
- [ ] (R) `uv run hack agent run --robot <robot> --config configs/agent.yaml` — runs for 30 s without crashing
- [ ] (B) Open the JSONL in `runs/` — skim 5 observation/plan/action triples. Sanity-check tool choices.
- [ ] (D) Stopwatch: end-to-end observation → action latency. Write the number in intake §7 under "first-pass latency".
- [ ] (all) Apply Decisions §7 (latency target) — one config edit based on measured number
- [ ] **DECISION POINT:** if adapter probe failed, drop to MockRobot now (Decisions §10 defaults). Continue with scripted demo path.

## T+1:00 — Iterate (B & D), adapter polish (R)

- [ ] (B) Run `uv run hack agent replay runs/<latest>.jsonl` against tweaked prompts; `hack agent diff` the actions
- [ ] (B) Commit prompt changes with a one-line behaviour note (no `# DAYOF:` comments left in prompts)
- [ ] (R) Fix adapter edge cases discovered in the 30-s run (units, blocking calls, coordinate flips)
- [ ] (R) Add `emote()` mapping to any LEDs/canned poses the robot supports
- [ ] (D) Capture a clean-ish run video (not the final, but rehearsal)
- [ ] (D) Verify dashboard shows live camera + stream of events

## T+1:15 — Stretch features (only if T+1:00 ended green)

- [ ] (B) Enable `router` if decided in Decisions §4; verify shortcut path via a quick voice test
- [ ] (B) Enable `tracker` if Decisions §7 said to; observe if motion smoothens
- [ ] (R) Wire second ZGX into the agent if we're running hot on ZGX A (STT/TTS split)
- [ ] (D) Start writing the 60-second demo narration in `docs/submit/narration.md`

**If any T+1:15 task slips past T+1:25, drop it. Freeze begins at T+1:30.**

## T+1:30 — Freeze + demo prep

- [ ] (all) `git tag freeze` — no more code edits. Only `configs/agent.yaml` tuning allowed.
- [ ] (D) `uv run hack demo record --out runs/submit.jsonl --video runs/submit.mp4` — record 2 takes, keep the best
- [ ] (D) Verify `hack demo play runs/submit.jsonl` works with network cable unplugged
- [ ] (D) Screenshots for `docs/submit/`: dashboard mid-run, robot in action, transcript panel
- [ ] (B) Lock the final `agent.yaml` — no more prompt edits
- [ ] (R) Adapter on read-only — no more changes

## T+1:45 — Final capture

- [ ] (D) Final recorded take
- [ ] (D) Print the judge handoff sheet (team name **Just Build**, one-sentence what to watch for, trigger steps, fallback command)
- [ ] (all) Run `uv run hack doctor` one last time — screenshot green rows
- [ ] (all) `git tag submit` and commit the submission artefacts under `docs/submit/`

## T+1:55 — Submit

- [ ] (all) Hand over to judges per the organiser's submission mechanism
- [ ] (all) Shut the laptops. Breathe.

---

## Kill-switch reference (from `day_of_playbook.md` cut-list)

| At | If | Drop |
|---|---|---|
| T+1:00 | adapter still red | Go to MockRobot + scripted demo (Decisions §10) |
| T+1:00 | STT flaky | Text input via dashboard instead |
| T+1:15 | latency > 3.5 s | Smaller model (Decisions §7 last row) |
| T+1:30 | anything new crashing | Roll back to last green commit via `git reset --hard <sha>` (ask before force operations) |
| T+1:45 | live run unreliable | Ship the recorded take only |

Never drop: dashboard, JSONL logs, the single `RobotAdapter` (no parallel adapters).
