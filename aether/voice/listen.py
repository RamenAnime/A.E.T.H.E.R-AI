"""Offline speech-to-text using Vosk (local, no cloud).

Vosk runs entirely on-device. Download a model once (see docs/MANJARO.md) and
point AETHER_VOSK_MODEL at it, or drop it in ./models/vosk.

This module never imports vosk/sounddevice at module load, so the rest of
A.E.T.H.E.R. keeps working even if speech extras are not installed.
"""

from __future__ import annotations

import json
import os
import queue
from pathlib import Path
from typing import Callable, Optional


def stt_available() -> bool:
    try:
        import sounddevice  # noqa: F401
        import vosk  # noqa: F401

        return True
    except Exception:
        return False


def find_model(explicit: str = "") -> Optional[str]:
    """Locate a Vosk model directory."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    env = os.getenv("AETHER_VOSK_MODEL", "")
    if env:
        candidates.append(env)
    candidates += [
        "./models/vosk",
        str(Path.home() / ".cache" / "vosk"),
        "/usr/share/vosk-model",
    ]
    for c in candidates:
        p = Path(c).expanduser()
        if p.is_dir() and any(p.iterdir()):
            return str(p)
    return None


class VoiceListener:
    """Continuous microphone listener that yields recognized phrases."""

    def __init__(self, model_path: str = "", samplerate: int = 16000):
        self.model_path = find_model(model_path)
        self.samplerate = samplerate
        self._model = None
        self._stop = False

    def available(self) -> bool:
        return stt_available() and self.model_path is not None

    def _ensure_model(self) -> None:
        if self._model is None:
            import vosk

            vosk.SetLogLevel(-1)
            self._model = vosk.Model(self.model_path)

    def listen_loop(self, on_phrase: Callable[[str], None], should_stop: Optional[Callable[[], bool]] = None) -> None:
        """Block, streaming recognized phrases to on_phrase until stopped."""
        import sounddevice as sd
        import vosk

        self._ensure_model()
        self._stop = False
        audio_q: "queue.Queue[bytes]" = queue.Queue()

        def cb(indata, _frames, _time, _status):
            audio_q.put(bytes(indata))

        rec = vosk.KaldiRecognizer(self._model, self.samplerate)
        with sd.RawInputStream(
            samplerate=self.samplerate, blocksize=8000, dtype="int16", channels=1, callback=cb
        ):
            while not self._stop and not (should_stop and should_stop()):
                try:
                    data = audio_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if rec.AcceptWaveform(data):
                    text = json.loads(rec.Result()).get("text", "").strip()
                    if text:
                        on_phrase(text)

    def stop(self) -> None:
        self._stop = True
