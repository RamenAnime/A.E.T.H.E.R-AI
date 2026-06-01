"""Persona tests."""

from aether.constants import AETHER_ACRONYM_FULL, AETHER_ACRONYM_LINE
from aether.persona import acknowledgement, available_personas, boot_greeting, build_persona, time_greeting


def test_acronym_constants():
    assert "Autonomous" in AETHER_ACRONYM_FULL
    assert "Engineering" in AETHER_ACRONYM_LINE


def test_time_greeting_parts():
    p = build_persona("aether", "A.E.T.H.E.R.", "sir")
    assert time_greeting(p, "sir", hour=9).startswith("Good morning, sir")
    assert "afternoon" in time_greeting(p, "sir", hour=14)
    assert "evening" in time_greeting(p, "sir", hour=20)
    assert "How may I assist" in time_greeting(p, "sir", hour=9)


def test_aether_persona_addresses_user():
    p = build_persona("aether", "A.E.T.H.E.R.", "sir")
    assert p.id == "aether"
    assert "A.E.T.H.E.R." in p.system_prompt or "Autonomous Engineering" in p.system_prompt
    assert "sir" in p.system_prompt
    assert boot_greeting(p)
    assert acknowledgement(p)


def test_legacy_jarvis_alias_maps_to_aether():
    p = build_persona("jarvis", "A.E.T.H.E.R.", "sir")
    assert p.id == "aether"


def test_custom_name_and_title():
    p = build_persona("aether", "A.E.T.H.E.R.", "boss")
    assert "boss" in p.system_prompt
    assert any("boss" in line for line in p.boot_lines)


def test_neutral_persona():
    p = build_persona("neutral", "AETHER", "sir")
    assert p.id == "neutral"
    assert "AETHER" in p.system_prompt


def test_available_personas():
    presets = available_personas()
    assert "aether" in presets
    assert "neutral" in presets
    assert "jarvis" not in presets
