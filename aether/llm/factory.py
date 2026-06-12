"""Construct the LLM router from project settings."""

from __future__ import annotations

from aether.config import Settings
from aether.llm.ollama_client import OllamaClient
from aether.llm.router import ModelRouter


def build_router(settings: Settings | None = None, ollama: OllamaClient | None = None) -> ModelRouter:
    settings = settings or Settings.from_env()
    ollama = ollama or OllamaClient(model=settings.ollama_model, host=settings.ollama_host)
    return ModelRouter(settings, ollama)
