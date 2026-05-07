# Project: DIS2026X1 hackathon agent (`hack`)

## Event

- **Team:** **Just Build** — Timur (repo owner), Kamila, Simon.
- **When/where:** 2026-05-08, Kistamässan, Stockholm (DIS2026X1).
- **Constraint:** 2-hour build window after a 30-min challenge reveal.
- **Goal:** AI agent that controls a physical robot using vision + audio.
- **Evaluation:** hardware utilization, sensor/input integration, agent quality.
- **Prize:** HP ZGX Nano AI Station.

## Hardware provided

- 2× **HP ZGX Nano AI Station** per team (NVIDIA GB10 Grace Blackwell, 128 GB unified RAM, 1000 TOPS FP4, DGX OS).
- Paired to the user's laptop via 200 Gbps networking.
- Physical robot — **SDK unknown until event start**.

## Local dev setup (Mac)

- Ollama runs as a Homebrew background service: `brew services start ollama`. Endpoint is `http://127.0.0.1:11434`.
- Default Mac models: `qwen2.5:7b` (LLM) and `qwen2.5vl:7b` (VLM — no dash in the Ollama tag, has dash in NIM containers). Both are wired into `configs/agent.yaml`.
- Day-of swap: ZGX boxes ship with **vLLM + llama.cpp + Nemotron + OpenCode pre-installed** (organizer email 2026-05-05). Provided models: **NVIDIA Nemotron 3 Nano Omni** (multimodal — single endpoint can serve both LLM and VLM roles) and **Qwen 3.6 35B A3B** (LLM, MoE-style). Switch `provider: openai-compat`, set `model:` to the exact tag vLLM serves (confirm at event start), point `base_url` at `http://<zgx-a>:8000/v1`. No code changes required.

## Architectural commitments (do not violate)

- **Pluggable `RobotAdapter`** (`src/hack/robot/base.py`) is the only robot integration surface. Day-of work = implement one adapter, not rewrite the runtime.
- **Pluggable model adapters** (`src/hack/models/`) — `LLMAdapter` + `VLMAdapter` ABCs with `ollama` / `gemini` / `openai-compat` / `nim` concrete. Runtime consumes them via `make_llm(cfg['llm'])` / `make_vlm(cfg['vlm'])`. Swap providers by editing YAML — never by touching runtime code.
- **Plan memory** (`src/hack/agent/plan_memory.py`) — shared between `hack.agent.runtime` (judged demo) and `hack.rehearsal.runner` (playground). A voice cue triggers decomposition into typed `PlanStep(text, tool?)` objects. Pre-baked steps (tool present) execute directly, bypassing VLM+planner. Unrecognised cues alert + idle — **no fallback behaviour anywhere**.
- **Safety layer** — `plan_memory.clamp_call()` caps every `move` to `robot.safety`; `expand_plan_steps()` auto-splits oversized pre-baked moves; `required_tools_for_step()` enforces semantic coverage (`speak` != `move`).
- **Regression gate** — `uv run hack regression` runs the curated cue suite in `docs/TEST_CUES.md` against any config. Must pass before committing prompt/runner changes.
- **Python 3.11+, uv-managed.** Never call `pip` directly; use `uv pip`, `uv run`, `uv sync`.
- **Pydantic for every structured I/O** (observations, actions, config).
- **Local inference only on the judged run.** Ollama / NIM. Gemini is allowed for rehearsal only.
- **Single CLI entry point `hack`** (Typer).
- **JSONL logging everywhere** — every observation, plan, action, alert. Demo replays from these logs.

## Day-of rules

1. At 10:30, run `hack doctor`. If any red, fix before writing agent code.
2. Never rewrite `agent/runtime.py` — only touch `configs/agent.yaml`, prompts, and the new robot adapter.
3. Preserve JSONL traces under `runs/` — they are the demo.
4. **Cut-list at T-30 min:** kill audio if flaky, fall back to MockRobot + scripted demo if adapter broken, disable dashboard if unstable.
5. Commit often. Branch per risky change.

## Prep tracking

`docs/PREP_TODO.md` is the single source of truth for "what's done, what's next." **Keep it updated**: when you complete a substantive item, tick it there in the same change. When you discover new work, add it.

## Auto log watching (mandatory)

**Whenever the user starts a TUI session, rehearsal, or says "test it" / "try it" / "I'm testing":**
1. Immediately arm a Monitor on the latest `runs/rehearsal-*.jsonl` using `/tmp/hack_watch.py`.
2. Do NOT ask for permission — this is pre-approved.
3. Report events inline (cues, plans, actions, alerts, STOP results).
4. If the monitor times out and the user is still testing, re-arm it.
5. After STOP, check `runs/issues.ndjson` for correctness findings.

This must happen automatically every time without the user asking.

## Rehearsal loop (pre-event)

`uv run hack rehearse --scenario <name>` runs the full agent against a virtual-world mock robot (synthetic frame rendering, scripted voice cues, success criterion). Writes `runs/rehearsal-<scenario>-<ts>.json` and prints regression diff vs previous run of the same scenario. Scenarios live in `src/hack/rehearsal/scenarios.py` — add new ones when the challenge shape suggests it.

After every code/config/prompt change: rehearse. After every rehearsal: append one row to `docs/REHEARSALS.md` with the insight and the action taken.

## Day-of workflow

At event start, in order:

1. `uv run hack recon user@<zgx-a>` and `uv run hack recon user@<zgx-b>` (also `--local` on each laptop). Produces `runs/recon-latest.json` — the **machine-authoritative** facts (GPU, NIM containers, Ollama state, disk, ports). This output overrides anything hand-written in intake §6.
2. **Free-text path (default):** one typist writes live notes into `docs/DAY_OF_BRIEF.md` during the intro. By T+0:25 they say *"process the brief"* and the `day-of-brief` skill turns it into a missing-facts list + proposed `configs/agent.yaml` edits + first three tasks per role. Skip the structured `DAY_OF_INTAKE.md` — the skill backfills it.
3. **Structured path (fallback):** if the team has time, fill `docs/DAY_OF_INTAKE.md` directly. Skip §6; recon covers it.
4. Walk `docs/DAY_OF_DECISIONS.md` top-to-bottom. Each row maps an intake/brief/recon answer to an explicit repo change.
5. Run `uv run hack intake` — prints recon summary (authoritative) + unfilled blanks + `# DAYOF:` code punch-list + cut-list triggers.
6. Open `docs/DAY_OF_TASKS.md` (role × 15-min slice) and start ticking.

**Rule:** `rg "# DAYOF:" -n` is the exhaustive code punch-list. Every touch-point expected to change on the day is tagged. Do not edit the runtime in ways these markers don't cover — that's scope creep under time pressure.

## Key files

- `docs/PREP_TODO.md` — prep tracker (update as items complete).
- `docs/PRE_EVENT_CHECKLIST.md` — consolidated T–20d → T+0 actionable list.
- `docs/ARCHITECTURE.md` — component layout + which machine runs what.
- `docs/DAY_OF_BRIEF.md` — free-text notes typed during the intro (primary path).
- `docs/DAY_OF_INTAKE.md` — structured 12-section intake (fallback path).
- `docs/DAY_OF_DECISIONS.md` — intake → repo choice matrix.
- `docs/DAY_OF_TASKS.md` — live task board for the 2-hour build.
- `docs/DEMO_SCRIPT.md` — 60-second judged-run narration.
- `src/hack/cli.py` — CLI surface (Typer).
- `src/hack/robot/base.py` — adapter contract.
- `src/hack/agent/runtime.py` — event loop (leave alone day-of).
- `configs/agent.yaml` — prompts and model choices (tune freely).
- `scripts/bootstrap_zgx.sh` — ZGX Nano cold-start.
- `docs/day_of_playbook.md` — minute-by-minute plan.
- `docs/zgx_notes.md` — DGX OS / NIM cheatsheet.

## Skills

Use `.claude/skills/` entries when they match — do not reinvent their steps:

**Setup / kickoff**
- `day-of-brief` — turn `docs/DAY_OF_BRIEF.md` into missing-facts list + config edits + first three tasks. Trigger: *"process the brief"* after the intro.
- `recon-summary` — run `hack recon` on both ZGX boxes and produce a 5-line summary + the next config edit. Trigger: *"recon"*, *"what's on the ZGX"*.
- `zgx-bootstrap` — bring up the ZGX Nano serving stack from cold.

**Build window (mid-flight)**
- `robot-adapter` — wire a new RobotAdapter once the SDK is known.
- `swap-llm` — swap LLM/VLM provider/model/base_url in `configs/agent.yaml` + smoke test. Trigger: *"swap LLM"*, *"flip to ZGX-B"*, *"fall back to laptop VLM"*.
- `agent-prompt` — prompt iteration via JSONL replay.
- `watch-rehearsal` — auto-monitors rehearsal logs (already on; mandatory).

**Cut-list / submit**
- `cut-list` — when behind schedule, owns the cut order so the team doesn't debate. Trigger: *"we're behind"*, *"T+1:30"*, *"drop audio"*.
- `demo-polish` — final 20-minute submission prep.

## Parallel work via subagents

Spawn `Agent(subagent_type="Explore", ...)` ad-hoc — no skill required — when:
- The robot is revealed and someone needs to read an unknown SDK while another teammate keeps building.
- A research question would dump >2 KB of search output into the main context (delegate, get a summary).
- Two independent investigations can run at once — send both Agent calls in a single message so they run in parallel.

Do **not** spawn subagents for: simple greps (use Bash), single-file reads (use Read), or anything where the answer is one tool call away.

## Working in this repo (Claude Code)

`.claude/settings.json` pre-approves the safe, common operations so you don't pause for confirmations. Specifically allowed without asking:

- All `uv`, `hack`, `pytest`, `ruff`, `pyright`, `python` invocations
- All read/inspect commands (`ls`, `cat`, `head`, `tail`, `git status`/`diff`/`log`, `nvidia-smi`, `ollama list`, `docker ps`, `lsof`, etc.)
- Edits and writes anywhere in `src/`, `tests/`, `docs/`, `configs/`, `scripts/`, `.claude/skills/`, `runs/`, plus top-level `README.md` / `CLAUDE.md` / `pyproject.toml` / `.gitignore`
- Local `git` operations including `add`, `commit`, `branch`, `switch`, `tag`, `stash`, `restore`, `fetch`, `pull`
- `WebFetch` against the docs sites we actually use (Python, Astral, FastAPI, Typer, Pydantic, Ollama, NVIDIA, HuggingFace, GitHub)

Explicitly **denied** (always requires user confirmation if absolutely needed): `git push` (any form), `git reset --hard`, `git clean -fd`, `sudo`, piping `curl` into a shell, removing models/containers, reading any `.env` / `~/.ssh` / `~/.aws` / `**/secrets/**`.

Behavioral consequences:

- **Just run the command.** Don't ask "should I run `uv run pytest`?" — run it.
- **Edit files directly.** Don't ask before modifying files in the allowed paths.
- **Read freely.** Use `Glob`/`Grep`/`Read` without preamble.
- **Do not attempt** to push, force-push, sudo, or read secrets. If the user wants a push, they can do it themselves with `! git push` or grant temporary permission.

A `SessionStart` hook ensures `.venv` exists; a `PostToolUse` hook runs `ruff check --fix` on any Python file you've edited. Don't fight either — they're idempotent.

For per-teammate overrides (extra domains, enabling `git push` for one person), copy `.claude/settings.local.json.example` → `.claude/settings.local.json` (gitignored).
