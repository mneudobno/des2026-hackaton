"""UI observation helpers.

Chrome MCP tools are only callable from inside a Claude Code session — this
module gives Claude a stable place to write snapshots so `hack observe` can
pick them up. Claude saves snapshots via `save_snapshot()`; the report reads
`runs/ui-latest.json`.

During a Claude Code session, the assistant should call something like:

```
from hack.observation.ui_watcher import save_snapshot
save_snapshot({
    "url": "http://127.0.0.1:8000",
    "console_errors": [...],
    "mic_state": "off",
    "camera_img_status": 200,
    "screenshot_path": "runs/ui-2026-04-15T18-30.png",
    "notes": ["dashboard loaded cleanly", "mic button enabled"],
})
```

Outside of Claude Code, `hack observe` still works — the UI section of the
report simply reports "no UI snapshot present".
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


SNAPSHOT_DIR = Path("runs")
LATEST_PATH = SNAPSHOT_DIR / "ui-latest.json"


def save_snapshot(data: dict[str, Any], out_dir: Path = SNAPSHOT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = out_dir / f"ui-{ts}.json"
    payload = {"ts": ts, **data}
    path.write_text(json.dumps(payload, indent=2, default=str))
    LATEST_PATH.write_text(path.read_text())
    return path


def load_latest(out_dir: Path = SNAPSHOT_DIR) -> dict[str, Any] | None:
    p = out_dir / "ui-latest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None
