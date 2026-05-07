---
---

# Voice-cue regression suite

A small, hand-curated set of mic cues that every planner / decomposer / runner change should pass. Run it with:

```bash
uv run hack regression                                   # Ollama (default configs/agent.yaml)
uv run hack regression --config configs/agent.gemini.yaml
uv run hack regression --name spin_360                    # single case
```

Exit code 0 if all pass, 1 if any fail. Results land in `runs/regression-latest.json` and a row appended to `docs/REHEARSALS.md`.

The cases are defined in `src/hack/rehearsal/regression.py` (edit there to add/tweak).

## Cases

### 1. `spin_360`

**Cue:** `spin 360`

**What it tests:** the decomposer respects per-tick safety limits by emitting multiple small-rotation steps that sum to a full 2π.

**Pass criteria:**
- ≥6 pre-baked `move` steps.
- Sum of `dtheta` across all steps is in `[0.8·2π, 1.3·2π]` (i.e. 288°–468°). Allows slack for the decomposer rounding.

**Why it matters:** catches the single-step-turn regression where the whole rotation compresses into one oversized `dtheta` and gets clamped to ≤0.6 rad.

### 2. `go_to_random_and_back`

**Cue:** `go to random place and back to initial position`

**What it tests:** compound cue decomposition with origin bookkeeping — the agent must remember where it started before wandering and return to that pose.

**Pass criteria:**
- Plan contains a `remember` tool call OR a step text mentioning "remember" / "recall" / "origin".
- Plan contains a return step (text mentions "back" / "return" / "origin" / "start" / "initial").

**Why it matters:** compound cues are where small models fail; this one catches the "agent wanders and never returns" failure that shipped regressions are most likely to cause.

## Adding a new case

Edit `src/hack/rehearsal/regression.py`:

```python
CASES.append(CueCase(
    name="my_cue",
    cue="the literal mic transcription we expect users to say",
    expected_tools={"move", "speak"},
    min_steps=2,
    max_steps=8,
    check_plan=lambda steps: _custom_check(steps),
))
```

Then document the new case here. Keep each case atomic — one cue, one criterion.
