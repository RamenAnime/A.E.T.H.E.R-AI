# A.E.T.H.E.R.

**Autonomous · Engineering · Thinking · Heuristic · Expert · Responder**

A local-first assistant for chat, research, software generation, CAD workflows, smart home control, and optional 3D printer integration. Models run through [Ollama](https://ollama.com/) on your machine. No cloud LLM is required.

[![CI](https://github.com/RamenAnime/A.E.T.H.E.R-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/RamenAnime/A.E.T.H.E.R-AI/actions/workflows/ci.yml)

## What it does

| Area | Summary |
|------|---------|
| Chat | Single-turn and session chat with optional voice output |
| Research | Multi-pass learning pipeline with structured notes stored locally |
| Build | Generate application code from a spec, with approval before writes |
| CAD | OpenSCAD models, BOM, wiring guides, optional printer upload |
| Smart home | Home Assistant device control when configured |
| Autonomy | Bounded self-directed loops with typed restrictions and a kill switch |

Interfaces: CLI, web UI (FastAPI), and optional native desktop app (PySide6 on Linux).

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/download) with at least one chat model (for example `llama3.1:8b`)
- Optional: code model (`qwen2.5-coder:7b`), ElevenLabs key for cloud TTS, Home Assistant token, OctoPrint or Moonraker for printers

## Install

```bash
git clone https://github.com/RamenAnime/A.E.T.H.E.R-AI.git
cd aether
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -e .
cp .env.example .env
ollama pull llama3.1:8b
aether doctor
```

Optional feature groups:

```bash
pip install -e ".[desktop,stt,airllm,vector]"
```

- `desktop`: PySide6 app and global hotkey (`Ctrl+Alt+A` on Linux)
- `stt`: offline speech input (Vosk)
- `airllm`: quantized models for large contexts
- `vector`: ChromaDB (reserved for future RAG)

### Manjaro / Arch (native desktop)

```bash
bash packaging/install-manjaro.sh
aether-app
```

See [docs/INSTALL.md](docs/INSTALL.md) and [docs/MANJARO.md](docs/MANJARO.md).

## Quick usage

```bash
aether chat "Explain Kubernetes in two paragraphs"
aether do "build a FastAPI todo API with SQLite"
aether learn "robotic engineering"
aether build-app "inventory API with JWT auth" --name inventory-api
aether web                    # http://127.0.0.1:8787
aether capabilities           # list configured features
```

Voice and continuous session:

```bash
aether assistant              # terminal session with greetings and TTS
aether-app                    # desktop app with offline wake word (Linux + stt extra)
```

Autonomous mode (review restrictions before use):

```bash
aether auto "Study robotics, then draft a printable frame design" \
  --restrictions "no printing without approval, no purchases, no file deletes" \
  --max-iters 8 --minutes 20
aether stop                   # kill switch (also: touch data/STOP)
```

## Configuration

Copy `.env.example` to `.env`. Common settings:

```env
OLLAMA_MODEL=llama3.1:8b
OLLAMA_CODE_MODEL=qwen2.5-coder:7b
AETHER_ASSISTANT_NAME=A.E.T.H.E.R.
AETHER_WAKE_WORD=aether
HOMEASSISTANT_URL=http://homeassistant.local:8123
HOMEASSISTANT_TOKEN=
```

Run `aether doctor` to verify Ollama, models, and integrations.

## Project layout

```
aether/
  aether/           Python package
    agents/         Research, CAD, software, printer agents
    autonomy/       Guardrails, kill switch, autonomous loop
    brain/          Natural-language command routing
    desktop/        PySide6 native UI
    integrations/   Home Assistant, OctoPrint, Moonraker
    llm/            Ollama and optional AirLLM routing
    pipeline/       Learn/build and app generation
    voice/          TTS and offline STT helpers
    web/            FastAPI server and static UI
  docs/             Platform and hardware guides
  packaging/        Linux install script and .desktop file
  tests/
```

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md) - install checklist (Linux)
- [docs/MANJARO.md](docs/MANJARO.md) - desktop app, Vosk, tray, hotkey
- [docs/ANDROID.md](docs/ANDROID.md) - PWA on phone over LAN
- [docs/ENDER3_V3.md](docs/ENDER3_V3.md) - Ender 3 V3 printer setup

## Safety

Autonomous mode and code generation can modify files or trigger external systems. Defaults require approval for sensitive actions. Generated CAD, BOM, and wiring output is a starting point only: review with qualified people before building or powering hardware.

LLM output can be wrong. Do not treat it as certified engineering, legal, or medical advice.

## Development

```bash
pip install -e .
pytest tests/ -q
```

CI runs the same test suite on push and pull requests (see `.github/workflows/ci.yml`).

## License

MIT. See [LICENSE](LICENSE).
