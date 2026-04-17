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


class WorldMap(Static):
    """ASCII top-down view of the virtual world — fills available space."""

    DEFAULT_CSS = """
    WorldMap {
        height: 1fr;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pose = (0.0, 0.0, 0.0)
        self._objects: list[dict] = []
        self._collisions = 0
        self._trail: list[tuple[float, float]] = []

    def render_world(
        self,
        pose: tuple[float, float, float],
        objects: list[dict],
        collisions: int = 0,
    ) -> None:
        self._pose = pose
        self._objects = objects
        self._collisions = collisions
        # Track robot trail (last 30 positions).
        self._trail.append((pose[0], pose[1]))
        if len(self._trail) > 30:
            self._trail = self._trail[-30:]
        self._refresh_map()

    def _refresh_map(self) -> None:
        # Use the widget's actual size to fill the panel.
        size = self.size
        w = max(size.width - 4, 30)  # leave room for borders
        h = max(size.height - 4, 10)
        pose = self._pose
        objects = self._objects

        # Viewport: fit all points with margin.
        xs = [pose[0]] + [o["x"] for o in objects]
        ys = [pose[1]] + [o["y"] for o in objects]
        for tx, ty in self._trail:
            xs.append(tx)
            ys.append(ty)
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0) * 1.3
        half = span / 2

        def to_cell(x: float, y: float) -> tuple[int, int]:
            col = int((x - (cx - half)) / span * (w - 1))
            row = int((1.0 - (y - (cy - half)) / span) * (h - 1))
            return max(0, min(w - 1, col)), max(0, min(h - 1, row))

        # Build grid with background dots for spatial reference.
        grid: list[list[str]] = [["·" if (r + c) % 6 == 0 else " " for c in range(w)] for r in range(h)]
        # Color layer (markup per cell: None = default dim, or a style string).
        colors: list[list[str | None]] = [[None for _ in range(w)] for _ in range(h)]

        # Draw origin crosshair.
        ox, oy = to_cell(0, 0)
        if 0 <= oy < h:
            for c in range(w):
                if grid[oy][c] == " ":
                    grid[oy][c] = "─"
                    colors[oy][c] = "dim green"
        if 0 <= ox < w:
            for r in range(h):
                if grid[r][ox] in (" ", "─"):
                    grid[r][ox] = "│" if grid[r][ox] == " " else "┼"
                    colors[r][ox] = "dim green"

        # Draw obstacle exclusion zones (dashed circles approximated as ring of dots).
        for obj in objects:
            if not obj.get("is_obstacle"):
                continue
            radius = obj.get("radius", 0.1) + 0.08  # + robot radius
            for angle_step in range(16):
                a = angle_step * 2 * math.pi / 16
                ex = obj["x"] + radius * math.cos(a)
                ey = obj["y"] + radius * math.sin(a)
                ec, er = to_cell(ex, ey)
                if 0 <= er < h and 0 <= ec < w and grid[er][ec] in (" ", "·"):
                    grid[er][ec] = "·"
                    colors[er][ec] = "red"

        # Draw robot trail.
        for i, (tx, ty) in enumerate(self._trail[:-1]):
            tc, tr = to_cell(tx, ty)
            if 0 <= tr < h and 0 <= tc < w and grid[tr][tc] in (" ", "·", "─", "│"):
                grid[tr][tc] = "·"
                fade = "dim" if i < len(self._trail) // 2 else ""
                colors[tr][tc] = f"{fade} cyan".strip()

        # Draw objects.
        for obj in objects:
            col, row = to_cell(obj["x"], obj["y"])
            if obj.get("is_obstacle"):
                ch, color = "⬤", "bold red"
            elif obj.get("is_container"):
                ch, color = "◆", "bold green"
            elif obj.get("is_target"):
                ch, color = "■", "bold yellow"
            else:
                ch, color = "□", "bold blue"
            if 0 <= row < h and 0 <= col < w:
                grid[row][col] = ch
                colors[row][col] = color
                # Label above the object.
                label = obj.get("name", "")[:6]
                label_row = row - 1
                if label_row >= 0:
                    for i, c in enumerate(label):
                        lc = col - len(label) // 2 + i
                        if 0 <= lc < w and grid[label_row][lc] in (" ", "·", "─"):
                            grid[label_row][lc] = c
                            colors[label_row][lc] = f"dim {color.replace('bold ', '')}"

        # Draw robot direction beam (3 cells ahead showing facing direction).
        rx, ry = to_cell(pose[0], pose[1])
        theta = pose[2]
        beam_chars = "·•·"
        for bi in range(1, 4):
            bx = pose[0] + bi * 0.06 * span * math.cos(theta)
            by = pose[1] + bi * 0.06 * span * math.sin(theta)
            bc, br = to_cell(bx, by)
            if 0 <= br < h and 0 <= bc < w and grid[br][bc] in (" ", "·", "─", "│"):
                grid[br][bc] = beam_chars[min(bi - 1, 2)]
                colors[br][bc] = "bold green"

        # Draw robot (always on top). 16 directions for ~22.5° resolution.
        # Index 0 = 0 rad (east/right), counter-clockwise.
        _ARROWS = "→⬈↗⬈↑⬉↖⬉←⬋↙⬋↓⬊↘⬊"
        # theta=0 → east (index 0), theta=π/2 → north (index 4), etc.
        idx = int((theta / (2 * math.pi) * 16 + 0.5) % 16)
        robot_ch = _ARROWS[idx]
        if 0 <= ry < h and 0 <= rx < w:
            grid[ry][rx] = robot_ch
            colors[ry][rx] = "bold white on dark_green"
            # Robot label below.
            label_row = ry + 1
            if label_row < h:
                for i, c in enumerate("▲BOT"):
                    lc = rx - 1 + i
                    if 0 <= lc < w and grid[label_row][lc] in (" ", "·", "─"):
                        grid[label_row][lc] = c
                        colors[label_row][lc] = "bold white"

        # Render with Rich markup.
        lines: list[str] = []
        for r in range(h):
            row_str = ""
            for c in range(w):
                ch = grid[r][c]
                clr = colors[r][c]
                if clr:
                    row_str += f"[{clr}]{ch}[/]"
                else:
                    row_str += f"[dim]{ch}[/]"
            lines.append(row_str)

        # Info bar.
        info = (
            f"[bold]pose[/]=({pose[0]:+.2f},{pose[1]:+.2f}) "
            f"[bold]θ[/]={math.degrees(pose[2]):+.0f}° "
            f"[bold]col[/]={self._collisions}"
        )
        lines.append(info)
        self.update("\n".join(lines))


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
    #world-map {
        height: 1fr;
        border: solid #1f401f;
        padding: 0;
        overflow: hidden;
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
        Binding("ctrl+r", "restart", "Restart"),
        Binding("ctrl+o", "cycle_scenario", "Scenario"),
        Binding("ctrl+k", "kill", "Kill"),
    ]

    SCENARIOS = ["dance", "obstacle-course", "obstacle-hard", "obstacle-wall",
                 "pick-and-place", "follow", "chit-chat"]

    def __init__(
        self,
        trace_path: Path | None = None,
        follow: bool = True,
        cues_path: Path = Path("runs/live_cues.ndjson"),
        scenario: str = "dance",
        config: str = "configs/agent.yaml",
    ) -> None:
        super().__init__()
        self.trace_path = trace_path
        self.follow = follow
        self.cues_path = cues_path
        self.scenario = scenario
        self.config = config
        self._rehearsal_proc: Any = None
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
                yield WorldMap("[dim]— awaiting world data —[/]", id="world-map")
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
        self.query_one("#world-map", WorldMap).border_title = "WORLD"
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
        elif kind == "world_state":
            world_map = self.query_one("#world-map", WorldMap)
            pose = tuple(e.get("pose", [0, 0, 0]))
            objects = e.get("objects", [])
            cols = e.get("collisions", 0)
            world_map.render_world(pose, objects, cols)
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

    def _kill_rehearsal(self) -> None:
        if self._rehearsal_proc and self._rehearsal_proc.poll() is None:
            self._rehearsal_proc.terminate()
            self._rehearsal_proc = None

    def _start_rehearsal(self) -> None:
        import subprocess
        self._kill_rehearsal()
        # Clear cues + issues.
        cues = Path("runs/live_cues.ndjson")
        cues.parent.mkdir(parents=True, exist_ok=True)
        cues.write_text("")
        Path("runs/issues.ndjson").write_text("")
        # Determine config: obstacle scenarios use obstacle config, others use default.
        cfg = self.config
        if "obstacle" in self.scenario and Path("configs/agent.obstacle.yaml").exists():
            cfg = "configs/agent.obstacle.yaml"
        cmd = [
            "uv", "run", "hack", "rehearse",
            "--scenario", self.scenario,
            "--config", cfg,
            "--delay", "0.5",
            "--ticks", "200",
            "--no-display",
        ]
        self._rehearsal_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        alerts = self.query_one("#alerts-log", RichLog)
        alerts.write(f"[bold green]▶ started[/] {self.scenario} (pid {self._rehearsal_proc.pid})")
        self.sub_title = f"{self.scenario} — starting…"
        # Give it a moment then re-tail the new trace.
        import time as _t
        _t.sleep(1)
        self._start_tail()

    def action_restart(self) -> None:
        """Ctrl+R: restart rehearsal with current scenario."""
        self._start_rehearsal()

    def action_cycle_scenario(self) -> None:
        """Ctrl+O: cycle through scenarios (shown in alerts)."""
        try:
            idx = self.SCENARIOS.index(self.scenario)
        except ValueError:
            idx = -1
        self.scenario = self.SCENARIOS[(idx + 1) % len(self.SCENARIOS)]
        alerts = self.query_one("#alerts-log", RichLog)
        alerts.write(f"[yellow]scenario → {self.scenario}[/] (Ctrl+R to start)")

    def action_kill(self) -> None:
        """Ctrl+K: kill the running rehearsal."""
        self._kill_rehearsal()
        alerts = self.query_one("#alerts-log", RichLog)
        alerts.write("[red]rehearsal killed[/]")


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
    scenario: str = "dance",
    config: str = "configs/agent.yaml",
) -> None:
    app = HackTUI(
        trace_path=trace_path, follow=follow, cues_path=cues_path,
        scenario=scenario, config=config,
    )
    app.run()
