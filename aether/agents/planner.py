from __future__ import annotations

from typing import Any, Dict

from aether.agents.base import AgentResult, BaseAgent


class PlannerAgent(BaseAgent):
    role_name = "planner"

    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        def work() -> AgentResult:
            topic = input_data.get("topic") or input_data.get("planner_output", {}).get("topic", "general")
            concepts = input_data.get("concepts", [])
            system = (
                "You are a learning planner. Return a short numbered study plan (5-7 steps) "
                "as plain text."
            )
            user = f"Topic: {topic}\nKnown concepts: {concepts}\nCreate a study plan."
            plan_text = self._llm_prompt(system, user)
            return self._ok(
                {
                    "topic": topic,
                    "plan": plan_text,
                    "steps": [line.strip() for line in plan_text.splitlines() if line.strip()],
                }
            )

        return self._run_timed(work)
