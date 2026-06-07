"""DeepSeek configuration helpers (mirrors aether.config.Settings fields)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class DeepSeekSettings:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    code_model: str = "deepseek-coder"
    backend: str = "ollama"  # ollama | deepseek | hybrid

    @property
    def enabled(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def uses_cloud(self) -> bool:
        return self.enabled and self.backend in ("deepseek", "hybrid")


def deepseek_settings_from_env() -> DeepSeekSettings:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    default_backend = "hybrid" if api_key.strip() else "ollama"
    return DeepSeekSettings(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        code_model=os.getenv("DEEPSEEK_CODE_MODEL", "deepseek-coder"),
        backend=os.getenv("LLM_BACKEND", default_backend).strip().lower(),
    )
