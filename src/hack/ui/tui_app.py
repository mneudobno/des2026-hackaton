"""Textual TUI — full-featured terminal dashboard with command input.

No browser, no port. Works over SSH, in Kitty, iTerm, VS Code terminal.
Type commands at the bottom to control the robot.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static


class StatusBar(Static):
    def update_status(
        self,
        state: str = "idle",
        llm: str = "—",
        vlm: str = "—",
        vlm_ms: float = 0,
        planner_ms: float = 0,
        pose: tuple[float, float, float] = (0, 0, 0),
        dist: float = 0,
        collisions: int = 0,
        tick: int = 0,
    ) -> None:
        icons = {"idle": "⚫", "vlm": "🔵", "planner": "🟣", "acting": "🟢", "error": "🔴", "pass": "✅", "fail": "❌"}
        icon = icons.get(state, "⚪")
        self.update(
            f"{icon} [bold]{state}[/]  t={tick}  │  "
            f"LLM [cyan]{llm}[/]  VLM [cyan]{vlm}[/]  │  "
            f"V={vlm_ms:.0f}ms P={planner_ms:.0f}ms  │  "
            f"pose=({pose[0]:+.2f},{pose[1]:+.2f},θ={math.degrees(pose[2]):+.0f}°)  "
            f"dist={dist:.2f}  col={collisions}"
        )


class PlanPanel(Static):
    def set_plan(self, cue: str, steps: list[dict], idx: int) -> None:
        lines = [f"[bold yellow]▶ {cue}[/]", ""]
        for i, s in enumerate(steps):
            txt = s.get("text", "") if isinstance(s, dict) else str(s)
            has_tool = isinstance(s, dict) and s.get("tool")
            tag = "[dim cyan]PRE[/]" if has_tool else "[dim magenta]LLM[/]"
            if i < idx:
                lines.append(f"  [dim green]✓[/] [dim]{i + 1:>2}. {tag} {txt}[/]")
            elif i == idx:
                lines.append(f"  [bold yellow]▶[/] [bold]{i + 1:>2}. {tag} {txt}[/]")
            else:
                lines.append(f"  [dim]  {i + 1:>2}. {tag} {txt}[/]")
        self.update("\n".join(lines))

    def clear_plan(self) -> None:
        self.update("[dim]— no active plan —[/]")


class HackTUI(App):
    CSS = """
    Screen {
        background: #0a140a;
        color: #4cff4c;
    }
    Header {
        background: #0c1a0c;
        color: #4cff4c;
    }
    Footer {
        background: #0c1a0c;
    }
    #status-bar {
        height: 2;
        background: #0c1a0c;
        border: solid #1f401f;
        padding: 0 1;
    }
    #main {
        height: 1fr;
    }
    #left-col {
        width: 1fr;
        border: solid #1f401f;
    }
    #right-col {
        width: 1fr;
    }
    #plan-panel {
        height: 1fr;
        border: solid #1f401f;
        padding: 0 1;
        overflow-y: auto;
    }
    #actions-log {
        height: 2fr;
        border: solid #1f401f;
    }
    #voice-log {
        height: 1fr;
        border: solid #1f401f;
    }
    #alerts-log {
        height: 1fr;
        border: solid #1f401f;
    }
    RichLog {
        background: #060c06;
        scrollbar-size: 1 1;
    }
    Input {
        background: #0c1a0c;
        border: solid #1f401f;
        color: #4cff4c;
    }
    Input:focus {
        border: solid #4cff4c;
    }
    """

    TITLE = "HACK//AGENT"
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+r", "restart", "Restart rehearsal"),
    ]

    def __init__(
        self,
        trace_path: Path | None = None,
        follow: bool = True,
        cues_path: Path = Path("runs/live_cues.ndjson"),
    ) -> None:
        super().__init__()
        self.trace_path = trace_path
        self.follow = follow
        self.cues_path = cues_path
        # State
        self._plan_cue = ""
        self._plan_steps: list[dict] = []
        self._plan_idx = 0
        self._state = "idle"
        self._llm = "—"
        self._vlm = "—"
        self._vlm_ms = 0.0
        self._planner_ms = 0.0
        self._pose = (0.0, 0.0, 0.0)
        self._dist = 0.0
        self._collisions = 0
        self._tick = 0
        self._tool_counts: dict[str, int] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusBar(id="status-bar")
        with Horizontal(id="main"):
            with Vertical(id="left-col"):
                yield PlanPanel("[dim]— no active plan —[/]", id="plan-panel")
            with Vertical(id="right-col"):
                yield RichLog(highlight=True, markup=True, id="actions-log")
                yield RichLog(highlight=True, markup=True, id="voice-log")
                yield RichLog(highlight=True, markup=True, id="alerts-log")
        yield Input(placeholder="> type a command and press Enter…", id="cmd-input")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#actions-log", RichLog).border_title = "ACTIONS"
        self.query_one("#voice-log", RichLog).border_title = "VOICE"
        self.query_one("#alerts-log", RichLog).border_title = "ALERTS"
        self.query_one("#plan-panel", PlanPanel).border_title = "PLAN"
        self._start_tail()

    @on(Input.Submitted, "#cmd-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.clear()
        self.cues_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cues_path.open("a") as f:
            f.write(json.dumps({"ts": time.time(), "text": text}) + "\n")
        voice = self.query_one("#voice-log", RichLog)
        voice.write(f"[bold yellow]YOU:[/] {text}")

    @work(thread=True)
    def _start_tail(self) -> None:
        import time as _time
        runs = Path("runs")
        trace = self.trace_path
        if trace is None:
            traces = sorted(runs.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not traces:
                self.call_from_thread(self._log_alert, "no JSONL traces found in runs/")
                return
            trace = traces[0]
        self.sub_title = str(trace.name)
        with trace.open() as fh:
            if self.follow:
                fh.seek(0, 2)
            else:
                fh.seek(0)
            while not self._is_shutting_down:
                line = fh.readline()
                if not line:
                    if not self.follow:
                        break
                    _time.sleep(0.1)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self.call_from_thread(self._handle_event, event)

    @property
    def _is_shutting_down(self) -> bool:
        return self._exit

    def _handle_event(self, e: dict[str, Any]) -> None:
        kind = e.get("kind", "")
        tick = e.get("tick")
        if tick is not None:
            self._tick = tick

        actions = self.query_one("#actions-log", RichLog)
        voice = self.query_one("#voice-log", RichLog)
        alerts = self.query_one("#alerts-log", RichLog)
        plan = self.query_one("#plan-panel", PlanPanel)
        status = self.query_one("#status-bar", StatusBar)

        if kind == "start":
            self.sub_title = f"{e.get('scenario', '')} — running"
            self._tool_counts = {}
        elif kind == "model_info":
            self._llm = e.get("llm_model", "—")
            self._vlm = e.get("vlm_model", "—")
        elif kind == "status":
            s = e.get("state", "")
            if s == "vlm_thinking":
                self._state = "vlm"
            elif s == "vlm_done":
                self._vlm_ms = e.get("ms", 0)
                self._state = "idle"
            elif s == "planner_thinking":
                self._state = "planner"
            elif s == "planner_done":
                self._planner_ms = e.get("ms", 0)
                self._state = "acting"
            elif "error" in s:
                self._state = "error"
        elif kind == "idle":
            self._state = "idle"
        elif kind == "live_cue":
            voice.write(f"[bold cyan]MIC t{tick}:[/] {e.get('text', '')}")
        elif kind == "scripted_cue":
            voice.write(f"[dim]CUE t{tick}:[/] {e.get('text', '')}")
        elif kind == "plan_installed":
            self._plan_cue = e.get("cue", "")
            self._plan_steps = e.get("steps", [])
            self._plan_idx = 0
            plan.set_plan(self._plan_cue, self._plan_steps, 0)
        elif kind == "plan_progress":
            self._plan_idx = e.get("step_index", 0)
            plan.set_plan(self._plan_cue, self._plan_steps, self._plan_idx)
        elif kind == "plan_complete":
            self._plan_idx = len(self._plan_steps)
            plan.set_plan(self._plan_cue, self._plan_steps, self._plan_idx)
        elif kind == "action":
            call = e.get("call", {})
            name = call.get("name", "?")
            args = call.get("args", {})
            src = e.get("source", "llm")
            self._tool_counts[name] = self._tool_counts.get(name, 0) + 1
            tag = "[cyan]PRE[/]" if src == "pre-baked" else "[magenta]LLM[/]"
            actions.write(f"t{tick} {tag} {name} {_fmt(name, args)}")
        elif kind == "alert":
            code = e.get("code", "")
            if code in ("deterministic-plan",):
                return  # info, not error
            msg = e.get("message", "")
            alerts.write(f"[bold red]t{tick}[/] {code}: {msg[:80]}")
        elif kind == "observation":
            state_data = e.get("state", {}) if "state" in e else {}
            pose = state_data.get("pose")
            if pose:
                self._pose = tuple(pose)
            extra = state_data.get("extra", {})
            self._dist = extra.get("dist_from_origin", 0)
            self._collisions = extra.get("collision_count", self._collisions)
        elif kind == "stop":
            ok = e.get("success", False)
            reason = e.get("reason", "")
            self._state = "pass" if ok else "fail"
            style = "bold green" if ok else "bold red"
            alerts.write(f"[{style}]{'PASS' if ok else 'FAIL'}: {reason}[/]")
            self.sub_title = f"{'PASS' if ok else 'FAIL'} — {reason[:40]}"

        status.update_status(
            state=self._state, llm=self._llm, vlm=self._vlm,
            vlm_ms=self._vlm_ms, planner_ms=self._planner_ms,
            pose=self._pose, dist=self._dist, collisions=self._collisions,
            tick=self._tick,
        )

    def _log_alert(self, msg: str) -> None:
        self.query_one("#alerts-log", RichLog).write(f"[red]{msg}[/]")


def _fmt(name: str, args: dict) -> str:
    if name == "move":
        parts = []
        dx, dy, dt = args.get("dx", 0), args.get("dy", 0), args.get("dtheta", 0)
        if dx:
            parts.append(f"{'fwd' if dx > 0 else 'back'} {abs(dx):.2f}m")
        if dy:
            parts.append(f"{'left' if dy > 0 else 'right'} {abs(dy):.2f}m")
        if dt:
            parts.append(f"{'left' if dt > 0 else 'right'} {abs(math.degrees(dt)):.0f}°")
        return " ".join(parts) or "no-op"
    if name == "speak":
        return f'"{args.get("text", "")}"'
    if name == "emote":
        return args.get("label", "")
    return str(args) if args else ""


def run_textual_tui(
    trace_path: Path | None = None,
    follow: bool = True,
    cues_path: Path = Path("runs/live_cues.ndjson"),
) -> None:
    app = HackTUI(trace_path=trace_path, follow=follow, cues_path=cues_path)
    app.run()
