from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class JsonlLogger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", buffering=1)

    def log(self, kind: str, **payload: Any) -> None:
        rec = {"ts": time.time(), "kind": kind, **payload}
        self._fh.write(json.dumps(rec, default=str) + "\n")

    def close(self) -> None:
        self._fh.close()
