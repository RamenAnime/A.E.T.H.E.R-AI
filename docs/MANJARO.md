# A.E.T.H.E.R. on Manjaro (native desktop app)

Install checklist: [INSTALL.md](INSTALL.md).

A real local application, no browser. It runs the model router, command
dispatcher, learn/build pipelines, smart-home control, and offline voice all in
one window.

## One-shot install

```bash
cd aether
bash packaging/install-manjaro.sh
```

That installs system packages, Ollama, a Python venv with the desktop + voice
extras, an offline speech model, and a menu launcher.

Then pull at least one model (a code model makes "build me an app" much better):

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b     # set OLLAMA_CODE_MODEL=qwen2.5-coder:7b in .env
```

Launch it:

```bash
aether-app            # or run "A.E.T.H.E.R." from your app menu
```

## Manual install

```bash
sudo pacman -S --needed python python-pip pyside6 portaudio espeak-ng mpv ffmpeg
python -m venv .venv && source .venv/bin/activate
pip install -e ".[desktop,stt]"
```

System package notes:

- `pyside6`: the GUI toolkit (the `[desktop]` extra also pip-installs it if you skip pacman).
- `portaudio`: required by `sounddevice` for microphone capture.
- `espeak-ng`: free offline text-to-speech fallback (used when no ElevenLabs key).
- `mpv` / `ffmpeg`: audio playback for ElevenLabs voice.

## Offline voice (Vosk)

Voice input is fully local via Vosk. The installer downloads the small English
model to `models/vosk`. To use a different one:

```bash
# pick a model from https://alphacephei.com/vosk/models
export AETHER_VOSK_MODEL=/path/to/vosk-model-en-us-0.22
```

In the app, click **🎤 Listen**, then say **"Aether, build me a REST API"**.

## System tray and global hotkey

- Closing the window **minimizes to tray** (does not quit)
- **Double-click** the tray icon to open
- **Ctrl+Alt+A** summons the app from anywhere (requires `pynput`, included in `[desktop]`)
- **Autonomy** tab: set a mission, restrictions, Start / **STOP**

## Start automatically on login

```bash
cp packaging/aether.desktop ~/.config/autostart/
```

## Everything still works headless

The desktop app is additive. The CLI and web UI are unchanged:

```bash
aether assistant          # hands-free terminal conversation
aether do "..."           # single command
aether web --lan          # phone access over Wi-Fi
aether capabilities       # list every feature
```

## Troubleshooting

- "The desktop app needs PySide6" → `pip install 'aether[desktop]'` or `sudo pacman -S pyside6`.
- Mic button says voice not ready → install the `[stt]` extra and a Vosk model.
- No sound → install `espeak-ng` (fallback) or set an ElevenLabs key; ensure `mpv`/`ffmpeg` present.
- No models listed → `ollama serve` running and `ollama pull <model>` done.
