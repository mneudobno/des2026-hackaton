from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import numpy as np


@dataclass
class Utterance:
    text: str
    ts: float


class MicTranscriber:
    """Streaming mic → VAD → Whisper. Emits Utterance per detected speech segment.

    Lazy imports keep the base install slim — extras `[audio]` provide faster-whisper
    and silero-vad. Falls back to fixed-window chunking if VAD is unavailable.
    """

    def __init__(
        self,
        model: str = "large-v3-turbo",
        language: str = "en",
        sample_rate: int = 16000,
        chunk_seconds: float = 1.5,
    ) -> None:
        self.model_name = model
        self.language = language
        self.sr = sample_rate
        self.chunk_samples = int(chunk_seconds * sample_rate)
        self._whisper = None
        self._vad = None

    def _ensure_models(self) -> None:
        if self._whisper is None:
            from faster_whisper import WhisperModel
            self._whisper = WhisperModel(self.model_name, device="auto", compute_type="auto")
        if self._vad is None:
            try:
                from silero_vad import load_silero_vad
                self._vad = load_silero_vad()
            except ImportError:
                self._vad = False  # sentinel — VAD unavailable, use fixed windows

    async def utterances(self):
        import sounddevice as sd

        self._ensure_models()
        q: asyncio.Queue[np.ndarray] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def cb(indata, frames, t, status):  # noqa: ANN001
            loop.call_soon_threadsafe(q.put_nowait, indata.copy().squeeze())

        with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32", callback=cb, blocksize=self.chunk_samples):
            buf = np.zeros(0, dtype=np.float32)
            while True:
                chunk = await q.get()
                buf = np.concatenate([buf, chunk])
                if len(buf) < self.chunk_samples * 2:
                    continue
                segment = buf[: self.chunk_samples * 2]
                buf = buf[self.chunk_samples:]
                rms = float(np.sqrt(np.mean(segment**2)))
                if rms < 0.01:
                    continue
                segs, _ = await asyncio.to_thread(self._whisper.transcribe, segment, language=self.language)
                text = " ".join(s.text.strip() for s in segs).strip()
                if text:
                    yield Utterance(text=text, ts=time.time())
