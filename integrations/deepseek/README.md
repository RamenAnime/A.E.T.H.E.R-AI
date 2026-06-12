# DeepSeek integration for A.E.T.H.E.R.

This folder is the self-contained DeepSeek kit for the repo. Once you add
`DEEPSEEK_API_KEY` to your project `.env`, A.E.T.H.E.R. can route chat, research,
app building, and CAD generation through DeepSeek while keeping Ollama as a local
fallback.

## Quick start

1. Copy the env vars from [`env.example`](env.example) into your project root `.env`.
2. Set your key:

   ```env
   DEEPSEEK_API_KEY=sk-your-key-here
   LLM_BACKEND=hybrid
   ```

3. Verify:

   ```bash
   aether doctor
   ```

   You should see DeepSeek reported as configured and reachable.

4. Use A.E.T.H.E.R. normally:

   ```bash
   aether chat "Explain stepper motors"
   aether do "build me a FastAPI inventory API"
   aether build-app "todo backend with SQLite"
   aether web
   ```

## What gets routed where

| Task type | Hybrid mode | DeepSeek-only |
|-----------|-------------|---------------|
| Chat / persona | `deepseek-chat` | `deepseek-chat` |
| Plan / classify (`aether do`) | `deepseek-chat` | `deepseek-chat` |
| Code / build-app | `deepseek-coder` | `deepseek-coder` |
| Research / learn | `deepseek-chat` | `deepseek-chat` |
| CAD / OpenSCAD | `deepseek-chat` | `deepseek-chat` |
| Embeddings | Ollama (`nomic-embed-text`) | Ollama |

In **hybrid** mode, if DeepSeek errors or is unreachable, the router falls back
to your configured Ollama models automatically.

## Files in this folder

| File | Purpose |
|------|---------|
| [`client.py`](client.py) | OpenAI-compatible DeepSeek HTTP client |
| [`config.py`](config.py) | Env parsing helpers |
| [`env.example`](env.example) | Copy-paste env block |
| [`README.md`](README.md) | This guide |

The main app imports this client through `aether.llm` and `ModelRouter`.

## Python usage (standalone)

```python
from integrations.deepseek import DeepSeekClient

client = DeepSeekClient()
print(client.complete("Say hello in one sentence."))
```

Or through the project router:

```python
from aether.config import Settings
from aether.llm.factory import build_router

settings = Settings.from_env()
router = build_router(settings)
print(router.routing_table())
print(router.complete("Design a 3D printable bracket.", task="code"))
```

## Models

Defaults (good starting point):

- **General / research / CAD:** `deepseek-chat`
- **Code / app builder:** `deepseek-coder`

Optional reasoning model:

```env
DEEPSEEK_MODEL=deepseek-reasoner
```

`deepseek-reasoner` is slower but stronger for multi-step planning.

## Costs and privacy

- DeepSeek bills per token on your DeepSeek account (not Cursor credits).
- Prompts leave your machine when `LLM_BACKEND` is `deepseek` or `hybrid`.
- For fully local / offline use, set `LLM_BACKEND=ollama` and leave the API key unset.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `DEEPSEEK_API_KEY is not set` | Add the key to `.env` in the project root |
| Doctor shows DeepSeek unreachable | Check key, network, and `DEEPSEEK_BASE_URL` |
| Still slow on web chat stream | Streaming uses Ollama today unless cloud is selected; non-stream paths use the router |
| Want local only again | `LLM_BACKEND=ollama` |

## API reference

- DeepSeek platform: https://platform.deepseek.com
- API docs: https://api-docs.deepseek.com
