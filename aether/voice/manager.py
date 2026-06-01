"""Voice output with ElevenLabs + system fallbacks."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from typing import Optional

from aether.voice.elevenlabs import ElevenLabsVoice


class VoiceManager:
    """Sync-friendly wrapper used by the harness."""

    def __init__(self, api_key: Optional[str] = None, voice_id: Optional[str] = None):
        self._eleven = ElevenLabsVoice(api_key=api_key, voice_id=voice_id)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._loop_task: Optional[asyncio.Task] = None
        self._running = False

    def speak(self, text: str) -> None:
        """Speak without blocking the caller (best effort)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._speak_async(text))
        except RuntimeError:
            asyncio.run(self._speak_async(text))

    async def _speak_async(self, text: str) -> None:
        if self._eleven.api_key:
            ok = await self._eleven.speak(text)
            if ok:
                return
        await self._system_tts(text)

    async def _system_tts(self, text: str) -> None:
        def run() -> None:
            if shutil.which("espeak-ng"):
                subprocess.run(["espeak-ng", text], capture_output=True, check=False)
            elif shutil.which("espeak"):
                subprocess.run(["espeak", text], capture_output=True, check=False)
            elif shutil.which("say"):
                subprocess.run(["say", text], capture_output=True, check=False)
            else:
                print(f"[A.E.T.H.E.R.] {text}")

        await asyncio.to_thread(run)
