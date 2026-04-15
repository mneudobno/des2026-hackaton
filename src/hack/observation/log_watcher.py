"""Coloured live tail of a rehearsal JSONL trace.

Designed to run in a terminal next to `hack rehearse` (or started by `hack observe`).
Prints one short line per event, colour-coded by severity:
  green  — plan with calls, action success
  yellow — parse failures, empty plans, live cues
  red    — clamp events, errors
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from rich.console import Console


async def watch(trace_path: Path, console: Console | None = None, stop_at_stop: bool = True) -> None:
    console = console or Console()
    console.print(f"[dim]tailing[/] {trace_path}")
    # Wait for file to exist (rehearsal may not have started yet)
    for _ in range(20):
        if trace_path.exists():
            break
        await asyncio.sleep(0.5)
    if not trace_path.exists():
        console.print(f"[red]trace not found: {trace_path}[/]")
        return

    with trace_path.open() as fh:
        fh.seek(0, 2)  # tail
        while True:
            line = fh.readline()
            if not line:
                await asyncio.sleep(0.2)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                console.print(f"[red]bad-line[/] {line[:80]}")
                continue
            _render(ev, console)
            if stop_at_stop and ev.get("kind") == "stop":
                return


def _render(ev: dict, console: Console) -> None:
    kind = ev.get("kind", "?")
    tick = ev.get("tick", "")
    tag = f"t{tick:>2}" if tick != "" else "   "
    if kind == "start":
        console.print(f"[bold]start[/] scenario={ev.get('scenario')}")
    elif kind == "observation":
        cue = ev.get("cue")
        scene = ((ev.get("observation") or {}).get("scene") or "")[:60]
        tail = f"  [blue]cue={cue!r}[/]" if cue else ""
        console.print(f"{tag}  [cyan]obs[/]   scene={scene!r}{tail}")
    elif kind == "plan":
        calls = ev.get("calls") or []
        note = ev.get("note", "")
        colour = "green" if calls else "yellow"
        brief = ", ".join(f"{c['name']}{c.get('args', '')}" for c in calls) or "(no calls)"
        console.print(f"{tag}  [{colour}]plan[/]  {brief}  — {note[:40]}")
    elif kind == "action":
        call = ev.get("call") or {}
        result = ev.get("result") or {}
        ok = result.get("ok")
        colour = "green" if ok else "red"
        console.print(f"{tag}  [{colour}]act[/]   {call.get('name')}{call.get('args')}")
    elif kind == "live_cue":
        console.print(f"{tag}  [yellow]cue[/]   {ev.get('text')!r}")
    elif kind == "clamp_summary":
        console.print(f"[red]clamp[/] {ev.get('count')} move() call(s) hit world bounds")
    elif kind == "stop":
        colour = "green" if ev.get("success") else "red"
        console.print(f"[bold {colour}]stop[/] success={ev.get('success')}  reason={ev.get('reason')}")
    else:
        console.print(f"{tag}  {kind}")
