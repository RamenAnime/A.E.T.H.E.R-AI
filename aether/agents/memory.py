from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from aether.agents.base import AgentResult, BaseAgent


class MemoryManager(BaseAgent):
    role_name = "memory"

    def __init__(self, llm_client: Any = None, store_path: str = "./data/memory.json"):
        super().__init__(llm_client)
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        def work() -> AgentResult:
            topic = input_data.get("topic", "unknown")
            sheet = input_data.get("synthesizer_output", {}).get(
                "study_sheet", input_data.get("study_sheet", "")
            )
            store = self._load()
            store[topic] = {
                "study_sheet": sheet,
                "curriculum": input_data.get("curriculum", ""),
                "depth": input_data.get("depth", "standard"),
                "metadata": {"source": "aether_workflow"},
            }
            self._save(store)
            return self._ok({"stored": True, "topic": topic, "entries": len(store)})

        return self._run_timed(work)

    def _load(self) -> Dict[str, Any]:
        if self.store_path.exists():
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        return {}

    def _save(self, data: Dict[str, Any]) -> None:
        self.store_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
