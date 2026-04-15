"""Post-rehearsal behaviour analyzer.

Reads a rehearsal JSONL trace and emits actionable flags. Each flag names the
ticks involved so an operator can jump straight to the offending events.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Flag:
    severity: str  # "red" | "yellow" | "green"
    code: str
    message: str
    ticks: list[int] = field(default_factory=list)


@dataclass
class AnalyzerResult:
    trace_path: Path
    flags: list[Flag]
    tool_calls: Counter
    ticks: int
    live_cues: list[tuple[int, str]]
    summary_line: str


def analyze(trace_path: Path) -> AnalyzerResult:
    events: list[dict[str, Any]] = []
    for raw in trace_path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    flags: list[Flag] = []
    tool_calls: Counter = Counter()
    live_cues: list[tuple[int, str]] = []
    ticks_total = 0
    scenario = ""
    router_called = False
    plan_events: list[dict[str, Any]] = []
    action_events: list[dict[str, Any]] = []
    obs_events: list[dict[str, Any]] = []
    clamp_summary: dict | None = None

    for ev in events:
        kind = ev.get("kind")
        if kind == "start":
            scenario = ev.get("scenario", "")
        elif kind == "observation":
            ticks_total = max(ticks_total, ev.get("tick", 0))
            obs_events.append(ev)
        elif kind == "plan":
            plan_events.append(ev)
        elif kind == "action":
            action_events.append(ev)
            name = (ev.get("call") or {}).get("name")
            if name:
                tool_calls[name] += 1
            if name == "route":
                router_called = True
        elif kind == "live_cue":
            live_cues.append((ev.get("tick", 0), ev.get("text", "")))
        elif kind == "clamp_summary":
            clamp_summary = ev

    # --- flags -----------------------------------------------------------
    # 1. parse failures
    parse_fail_ticks = [
        p["tick"] for p in plan_events if "parse_failed" in (p.get("note") or "")
    ]
    if parse_fail_ticks:
        flags.append(Flag("red", "parse-failed",
                          f"planner returned un-parseable JSON on {len(parse_fail_ticks)} tick(s)",
                          parse_fail_ticks))

    # 2. plans with zero calls
    empty_ticks = [p["tick"] for p in plan_events if not p.get("calls")]
    if empty_ticks:
        flags.append(Flag("yellow", "empty-plan",
                          f"planner returned no tool calls on {len(empty_ticks)} tick(s)",
                          empty_ticks))

    # 3. clamp events
    if clamp_summary:
        evs = clamp_summary.get("events", [])
        if len(evs) >= 3:
            sev = "red" if len(evs) >= 5 else "yellow"
            flags.append(Flag(sev, "move-clamped",
                              f"{len(evs)} move() calls clamped by world bounds — planner is asking "
                              f"for motion the world can't deliver",
                              [e["tick"] for e in evs]))

    # 4. tool+args stuck (same exact call ≥3 consecutive ticks)
    repeats: list[int] = []
    for i in range(2, len(action_events)):
        a, b, c = action_events[i - 2:i + 1]
        if a.get("call") == b.get("call") == c.get("call"):
            repeats.append(c.get("tick", 0))
    if repeats:
        flags.append(Flag("yellow", "stuck-tool",
                          "same tool+args issued 3+ ticks in a row — planner may be looping",
                          sorted(set(repeats))))

    # 5. cue ignored — a live_cue arrived but the next plan's calls don't mention any cue keyword
    cue_ignored: list[int] = []
    for t, text in live_cues:
        next_plans = [p for p in plan_events if p.get("tick") == t or p.get("tick") == t + 1]
        keywords = [w.lower() for w in text.split() if len(w) > 3]
        if next_plans and keywords and not any(
            any(k in json.dumps(p).lower() for k in keywords) for p in next_plans
        ):
            cue_ignored.append(t)
    if cue_ignored:
        flags.append(Flag("yellow", "cue-ignored",
                          "live voice cue did not visibly influence the next plan",
                          cue_ignored))

    # 6. VLM scene empty for entire run
    empty_scene = all(not (o.get("observation") or {}).get("scene") for o in obs_events)
    if obs_events and empty_scene:
        flags.append(Flag("yellow", "vlm-blank",
                          "VLM never produced a non-empty scene — VLM not wired or prompt mismatched",
                          []))

    # 7. router never triggered in chit-chat
    if scenario == "chit-chat" and not router_called:
        flags.append(Flag("yellow", "router-off",
                          "chit-chat scenario but router never triggered — check cfg['router']['enabled']",
                          []))

    # 8. no `speak` in chit-chat or dance
    if scenario in ("chit-chat", "dance") and tool_calls.get("speak", 0) == 0:
        flags.append(Flag("yellow", "no-speak",
                          f"{scenario!r} scenario with 0 `speak` calls — planner prompt not encouraging speech",
                          []))

    # 9. high planner latency (if any plan took > 10s)
    # NOTE: timings live in the JSON summary, not the JSONL trace, so this is a softer signal.

    if not flags:
        flags.append(Flag("green", "all-clear", "no behaviour flags raised", []))

    summary_line = (
        f"{scenario or 'unknown'}  ticks={ticks_total}  "
        f"tools={dict(tool_calls)}  flags={len([f for f in flags if f.severity != 'green'])}"
    )
    return AnalyzerResult(
        trace_path=trace_path,
        flags=flags,
        tool_calls=tool_calls,
        ticks=ticks_total,
        live_cues=live_cues,
        summary_line=summary_line,
    )
