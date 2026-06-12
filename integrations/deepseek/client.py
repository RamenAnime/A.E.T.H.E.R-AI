"""OpenAI-compatible DeepSeek chat client for A.E.T.H.E.R.

DeepSeek exposes an OpenAI-style /v1/chat/completions endpoint. This client
implements the same surface as aether.llm.ollama_client.OllamaClient so it can
drop into ModelRouter without changing agents.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Generator, List, Optional


class DeepSeekError(RuntimeError):
    """Raised when the DeepSeek API returns an error response."""


class DeepSeekClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        code_model: Optional[str] = None,
        timeout: float = 120.0,
    ):
        self.api_key = (api_key or os.getenv("DEEPSEEK_API_KEY", "")).strip()
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.code_model = code_model or os.getenv("DEEPSEEK_CODE_MODEL", "deepseek-coder")
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        data = self._post("/v1/chat/completions", payload)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError(f"Unexpected DeepSeek response: {data!r}") from exc

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        for line in self._post_stream("/v1/chat/completions", payload):
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                parsed = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            delta = parsed.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if delta:
                yield delta

    def complete(self, prompt: str, system: str = "", model: Optional[str] = None) -> str:
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, model=model)

    def ping(self) -> bool:
        if not self.is_configured():
            return False
        try:
            self.complete("Reply with exactly: OK", system="You are a health check. One word only.")
            return True
        except Exception:
            return False

    def list_models(self) -> List[str]:
        seen: List[str] = []
        for name in (self.model, self.code_model, "deepseek-reasoner"):
            if name and name not in seen:
                seen.append(name)
        return seen

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise DeepSeekError("DEEPSEEK_API_KEY is not set")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DeepSeekError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise DeepSeekError(f"DeepSeek connection failed: {exc}") from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DeepSeekError(f"DeepSeek returned non-JSON: {raw[:500]}") from exc

    def _post_stream(self, path: str, payload: Dict[str, Any]) -> Generator[str, None, None]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                while True:
                    line = response.readline()
                    if not line:
                        break
                    yield line.decode("utf-8", errors="replace").rstrip("\r\n")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DeepSeekError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise DeepSeekError(f"DeepSeek connection failed: {exc}") from exc
