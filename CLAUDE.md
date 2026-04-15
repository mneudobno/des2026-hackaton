# Project: DIS2026X1 hackathon agent (`hack`)

## Event

- **When/where:** 2026-05-08, Kistamässan, Stockholm (DIS2026X1).
- **Constraint:** 2-hour build window after a 30-min challenge reveal.
- **Team:** 3 people.
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
- Day-of swap: change `model:` in `configs/agent.yaml` to `qwen2.5:14b-instruct` and point `base_url` at the ZGX IP. No code changes required.

## Architectural commitments (do not violate)

- **Pluggable `RobotAdapter`** (`src/hack/robot/base.py`) is the only integration surface. Day-of work = implement one adapter, not rewrite the runtime.
- **Python 3.11+, uv-managed.** Never call `pip` directly; use `uv pip`, `uv run`, `uv sync`.
- **Pydantic for every structured I/O** (observations, actions, config).
- **Local inference only** — no cloud fallbacks in the judged run. Ollama for fallback, NVIDIA NIM for primary serving.
- **Single CLI entry point `hack`** (Typer). New functionality extends the CLI, not random scripts.
- **JSONL logging everywhere** — every observation, plan, action. Demo replays from these logs.

## Day-of rules

1. At 10:30, run `hack doctor`. If any red, fix before writing agent code.
2. Never rewrite `agent/runtime.py` — only touch `configs/agent.yaml`, prompts, and the new robot adapter.
3. Preserve JSONL traces under `runs/` — they are the demo.
4. **Cut-list at T-30 min:** kill audio if flaky, fall back to MockRobot + scripted demo if adapter broken, disable dashboard if unstable.
5. Commit often. Branch per risky change.

## Key files

- `src/hack/cli.py` — CLI surface (Typer).
- `src/hack/robot/base.py` — adapter contract.
- `src/hack/agent/runtime.py` — event loop (leave alone day-of).
- `configs/agent.yaml` — prompts and model choices (tune freely).
- `scripts/bootstrap_zgx.sh` — ZGX Nano cold-start.
- `docs/day_of_playbook.md` — minute-by-minute plan.
- `docs/zgx_notes.md` — DGX OS / NIM cheatsheet.

## Skills

Use `.claude/skills/` entries when they match — do not reinvent their steps:

- `robot-adapter` — wiring a new robot SDK
- `agent-prompt` — prompt iteration via replay
- `zgx-bootstrap` — bringing up the ZGX Nano serving stack
- `demo-polish` — final submission prep

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
