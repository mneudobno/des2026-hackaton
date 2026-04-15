from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Frame:
    image: np.ndarray  # BGR, shape (H, W, 3), uint8
    ts: float
    seq: int


class Camera:
    """Async webcam capture with FPS throttling and frame-diff gating.

    Iterating yields Frame objects only when the scene has meaningfully changed
    (or when min_interval has elapsed), so the VLM doesn't see redundant inputs.
    """

    def __init__(
        self,
        device: int = 0,
        fps: float = 2.0,
        downscale_to: int = 768,
        diff_threshold: float = 0.02,
    ) -> None:
        self.device = device
        self.min_interval = 1.0 / max(fps, 0.1)
        self.downscale_to = downscale_to
        self.diff_threshold = diff_threshold
        self._cap: cv2.VideoCapture | None = None
        self._last_small: np.ndarray | None = None
        self._seq = 0

    async def __aenter__(self) -> "Camera":
        self._cap = cv2.VideoCapture(self.device)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open camera device {self.device}")
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    def _downscale(self, img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        m = max(h, w)
        if m <= self.downscale_to:
            return img
        scale = self.downscale_to / m
        return cv2.resize(img, (int(w * scale), int(h * scale)))

    def _diff(self, a: np.ndarray, b: np.ndarray) -> float:
        ah = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        bh = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        if ah.shape != bh.shape:
            bh = cv2.resize(bh, (ah.shape[1], ah.shape[0]))
        return float(np.mean(np.abs(ah - bh)))

    async def frames(self):
        assert self._cap is not None
        last_emit = 0.0
        while True:
            ok, frame = await asyncio.to_thread(self._cap.read)
            if not ok:
                await asyncio.sleep(0.05)
                continue
            small = self._downscale(frame)
            now = time.time()
            elapsed = now - last_emit
            changed = (
                self._last_small is None
                or self._diff(self._last_small, small) > self.diff_threshold
            )
            if elapsed >= self.min_interval and changed:
                self._seq += 1
                self._last_small = small
                last_emit = now
                yield Frame(image=small, ts=now, seq=self._seq)
            else:
                await asyncio.sleep(min(0.05, max(self.min_interval - elapsed, 0.0)))
