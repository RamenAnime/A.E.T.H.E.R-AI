from __future__ import annotations

from typing import Any, Dict, List

from aether.agents.base import AgentResult, BaseAgent


class ValidationAgent(BaseAgent):
    role_name = "validation"

    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        def work() -> AgentResult:
            facts: List[str] = []
            research = input_data.get("research_output", {})
            if isinstance(research, dict):
                synthesis = research.get("synthesis", research)
                facts = synthesis.get("facts", input_data.get("facts", []))
            if not facts:
                facts = input_data.get("facts", ["No facts to validate."])
            validated = []
            for fact in facts[:10]:
                score = 0.85 if len(fact) > 20 else 0.6
                validated.append({"fact": fact, "confidence": score, "validated": score >= 0.7})
            return self._ok({"validated_facts": validated, "count": len(validated)})

        return self._run_timed(work)
