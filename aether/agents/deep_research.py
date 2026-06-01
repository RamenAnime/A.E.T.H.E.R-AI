"""Graduate-depth multi-pass research agent."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from aether.agents.base import AgentResult, BaseAgent

GRADUATE_SYSTEM = """You are a graduate-level engineering instructor and researcher.
Produce rigorous, structured technical content suitable for advanced study.
Include: theory, equations where relevant, design tradeoffs, safety constraints,
industry standards, software tools, and practical labs. Be thorough but organized."""

JAPANESE_SYSTEM = """You are a professor of Japanese language and linguistics at graduate level.
Produce rigorous, structured content for deep mastery of Japanese (not tourist phrases).
Include: accurate script usage, grammar with examples in Japanese + romaji + English gloss,
common pitfalls for English speakers, JLPT level tags where relevant, and practice drills.
Use Japanese characters in examples. Be thorough and organized."""

JAPANESE_PASSES: List[Tuple[str, str]] = [
    ("writing_systems", "Hiragana, katakana, kanji structure, radicals, stroke order, on/kun readings"),
    ("grammar_core", "Particles, verb/adjective conjugation, tense, aspect, basic keigo"),
    ("grammar_advanced", "Conditionals, passive/causative, honorific/humble forms, written vs spoken"),
    ("vocabulary", "Core word families, counters, compounds, pitch accent, collocation"),
    ("communication", "Conversation patterns, listening strategies, pragmatics, dialect notes"),
    ("culture_mastery", "Culture in language, media immersion, business/formal Japanese, JLPT N1 depth"),
]

_JA_TOPIC = re.compile(
    r"japanese|japan|nihongo|hiragana|katakana|kanji|jlpt|日本語|日本",
    re.IGNORECASE,
)


class DeepResearchAgent(BaseAgent):
    role_name = "deep_research"

    PASSES = [
        ("foundations", "Core theory, math, and first principles"),
        ("methods", "Methods, tools, workflows (CAD, simulation, fabrication)"),
        ("applications", "Real-world systems, case studies, failure modes"),
        ("frontier", "Current research, open problems, best practices"),
    ]

    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        def work() -> AgentResult:
            topic = input_data.get("topic", "unknown")
            plan = input_data.get("planner_output", {}).get("plan", "")
            japanese = _JA_TOPIC.search(topic) is not None
            passes = JAPANESE_PASSES if japanese else self.PASSES
            system = JAPANESE_SYSTEM if japanese else GRADUATE_SYSTEM
            depth = "graduate Japanese / JLPT N1 depth" if japanese else "graduate study level"

            sections: List[Dict[str, str]] = []
            all_concepts: List[str] = []
            all_facts: List[str] = []

            for pass_id, focus in passes:
                user = (
                    f"Topic: {topic}\nDepth: {depth}\n"
                    f"Pass: {pass_id}: {focus}\nPlan context:\n{plan[:3000]}\n\n"
                    "Write 800-1200 words with clear headings."
                )
                text = self._llm_prompt(system, user)
                sections.append({"pass": pass_id, "focus": focus, "content": text})
                all_concepts.extend(_bullets(text, "concept"))
                all_facts.extend(_bullets(text))

            curriculum = "\n\n".join(
                f"## {s['pass'].replace('_', ' ').title()}: {s['focus']}\n\n{s['content']}" for s in sections
            )
            return self._ok(
                {
                    "synthesis": {
                        "concepts": list(dict.fromkeys(all_concepts))[:40],
                        "facts": list(dict.fromkeys(all_facts))[:60],
                        "summary": sections[-1]["content"][:1500] if sections else "",
                        "track": "japanese" if japanese else "general",
                    },
                    "curriculum": curriculum,
                    "sections": sections,
                },
                trust=0.92,
            )

        return self._run_timed(work)


def _bullets(text: str, keyword: str = "") -> List[str]:
    lines = []
    for line in text.splitlines():
        t = line.strip()
        if t.startswith(("-", "*", "•")) and len(t) > 3:
            lines.append(t.lstrip("-*• ").strip())
        elif keyword and keyword in line.lower() and ":" in line:
            lines.append(t.split(":", 1)[-1].strip())
    return lines[:15]
