from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="hack — DIS2026X1 robot-agent CLI", no_args_is_help=True)
serve = typer.Typer(help="Local model serving (Ollama / NIM).")
robot = typer.Typer(help="Robot adapter probes and teleop.")
agent = typer.Typer(help="Agent runtime: run and replay.")
sensors = typer.Typer(help="Sensor pipelines: camera and mic.")
demo = typer.Typer(help="Demo capture and playback.")
app.add_typer(serve, name="serve")
app.add_typer(robot, name="robot")
app.add_typer(agent, name="agent")
app.add_typer(sensors, name="sensors")
app.add_typer(demo, name="demo")

console = Console()


# ---------- rehearse (pre-event + day-of) ----------
@app.command()
def rehearse(
    scenario: str = typer.Option("pick-and-place", help="pick-and-place | follow | chit-chat | dance | obstacle-course"),
    config: Path = typer.Option(Path("configs/agent.yaml"), "--config"),
    ticks: int = typer.Option(0, help="Override scenario max_ticks (0 = use scenario default)."),
    save_frames: bool = typer.Option(False, help="Save every rendered frame to runs/rehearsal-frames-<ts>/."),
    display: bool = typer.Option(False, "--display/--no-display", help="Open an OpenCV window showing the robot live."),
    delay: float = typer.Option(0.0, help="Seconds to wait between ticks. Useful with --display (e.g. 0.4)."),
    adapter: str = typer.Option("virtual", help="virtual (Mac playground) | mock | http | ros2 | lerobot — use a real robot."),
    tui: bool = typer.Option(False, "--tui/--no-tui", help="Show live Rich terminal dashboard alongside the rehearsal."),
) -> None:
    """Run a scripted rehearsal against a virtual-world mock robot and write metrics.

    Use this repeatedly on Mac+Ollama to shake out regressions before the event.
    Each run writes runs/rehearsal-<scenario>-<ts>.json and a JSONL trace.
    Add --tui for a live terminal dashboard (no browser needed).
    Add --display for an OpenCV window animation.
    """
    import asyncio as _aio
    import time as _time

    from hack.rehearsal.runner import compare_to_previous, rehearse as do_rehearse, write_summary

    frames_dir = None
    if save_frames:
        frames_dir = Path(f"runs/rehearsal-frames-{int(_time.time())}")

    console.print(f"[cyan]rehearsing[/] scenario={scenario}  display={display}  tui={tui}  delay={delay}s")
    if not display and not tui:
        console.print("  dashboard: [cyan]uv run hack tui[/] or [cyan]hack ui --rehearsal[/]")

    async def _run_with_tui() -> Any:
        """Run the rehearsal; if --tui, launch the TUI in parallel after a short delay."""
        nonlocal tui
        reh = do_rehearse(
            scenario_name=scenario,
            config_path=config,
            max_ticks=(ticks or None),
            image_save_dir=frames_dir,
            display=display,
            delay=delay,
            adapter=adapter,
        )
        if tui:
            import asyncio as _a
            from hack.ui.terminal import run_tui
            reh_task = _a.create_task(reh)
            await _a.sleep(0.5)  # let the trace file be created
            traces = sorted(Path("runs").glob(f"rehearsal-{scenario}-*.jsonl"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
            if traces:
                tui_task = _a.create_task(run_tui(traces[0], follow=True))
                result = await reh_task
                tui_task.cancel()
                try:
                    await tui_task
                except _a.CancelledError:
                    pass
                return result
            else:
                return await reh_task
        else:
            return await reh

    t0 = _time.time()
    m = _aio.run(_run_with_tui())
    total = _time.time() - t0
    path = write_summary(m, Path("runs"), config_snapshot=config)
    console.print(f"[green]wrote[/] {path}")

    t = Table(title=f"rehearsal: {scenario}", show_lines=False)
    t.add_column("metric", style="cyan")
    t.add_column("value")
    s = m.summary()
    t.add_row("success", f"{'✅' if s['success'] else '❌'}  {s['success_reason']}")
    t.add_row("ticks_run", str(s["ticks_run"]))
    vm, pm = s["vlm_ms"], s["planner_ms"]
    if vm.get("n"):
        t.add_row("vlm_ms", f"n={vm['n']}  mean={vm['mean']:.0f}  p50={vm['p50']:.0f}  p95={vm['p95']:.0f}  max={vm['max']:.0f}")
    if pm.get("n"):
        t.add_row("planner_ms", f"n={pm['n']}  mean={pm['mean']:.0f}  p50={pm['p50']:.0f}  p95={pm['p95']:.0f}  max={pm['max']:.0f}")
    t.add_row("tool_calls", ", ".join(f"{k}:{v}" for k, v in s["tool_calls"].items()) or "—")
    t.add_row("parse_failures", f"vlm={s['vlm_parse_failures']}  plan={s['plan_parse_failures']}")
    t.add_row("total_wall_s", f"{total:.1f}")
    console.print(t)

    console.rule("vs previous rehearsal")
    for line in compare_to_previous(scenario, m, Path("runs")):
        console.print(f"  {line}")

    console.rule("next")
    console.print("Append one line to [cyan]docs/REHEARSALS.md[/] — date, scenario, key metric, insight, action.")


# ---------- test-all (single health gate) ----------
@app.command("test-all")
def test_all(
    config: Path = typer.Option(Path("configs/agent.yaml"), "--config"),
) -> None:
    """Run ALL tests in sequence: unit tests → regression → obstacle-course.

    Single pass/fail gate for any config or code change. Exit 0 = ship it.
    """
    import asyncio as _aio

    results: list[tuple[str, bool, str]] = []

    # 1. Unit tests
    console.rule("[bold]1/3 Unit tests[/]")
    r = subprocess.run(["uv", "run", "pytest", "tests/", "-q"], capture_output=True, text=True)
    ok = r.returncode == 0
    console.print(r.stdout[-200:] if r.stdout else "")
    if not ok:
        console.print(f"[red]{r.stderr[-200:]}")
    results.append(("pytest", ok, f"exit={r.returncode}"))

    # 2. Regression suite
    console.rule("[bold]2/3 Regression suite[/]")
    r = subprocess.run(
        ["uv", "run", "hack", "regression", "--config", str(config), "--no-save"],
        capture_output=True, text=True, timeout=300,
    )
    ok = r.returncode == 0
    console.print(r.stdout[-500:] if r.stdout else "")
    if not ok:
        console.print(f"[red]{r.stderr[-200:]}")
    results.append(("regression", ok, f"exit={r.returncode}"))

    # 3. Obstacle-course (mock VLM, scripted cue, fully automated)
    console.rule("[bold]3/3 Obstacle course[/]")
    obstacle_cfg = Path("configs/agent.obstacle.yaml")
    if obstacle_cfg.exists():
        from hack.rehearsal.runner import rehearse as do_rehearse
        m = _aio.run(do_rehearse(
            scenario_name="obstacle-course",
            config_path=obstacle_cfg,
            max_ticks=80,
            delay=0.0,
        ))
        ok = m.success
        console.print(f"  {'[green]PASS' if ok else '[red]FAIL'} — {m.success_reason}[/]")
        results.append(("obstacle-course", ok, m.success_reason))
    else:
        console.print("[yellow]skipped (no configs/agent.obstacle.yaml)[/]")
        results.append(("obstacle-course", True, "skipped"))

    # Summary
    console.rule("[bold]Summary[/]")
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        icon = "[green]PASS[/]" if ok else "[red]FAIL[/]"
        console.print(f"  {icon}  {name:20s}  {detail}")
    console.print(f"\n  {'[green]ALL PASSED' if passed == total else f'[red]{total - passed} FAILED'}[/]  ({passed}/{total})")
    if passed < total:
        raise typer.Exit(1)


# ---------- calibrate (day-of robot tuning) ----------
@app.command()
def calibrate(
    adapter: str = typer.Option("mock", help="Robot adapter to calibrate."),
    steps: int = typer.Option(3, help="Number of steps per measurement."),
    base_url: str = typer.Option("http://127.0.0.1:9000", help="Base URL for HTTP adapter."),
) -> None:
    """Automated calibration: send known motions, measure actual, compute scale factors.

    Prints a YAML block you can paste into your config's `robot.calibration` section.
    """
    from hack.robot import make

    async def go() -> None:
        kw: dict[str, object] = {}
        if adapter == "http":
            kw["base_url"] = base_url
        try:
            async with make(adapter, **kw) as r:
                lin = 0.2
                ang = 0.6

                # Linear calibration
                console.print(f"\n[cyan]Linear calibration[/]: sending {steps}× move(dx={lin})")
                for i in range(steps):
                    await r.move(lin, 0, 0)
                    console.print(f"  step {i+1}/{steps} done")
                expected_lin = lin * steps
                console.print(f"\n  Robot should have moved [bold]{expected_lin:.2f}m[/] forward.")
                actual_lin = typer.prompt("  How far did it actually move? (metres)", type=float, default=expected_lin)
                lin_scale = expected_lin / actual_lin if actual_lin > 0 else 1.0

                # Reset position
                for i in range(steps):
                    await r.move(-lin, 0, 0)

                # Angular calibration
                console.print(f"\n[cyan]Angular calibration[/]: sending {steps}× move(dtheta={ang})")
                for i in range(steps):
                    await r.move(0, 0, ang)
                    console.print(f"  step {i+1}/{steps} done")
                import math
                expected_deg = math.degrees(ang * steps)
                console.print(f"\n  Robot should have turned [bold]{expected_deg:.0f}°[/] left.")
                actual_deg = typer.prompt("  How many degrees did it actually turn?", type=float, default=expected_deg)
                ang_scale = expected_deg / actual_deg if actual_deg > 0 else 1.0

                console.print("\n[green]Calibration results:[/]")
                console.print(f"  linear_scale:  {lin_scale:.3f}")
                console.print(f"  angular_scale: {ang_scale:.3f}")
                console.print("\nPaste into your config under [cyan]robot.calibration:[/]")
                console.print("  calibration:")
                console.print(f"    linear_scale: {lin_scale:.3f}")
                console.print(f"    angular_scale: {ang_scale:.3f}")
                console.print("    prefer_forward_walk: true")
        except Exception as e:
            console.print(f"[red]calibration failed: {e}[/]")
            raise typer.Exit(1)

    asyncio.run(go())


# ---------- monitor (correctness watcher) ----------
@app.command()
def monitor(
    follow: bool = typer.Option(True, "--follow/--no-follow", help="Tail the latest trace in real-time (Ctrl-C to stop)."),
) -> None:
    """Watch the latest rehearsal/agent JSONL for correctness issues in real-time.

    Checks rotation overshoot, sign flips, safety clamps, semantic mismatches,
    and return-to-origin failures. Writes `runs/issues.ndjson` + a markdown
    report when done.
    """
    import asyncio as _aio

    from hack.observation.correctness_monitor import CorrectnessMonitor
    runs_dir = Path("runs")
    # Find latest JSONL
    traces = sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not traces:
        console.print("[red]no JSONL traces found in runs/[/]")
        raise typer.Exit(1)
    trace = traces[0]
    console.print(f"[cyan]monitoring[/] {trace}")
    mon = CorrectnessMonitor(runs_dir)

    import json as _json

    async def _watch() -> None:
        with trace.open() as fh:
            if not follow:
                fh.seek(0)
            else:
                fh.seek(0, 2)
            while True:
                line = fh.readline()
                if not line:
                    if not follow:
                        break
                    await _aio.sleep(0.2)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                mon.check_event(ev)
                # Print issues as they appear
                if mon.issues and mon.issues[-1].tick == ev.get("tick"):
                    latest = mon.issues[-1]
                    icon = {"error": "[red]ERR[/]", "warning": "[yellow]WARN[/]", "info": "[dim]INFO[/]"}.get(latest.severity, "")
                    console.print(f"  {icon} t{latest.tick} [{latest.category}] {latest.description[:100]}")
                    if latest.suggested_fix:
                        console.print(f"       [dim]fix: {latest.suggested_fix[:100]}[/]")
                if ev.get("kind") == "stop" and follow:
                    break

    try:
        _aio.run(_watch())
    except KeyboardInterrupt:
        pass
    report = mon.write_report()
    console.print(f"\n[green]{len(mon.issues)} issues logged[/] → {report}")
    console.print(mon.summarise())


# ---------- regression (cue test suite) ----------
@app.command()
def regression(
    config: Path = typer.Option(Path("configs/agent.yaml"), "--config"),
    name: str = typer.Option("", "--name", help="Comma-separated subset of case names (default: all)."),
    save: bool = typer.Option(True, "--save/--no-save", help="Append row to docs/REHEARSALS.md."),
    json_out: Path = typer.Option(Path("runs/regression-latest.json"), "--json"),
) -> None:
    """Run the maintained mic-cue regression suite against a config.

    Curated test cases live in `src/hack/rehearsal/regression.py::CASES`.
    Each case decomposes the cue via the planner LLM and checks the resulting
    plan against scenario-specific criteria (step count, tool mix, total rotation…).
    """
    import asyncio as _aio
    import json as _json

    from hack.rehearsal.regression import (
        append_to_log, format_report, run_all, summary_json,
    )

    names = [n.strip() for n in name.split(",") if n.strip()] if name else None
    results = _aio.run(run_all(config, names))
    console.print(format_report(config, results))
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(_json.dumps(summary_json(results), indent=2))
    console.print(f"[dim]json summary -> {json_out}[/]")
    if save:
        append_to_log(config, results)
    failed = [r for r in results if not r.ok]
    if failed:
        raise typer.Exit(1)


# ---------- observe (rehearsal analysis) ----------
@app.command()
def observe(
    scenario: str = typer.Option("dance", help="pick-and-place | follow | chit-chat | dance"),
    ticks: int = typer.Option(0, help="Override scenario max_ticks (0 = scenario default)."),
    config: Path = typer.Option(Path("configs/agent.yaml"), "--config"),
    delay: float = typer.Option(0.5, help="Seconds between ticks — helps mic/dashboard keep up."),
    display: bool = typer.Option(False, "--display/--no-display"),
) -> None:
    """Run a rehearsal with live log-watching and write an observation markdown report.

    After the rehearsal completes, reads `runs/ui-latest.json` (if present) for
    dashboard state and produces `runs/observation-<scenario>-<ts>.md` with
    run metrics, behaviour flags, and any UI findings.
    """
    import asyncio as _aio

    from hack.observation.analyzer import analyze
    from hack.observation.log_watcher import watch as watch_trace
    from hack.observation.report import write_report
    from hack.observation.ui_watcher import load_latest
    from hack.rehearsal.runner import rehearse as do_rehearse, write_summary

    runs_dir = Path("runs")
    runs_dir.mkdir(parents=True, exist_ok=True)
    # Predict the trace path so the watcher can tail it.
    # The runner names files by time.time() when called; we must pass a pre-chosen trace path.
    # To keep the runner unchanged we read the newest rehearsal-<scenario>-*.jsonl after a short wait.

    async def _main() -> None:
        reh_task = _aio.create_task(do_rehearse(
            scenario_name=scenario,
            config_path=config,
            max_ticks=(ticks or None),
            display=display,
            delay=delay,
        ))
        # Give the runner a moment to create the trace file
        await _aio.sleep(0.4)
        traces = sorted(runs_dir.glob(f"rehearsal-{scenario}-*.jsonl"))
        if not traces:
            await _aio.sleep(0.8)
            traces = sorted(runs_dir.glob(f"rehearsal-{scenario}-*.jsonl"))
        trace_path = traces[-1] if traces else None
        if trace_path is not None:
            watcher = _aio.create_task(watch_trace(trace_path, console))
        else:
            watcher = None
        metrics = await reh_task
        if watcher:
            await watcher
        summary_path = write_summary(metrics, runs_dir, config_snapshot=config)
        if trace_path is None:
            console.print("[red]no trace path detected; skipping report[/]")
            return
        analyzer_result = analyze(trace_path)
        ui_snapshot = load_latest()
        report_path = write_report(scenario, analyzer_result, summary_path, ui_snapshot)
        console.print(f"[green]observation report[/] -> {report_path}")

    _aio.run(_main())


# ---------- recon (day-of) ----------
@app.command()
def recon(
    host: str = typer.Argument("local", help="'local' or user@host to SSH into."),
    out_dir: Path = typer.Option(Path("runs"), "--out-dir"),
    ssh_opts: str = typer.Option("", "--ssh-opts", help="Extra flags passed to ssh, e.g. '-p 2222 -i ~/.ssh/zgx_key'."),
) -> None:
    """Collect an objective setup snapshot from a machine (local or over SSH).

    Saves text + JSON into `runs/recon-<host>-<ts>.{txt,json}` and refreshes
    `runs/recon-latest.json` (a copy of the most recent JSON) as the
    machine-authoritative source for `hack intake` to consume.
    """
    import json as _json
    import time as _time

    script = Path("scripts/zgx_recon.sh").resolve()
    if not script.exists():
        console.print(f"[red]missing {script}[/]")
        raise typer.Exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    safe_host = host.replace("@", "_at_").replace(":", "_").replace("/", "_")
    ts = int(_time.time())
    txt_path = out_dir / f"recon-{safe_host}-{ts}.txt"
    json_path = out_dir / f"recon-{safe_host}-{ts}.json"

    if host == "local":
        console.print(f"[cyan]running locally[/] → {txt_path}")
        cmd = ["bash", str(script), "--json", str(json_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        txt_path.write_text(proc.stdout + ("\n---stderr---\n" + proc.stderr if proc.stderr else ""))
    else:
        console.print(f"[cyan]uploading recon to {host}[/]")
        scp_cmd = ["scp", *ssh_opts.split(), str(script), f"{host}:/tmp/zgx_recon.sh"]
        r = subprocess.run(scp_cmd, capture_output=True, text=True)
        if r.returncode != 0:
            console.print(f"[red]scp failed[/]\n{r.stderr}")
            raise typer.Exit(1)
        console.print(f"[cyan]running on {host}[/]")
        ssh_cmd = [
            "ssh",
            *ssh_opts.split(),
            host,
            "bash /tmp/zgx_recon.sh --json /tmp/zgx_recon.json && cat /tmp/zgx_recon.json",
        ]
        # Run, splitting stdout: text output first, then `=== JSON written ===`, then the cat of JSON.
        proc = subprocess.run(ssh_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            console.print(f"[red]ssh failed[/]\n{proc.stderr}")
            raise typer.Exit(1)
        out = proc.stdout
        marker = "=== JSON written to /tmp/zgx_recon.json ==="
        if marker in out:
            text_part, _, json_part = out.partition(marker)
            txt_path.write_text(text_part + marker + "\n")
            json_path.write_text(json_part.strip() + "\n")
        else:
            txt_path.write_text(out)
            # try to parse trailing JSON block
            try:
                start = out.rindex("{")
                json_path.write_text(out[start:].strip() + "\n")
            except ValueError:
                console.print("[yellow]no JSON detected in remote output[/]")

    # Validate JSON and refresh the "latest" pointer.
    if json_path.exists():
        try:
            data = _json.loads(json_path.read_text())
            (out_dir / "recon-latest.json").write_text(json_path.read_text())
            _summarize_recon(data, host)
        except _json.JSONDecodeError as e:
            console.print(f"[red]invalid JSON at {json_path}: {e}[/]")
    else:
        console.print(f"[red]no JSON produced for {host}[/]")

    console.print(f"[green]saved[/] {txt_path} · {json_path}")


def _summarize_recon(data: dict, host: str) -> None:
    """Print a decision-ready summary highlighting what changes day-of choices."""
    t = Table(title=f"recon summary — {host}", show_lines=False)
    t.add_column("check", style="cyan")
    t.add_column("value")
    t.add_column("impact", style="dim")

    gpu = data.get("gpu", {})
    gpu_s = f"{gpu.get('name','?')} · {gpu.get('memory_total','?')} · driver {gpu.get('driver','?')}" if gpu.get("present") else "NO GPU"
    t.add_row("GPU", gpu_s, "determines local vs remote inference")

    docker = data.get("docker", {})
    nim = (docker.get("nim_containers") or "").strip()
    t.add_row("NIM containers", nim or "none detected", "if any, prefer NIM profile (Decisions §2)")
    t.add_row("Docker running", str(docker.get("running", False)), "")

    ollama = data.get("ollama", {})
    t.add_row("Ollama", "running" if ollama.get("running") else "not running", "bootstrap_zgx.sh starts it")
    t.add_row("Ollama models", ollama.get("models") or "none", "pull required models before agent run")

    t.add_row("NeMo Agent Toolkit", "present" if data.get("nat_present") else "absent", "crib prompts if present")
    t.add_row("Disk free /", data.get("disk_free_root", "?"), "need ~50 GB for models")
    t.add_row("Memory", data.get("memory", {}).get("total", "?"), "")
    t.add_row("Ports busy", data.get("ports_in_use") or "none", "avoid collisions for hack ui/serve")
    t.add_row("uv", "present" if data.get("uv_present") else "absent", "install uv if absent")
    console.print(t)


# ---------- intake (day-of) ----------
@app.command()
def intake(
    snapshot: bool = typer.Option(True, help="Snapshot DAY_OF_INTAKE.md into runs/ so the answers are versioned."),
    template: Path = typer.Option(Path("docs/DAY_OF_INTAKE.md"), help="Path to the intake template/doc."),
) -> None:
    """Print the day-of punch-list: machine recon (authoritative) + unfilled intake blanks
    + DAYOF code markers + cut-list triggers.

    Run this right after the 30-minute challenge intro is over. If `hack recon`
    produced `runs/recon-latest.json`, its values override intake §6 (machine wins).
    """
    import json as _json
    import re
    import time

    # 0. Recon data (authoritative for §6-ish facts)
    recon_path = Path("runs/recon-latest.json")
    recon: dict | None = None
    if recon_path.exists():
        try:
            recon = _json.loads(recon_path.read_text())
        except _json.JSONDecodeError:
            recon = None

    console.rule("[bold]Machine recon (authoritative over intake §6)[/]")
    if recon is None:
        console.print("[yellow]no runs/recon-latest.json — run `hack recon <host>` first.[/]")
    else:
        _summarize_recon(recon, recon.get("hostname", "?"))

    # 1. snapshot the human-filled intake
    if snapshot and template.exists():
        out = Path("runs") / f"intake-{int(time.time())}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(template.read_text())
        console.print(f"[green]snapshot[/] {template} -> {out}")

    # 2. unfilled blanks in the intake. We skip lines under §6 if recon covers them
    # (recon is the machine-authoritative source; don't nag humans for those).
    console.rule("[bold]Unfilled intake blanks (skipping §6 when recon present)[/]")
    if not template.exists():
        console.print(f"[red]{template} missing[/]")
    else:
        blank_re = re.compile(r"(:\s*\.\.\.\s*$)|(^\s*[-*]?\s*\.\.\.\s*$)|(_{3,})|(\bTBD\b)")
        lines = template.read_text().splitlines()
        # Find §6 block so we can skip it if recon is available.
        skip_ranges: list[tuple[int, int]] = []
        if recon is not None:
            in_six = False
            start = 0
            for idx, line in enumerate(lines, start=1):
                if line.lstrip().startswith("## 6."):
                    in_six = True
                    start = idx
                elif in_six and line.lstrip().startswith("## "):
                    skip_ranges.append((start, idx - 1))
                    in_six = False
            if in_six:
                skip_ranges.append((start, len(lines)))
        def in_skip(n: int) -> bool:
            return any(a <= n <= b for a, b in skip_ranges)

        unfilled = [(i, ln.strip()[:80]) for i, ln in enumerate(lines, start=1)
                    if blank_re.search(ln) and not in_skip(i)]
        if not unfilled:
            console.print("[green]all blanks filled[/]")
        else:
            for n, text in unfilled[:40]:
                console.print(f"  [yellow]{n:>4}[/] {text}")
            if len(unfilled) > 40:
                console.print(f"  [dim]...and {len(unfilled) - 40} more[/]")

    # 3. DAYOF markers grouped by file (skip self — the scanner lines in this CLI).
    console.rule("[bold]# DAYOF: code punch-list[/]")
    hits: dict[str, list[tuple[int, str]]] = {}
    self_path = Path(__file__).resolve()
    for path in sorted(Path("src").rglob("*.py")):
        if path.resolve() == self_path:
            continue
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("# DAYOF:"):
                hits.setdefault(str(path), []).append((i, line.strip()))
    for cfg_path in (Path("configs/agent.yaml"),):
        if cfg_path.exists():
            for i, line in enumerate(cfg_path.read_text().splitlines(), start=1):
                stripped = line.lstrip()
                if stripped.startswith("# DAYOF:"):
                    hits.setdefault(str(cfg_path), []).append((i, line.strip()))
    if not hits:
        console.print("[green]no DAYOF markers left (either done or never placed)[/]")
    else:
        for path, rows in hits.items():
            console.print(f"[cyan]{path}[/]")
            for n, text in rows:
                console.print(f"  {n:>4}  {text[:120]}")

    # 4. cut-list reminders
    console.rule("[bold]Cut-list triggers (from day_of_playbook.md)[/]")
    console.print("  T+1:00 adapter red     → MockRobot + scripted demo")
    console.print("  T+1:00 STT flaky       → dashboard text input")
    console.print("  T+1:15 latency > 3.5s  → smaller model (Decisions §7)")
    console.print("  T+1:30 new crash       → git reset to last green commit")
    console.print("  T+1:45 live unreliable → ship recorded take")

    console.rule("[bold]Next[/]")
    console.print("Walk [cyan]docs/DAY_OF_DECISIONS.md[/] top to bottom, then open [cyan]docs/DAY_OF_TASKS.md[/] and tick.")


# ---------- doctor ----------
@app.command()
def doctor() -> None:
    """Full environment check. Run this first on event day."""
    table = Table(title="hack doctor", show_lines=False)
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    def row(name: str, ok: bool, detail: str) -> None:
        table.add_row(name, "[green]OK[/]" if ok else "[red]FAIL[/]", detail)

    # python
    import sys
    row("python", sys.version_info >= (3, 11), sys.version.split()[0])

    # uv
    uv = shutil.which("uv")
    row("uv", uv is not None, uv or "not found")

    # GPU (nvidia-smi if present)
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.check_output([smi, "--query-gpu=name,memory.total", "--format=csv,noheader"], text=True, timeout=3).strip()
            row("nvidia-smi", True, out.splitlines()[0])
        except Exception as e:
            row("nvidia-smi", False, str(e))
    else:
        row("nvidia-smi", False, "not found (expected on Mac dev; required on ZGX)")

    # camera
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        ok = cap.isOpened()
        if ok:
            ret, frame = cap.read()
            ok = ret and frame is not None
            shape = getattr(frame, "shape", None)
        cap.release()
        row("camera (cv2 :0)", ok, str(shape) if ok else "no frame")
    except Exception as e:
        row("camera (cv2 :0)", False, str(e))

    # mic
    try:
        import sounddevice as sd
        devs = [d for d in sd.query_devices() if d["max_input_channels"] > 0]
        row("microphone", bool(devs), f"{len(devs)} input device(s)")
    except Exception as e:
        row("microphone", False, str(e))

    # ports
    for port in (11434, 8000):
        s = socket.socket()
        s.settimeout(0.2)
        try:
            s.connect(("127.0.0.1", port))
            row(f"port :{port}", True, "in use (server up?)")
        except OSError:
            row(f"port :{port}", True, "free")
        finally:
            s.close()

    # config
    cfg = Path("configs/agent.yaml")
    row("configs/agent.yaml", cfg.exists(), str(cfg.resolve()) if cfg.exists() else "missing")

    console.print(table)


# ---------- serve ----------
@serve.command("start")
def serve_start(models: str = typer.Option("llm,vlm,stt,tts", help="Comma-separated subset.")) -> None:
    """Launch local model servers via scripts/bootstrap_zgx.sh."""
    script = Path("scripts/bootstrap_zgx.sh")
    if not script.exists():
        console.print("[red]scripts/bootstrap_zgx.sh missing[/]")
        raise typer.Exit(1)
    subprocess.run(["bash", str(script), "--models", models], check=False)


@serve.command("status")
def serve_status(host: str = "127.0.0.1") -> None:
    """Probe each local model server."""
    import httpx
    targets = {
        "ollama": f"http://{host}:11434/api/tags",
    }
    for name, url in targets.items():
        try:
            r = httpx.get(url, timeout=2.0)
            console.print(f"[green]{name}[/] {url} -> {r.status_code}")
        except Exception as e:
            console.print(f"[red]{name}[/] {url} -> {e}")


@serve.command("stop")
def serve_stop(force: bool = False) -> None:
    """Stop local model servers (best-effort)."""
    if force:
        subprocess.run(["pkill", "-9", "-f", "ollama"], check=False)
    else:
        subprocess.run(["pkill", "-f", "ollama"], check=False)


@serve.command("warmup")
def serve_warmup() -> None:
    """Fire 3 tiny prompts to warm caches."""
    import httpx
    for i in range(3):
        try:
            r = httpx.post(
                "http://127.0.0.1:11434/api/generate",
                json={"model": "qwen2.5:7b", "prompt": "ok", "stream": False, "options": {"num_predict": 4}},
                timeout=30.0,
            )
            console.print(f"warmup {i+1}: {r.status_code}")
        except Exception as e:
            console.print(f"[red]warmup {i+1} failed: {e}[/]")


# ---------- robot ----------
@robot.command("probe")
def robot_probe(adapter: str = "mock", base_url: str = "http://127.0.0.1:9000") -> None:
    """Cycle every adapter method with safe small values."""
    from hack.robot import make

    async def go() -> None:
        kw: dict[str, object] = {}
        if adapter == "http":
            kw["base_url"] = base_url
        try:
            async with make(adapter, **kw) as r:
                console.print(f"[bold]probing {adapter}[/]")
                await r.move(0.05, 0.0, 0.0)
                await r.move(0.0, 0.0, 0.1)
                await r.set_joint("test", 0.5)
                await r.grasp()
                await r.release()
                await r.emote("hello")
                state = await r.get_state()
                console.print(state)
        except Exception as e:
            console.print(f"[red]robot probe failed ({adapter}): {e}[/]")
            raise typer.Exit(1)

    asyncio.run(go())


@robot.command("teleop")
def robot_teleop(adapter: str = "mock") -> None:
    """Keyboard teleop: WASD move, Q/E yaw, G grasp, R release, X quit."""
    import sys
    import termios
    import tty

    from hack.robot import make

    async def go() -> None:
        async with make(adapter) as r:
            console.print("WASD = move, Q/E = yaw, G = grasp, R = release, X = quit")
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                while True:
                    ch = sys.stdin.read(1).lower()
                    if ch == "x":
                        break
                    if ch == "w":
                        await r.move(0.1, 0, 0)
                    elif ch == "s":
                        await r.move(-0.1, 0, 0)
                    elif ch == "a":
                        await r.move(0, 0.1, 0)
                    elif ch == "d":
                        await r.move(0, -0.1, 0)
                    elif ch == "q":
                        await r.move(0, 0, 0.2)
                    elif ch == "e":
                        await r.move(0, 0, -0.2)
                    elif ch == "g":
                        await r.grasp()
                    elif ch == "r":
                        await r.release()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

    asyncio.run(go())


# ---------- agent ----------
@agent.command("run")
def agent_run(
    robot: str = typer.Option("mock", "--robot"),
    config: Path = typer.Option(Path("configs/agent.yaml"), "--config"),
) -> None:
    """Run the live agent loop."""
    from hack.agent.runtime import run as runtime_run

    try:
        asyncio.run(runtime_run(robot_name=robot, config_path=config))
    except Exception as e:
        console.print(f"[red]agent run failed: {e}[/]")
        raise typer.Exit(1)


@agent.command("replay")
def agent_replay(trace: Path, config: Path = Path("configs/agent.yaml")) -> None:
    """Replay a JSONL trace through the current planner config."""
    from hack.agent.runtime import replay as runtime_replay

    asyncio.run(runtime_replay(trace=trace, config_path=config))


@agent.command("diff")
def agent_diff(a: Path, b: Path) -> None:
    """Diff actions chosen between two JSONL traces."""
    import json

    aa = [json.loads(line) for line in a.read_text().splitlines() if line.strip()]
    bb = [json.loads(line) for line in b.read_text().splitlines() if line.strip()]
    for i, (x, y) in enumerate(zip(aa, bb)):
        ax = x.get("action")
        bx = y.get("action")
        if ax != bx:
            console.print(f"[yellow]{i}[/] {ax} -> {bx}")


# ---------- sensors ----------
@sensors.command("camera")
def sensors_camera(show: bool = True, device: int = 0) -> None:
    """Live camera preview with FPS overlay."""
    import time
    import cv2

    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        console.print("[red]camera not available[/]")
        raise typer.Exit(1)
    last = time.time()
    fps = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            now = time.time()
            fps = 0.9 * fps + 0.1 * (1.0 / max(now - last, 1e-3))
            last = now
            if show:
                cv2.putText(frame, f"{fps:5.1f} fps", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                cv2.imshow("hack camera", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()


@sensors.command("mic")
def sensors_mic(transcribe: bool = False, seconds: float = 5.0) -> None:
    """Record from default mic; optionally transcribe with Whisper."""
    import numpy as np
    import sounddevice as sd

    sr = 16000
    console.print(f"recording {seconds:.1f}s @ {sr} Hz...")
    audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    audio = np.squeeze(audio)
    rms = float(np.sqrt(np.mean(audio**2)))
    console.print(f"rms={rms:.4f}")
    if transcribe:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            console.print("[red]install with: uv pip install '.[audio]'[/]")
            raise typer.Exit(1)
        model = WhisperModel("small", device="auto", compute_type="auto")
        segs, _ = model.transcribe(audio, language="en")
        for s in segs:
            console.print(f"[{s.start:5.2f}-{s.end:5.2f}] {s.text}")


# ---------- tui (terminal UI) ----------
@app.command("tui")
def tui(
    trace: Path = typer.Argument(None, help="JSONL trace to tail. Default: latest in runs/."),
    no_follow: bool = typer.Option(False, "--no-follow", help="Read the whole file then exit (replay mode)."),
    scenario: str = typer.Option("dance", "--scenario", help="Default scenario for Ctrl+R restart."),
    config: str = typer.Option("configs/agent.yaml", "--config", help="Default config for Ctrl+R restart."),
) -> None:
    """Full-screen terminal dashboard with command input and rehearsal controls.

    Type a command at the bottom → sends to robot. Keyboard shortcuts:
      Ctrl+R  restart rehearsal (current scenario)
      Ctrl+O  cycle scenario (dance → obstacle-course → …)
      Ctrl+K  kill running rehearsal
      Ctrl+C  quit

    World map shows robot (arrow), obstacles (●), goal (◆) in real-time.
    """
    from hack.ui.tui_app import run_textual_tui

    run_textual_tui(trace_path=trace, follow=not no_follow, scenario=scenario, config=config)


# ---------- world (Kitty image viewer) ----------
@app.command("world")
def world(
    interval: float = typer.Option(0.3, help="Refresh interval in seconds."),
    frame: Path = typer.Option(Path("runs/last_frame.jpg"), help="Frame path to display."),
) -> None:
    """Live world view using Kitty's icat — pixel-perfect, auto-refreshing.

    Run in a separate Kitty pane alongside `hack tui`. Shows the full-resolution
    OpenCV frame from the rehearsal runner, updated every --interval seconds.
    Press Ctrl+C to stop.
    """
    import time as _time

    if not shutil.which("kitten"):
        console.print("[red]kitten not found — this command requires Kitty terminal[/]")
        console.print("[dim]alternative: watch -n 0.5 kitten icat --clear runs/last_frame.jpg[/]")
        raise typer.Exit(1)

    console.print(f"[dim]watching {frame} every {interval}s — Ctrl+C to stop[/]")
    try:
        while True:
            if frame.exists():
                # Get terminal size in columns and use it to scale the image.
                try:
                    cols = os.get_terminal_size().columns
                except OSError:
                    cols = 80
                subprocess.run(
                    ["kitten", "icat", "--clear", "--align", "left",
                     "--place", f"{cols}x{cols}@0x0",
                     str(frame)],
                    check=False,
                )
            _time.sleep(interval)
    except KeyboardInterrupt:
        # Clear the image on exit.
        subprocess.run(["kitten", "icat", "--clear"], check=False)


# ---------- ui (web) ----------
@app.command("ui")
def ui(host: str = "127.0.0.1", port: int = 8000, rehearsal: bool = typer.Option(False, "--rehearsal", help="Serve the rehearsal dashboard (adds mic + cue input). Never use on event day.")) -> None:
    """Run the web dashboard — the day-of one by default, the rehearsal one with --rehearsal."""
    import uvicorn
    target = "hack.rehearsal.dashboard:app" if rehearsal else "hack.ui.app:app"
    if rehearsal:
        console.print("[yellow]rehearsal[/] dashboard — mic + cue enabled. Do NOT use on event day.")
    uvicorn.run(target, host=host, port=port, reload=False)


# ---------- demo ----------
@demo.command("record")
def demo_record(out: Path = Path("runs/submit.jsonl"), video: Path | None = None) -> None:
    """Run the agent and record a clean JSONL trace (and optional video)."""
    from hack.agent.runtime import run as runtime_run

    out.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"recording to {out}...")
    asyncio.run(runtime_run(robot_name="mock", config_path=Path("configs/agent.yaml"), trace_out=out, video_out=video))


@demo.command("play")
def demo_play(trace: Path) -> None:
    """Replay a trace through the dashboard for judges."""
    console.print(f"streaming {trace} to dashboard at http://127.0.0.1:8000/replay")
    import uvicorn
    import os
    os.environ["HACK_REPLAY_TRACE"] = str(trace)
    uvicorn.run("hack.ui.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    app()
