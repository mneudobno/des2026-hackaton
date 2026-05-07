"""Live commentary — JSONL agent events → plain-English narration via the local LLM.

Designed to run as a third pane alongside `hack tui` and `hack agent run`.
Tails the latest JSONL trace, filters to interesting events (plan_installed,
action, alert, live_cue, stop), and prints one short sentence per event via the
same LLMAdapter the agent uses.

Cut-list-friendly: this is **demo-additive, not demo-critical**. If commentary
is slow or wrong on the day, just kill the pane — the agent and dashboard run
fine without it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

from hack.models.base import LLMAdapter

# Events worth narrating. Skip raw observations + world_state (too noisy).
INTERESTING_KINDS = frozenset(
    {"plan_installed", "action", "alert", "live_cue", "stop"}
)

_NARRATE_PROMPT = (
    "You narrate an AI robot agent's decisions for a live, non-technical "
    "audience watching a hackathon demo. The agent just emitted this event:\n"
    "\n"
    "EVENT: {event}\n"
    "\n"
    "Produce ONE short plain-English sentence (≤14 words) describing what the "
    "agent just did and (briefly) why. No technical jargon. No quotation marks. "
    "No JSON. Output the sentence and nothing else."
)


def _parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


async def _narrate(event: dict, llm: LLMAdapter) -> str:
    """One LLM call → one sentence. Free-form text (no JSON mode)."""
    # Truncate the event to keep the prompt cheap; the LLM only needs the gist.
    payload = json.dumps(event, default=str)[:600]
    prompt = _NARRATE_PROMPT.format(event=payload)
    try:
        text = await llm.complete(prompt, json_mode=False)
    except Exception as exc:  # network blip, parse error, etc.
        return f"[narration unavailable: {type(exc).__name__}]"
    # Take the first non-empty line, cap length.
    for line in (text or "").splitlines():
        line = line.strip().strip('"').strip("'")
        if line:
            return line[:140]
    return "[empty narration]"


async def commentate(
    trace_path: Path,
    llm: LLMAdapter,
    sink: Callable[[str], None] = print,
    *,
    follow: bool = True,
    poll_seconds: float = 0.25,
) -> None:
    """Tail `trace_path` and emit one-line narration per interesting event.

    `sink` defaults to `print`; CLI passes `console.print` for Rich formatting.
    Returns when the trace logs a `stop` event (or, with `follow=False`, when
    EOF is reached).
    """
    with trace_path.open() as fh:
        # Start at end when following live (skip historical events the audience
        # won't care about); replay from start when --no-follow.
        fh.seek(0, 2 if follow else 0)
        while True:
            line = fh.readline()
            if not line:
                if not follow:
                    return
                await asyncio.sleep(poll_seconds)
                continue
            event = _parse_line(line)
            if event is None:
                continue
            kind = event.get("kind")
            if kind not in INTERESTING_KINDS:
                continue
            sentence = await _narrate(event, llm)
            tick = event.get("tick", "?")
            sink(f"  t{tick} · {sentence}")
            if kind == "stop":
                return
