#!/usr/bin/env bash
# A.E.T.H.E.R. installer for Manjaro / Arch.
# Installs system deps, sets up a venv, installs A.E.T.H.E.R. with desktop + voice,
# and registers the app launcher so it shows up in your application menu.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "==> A.E.T.H.E.R. setup for Manjaro"
echo "    Repo: $REPO_DIR"

# 1. System packages (Qt for the GUI, audio for the mic, espeak for fallback TTS).
if command -v pacman >/dev/null 2>&1; then
  echo "==> Installing system packages (sudo)"
  sudo pacman -S --needed --noconfirm \
    python python-pip python-virtualenv \
    pyside6 \
    portaudio \
    espeak-ng \
    mpv ffmpeg || true
fi

# 2. Ollama (local model server).
if ! command -v ollama >/dev/null 2>&1; then
  echo "==> Installing Ollama"
  curl -fsSL https://ollama.com/install.sh | sh || \
    echo "    Install Ollama manually from https://ollama.com/download"
fi

# 3. Python environment.
echo "==> Creating virtual environment (.venv)"
python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
echo "==> Installing A.E.T.H.E.R. with desktop + voice extras"
pip install -e ".[desktop,stt]"

# 4. Offline voice model (Vosk small English).
MODEL_DIR="$REPO_DIR/models/vosk"
if [ ! -d "$MODEL_DIR" ]; then
  echo "==> Downloading offline speech model (Vosk small EN, ~40MB)"
  mkdir -p "$REPO_DIR/models"
  TMP_ZIP="$REPO_DIR/models/vosk.zip"
  if curl -fL -o "$TMP_ZIP" https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip; then
    (cd "$REPO_DIR/models" && unzip -q vosk.zip && mv vosk-model-small-en-us-0.15 vosk && rm -f vosk.zip)
  else
    echo "    Could not download model. Set AETHER_VOSK_MODEL later. See docs/MANJARO.md"
  fi
fi

# 5. Desktop launcher.
echo "==> Registering desktop launcher"
APPS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons"
mkdir -p "$APPS_DIR" "$ICON_DIR"
install -m644 "$REPO_DIR/packaging/aether.desktop" "$APPS_DIR/aether.desktop"
if [ -f "$REPO_DIR/aether/web/static/icons/icon-512.png" ]; then
  install -m644 "$REPO_DIR/aether/web/static/icons/icon-512.png" "$ICON_DIR/aether.png"
fi
update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo ""
echo "==> Done."
echo "    Pull a model:   ollama pull llama3.1:8b   (and a code model, e.g. qwen2.5-coder)"
echo "    Launch the app: aether-app   (or find 'A.E.T.H.E.R.' in your menu)"
echo "    The .venv must be active for the 'aether' / 'aether-app' commands."
