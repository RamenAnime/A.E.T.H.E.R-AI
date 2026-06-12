"""Tests for DeepSeek client and hybrid ModelRouter routing."""

import json
from unittest.mock import MagicMock, patch

from aether.config import Settings
from aether.llm.router import ModelRouter
from integrations.deepseek.client import DeepSeekClient, DeepSeekError


def _fake_response(payload: dict, status: int = 200):
    body = json.dumps(payload).encode("utf-8")

    class _Resp:
        def __init__(self):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    if status != 200:
        import urllib.error

        err = urllib.error.HTTPError("https://api.deepseek.com/v1/chat/completions", status, "err", {}, None)
        err.read = lambda: body
        raise err
    return _Resp()


def test_deepseek_client_complete():
    client = DeepSeekClient(api_key="sk-test")
    payload = {"choices": [{"message": {"content": "hello"}}]}
    with patch("urllib.request.urlopen", return_value=_fake_response(payload)):
        assert client.complete("hi") == "hello"


def test_deepseek_client_requires_key():
    client = DeepSeekClient(api_key="")
    try:
        client.complete("hi")
        assert False, "expected DeepSeekError"
    except DeepSeekError:
        pass


def test_router_uses_cloud_models_when_configured():
    settings = Settings(
        deepseek_api_key="sk-test",
        llm_backend="hybrid",
        deepseek_model="deepseek-chat",
        deepseek_code_model="deepseek-coder",
    )

    class _FakeOllama:
        def list_models(self):
            return ["llama3.1:8b"]

        def ping(self):
            return True

        def complete(self, prompt, system="", model=None):
            return "local"

        def chat(self, messages, model=None, temperature=0.7):
            return "local"

    router = ModelRouter(settings, _FakeOllama())
    assert router.resolve("general") == "deepseek-chat"
    assert router.resolve("code") == "deepseek-coder"

    with patch.object(DeepSeekClient, "complete", return_value="cloud") as mocked:
        assert router.complete("build api", task="code") == "cloud"
        mocked.assert_called_once()


def test_router_hybrid_falls_back_to_ollama():
    settings = Settings(deepseek_api_key="sk-test", llm_backend="hybrid")

    class _FakeOllama:
        def list_models(self):
            return ["llama3.1:8b"]

        def ping(self):
            return True

        def complete(self, prompt, system="", model=None):
            return "local-fallback"

        def chat(self, messages, model=None, temperature=0.7):
            return "local-fallback"

    router = ModelRouter(settings, _FakeOllama())
    with patch.object(DeepSeekClient, "complete", side_effect=DeepSeekError("down")):
        assert router.complete("hello", task="general") == "local-fallback"
