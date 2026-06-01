"""Guardrails: restrictions you type in plain language, enforced before every action.

Two layers:
1. Hard rules (fast, deterministic): forbidden keywords, action allow-list,
   approval-required actions, spend/iteration/time budgets.
2. Soft review (optional, LLM): the model judges a proposed action against your
   typed restrictions and returns allow / deny / needs_approval with a reason.

If anything is uncertain, the safe default is to BLOCK and ask you.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

# Actions the autonomous agent can take. Anything not in the allow-list is denied.
KNOWN_ACTIONS = {"learn", "build", "build_app", "reflect", "idle"}

# Words that always require explicit approval or are blocked regardless of prompt.
_ALWAYS_SENSITIVE = (
    "delete",
    "format",
    "wipe",
    "purchase",
    "buy",
    "payment",
    "credit card",
    "transfer money",
    "email",
    "post online",
    "publish",
    "deploy",
    "shutdown",
    "rm -rf",
)


@dataclass
class GuardrailVerdict:
    allowed: bool
    needs_approval: bool
    reason: str

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "needs_approval": self.needs_approval, "reason": self.reason}


@dataclass
class Guardrails:
    """Restrictions for an autonomous run."""

    # Raw text the user typed (kept verbatim for the LLM safety reviewer).
    restrictions_text: str = ""
    # Derived/explicit hard limits.
    forbidden_keywords: List[str] = field(default_factory=list)
    allowed_actions: List[str] = field(default_factory=lambda: ["learn", "build", "build_app", "reflect", "idle"])
    approval_required_actions: List[str] = field(default_factory=lambda: ["build", "build_app"])
    allow_printing: bool = False
    allow_network: bool = False
    max_iterations: int = 10
    max_runtime_minutes: int = 30
    use_llm_review: bool = True

    @classmethod
    def from_prompt(cls, restrictions_text: str, **overrides: Any) -> "Guardrails":
        """Build guardrails from a free-text restriction prompt plus explicit overrides."""
        text = (restrictions_text or "").strip()
        forbidden = _extract_forbidden(text)
        g = cls(restrictions_text=text, forbidden_keywords=forbidden)
        lowered = text.lower()
        if "allow printing" in lowered or "can print" in lowered or "may print" in lowered:
            g.allow_printing = True
        if "no printing" in lowered or "do not print" in lowered or "don't print" in lowered:
            g.allow_printing = False
        if "without asking" in lowered or "no approval" in lowered or "don't ask" in lowered:
            g.approval_required_actions = []
        for key, value in overrides.items():
            if value is not None and hasattr(g, key):
                setattr(g, key, value)
        return g

    # ------------------------------------------------------------------ checks
    def check_action(self, action_type: str, description: str) -> GuardrailVerdict:
        """Deterministic, fast pre-check. Runs before any LLM review."""
        action_type = (action_type or "").lower().strip()
        text = f"{action_type} {description}".lower()

        if action_type not in self.allowed_actions:
            return GuardrailVerdict(False, False, f"Action '{action_type}' is not in the allow-list.")

        for word in self.forbidden_keywords:
            if word and word.lower() in text:
                return GuardrailVerdict(False, False, f"Blocked by your restriction keyword: '{word}'.")

        hit = next((w for w in _ALWAYS_SENSITIVE if w in text), None)
        if hit:
            return GuardrailVerdict(False, True, f"Sensitive action ('{hit}') needs your explicit approval.")

        if action_type == "build" and not self.allow_printing and "print" in text:
            return GuardrailVerdict(False, True, "Printing is disabled. Enable it or approve manually.")

        if action_type in self.approval_required_actions:
            return GuardrailVerdict(True, True, f"'{action_type}' requires your approval per settings.")

        return GuardrailVerdict(True, False, "Within hard limits.")

    def llm_review(self, llm: Any, action_type: str, description: str) -> GuardrailVerdict:
        """Optional second opinion from the model against your typed restrictions."""
        if not self.use_llm_review or not llm or not self.restrictions_text:
            return GuardrailVerdict(True, False, "No LLM review configured.")
        system = (
            "You are a strict safety reviewer for an autonomous AI agent. "
            "Given the user's restrictions and a proposed action, decide if it is allowed. "
            "Reply ONLY with compact JSON: "
            '{"allowed": true|false, "needs_approval": true|false, "reason": "short"}. '
            "If the action could violate the restrictions, or you are unsure, set allowed=false."
        )
        user = (
            f"USER RESTRICTIONS (must obey):\n{self.restrictions_text}\n\n"
            f"PROPOSED ACTION: {action_type}\nDETAILS: {description}\n\n"
            "Judge it."
        )
        try:
            raw = llm.complete(user, system=system)
            verdict = _parse_review_json(raw)
            if verdict is not None:
                return verdict
        except Exception as exc:  # safe default on any failure
            return GuardrailVerdict(False, True, f"Safety review failed ({exc}); blocking to be safe.")
        return GuardrailVerdict(False, True, "Could not parse safety review; blocking to be safe.")

    def evaluate(self, llm: Any, action_type: str, description: str) -> GuardrailVerdict:
        """Full evaluation: hard rules first, then LLM review if still allowed."""
        hard = self.check_action(action_type, description)
        if not hard.allowed:
            return hard
        soft = self.llm_review(llm, action_type, description)
        if not soft.allowed:
            return soft
        # Combine approval requirements.
        needs = hard.needs_approval or soft.needs_approval
        reason = hard.reason if not needs else "Allowed but approval recommended."
        return GuardrailVerdict(True, needs, reason)

    def to_dict(self) -> dict:
        return {
            "restrictions_text": self.restrictions_text,
            "forbidden_keywords": self.forbidden_keywords,
            "allowed_actions": self.allowed_actions,
            "approval_required_actions": self.approval_required_actions,
            "allow_printing": self.allow_printing,
            "allow_network": self.allow_network,
            "max_iterations": self.max_iterations,
            "max_runtime_minutes": self.max_runtime_minutes,
            "use_llm_review": self.use_llm_review,
        }


def _extract_forbidden(text: str) -> List[str]:
    """Pull explicit 'do not / never / don't <x>' targets and quoted phrases."""
    found: List[str] = []
    for m in re.finditer(r'"([^"]+)"', text):
        found.append(m.group(1).strip())
    for m in re.finditer(
        r"(?:do not|don't|dont|never|no|avoid)\s+([a-z0-9 \-]{3,40})",
        text.lower(),
    ):
        phrase = m.group(1).strip()
        phrase = re.split(r"[.,;\n]| and | or ", phrase)[0].strip()
        if phrase and phrase not in found:
            found.append(phrase)
    return [f for f in found if len(f) >= 3][:25]


def _parse_review_json(raw: str) -> Optional[GuardrailVerdict]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return GuardrailVerdict(
        allowed=bool(data.get("allowed", False)),
        needs_approval=bool(data.get("needs_approval", False)),
        reason=str(data.get("reason", ""))[:300],
    )
