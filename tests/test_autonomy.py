"""Autonomy tests with a fake LLM (no Ollama needed)."""

import json

from aether.autonomy.control import AutonomyControl, ControlState
from aether.autonomy.guardrails import Guardrails
from aether.config import Settings


def test_guardrails_parse_forbidden():
    g = Guardrails.from_prompt('do not print, never spend money, avoid "weapons"')
    joined = " ".join(g.forbidden_keywords).lower()
    assert "weapons" in joined
    assert any("spend" in k or "money" in k for k in g.forbidden_keywords)


def test_guardrails_block_forbidden_keyword():
    g = Guardrails.from_prompt('do not touch "secret"', use_llm_review=False)
    v = g.check_action("learn", "study the secret files")
    assert v.allowed is False


def test_guardrails_unknown_action_blocked():
    g = Guardrails.from_prompt("", use_llm_review=False)
    v = g.check_action("hack", "do something")
    assert v.allowed is False


def test_guardrails_sensitive_needs_approval():
    g = Guardrails.from_prompt("", use_llm_review=False)
    v = g.check_action("build", "delete everything in the folder")
    assert v.allowed is False
    assert v.needs_approval is True


def test_guardrails_printing_disabled():
    g = Guardrails.from_prompt("", allow_printing=False, use_llm_review=False)
    v = g.check_action("build", "print the part on the ender 3")
    assert v.needs_approval is True


def test_control_kill_switch(tmp_path):
    c = AutonomyControl(str(tmp_path))
    assert c.should_stop() is False
    c.stop("test")
    assert c.should_stop() is True
    assert c.state == ControlState.STOPPING


def test_control_stop_file(tmp_path):
    c = AutonomyControl(str(tmp_path))
    (tmp_path / "STOP").write_text("x", encoding="utf-8")
    assert c.should_stop() is True


class _FakeLLM:
    """Plans one learn step, then stops. Approves nothing sensitive."""

    def __init__(self):
        self.calls = 0

    def complete(self, prompt: str, system: str = "", model=None) -> str:
        # Safety reviewer
        if "safety reviewer" in system.lower():
            return json.dumps({"allowed": True, "needs_approval": False, "reason": "ok"})
        # Planner
        if "planning brain" in system.lower():
            self.calls += 1
            if self.calls == 1:
                return json.dumps({"action": "learn", "topic": "robotics basics", "why": "start"})
            return json.dumps({"action": "stop", "why": "done"})
        # Deep research / synth / plan content
        if "professor" in system.lower() or "graduate" in prompt.lower():
            return "## foundations\n- concept\n- fact\n"
        return "step one\nstep two\n"


def test_autonomous_run_stops_cleanly(tmp_path):
    from aether.autonomy.agent import AutonomousAgent

    settings = Settings(data_dir=str(tmp_path), traces_db=str(tmp_path / "t.db"))
    g = Guardrails.from_prompt("stay on robotics", max_iterations=4, max_runtime_minutes=1, use_llm_review=True)
    agent = AutonomousAgent(_FakeLLM(), settings, g, control=AutonomyControl(str(tmp_path)))
    result = agent.run("learn robotics")
    assert result["iterations"] >= 1
    assert result["state"] in ("stopped", "idle")
    # It should have learned at least one topic.
    assert any(c.get("action") == "learn" for c in result["completed"])
