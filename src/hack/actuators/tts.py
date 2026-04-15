from __future__ import annotations

import asyncio
import shutil
import subprocess


class TTS:
    """Tiny TTS wrapper. Default uses macOS `say` for dev, Piper on Linux/ZGX.

    Day-of: switch via config; Piper voice models live alongside `bootstrap_zgx.sh`.
    """

    def __init__(self, voice: str = "en_US-amy-medium", barge_in: bool = True) -> None:
        self.voice = voice
        self.barge_in = barge_in
        self._proc: subprocess.Popen | None = None

    async def speak(self, text: str) -> None:
        if not text.strip():
            return
        if self.barge_in and self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                self._proc.kill()

        if shutil.which("piper"):
            cmd = ["piper", "--model", self.voice, "--output_raw"]
            self._proc = await asyncio.to_thread(
                subprocess.Popen, cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL
            )
            assert self._proc.stdin is not None
            self._proc.stdin.write(text.encode())
            self._proc.stdin.close()
        elif shutil.which("say"):
            self._proc = await asyncio.to_thread(subprocess.Popen, ["say", text])
        else:
            print(f"[tts:{self.voice}] {text}")
