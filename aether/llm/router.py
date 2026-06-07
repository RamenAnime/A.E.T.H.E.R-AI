"""Multi-model router: local Ollama plus optional DeepSeek cloud.

A.E.T.H.E.R. is local-first. This router sits in front of:
  - Ollama general model   (planning, chat, reasoning)
  - Ollama code model       (writing code / configs / infrastructure)
  - Ollama embedding model  (vectors / search)
  - AirLLM quantized model  (optional, huge-context / large models on small VRAM)
  - DeepSeek cloud models   (optional, when DEEPSEEK_API_KEY is set)

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

_CLOUD_TASKS = frozenset(
    {
        "general",
        "chat",
        "plan",
        "reason",
        "research",
        "code",
        "engineer",
        "infra",
        "config",
        "long",
        "huge",
    }
)


class ModelRouter:
    """Routes each request to the most suitable local or cloud model."""

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
        self._deepseek = None  # lazy

    # ---------------------------------------------------------------- helpers
    def available_models(self, refresh: bool = False) -> List[str]:
        if self._available is None or refresh:
            names = self.ollama.list_models()
            if self._cloud_enabled():
                for name in self._get_deepseek().list_models():
                    if name not in names:
                        names.append(name)
            self._available = names
        return self._available

    def _cloud_enabled(self) -> bool:
        return bool(self.settings.deepseek_api_key.strip()) and self.settings.llm_backend in (
            "deepseek",
            "hybrid",
        )

    def _use_cloud(self, task: str) -> bool:
        if not self._cloud_enabled():
            return False
        if self.settings.llm_backend == "deepseek":
            return (task or "general").lower() != "embed"
        return (task or "general").lower() in _CLOUD_TASKS

    def _cloud_model_for_task(self, task: str) -> str:
        client = self._get_deepseek()
        slot = _TASK_SLOTS.get((task or "general").lower(), "general")
        if slot == "code":
            return client.code_model
        return client.model

    def _get_deepseek(self):
        if self._deepseek is not None:
            return self._deepseek
        from integrations.deepseek.client import DeepSeekClient

        self._deepseek = DeepSeekClient(
            api_key=self.settings.deepseek_api_key,
            base_url=self.settings.deepseek_base_url,
            model=self.settings.deepseek_model,
            code_model=self.settings.deepseek_code_model,
        )
        return self._deepseek

    def _has(self, model: str) -> bool:
        if not model:
            return False
        if self._cloud_enabled() and model in self._get_deepseek().list_models():
            return True
        names = self.ollama.list_models()
        if not names:
            return True  # can't verify; assume present so we still try
        base = model.split(":")[0]
        return any(model == n or n.split(":")[0] == base for n in names)

    def resolve(self, task: str = "general") -> str:
        """Return the concrete model name to use for a task, with fallback."""
        if self._use_cloud(task):
            return self._cloud_model_for_task(task)
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
            and not self._use_cloud(task)
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
        if model is None and self._use_cloud(task):
            chosen = self._cloud_model_for_task(task)
            try:
                return self._get_deepseek().complete(prompt, system=system, model=chosen)
            except Exception:
                if self.settings.llm_backend != "hybrid":
                    raise
        chosen = model or self.resolve(task)
        if self._cloud_enabled() and chosen in self._get_deepseek().list_models():
            try:
                return self._get_deepseek().complete(prompt, system=system, model=chosen)
            except Exception:
                if self.settings.llm_backend != "hybrid":
                    raise
        return self.ollama.complete(prompt, system=system, model=chosen)

    def chat(
        self,
        messages: List[Dict[str, str]],
        task: str = "general",
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        if model is None and self._use_cloud(task):
            chosen = self._cloud_model_for_task(task)
            try:
                return self._get_deepseek().chat(messages, model=chosen, temperature=temperature)
            except Exception:
                if self.settings.llm_backend != "hybrid":
                    raise
        chosen = model or self.resolve(task)
        if self._cloud_enabled() and chosen in self._get_deepseek().list_models():
            try:
                return self._get_deepseek().chat(messages, model=chosen, temperature=temperature)
            except Exception:
                if self.settings.llm_backend != "hybrid":
                    raise
        return self.ollama.chat(messages, model=chosen, temperature=temperature)

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        task: str = "general",
        model: Optional[str] = None,
        temperature: float = 0.7,
    ):
        chosen = model or self.resolve(task)
        if self._cloud_enabled() and chosen in self._get_deepseek().list_models():
            return self._get_deepseek().chat_stream(messages, model=chosen, temperature=temperature)
        raise NotImplementedError("Streaming is only available for configured cloud models or Ollama directly.")

    def ping(self) -> bool:
        cloud_ok = False
        if self._cloud_enabled():
            try:
                cloud_ok = self._get_deepseek().ping()
            except Exception:
                cloud_ok = False
        local_ok = self.ollama.ping()
        if self.settings.llm_backend == "deepseek":
            return cloud_ok
        if self.settings.llm_backend == "hybrid":
            return cloud_ok or local_ok
        return local_ok

    def list_models(self) -> List[str]:
        return self.available_models(refresh=True)

    def cloud_model_names(self) -> List[str]:
        if not self._cloud_enabled():
            return []
        return self._get_deepseek().list_models()

    def supports_cloud_stream(self, model: str) -> bool:
        return model in self.cloud_model_names()

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
        if self.settings.use_airllm and not self._use_cloud("long"):
            seen["long"] = f"AirLLM({self.settings.airllm_quantization}) -> {seen['long']}"
        seen["backend"] = self.settings.llm_backend
        if self._cloud_enabled():
            seen["cloud"] = f"DeepSeek ({self.settings.deepseek_base_url})"
        return seen
