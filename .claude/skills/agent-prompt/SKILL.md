---
name: agent-prompt
description: Iterate on planner or observation prompts by replaying prior JSONL traces. Use when tuning prompts, when the agent feels unresponsive, incoherent, or is picking wrong tools.
---

# Prompt iteration via replay

Never iterate prompts against a live robot. Replay past observations against the new prompt and diff the chosen actions.

## Steps

1. **Find the trace** in `runs/<timestamp>.jsonl` from a representative run.
2. **Edit** `configs/agent.yaml` — usually the `system_prompt`, `observation_prompt`, or tool descriptions. Keep the old one in a git-tracked diff, not in a code comment.
3. **Replay:** `hack agent replay runs/<ts>.jsonl --config configs/agent.yaml`. This feeds each observation to the new planner and writes `runs/<ts>.replay.jsonl`.
4. **Diff actions:** `hack agent diff runs/<ts>.jsonl runs/<ts>.replay.jsonl`. Look for: fewer `think` loops, fewer wasted `look_at`, faster commitment to `move`/`grasp`.
5. If better, commit the config with a one-line message naming the behavior change.

## Tuning heuristics

- **Agent is slow/thinky:** shorten system prompt, remove philosophical framing, give 2–3 concrete examples of good traces.
- **Agent ignores audio:** raise audio events' salience in the observation prompt, or move them into the user-turn slot instead of as context.
- **Agent tool-thrashes:** require a one-sentence justification in each tool call and penalize re-planning in the prompt.
- **Agent hallucinates objects:** tighten VLM prompt to "list only what is clearly visible; if uncertain, say so."

## Do not

- Do not change `runtime.py` to fix a prompt problem.
- Do not add new tools mid-hackathon; tune the existing set.
