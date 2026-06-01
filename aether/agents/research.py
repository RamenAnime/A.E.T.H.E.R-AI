from __future__ import annotations

from typing import Any, Dict

from aether.agents.base import AgentResult, BaseAgent


class ResearchAgent(BaseAgent):
    role_name = "research"

    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        def work() -> AgentResult:
            topic = input_data.get("topic", "unknown topic")
            plan = input_data.get("planner_output", {}).get("plan", "")
            system = (
                "You are a research synthesizer. Produce JSON-like plain text with sections: "
                "concepts (bullet list), facts (bullet list), summary (one paragraph)."
            )
            user = f"Topic: {topic}\nPlan:\n{plan}\nSynthesize key concepts and facts."
            text = self._llm_prompt(system, user)
            synthesis = {
                "concepts": _extract_section(text, "concepts"),
                "facts": _extract_section(text, "facts"),
                "summary": text[:2000],
            }
            return self._ok({"synthesis": synthesis, "raw": text})

        return self._run_timed(work)


def _extract_section(text: str, name: str) -> list:
    lines = []
    capture = False
    for line in text.splitlines():
        lower = line.lower()
        if name in lower:
            capture = True
            continue
        if capture and line.strip().startswith(("-", "*", "•")):
            lines.append(line.strip().lstrip("-*• ").strip())
        elif capture and line.strip() and not line.strip().startswith(("-", "*")):
            if lines:
                break
    return lines or [line.strip() for line in text.splitlines() if line.strip()][:5]
