"""ElevenLabs TTS with cross-platform audio playback."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import tempfile
from typing import List, Optional

import aiohttp


class ElevenLabsVoice:
    API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    def __init__(self, api_key: Optional[str] = None, voice_id: Optional[str] = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "HBr48ROZd1B2dv74C8bN")
        self._session: Optional[aiohttp.ClientSession] = None
        self._is_speaking = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def speak(self, text: str, stability: float = 0.5, similarity: float = 0.75) -> bool:
        if not self.api_key:
            print(f"[TTS] {text}")
            return False
        if len(text) > 5000:
            for chunk in self._split_text(text, 5000):
                await self._speak_chunk(chunk, stability, similarity)
            return True
        return await self._speak_chunk(text, stability, similarity)

    async def _speak_chunk(self, text: str, stability: float, similarity: float) -> bool:
        self._is_speaking = True
        try:
            session = await self._get_session()
            url = self.API_URL.format(voice_id=self.voice_id)
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key,
            }
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity,
                },
            }
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    print(f"ElevenLabs error: {resp.status} - {await resp.text()}")
                    return False
                audio_data = await resp.read()
                await self._play_audio(audio_data)
                return True
        except Exception as exc:
            print(f"TTS error: {exc}")
            return False
        finally:
            self._is_speaking = False

    async def _play_audio(self, audio_data: bytes) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name
        try:
            await asyncio.to_thread(_play_file_sync, temp_path)
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def speak_sync(self, text: str) -> bool:
        return asyncio.run(self.speak(text))

    def _split_text(self, text: str, max_length: int) -> List[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: List[str] = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) < max_length:
                current = f"{current} {sentence}".strip() if current else sentence
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
        return chunks

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


def _play_file_sync(path: str) -> None:
    import shutil

    players = [
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
        ["mpv", "--no-video", "--really-quiet", path],
    ]
    for cmd in players:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, check=True, timeout=300)
                return
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue
    if sys.platform == "win32":
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "Add-Type -AssemblyName presentationCore; "
                        f"$m = New-Object System.Windows.Media.MediaPlayer; "
                        f"$m.Open([Uri]::new((Resolve-Path '{path}').Path)); "
                        "$m.Play(); Start-Sleep -Seconds 2; "
                        "while($m.Position -lt $m.NaturalDuration.TimeSpan){ Start-Sleep -Milliseconds 200 }"
                    ),
                ],
                check=False,
                timeout=300,
            )
            return
        except Exception:
            os.startfile(path)  # noqa: S606
            return
    print(f"[Audio saved] {path}")
