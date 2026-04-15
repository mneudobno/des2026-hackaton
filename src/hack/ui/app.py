"""Day-of dashboard — minimal, no rehearsal-only features.

- `/` HTML page with live camera + SSE event stream
- `/camera.jpg` serves `runs/last_frame.jpg`
- `/events` tails the newest `runs/*.jsonl`

Rehearsal-only affordances (mic cue, scenario controls) live in
`hack.rehearsal.dashboard` so this file stays trusted for the judged demo.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

app = FastAPI(title="hack dashboard")


INDEX_HTML = """
<!doctype html>
<html><head><title>hack dashboard</title>
<style>
body{margin:0;background:#0b0d10;color:#e6e6e6;font:14px/1.4 -apple-system,monospace}
.grid{display:grid;grid-template-columns:3fr 2fr;gap:12px;padding:12px;height:100vh;box-sizing:border-box}
.panel{background:#15181c;border:1px solid #232830;border-radius:8px;padding:12px;overflow:auto;display:flex;flex-direction:column;min-height:0}
.hdr{display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap}
h2{margin:0;font-size:13px;color:#7aa2ff;text-transform:uppercase;letter-spacing:.08em}
.kind{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;margin-right:6px}
.observation{background:#1a3050;color:#9cc4ff}
.plan{background:#3a2a55;color:#d0a8ff}
.action{background:#1f3d2a;color:#9be8a8}
.info{background:#2a2a2a;color:#c0c0c0}
pre{margin:0;white-space:pre-wrap;word-break:break-word;font-size:11px}
.row{border-bottom:1px solid #1f242a;padding:6px 0}
img{width:100%;height:auto;border-radius:6px;image-rendering:pixelated;flex:1;object-fit:contain;background:#000}
#stream{flex:1;overflow-y:auto}
</style></head>
<body>
<div class="grid">
  <div class="panel"><div class="hdr"><h2>Live camera</h2></div><img id="cam" src="/camera.jpg"/></div>
  <div class="panel"><div class="hdr"><h2>Stream</h2></div><div id="stream"></div></div>
</div>
<script>
const stream = document.getElementById("stream");
const es = new EventSource("/events");
es.onmessage = (e) => {
  const r = JSON.parse(e.data);
  const div = document.createElement("div");
  div.className = "row";
  div.innerHTML = `<span class="kind ${r.kind}">${r.kind}</span><pre>${JSON.stringify(r, null, 2)}</pre>`;
  stream.prepend(div);
  while (stream.children.length > 80) stream.lastChild.remove();
};
setInterval(() => { document.getElementById("cam").src = "/camera.jpg?" + Date.now(); }, 500);
</script>
</body></html>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return INDEX_HTML


@app.get("/camera.jpg")
async def camera_jpg():
    """Serve the latest camera frame if recorded; otherwise a placeholder."""
    p = Path("runs/last_frame.jpg")
    if p.exists():
        return StreamingResponse(p.open("rb"), media_type="image/jpeg")
    import base64
    gif = base64.b64decode("R0lGODlhAQABAAAAACwAAAAAAQABAAA=")
    return StreamingResponse(iter([gif]), media_type="image/gif")


def _tail_jsonl(path: Path) -> AsyncIterator[str]:
    async def gen() -> AsyncIterator[str]:
        if not path.exists():
            yield "data: {\"kind\":\"info\",\"msg\":\"no trace yet\"}\n\n"
            while not path.exists():
                await asyncio.sleep(0.5)
        with path.open() as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if not line:
                    await asyncio.sleep(0.2)
                    continue
                yield f"data: {line.strip()}\n\n"
    return gen()


def _replay_jsonl(path: Path) -> AsyncIterator[str]:
    async def gen() -> AsyncIterator[str]:
        for line in path.read_text().splitlines():
            if line.strip():
                yield f"data: {line}\n\n"
                await asyncio.sleep(0.4)
    return gen()


@app.get("/events")
async def events():
    replay_path = os.environ.get("HACK_REPLAY_TRACE")
    if replay_path:
        return StreamingResponse(_replay_jsonl(Path(replay_path)), media_type="text/event-stream")
    runs = sorted(Path("runs").glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) if Path("runs").exists() else []
    target = runs[0] if runs else Path("runs/_none.jsonl")
    return StreamingResponse(_tail_jsonl(target), media_type="text/event-stream")
