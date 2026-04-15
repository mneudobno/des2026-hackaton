from __future__ import annotations

import asyncio
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

    asyncio.run(runtime_run(robot_name=robot, config_path=config))


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


# ---------- ui ----------
@app.command("ui")
def ui(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the FastAPI dashboard."""
    import uvicorn
    uvicorn.run("hack.ui.app:app", host=host, port=port, reload=False)


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
