from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class JsonlLogger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", buffering=1)
        self._listeners: list[Any] = []

    def add_listener(self, listener: Any) -> None:
        """Register an object with a `check_event(dict)` method.
        Called on every `log()` invocation so the listener sees events in real-time."""
        self._listeners.append(listener)

    def log(self, kind: str, **payload: Any) -> None:
        rec = {"ts": time.time(), "kind": kind, **payload}
        self._fh.write(json.dumps(rec, default=str) + "\n")
        for listener in self._listeners:
            try:
                listener.check_event(rec)
            except Exception:
                pass

    def close(self) -> None:
        self._fh.close()
