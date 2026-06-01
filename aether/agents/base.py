"""Base agent types."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AgentResult:
    agent_name: str
    status: str
    output: Any
    trust_score: float = 1.0
    processing_time: float = 0.0


class BaseAgent(ABC):
    role_name: str = "base"

    def __init__(self, llm_client: Any = None):
        self.llm = llm_client

    @abstractmethod
    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        ...

    def _llm_prompt(self, system: str, user: str) -> str:
        if not self.llm:
            return user
        return self.llm.complete(user, system=system)

    def _ok(self, output: Any, trust: float = 0.9) -> AgentResult:
        return AgentResult(
            agent_name=self.role_name,
            status="completed",
            output=output,
            trust_score=trust,
            processing_time=0.0,
        )

    def _run_timed(self, fn) -> AgentResult:
        start = time.time()
        result = fn()
        result.processing_time = time.time() - start
        return result
