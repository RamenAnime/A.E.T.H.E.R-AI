"""Ollama chat client used by agents and the CLI."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


class OllamaClient:
    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        if self.host:
            os.environ["OLLAMA_HOST"] = self.host

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        import ollama

        response = ollama.chat(
            model=model or self.model,
            messages=messages,
            options={"temperature": temperature},
        )
        return response["message"]["content"]

    def complete(self, prompt: str, system: str = "", model: Optional[str] = None) -> str:
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, model=model)

    def ping(self) -> bool:
        try:
            import ollama

            ollama.list()
            return True
        except Exception:
            return False

    def list_models(self) -> List[str]:
        try:
            import ollama

            data = ollama.list()
            models = data.get("models", [])
            return [m.get("name", m.get("model", "")) for m in models]
        except Exception:
            return []
