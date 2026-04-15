# hack — DIS2026X1 robot-agent hackathon

Pluggable AI-agent runtime for the Data Innovation Summit 2026 robot hackathon (Stockholm, 2026-05-08).

## Setup

New to the repo? Read **[`docs/ONBOARDING.md`](docs/ONBOARDING.md)** — it covers prerequisites, one-time setup steps (chmod, macOS camera/mic permissions, local model pulls), and the smoke test sequence.

Quick path for someone who already has `uv`, `ollama`, and the relevant OS permissions:

```bash
uv sync
uv pip install -e ".[audio,llm,dev]"
uv run hack doctor
```

## Usage

```bash
hack serve start                      # launch local model servers
hack robot probe --adapter mock       # cycle every adapter method
hack agent run --robot mock           # full loop with MockRobot
hack ui                               # dashboard on :8000
hack demo record && hack demo play    # for judges
```

See `docs/day_of_playbook.md` for the minute-by-minute plan.
