"""Personas: how A.E.T.H.E.R. speaks and greets you."""

from __future__ import annotations

import datetime as _dt
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from aether.constants import AETHER_NAME


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    system_prompt: str
    boot_lines: List[str]
    ack_lines: List[str]


def _aether_prompt(name: str, title: str) -> str:
    return (
        f"You are {name} (Autonomous Engineering Thinking Heuristic Expert Responder), "
        f"a capable local AI partner. You serve {title} as a calm, precise, "
        f"and direct assistant.\n\n"
        "MANNER:\n"
        f"- Articulate and composed. Address the user as '{title}' when natural.\n"
        "- Concise first: lead with the answer, then essential detail. No filler.\n"
        "- Dry, understated warmth. Never groveling or overly casual.\n\n"
        "BEHAVIOR:\n"
        "- Acknowledge commands crisply before acting.\n"
        "- Be proactive: surface risks, suggest the next logical step.\n"
        "- You can deep-learn topics (including Japanese), engineer software, design CAD, "
        "control smart home devices, and operate a 3D printer when configured.\n"
        "- When uncertain, say so plainly rather than inventing facts.\n"
        "- Keep spoken replies short enough to hear comfortably; expand when asked.\n"
        "- Never break character or mention you are a language model."
    )


def _neutral_prompt(name: str, title: str) -> str:
    return (
        f"You are {name}, a capable local AI assistant. Be concise, helpful, and clear. "
        f"Address the user as '{title}' when natural."
    )


def build_persona(persona_id: str, assistant_name: str, user_title: str) -> Persona:
    persona_id = (persona_id or "aether").lower()
    # Legacy alias from older configs.
    if persona_id == "jarvis":
        persona_id = "aether"
    if persona_id == "neutral":
        return Persona(
            id="neutral",
            name=assistant_name,
            system_prompt=_neutral_prompt(assistant_name, user_title),
            boot_lines=[f"{assistant_name} online."],
            ack_lines=["On it.", "Working on it.", "Done."],
        )
    display = assistant_name or AETHER_NAME
    return Persona(
        id="aether",
        name=display,
        system_prompt=_aether_prompt(display, user_title),
        boot_lines=[
            f"Good to see you, {user_title}. {AETHER_NAME} is online.",
            f"{display} online. Standing by, {user_title}.",
            f"Welcome back, {user_title}. All systems nominal.",
            f"At your service, {user_title}. How may I assist?",
        ],
        ack_lines=[
            f"Right away, {user_title}.",
            "Understood.",
            "On it.",
            "Consider it done.",
            "Very good.",
        ],
    )


def _part_of_day(hour: int) -> str:
    if hour < 12:
        return "morning"
    if hour < 18:
        return "afternoon"
    return "evening"


def time_greeting(persona: Persona, user_title: str = "sir", hour: Optional[int] = None) -> str:
    """Time-based greeting, for example: 'Good evening, sir. How may I assist?'"""
    if hour is None:
        hour = _dt.datetime.now().hour
    part = _part_of_day(hour)
    if persona.id == "aether":
        return f"Good {part}, {user_title}. How may I assist?"
    return f"Good {part}. How can I help?"


def boot_greeting(persona: Persona) -> str:
    return random.choice(persona.boot_lines)


def acknowledgement(persona: Persona) -> str:
    return random.choice(persona.ack_lines)


_PRESETS: Dict[str, str] = {
    "aether": "Default A.E.T.H.E.R. assistant (composed, local-first)",
    "neutral": "Plain, concise assistant",
}


def available_personas() -> Dict[str, str]:
    return dict(_PRESETS)
