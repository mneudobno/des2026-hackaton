"""Terminal UI — Rich Live dashboard for rehearsal and day-of agent runs.

No browser, no port, no Chrome MCP. Works over SSH. Shows everything in one
terminal panel using Rich's Live display.

Usage:
    # Standalone tail of an active trace:
    hack tui

    # Or integrated into rehearse/agent-run (future):
    hack rehearse --scenario dance --tui
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class TerminalUI:
    """Stateful terminal dashboard driven by JSONL events."""

    def __init__(self, max_log: int = 30) -> None:
        self.scenario: str = ""
        self.llm_model: str = "—"
        self.llm_host: str = "—"
        self.vlm_model: str = "—"
        self.vlm_host: str = "—"
        self.state: str = "idle"
        self.state_detail: str = "awaiting cue"
        self.vlm_ms: float = 0
        self.planner_ms: float = 0
        self.vlm_history: deque[float] = deque(maxlen=10)
        self.planner_history: deque[float] = deque(maxlen=10)
        self.tick: int = 0
        # Plan
        self.plan_cue: str = ""
        self.plan_steps: list[dict] = []
        self.plan_idx: int = 0
        # Logs
        self.voice: deque[str] = deque(maxlen=max_log)
        self.actions: deque[str] = deque(maxlen=max_log)
        self.alerts: deque[str] = deque(maxlen=max_log)
        # Pose
        self.pose: tuple[float, float, float] = (0, 0, 0)
        self.dist_origin: float = 0
        self.collisions: int = 0
        # Counters
        self.tool_counts: dict[str, int] = {}
        self.total_ticks: int = 0
        self.success: str | None = None

    def feed(self, event: dict[str, Any]) -> None:
        kind = event.get("kind", "")
        tick = event.get("tick")
        if tick is not None:
            self.tick = tick

        if kind == "start":
            self.scenario = event.get("scenario", "")
            self.success = None
            self.tool_counts = {}
            self.collisions = 0
        elif kind == "model_info":
            self.llm_model = event.get("llm_model", "—")
            self.llm_host = event.get("llm_host", "—")
            self.vlm_model = event.get("vlm_model", "—")
            self.vlm_host = event.get("vlm_host", "—")
        elif kind == "status":
            s = event.get("state", "")
            if s == "vlm_thinking":
                self.state, self.state_detail = "vlm", f"VLM thinking (t{tick})"
            elif s == "vlm_done":
                self.vlm_ms = event.get("ms", 0)
                self.vlm_history.append(self.vlm_ms)
                self.state, self.state_detail = "idle", "VLM done"
            elif s == "planner_thinking":
                self.state, self.state_detail = "planner", f"Planner thinking (t{tick})"
            elif s == "planner_done":
                self.planner_ms = event.get("ms", 0)
                self.planner_history.append(self.planner_ms)
                self.state, self.state_detail = "acting", "acting"
            elif "error" in s:
                self.state, self.state_detail = "error", s
        elif kind == "idle":
            self.state, self.state_detail = "idle", "awaiting voice cue"
        elif kind == "live_cue":
            self.voice.appendleft(f"[t{tick}] YOU: {event.get('text', '')}")
        elif kind == "scripted_cue":
            self.voice.appendleft(f"[t{tick}] CUE: {event.get('text', '')}")
        elif kind == "plan_installed":
            self.plan_cue = event.get("cue", "")
            self.plan_steps = event.get("steps", [])
            self.plan_idx = 0
        elif kind == "plan_progress":
            self.plan_idx = event.get("step_index", 0)
        elif kind == "plan_complete":
            self.plan_idx = len(self.plan_steps)
        elif kind == "action":
            call = event.get("call", {})
            name = call.get("name", "?")
            args = call.get("args", {})
            src = event.get("source", "llm")
            self.tool_counts[name] = self.tool_counts.get(name, 0) + 1
            tag = "[PRE]" if src == "pre-baked" else "[LLM]"
            self.actions.appendleft(f"[t{tick}] {tag} {name} {_fmt_args(name, args)}")
        elif kind == "alert":
            code = event.get("code", "")
            msg = event.get("message", "")
            # Only show real errors in the alerts panel.
            if code in ("deterministic-plan", "plan-corrected"):
                return  # info, not error
            self.alerts.appendleft(f"[t{tick}] {code}: {msg[:80]}")
        elif kind == "observation":
            obs = event.get("observation", {})
            extra = event.get("state", {}).get("extra", {}) if "state" in event else {}
            pose = event.get("state", {}).get("pose") if "state" in event else None
            if pose:
                self.pose = tuple(pose)
            self.dist_origin = extra.get("dist_from_origin", 0)
            self.collisions = extra.get("collision_count", self.collisions)
        elif kind == "clamp_summary":
            self.collisions = event.get("count", 0)
        elif kind == "stop":
            ok = event.get("success", False)
            reason = event.get("reason", "")
            self.success = f"{'PASS' if ok else 'FAIL'}: {reason}"
            self.state, self.state_detail = ("pass" if ok else "fail"), reason

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )
        layout["left"].split_column(
            Layout(name="status", size=8),
            Layout(name="plan"),
        )
        layout["right"].split_column(
            Layout(name="actions"),
            Layout(name="voice", size=8),
            Layout(name="alerts", size=8),
        )

        # Header
        state_icon = {"idle": "⚫", "vlm": "🔵", "planner": "🟣", "acting": "🟢", "error": "🔴", "pass": "✅", "fail": "❌"}.get(self.state, "⚪")
        header_text = Text()
        header_text.append("▓ HACK//AGENT ", style="bold green")
        header_text.append(f"scenario={self.scenario}  ", style="dim")
        header_text.append(f"tick={self.tick}  ", style="cyan")
        header_text.append(f"{state_icon} {self.state_detail}", style="bold")
        layout["header"].update(Panel(header_text, style="green"))

        # Status panel
        st = Table(show_header=False, box=None, padding=(0, 1))
        st.add_column("k", style="dim", width=12)
        st.add_column("v")
        st.add_row("LLM", f"{self.llm_model} @ {self.llm_host}")
        st.add_row("VLM", f"{self.vlm_model} @ {self.vlm_host}")
        vmean = int(sum(self.vlm_history) / max(len(self.vlm_history), 1)) if self.vlm_history else 0
        pmean = int(sum(self.planner_history) / max(len(self.planner_history), 1)) if self.planner_history else 0
        st.add_row("VLM ms", f"{self.vlm_ms:.0f}  (mean {vmean})")
        st.add_row("Planner ms", f"{self.planner_ms:.0f}  (mean {pmean})")
        st.add_row("Pose", f"({self.pose[0]:+.2f}, {self.pose[1]:+.2f}, θ={self.pose[2]:+.2f})")
        st.add_row("Dist origin", f"{self.dist_origin:.3f}m  collisions={self.collisions}")
        layout["status"].update(Panel(st, title="[bold cyan]STATUS[/]", border_style="cyan"))

        # Plan panel
        plan_lines: list[str] = []
        if self.plan_cue:
            plan_lines.append(f"[bold yellow]> {self.plan_cue}[/]")
            for i, s in enumerate(self.plan_steps):
                txt = s.get("text", "") if isinstance(s, dict) else str(s)
                has_tool = isinstance(s, dict) and s.get("tool")
                tag = "[PRE]" if has_tool else "[LLM]"
                if i < self.plan_idx:
                    plan_lines.append(f"  [dim]✓ {i+1:>2}. {tag} {txt}[/]")
                elif i == self.plan_idx:
                    plan_lines.append(f"  [bold yellow]▶ {i+1:>2}. {tag} {txt}[/]")
                else:
                    plan_lines.append(f"  [dim]  {i+1:>2}. {tag} {txt}[/]")
        else:
            plan_lines.append("[dim]— no active plan —[/]")
        layout["plan"].update(Panel(
            Text.from_markup("\n".join(plan_lines)),
            title="[bold yellow]PLAN[/]",
            border_style="yellow",
        ))

        # Actions
        tool_summary = "  ".join(f"{k}={v}" for k, v in sorted(self.tool_counts.items()))
        act_text = "\n".join(list(self.actions)[:15]) or "[dim]—[/]"
        layout["actions"].update(Panel(
            Text.from_markup(f"[dim]{tool_summary}[/]\n{act_text}"),
            title="[bold green]ACTIONS[/]",
            border_style="green",
        ))

        # Voice
        voice_text = "\n".join(list(self.voice)[:6]) or "[dim]—[/]"
        layout["voice"].update(Panel(
            Text.from_markup(voice_text),
            title="[bold blue]VOICE[/]",
            border_style="blue",
        ))

        # Alerts
        alerts_text = "\n".join(list(self.alerts)[:6]) or "[dim]—[/]"
        layout["alerts"].update(Panel(
            Text.from_markup(alerts_text),
            title=f"[bold red]ALERTS ({len(self.alerts)})[/]",
            border_style="red",
        ))

        # Footer
        if self.success:
            style = "bold green" if self.success.startswith("PASS") else "bold red"
            layout["footer"].update(Panel(Text(self.success, style=style)))
        else:
            layout["footer"].update(Panel(Text("running…", style="dim")))

        return layout


def _fmt_args(name: str, args: dict) -> str:
    if name == "move":
        parts = []
        dx = args.get("dx", 0)
        dy = args.get("dy", 0)
        dt = args.get("dtheta", 0)
        if dx:
            parts.append(f"{'fwd' if dx > 0 else 'back'} {abs(dx):.2f}m")
        if dy:
            parts.append(f"{'left' if dy > 0 else 'right'} {abs(dy):.2f}m")
        if dt:
            import math
            parts.append(f"{'left' if dt > 0 else 'right'} {abs(math.degrees(dt)):.0f}°")
        return " ".join(parts) or "no-op"
    if name == "speak":
        return f'"{args.get("text", "")}"'
    if name == "emote":
        return args.get("label", "")
    return str(args) if args else ""


async def run_tui(trace_path: Path | None = None, follow: bool = True) -> None:
    """Main entry: tail a JSONL trace with Rich Live."""
    runs = Path("runs")
    if trace_path is None:
        traces = sorted(runs.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not traces:
            Console().print("[red]no JSONL traces found in runs/[/]")
            return
        trace_path = traces[0]

    ui = TerminalUI()
    console = Console()
    console.print(f"[dim]tailing {trace_path}[/]")

    with Live(ui.render(), console=console, refresh_per_second=4, screen=True) as live:
        with trace_path.open() as fh:
            if follow:
                fh.seek(0, 2)
            else:
                fh.seek(0)
            while True:
                line = fh.readline()
                if not line:
                    if not follow:
                        break
                    await asyncio.sleep(0.15)
                    live.update(ui.render())
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ui.feed(event)
                live.update(ui.render())
                if event.get("kind") == "stop" and follow:
                    await asyncio.sleep(2)  # show final state briefly
                    break
