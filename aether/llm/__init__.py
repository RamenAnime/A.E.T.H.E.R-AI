from aether.llm.factory import build_router
from aether.llm.ollama_client import OllamaClient
from aether.llm.router import ModelRouter

__all__ = ["OllamaClient", "ModelRouter", "build_router"]


def __getattr__(name: str):
    if name in ("AirLLMManager", "OllamaAirLLMBridge", "QuantizationLevel"):
        from aether.llm import airllm_manager as m

        return getattr(m, name)
    raise AttributeError(name)
