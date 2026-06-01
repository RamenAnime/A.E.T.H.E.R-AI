# Install checklist

Use this after cloning the repository on a Linux machine (Manjaro, Arch, or similar).

## 1. Run the installer

From the repository root:

```bash
bash packaging/install-manjaro.sh
```

This installs system packages, creates `.venv`, installs A.E.T.H.E.R. with desktop and voice extras, downloads a small Vosk model, and registers the application menu entry.

## 2. Activate the environment

Each new terminal session:

```bash
source .venv/bin/activate
```

## 3. Pull models

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b
```

Optional: set `OLLAMA_CODE_MODEL=qwen2.5-coder:7b` in `.env`.

## 4. Configure

```bash
cp .env.example .env
```

Edit `.env` for Home Assistant, printer URLs, or voice settings as needed.

## 5. Launch

```bash
aether-app
```

Or open **A.E.T.H.E.R.** from your application menu.

## Useful commands

```bash
aether doctor
aether capabilities
aether assistant
aether do "your request"
```

Global hotkey: `Ctrl+Alt+A` (Linux, with the `desktop` extra).  
Wake word: say **"Aether, …"** after clicking Listen in the desktop app.

Full desktop setup: [MANJARO.md](MANJARO.md).
