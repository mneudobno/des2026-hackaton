# Team onboarding

Get from zero to a working `hack agent run --robot mock` in about 15 minutes. Run the steps in order; each is idempotent.

## 1. Prerequisites

| Tool | Why | Install |
|------|-----|---------|
| Python ≥ 3.11 | runtime | macOS: `brew install python@3.12` · Linux: distro pkg |
| `uv` | the only allowed package manager for this repo | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Git | source control | already installed |
| `ollama` | local LLM/VLM serving for the agent loop | `brew install ollama` (macOS) · `curl -fsSL https://ollama.com/install.sh \| sh` (Linux) |
| (Optional) `piper` | Linux/ZGX TTS — macOS uses built-in `say` | `pip install piper-tts` and download a voice |
| Webcam + mic | sensor smoke tests | built-in is fine |

> **Do not run `pip` directly.** All Python operations go through `uv`.

## 2. Clone and install

```bash
git clone <repo-url> hackaton
cd hackaton

# Create the venv and install all extras (audio + llm + dev)
uv sync
uv pip install -e ".[audio,llm,dev]"
```

This installs the `hack` CLI on your `$PATH` (inside `.venv`). Run `uv run hack --help` or activate the venv first.

## 3. One-time setup steps

These steps are not handled by `uv sync` — you must run them once per machine.

### a. Make scripts executable

The shell scripts under `scripts/` ship executable from git, but if `git` lost the bit (e.g. on Windows checkouts) restore it:

```bash
chmod +x scripts/bootstrap_zgx.sh
```

### b. Grant macOS permissions

macOS gates camera and microphone access. The first time `hack doctor`, `hack sensors camera`, or `hack sensors mic` runs you'll get a system prompt — **click Allow**. If you missed it:

- **Camera:** System Settings → Privacy & Security → Camera → enable Terminal (or your IDE)
- **Microphone:** System Settings → Privacy & Security → Microphone → same
- **Screen recording** (only needed for `hack demo record --video`): same path

### c. Start Ollama and pull models

```bash
# macOS (Homebrew):
brew services start ollama       # background service, restarts at login
# Linux (or one-off):
nohup ollama serve >/tmp/ollama.log 2>&1 &

# Smoke test the daemon:
curl -sf http://127.0.0.1:11434/api/tags && echo " ollama up"

# Pull the dev models (~10 GB total, runs once)
ollama pull qwen2.5:7b           # LLM planner
ollama pull qwen2.5vl:7b         # VLM (note: no dash in the Ollama tag)
```

These two models match `configs/agent.yaml` defaults and are sized for a Mac. On the day-of ZGX boxes the bigger `qwen2.5:14b-instruct` (and optionally `llama-3.3-70b` via NIM) is pulled automatically by `scripts/bootstrap_zgx.sh`.

To stop the service later: `brew services stop ollama` (macOS) or `pkill -x ollama` (Linux).

To reclaim disk space: `ollama list` then `ollama rm <model>` (denied for Claude — run yourself).

## 4. Smoke test

```bash
uv run hack doctor                     # all rows green (or amber on Mac for nvidia-smi)
uv run hack robot probe --adapter mock # cycles all 6 methods, prints state
uv run pytest                          # unit tests pass
uv run hack ui                         # open http://127.0.0.1:8000 in browser
```

After §3c, the full agent loop should work on the Mac:

```bash
uv run hack serve status                       # ollama row green
uv run hack agent run --robot mock             # webcam → VLM → planner → MockRobot prints commands
# in another shell:
uv run hack ui                                 # http://127.0.0.1:8000 — live dashboard
```

If you skipped §3c, `hack agent run` will error on the first VLM call — that's expected and means the wiring is correct, just no model.

## 5. Claude Code

This repo is set up for fast, low-friction Claude Code sessions. `.claude/settings.json` is committed and pre-approves all the safe operations you'll routinely need (`uv`, `hack`, `pytest`, `ruff`, local `git` minus `push`, edits within `src/`/`tests/`/`docs/`/`configs/`/`scripts/`, doc-site `WebFetch`, etc.) and explicitly denies the dangerous ones (`git push`, `sudo`, `rm -rf`, secret reads).

Open the project directory in Claude Code and you should see virtually no permission prompts during normal work. A `SessionStart` hook auto-runs `uv sync` if `.venv` is missing; a `PostToolUse` hook runs `ruff check --fix` on edited Python files.

For personal overrides (e.g. enabling `git push` for yourself), copy:

```bash
cp .claude/settings.local.json.example .claude/settings.local.json
# edit your additions; this file is gitignored
```

The four project skills under `.claude/skills/` (`robot-adapter`, `agent-prompt`, `zgx-bootstrap`, `demo-polish`) are auto-discovered. Trigger them by describing the matching task — Claude will follow the SKILL.md steps verbatim, which is exactly what you want under hackathon time pressure.

## 6. Where to read next

- `CLAUDE.md` — architectural commitments and day-of rules. Read before changing anything in `src/hack/agent/runtime.py`.
- `docs/day_of_playbook.md` — minute-by-minute schedule and roles for May 8.
- `docs/zgx_overview.md` — what the ZGX Nano is and how we use it (read first).
- `docs/zgx_notes.md` — DGX OS / NIM / Ollama ops cheatsheet for the event hardware.
- `docs/prior_art.md` — similar setups, repos to study, lessons we're borrowing.
- `docs/DAY_OF_INTAKE.md` / `docs/DAY_OF_DECISIONS.md` / `docs/DAY_OF_TASKS.md` — event-day tactical docs.
- `scripts/zgx_recon.sh` + `hack recon <host>` — machine-side setup snapshot (pure bash, no deps on the target).
- `.claude/skills/*/SKILL.md` — pre-canned procedures Claude (and you) should follow for the four common day-of tasks.

## 7. Daily workflow

```bash
git pull
uv sync                  # picks up any dependency changes
uv run hack doctor       # verify env still healthy
# work on your assigned slice (see day_of_playbook.md roles)
uv run pytest            # before committing
git commit
```

## 8. Troubleshooting

| Symptom | Fix |
|--------|-----|
| `hack: command not found` | run `uv run hack ...` or `source .venv/bin/activate` |
| `cv2` import error on macOS | `uv pip install --reinstall opencv-python` |
| `sounddevice` cannot find PortAudio | macOS: `brew install portaudio`; Linux: `apt install libportaudio2` |
| Camera shows black frame | macOS privacy permissions (§3b) or another app holds the device |
| Ollama 404 on first call | `ollama pull <model>` — name must exactly match `configs/agent.yaml` (note `qwen2.5vl:7b` has no dash) |
| `Connection refused` on `:11434` | `brew services start ollama` (macOS) or `nohup ollama serve &` (Linux) |
| Ollama eats RAM | edit `configs/agent.yaml` to a smaller model, then `ollama rm` the big one |
| `bootstrap_zgx.sh: Permission denied` | `chmod +x scripts/bootstrap_zgx.sh` (§3a) |

Stuck longer than 10 minutes? Ping the team channel — don't burn time alone.
