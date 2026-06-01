from __future__ import annotations

from typing import Any, Dict

from aether.agents.base import AgentResult, BaseAgent


class KnowledgeSynthesizer(BaseAgent):
    role_name = "synthesizer"

    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        def work() -> AgentResult:
            topic = input_data.get("topic", "topic")
            validated = input_data.get("validation_output", {}).get(
                "validated_facts", input_data.get("validated_facts", [])
            )
            curriculum = input_data.get("curriculum", "")
            if not curriculum:
                ro = input_data.get("research_output", {})
                if isinstance(ro, dict):
                    curriculum = ro.get("curriculum", "")
            system = (
                "Create a graduate-level master study sheet (markdown): executive summary, "
                "key equations, design checklist, labs, and exam-style questions."
            )
            bullets = "\n".join(
                f"- {v.get('fact', v)}" if isinstance(v, dict) else f"- {v}"
                for v in validated[:15]
            )
            user = (
                f"Topic: {topic}\nValidated facts:\n{bullets}\n\n"
                f"Full curriculum excerpt:\n{str(curriculum)[:8000]}\n\n"
                "Write the master study sheet."
            )
            sheet = self._llm_prompt(system, user)
            return self._ok({"study_sheet": sheet, "format": "markdown"})

        return self._run_timed(work)
