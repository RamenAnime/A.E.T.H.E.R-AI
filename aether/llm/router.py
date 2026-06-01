"""Multi-model router: uses all your local LLMs, picking the best one per task.

A.E.T.H.E.R. is local-first. This router sits in front of:
  - Ollama general model   (planning, chat, reasoning)
  - Ollama code model       (writing code / configs / infrastructure)
  - Ollama embedding model  (vectors / search)
  - AirLLM quantized model  (optional, huge-context / large models on small VRAM)

It exposes the same .complete()/.chat() surface as OllamaClient, plus a
`task` hint so agents can ask for the right brain without knowing model names.
If a preferred model is not installed, it transparently falls back.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from aether.config import Settings
from aether.llm.ollama_client import OllamaClient

# Task -> which configured model slot to prefer.
_TASK_SLOTS = {
    "general": "general",
    "chat": "general",
    "plan": "general",
    "reason": "general",
    "research": "general",
    "code": "code",
    "engineer": "code",
    "infra": "code",
    "config": "code",
    "long": "long",
    "huge": "long",
    "embed": "embed",
}


class ModelRouter:
    """Routes each request to the most suitable locally-available model."""

    def __init__(self, settings: Optional[Settings] = None, ollama: Optional[OllamaClient] = None):
        self.settings = settings or Settings.from_env()
        self.ollama = ollama or OllamaClient(
            model=self.settings.ollama_model, host=self.settings.ollama_host
        )
        self.slots = {
            "general": self.settings.ollama_model,
            "code": self.settings.ollama_code_model,
            "embed": self.settings.ollama_embed_model,
            "long": self.settings.ollama_model,
        }
        self._available: Optional[List[str]] = None
        self._airllm = None  # lazy

    # ---------------------------------------------------------------- helpers
    def available_models(self, refresh: bool = False) -> List[str]:
        if self._available is None or refresh:
            self._available = self.ollama.list_models()
        return self._available

    def _has(self, model: str) -> bool:
        if not model:
            return False
        names = self.available_models()
        if not names:
            return True  # can't verify; assume present so we still try
        base = model.split(":")[0]
        return any(model == n or n.split(":")[0] == base for n in names)

    def resolve(self, task: str = "general") -> str:
        """Return the concrete model name to use for a task, with fallback."""
        slot = _TASK_SLOTS.get((task or "general").lower(), "general")
        preferred = self.slots.get(slot, self.settings.ollama_model)
        if self._has(preferred):
            return preferred
        # Fall back to general, then to whatever is installed.
        if self._has(self.settings.ollama_model):
            return self.settings.ollama_model
        names = self.available_models()
        return names[0] if names else self.settings.ollama_model

    def uses_airllm(self, task: str) -> bool:
        return (
            self.settings.use_airllm
            and _TASK_SLOTS.get((task or "general").lower()) == "long"
        )

    # ------------------------------------------------------------------ calls
    def complete(self, prompt: str, system: str = "", task: str = "general", model: Optional[str] = None) -> str:
        if model is None and self.uses_airllm(task):
            air = self._get_airllm()
            if air is not None:
                try:
                    return air.complete(prompt, system=system)
                except Exception:
                    pass  # fall through to Ollama
        chosen = model or self.resolve(task)
        return self.ollama.complete(prompt, system=system, model=chosen)

    def chat(self, messages: List[Dict[str, str]], task: str = "general", model: Optional[str] = None, temperature: float = 0.7) -> str:
        chosen = model or self.resolve(task)
        return self.ollama.chat(messages, model=chosen, temperature=temperature)

    def ping(self) -> bool:
        return self.ollama.ping()

    def list_models(self) -> List[str]:
        return self.available_models(refresh=True)

    def _get_airllm(self):
        if self._airllm is not None:
            return self._airllm
        try:
            from aether.llm import AirLLMManager  # lazy, optional torch

            self._airllm = AirLLMManager(
                quantization=self.settings.airllm_quantization,
                cache_dir=self.settings.airllm_cache_dir,
            )
        except Exception:
            self._airllm = None
        return self._airllm

    def routing_table(self) -> Dict[str, str]:
        """Human-readable view of which model handles which task."""
        seen: Dict[str, str] = {}
        for task in ("general", "code", "embed", "long"):
            seen[task] = self.resolve(task)
        if self.settings.use_airllm:
            seen["long"] = f"AirLLM({self.settings.airllm_quantization}) -> {seen['long']}"
        return seen
