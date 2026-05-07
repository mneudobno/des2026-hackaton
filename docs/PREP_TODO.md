# Preparation TODO — "Just Build" for DIS2026X1 (2026-05-08)

Single source of truth for hackathon prep. Keep this updated as we go — tick items with `[x]`, add notes inline. **Last updated: 2026-04-18.**

See also: [`PRE_EVENT_CHECKLIST.md`](./PRE_EVENT_CHECKLIST.md) (consolidated action list with commands + completion signals), [`DEMO_SCRIPT.md`](./DEMO_SCRIPT.md) (60-sec narration mapped to current implementation).

> Status legend: ✅ done · 🟡 in progress · ⏳ blocked/waiting · ⬜ todo · ❌ won't do

## 0. Admin

- [x] ✅ Team formed: Timur, Kamila, Simon. Name: **Just Build**.
- [x] ✅ Git repo created and pushed: https://github.com/mneudobno/des2026-hackaton
- [x] ✅ Hackathon description saved (`hackaton_description.md`)
- [ ] ⬜ All three teammates have repo access (Kamila, Simon invited as collaborators)
- [ ] ⬜ All three have read `docs/ONBOARDING.md` and ran `uv run hack doctor` locally
- [ ] ⬜ Confirm event registration / seat for all three
- [ ] ⬜ Confirm travel + lodging for all three (Stockholm, May 7–8)
- [ ] ⬜ Email organizers: can we bring pre-pulled models / Docker images on USB?

## 1. Repo scaffolding (DONE)

- [x] ✅ `pyproject.toml` with uv, Typer CLI entry, `[audio]`/`[llm]`/`[dev]` extras
- [x] ✅ `src/hack/` package skeleton
- [x] ✅ `CLAUDE.md` with architectural commitments + Claude Code rules
- [x] ✅ Four project skills under `.claude/skills/` (robot-adapter, agent-prompt, zgx-bootstrap, demo-polish)
- [x] ✅ `.claude/settings.json` with pre-approved permissions + deny list + hooks
- [x] ✅ `.gitignore`, `README.md`

## 2. Core code (DONE)

- [x] ✅ `RobotAdapter` base + `MockRobot`, `HTTPRobot`, `ROS2Robot` stub
- [x] ✅ Camera sensor with FPS + frame-diff gating
- [x] ✅ VLM client (Ollama-compat) → Pydantic `Observation`
- [x] ✅ Audio-in (faster-whisper + Silero VAD)
- [x] ✅ TTS (Piper on Linux/ZGX, `say` fallback on macOS)
- [x] ✅ Agent runtime (planner + tools + JSONL logger + event loop)
- [x] ✅ FastAPI dashboard with SSE stream + camera panel
- [x] ✅ CLI: `doctor`, `serve {start|status|stop|warmup}`, `robot {probe|teleop}`, `agent {run|replay|diff}`, `sensors {camera|mic}`, `ui`, `demo {record|play}`
- [x] ✅ `scripts/bootstrap_zgx.sh` — idempotent ZGX cold-start
- [x] ✅ `configs/agent.yaml` — single tuning surface

## 3. Docs

- [x] ✅ `docs/ONBOARDING.md` — team ramp-up incl. chmod, macOS perms, ollama install
- [x] ✅ `docs/zgx_overview.md` — conceptual intro to the hardware
- [x] ✅ `docs/zgx_notes.md` — DGX OS / NIM / Ollama ops cheatsheet + latency budget
- [x] ✅ `docs/day_of_playbook.md` — minute-by-minute schedule, cut-list
- [x] ✅ `docs/PREP_TODO.md` — this file
- [ ] ⬜ Team roles assigned (R/B/D) in `day_of_playbook.md`

## 4. Local verification on Mac

- [x] ✅ `uv sync` + `uv pip install -e ".[audio,llm,dev]"` clean
- [x] ✅ `uv run pytest` — 3 passing
- [x] ✅ `uv run ruff check src tests` — clean
- [x] ✅ `uv run hack --help` + all subcommand helps render
- [x] ✅ `uv run hack doctor` — camera/mic/ports green (nvidia-smi expected red on Mac)
- [x] ✅ `uv run hack robot probe --adapter mock` cycles all 6 methods
- [x] ✅ `uv run hack ui` boots; `/`, `/camera.jpg`, `/events` SSE all 200
- [x] ✅ Planner + VLM clients verified against a fake Ollama (synthetic)
- [x] ✅ Ollama installed via Homebrew and running as a service
- [ ] 🟡 `ollama pull qwen2.5:7b` — pulling (~5 GB, background)
- [ ] 🟡 `ollama pull qwen2.5vl:7b` — pulling (~5 GB, background)
- [ ] ⏳ `uv run hack serve warmup` against real Ollama — blocked on pulls
- [ ] ⏳ Full `uv run hack agent run --robot mock` end-to-end (webcam → real VLM → real LLM → MockRobot) — blocked on pulls
- [ ] ⬜ `uv run hack sensors camera --show` — live preview on laptop
- [ ] ⬜ `uv run hack sensors mic --transcribe` — live STT on laptop (downloads Whisper on first run, ~500 MB)
- [ ] ⬜ Measure end-to-end latency: webcam → VLM → planner → action. Target <2 s. Log result here: **TBD ms**
- [ ] ⬜ Record one clean `hack demo record` run, play it back via `hack demo play`

## 5. Teammate onboarding (for Kamila + Simon)

- [ ] ⬜ Each clones repo and completes `docs/ONBOARDING.md` steps 1–4
- [ ] ⬜ Each runs `uv run hack doctor` and reports result in team channel
- [ ] ⬜ Each can run `uv run hack agent run --robot mock` locally end-to-end
- [ ] ⬜ Walkthrough session: 30 min screen share of architecture + CLI + day-of rules

## 5b. Prior-art follow-ups (from `docs/prior_art.md`)

- [x] ✅ Read [HuggingFace DGX+Reachy blog](https://huggingface.co/blog/nvidia-reachy-mini) — architecture, model list, NAT config extracted
- [x] ✅ Study [`NVIDIA/dgx-spark-playbooks` / spark-reachy-photo-booth](https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/spark-reachy-photo-booth) — service list, model stack
- [x] ✅ Study [`brevdev/reachy-personal-assistant`](https://github.com/brevdev/reachy-personal-assistant) — three-terminal launch, NAT router pattern
- [x] ✅ Study [HuggingFace LeRobot repo](https://github.com/huggingface/lerobot) — `Robot` interface confirmed: `connect/get_observation/send_action`
- [x] ✅ Add `LeRobotAdapter` skeleton in `src/hack/robot/lerobot_adapter.py`
- [x] ✅ Add `sensors/tracker.py` — CSRT tracker between VLM calls (HALO + ByteTrack pattern)
- [x] ✅ Add `agent/router.py` — intent router (Phi-3 pattern from NVIDIA's NAT config)
- [x] ✅ Rewrite `configs/agent.yaml` with three profiles (Mac / ZGX-Ollama / ZGX-NIM+Nemotron)
- [x] ✅ Add `[robot]` optional extra to `pyproject.toml` (`lerobot` guarded)
- [x] ✅ Expand `docs/zgx_notes.md` with Nemotron model set + NAT detection steps
- [ ] ⬜ Clone `NVIDIA/dgx-spark-playbooks` during DGX rehearsal and run the photo-booth docker-compose once
- [ ] ⬜ Wire the router into `runtime.py` (currently plumbed in config only; planner-shortcut path not implemented)
- [ ] ⬜ Wire `BBoxTracker` into `runtime.py` between VLM calls (reinit on new VLM bbox, use `update()` per frame for target poses)
- [ ] ⬜ Pull `phi3:mini` on Mac to exercise the router end-to-end: `ollama pull phi3:mini`

## 6. DGX-class rehearsal (before May 8)

- [ ] ⬜ Rent a DGX Spark / A100 instance on Lambda or RunPod (~1 hour)
- [ ] ⬜ Rsync repo to the rented host
- [ ] ⬜ Run `bash scripts/bootstrap_zgx.sh --role primary` end-to-end — fix any surprises
- [ ] ⬜ From laptop: `uv run hack serve status --host <rented-ip>` — green
- [ ] ⬜ Full agent loop against rented GPU — measure latency, compare to Mac
- [ ] ⬜ Update `docs/zgx_notes.md` with anything surprising

## 7. Pre-event checklist (May 7)

- [ ] ⬜ Pull latest from `main`, `uv sync`, `uv run hack doctor` — green on all three laptops
- [ ] ⬜ `git status` clean on all three
- [ ] ⬜ USB drive packed with: latest repo snapshot, pre-pulled model blobs (if organizers allow), printed `day_of_playbook.md` + `zgx_notes.md`
- [ ] ⬜ Pack: laptop + charger, Ethernet adapter, 2× USB-C cables, phones charged (video backup)
- [ ] ⬜ Sleep.

## 8. Event day (May 8)

Detailed role × 15-min-slice task board: **[`docs/DAY_OF_TASKS.md`](./DAY_OF_TASKS.md)**. Ticking that file is the day's source of truth.

Supporting artefacts (created during prep):
- [x] ✅ `docs/DAY_OF_INTAKE.md` — blank intake form filled live during intro
- [x] ✅ `docs/DAY_OF_DECISIONS.md` — intake answer → repo config/adapter mapping
- [x] ✅ `docs/DAY_OF_TASKS.md` — role × 15-min slice live task board
- [x] ✅ `# DAYOF:` markers placed across code and `configs/agent.yaml` (~18 sites)
- [x] ✅ `uv run hack intake` — prints recon summary (authoritative) + unfilled blanks + DAYOF punch-list + cut-list triggers
- [x] ✅ `scripts/zgx_recon.sh` + `uv run hack recon <host>` — machine-side setup snapshot (GPU, NIM, Ollama, disk, ports) saved to `runs/recon-latest.json`
- [x] ✅ `uv run hack rehearse --scenario <pick-and-place|follow|chit-chat|dance>` — virtual-world rehearsal with metrics JSON + regression diff vs previous run
- [x] ✅ Model adapter registry (`src/hack/models/`) — `LLMAdapter` / `VLMAdapter` ABCs + `ollama` / `gemini` / `openai-compat` / `nim` concrete; `make_llm(cfg)` / `make_vlm(cfg)` factories
- [x] ✅ Plan memory in shared core (`src/hack/agent/plan_memory.py`) — `PlanStep(text, tool?)`, decomposer emits pre-baked kinematic calls; runner executes tool-present steps directly (bypasses VLM+planner)
- [x] ✅ No-fallback runtime — unrecognised cues alert + idle in both rehearsal runner AND day-of `hack agent run`
- [x] ✅ Safety layer — clamp on every `move`, auto-split oversized pre-baked steps, semantic coverage check (move ≠ remember ≠ speak ≠ emote)
- [x] ✅ `uv run hack regression` — curated mic-cue suite (`spin_360`, `go_to_random_and_back`) + `docs/TEST_CUES.md`; gates prompt/config changes
- [x] ✅ Terminal-style rehearsal dashboard — Fallout-aesthetic green-on-black, plan decomposition panel, voice/alert/movement panels, errors-only alerts
- [x] ✅ Gemini free-tier fallback (`configs/agent.gemini.yaml`) — strong planner when Mac hardware limits bite
- [x] ✅ Obstacle simulation — `WorldObject.is_obstacle`, collision detection, mock VLM (`vlm.provider: mock`), avoidance system, `obstacle-course` scenario
- [x] ✅ `navigate_to_target` deterministic case — computes path to any named world object
- [x] ✅ `classify_cue` priority fix — destination keywords → return_to_origin; backward keywords → single_move
- [x] ✅ Scripted cue fix — scenario cues now trigger full decompose/classify pipeline
- [x] ✅ Obstacle avoidance tuning — lateral dodge passes all 3 scenarios (course/hard/wall) with zero collisions
- [ ] ⬜ PlanMemory unit tests (`tests/test_plan_memory.py`)
- [ ] ⬜ Commit + push latest classifier fix (`go back` → `return_to_origin`)
- [ ] ⬜ DGX-class rehearsal with rented GPU (1 hour on Lambda/RunPod)
- [ ] ⬜ Terminal UI: plan decomposition panel not yet wired to events
- [ ] ⬜ Add `navigate_to_goal` to regression suite (`docs/TEST_CUES.md`)
- [ ] ⬜ Teammate onboarding: Kamila + Simon clone + run `hack doctor`
- [x] ✅ `docs/REHEARSALS.md` — append-only rehearsal log (date, scenario, models, success, latency, insight, action)
- [x] ✅ **Dual-host readiness** — `agent.pipeline_parallel` flag overlaps VLM(frame_N) with planner(obs_{N-1}); 26/26 scenarios pass with it enabled
- [x] ✅ **Adapter failover** — `base_urls` list on LLM/VLM adapters; transparent rotation on `httpx` connect/read-timeout errors; 7 unit tests
- [x] ✅ **Reachy Mini adapter stub** (`src/hack/robot/reachy_mini.py`) — maps 6-method contract onto real Pollen SDK shape; async-wrapped via `asyncio.to_thread`
- [x] ✅ **Unitree Go2 adapter stub** (`src/hack/robot/unitree_go2.py`) — maps 6-method contract onto `unitree_sdk2py` sport-mode; acrobatic emotes gated
- [x] ✅ **Adapter contract tests** (`tests/test_robot_adapter_stubs.py`) — 14 tests, SDK imports stubbed via `sys.modules`
- [x] ✅ **Demo narration** (`docs/DEMO_SCRIPT.md`) — 60-sec script with every beat tied to a live artifact or JSONL event
- [x] ✅ **Pre-event checklist** (`docs/PRE_EVENT_CHECKLIST.md`) — consolidated T–20d → T+0 action list with commands + completion signals

High-level beats (see `DAY_OF_TASKS.md` for atomic checklist):
- [ ] ⬜ T+0:00 — intake fill; `hack doctor` on all laptops + both ZGXs
- [ ] ⬜ T+0:15 — parallel setup (R bootstrap, B config, D dashboard+recording)
- [ ] ⬜ T+0:30 — first adapter probe green
- [ ] ⬜ T+0:45 — first real end-to-end; measure latency
- [ ] ⬜ T+1:00 — iterate; adapter polish
- [ ] ⬜ T+1:15 — stretch features (only if green)
- [ ] ⬜ T+1:30 — freeze + demo prep
- [ ] ⬜ T+1:45 — final capture + judge handoff sheet
- [ ] ⬜ T+1:55 — submit

## Open questions / research items

- [ ] ⬜ Which exact NIM containers ship on DGX OS by default? (verify at event)
- [ ] ⬜ Does event allow pre-shipped Docker images / USB models? (email organizers)
- [ ] ⬜ Likely robot type: mobile base, arm, quadruped, humanoid? (unknown until intro — our 6-method adapter covers all four)
- [ ] ⬜ Is Ethernet provided at every team station? (assume yes, bring adapter regardless)

## Risks

| Risk | Mitigation |
|---|---|
| NIM container wedges mid-build | Ollama fallback already in bootstrap script |
| Robot SDK has no Python bindings | `HTTPRobot` / `ROS2Robot` stubs cover most cases; worst case 20 min to wrap a CLI |
| Audio flaky in loud venue | Cut-list: drop audio, use dashboard text input |
| Latency > 2s | Drop VLM model size → FPS → LLM max_tokens (in that order) |
| Both ZGX go down | MockRobot + scripted demo; still shows agent quality |
