# hack — team "Just Build" @ DIS2026X1

Pluggable AI-agent runtime for the Data Innovation Summit 2026 robot hackathon (Stockholm, 2026-05-08). Team: **Just Build**.

## Setup

For day-of operation, the only doc you need is **[`docs/REF.md`](docs/REF.md)** — a one-page printable command card.

Quick setup for someone who already has `uv`, `ollama`, and the relevant OS permissions:

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

See `docs/day_of_playbook.md` for the minute-by-minute plan, and **`docs/PREP_TODO.md` for current prep status and what's left**.
