"""Cheap single-object tracker, fed by infrequent VLM bounding boxes.

Pattern lifted from HALO (`andrei-ace/HALO`) and NVIDIA's photo-booth playbook
(which uses Detectron2 + ByteTrack): the VLM grounds *what* and *where roughly*,
then a fast per-frame tracker emits continuous target poses so the control loop
doesn't block on LLM latency.

Usage:
    tracker = BBoxTracker()
    tracker.reinit(frame, bbox)      # when VLM gives us a new bbox
    ok, bbox = tracker.update(frame) # every frame
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class BBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def as_xywh(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h


class BBoxTracker:
    """Thin wrapper around OpenCV's CSRT tracker.

    CSRT is ~3x slower than KCF but far more robust; on a Mac laptop a 640x480
    frame tracks at 60+ FPS, plenty of headroom against a 2 FPS VLM.
    """

    def __init__(self) -> None:
        self._tracker: cv2.Tracker | None = None

    def reinit(self, frame: np.ndarray, bbox: BBox) -> None:
        self._tracker = cv2.TrackerCSRT_create()
        self._tracker.init(frame, bbox.as_xywh())

    def update(self, frame: np.ndarray) -> tuple[bool, BBox | None]:
        if self._tracker is None:
            return False, None
        ok, xywh = self._tracker.update(frame)
        if not ok:
            return False, None
        x, y, w, h = (int(v) for v in xywh)
        return True, BBox(x, y, w, h)
