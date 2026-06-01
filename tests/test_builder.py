"""Tests for multi-LLM router, app builder, commander, and smart home."""

import asyncio
import json
from pathlib import Path

from aether.brain.commander import Commander, _keyword_intent
from aether.config import Settings
from aether.integrations.smart_home import SmartHome
from aether.llm.router import ModelRouter
from aether.pipeline.app_builder import AppBuilderPipeline


class _FakeLLM:
    def list_models(self):
        return ["llama3.1:8b", "codellama:7b", "nomic-embed-text"]

    def ping(self):
        return True

    def complete(self, prompt, system="", model=None, task="general"):
        if "principal software architect" in system.lower():
            return json.dumps(
                {
                    "project_name": "demo-api",
                    "summary": "A tiny API",
                    "stack": ["python", "fastapi"],
                    "run_command": "uvicorn main:app",
                    "install_command": "pip install -r requirements.txt",
                    "files": [
                        {"path": "README.md", "purpose": "docs"},
                        {"path": "main.py", "purpose": "entry"},
                    ],
                }
            )
        if "senior engineer" in system.lower():
            return "print('hello world')"
        if "route a user request" in system.lower():
            return json.dumps({"intent": "build_app", "spec": prompt})
        return "ok reply"


def test_router_resolves_code_model():
    settings = Settings()
    router = ModelRouter(settings, _FakeLLM())
    assert "codellama" in router.resolve("code")
    assert "llama" in router.resolve("general")
    table = router.routing_table()
    assert "code" in table and "general" in table


def test_router_falls_back_when_missing():
    class Sparse(_FakeLLM):
        def list_models(self):
            return ["llama3.1:8b"]

    router = ModelRouter(Settings(), Sparse())
    # code model not installed -> falls back to general
    assert router.resolve("code") == "llama3.1:8b"


def test_app_builder_writes_files(tmp_path):
    settings = Settings(data_dir=str(tmp_path), traces_db=str(tmp_path / "t.db"), build_dir=str(tmp_path / "builds"))
    pipe = AppBuilderPipeline(_FakeLLM(), settings)
    result = asyncio.run(pipe.build("a tiny api", project_name="demo"))
    assert result["status"] == "complete"
    out = Path(result["dir"])
    assert (out / "main.py").exists()
    assert (out / "README.md").exists()
    assert (out / "BUILD_REPORT.md").exists()
    assert (out / "main.py").read_text().strip() == "print('hello world')"


def test_app_builder_blocks_path_traversal(tmp_path):
    class EvilLLM(_FakeLLM):
        def complete(self, prompt, system="", model=None, task="general"):
            if "principal software architect" in system.lower():
                return json.dumps(
                    {
                        "project_name": "evil",
                        "stack": ["python"],
                        "files": [{"path": "../../escape.txt", "purpose": "bad"}, {"path": "ok.py", "purpose": "good"}],
                    }
                )
            return "content"

    settings = Settings(data_dir=str(tmp_path), traces_db=str(tmp_path / "t.db"), build_dir=str(tmp_path / "builds"))
    pipe = AppBuilderPipeline(EvilLLM(), settings)
    result = asyncio.run(pipe.build("evil", project_name="evil"))
    assert "ok.py" in result["files"]
    assert not (tmp_path / "escape.txt").exists()


def test_commander_classifies_and_builds(tmp_path):
    settings = Settings(data_dir=str(tmp_path), traces_db=str(tmp_path / "t.db"), build_dir=str(tmp_path / "builds"))
    commander = Commander(settings, _FakeLLM())
    result = asyncio.run(commander.run("build me a tiny api backend"))
    assert result["intent"] == "build_app"
    assert result["status"] == "complete"


def test_keyword_intent_smart_home():
    assert _keyword_intent("turn off the living room lights")["intent"] == "smart_home"
    assert _keyword_intent("learn everything about robotics")["intent"] == "learn"
    assert _keyword_intent("build me a backend api")["intent"] == "build_app"


def test_smart_home_not_configured():
    home = SmartHome("", "")
    assert home.is_configured() is False
    assert home.ping() is False


def test_app_builder_approval_denied_writes_nothing(tmp_path):
    settings = Settings(data_dir=str(tmp_path), traces_db=str(tmp_path / "t.db"), build_dir=str(tmp_path / "builds"))
    pipe = AppBuilderPipeline(_FakeLLM(), settings)
    result = asyncio.run(pipe.build("a tiny api", project_name="demo", approve=lambda _plan: False))
    assert result["status"] == "cancelled"
    assert result["files"] == []
    assert not (tmp_path / "builds" / "demo" / "main.py").exists()


def test_app_builder_approval_granted(tmp_path):
    settings = Settings(data_dir=str(tmp_path), traces_db=str(tmp_path / "t.db"), build_dir=str(tmp_path / "builds"))
    pipe = AppBuilderPipeline(_FakeLLM(), settings)
    result = asyncio.run(pipe.build("a tiny api", project_name="demo", approve=lambda _plan: True))
    assert result["status"] == "complete"
    assert (tmp_path / "builds" / "demo" / "main.py").exists()


def test_autonomous_can_build_app(tmp_path):
    import json as _json

    from aether.autonomy.agent import AutonomousAgent
    from aether.autonomy.control import AutonomyControl
    from aether.autonomy.guardrails import Guardrails

    class AppPlanLLM(_FakeLLM):
        def __init__(self):
            self.calls = 0

        def complete(self, prompt, system="", model=None, task="general"):
            if "planning brain" in system.lower():
                self.calls += 1
                if self.calls == 1:
                    return _json.dumps({"action": "build_app", "spec": "a tiny api", "why": "mission"})
                return _json.dumps({"action": "stop", "why": "done"})
            if "safety reviewer" in system.lower():
                return _json.dumps({"allowed": True, "needs_approval": False, "reason": "ok"})
            return super().complete(prompt, system=system, model=model, task=task)

    settings = Settings(data_dir=str(tmp_path), traces_db=str(tmp_path / "t.db"), build_dir=str(tmp_path / "builds"))
    g = Guardrails.from_prompt("", max_iterations=3, max_runtime_minutes=1, use_llm_review=True)
    g.approval_required_actions = []  # let it run unattended for the test
    agent = AutonomousAgent(AppPlanLLM(), settings, g, control=AutonomyControl(str(tmp_path)))
    result = agent.run("build a tiny api")
    assert any(c.get("action") == "build_app" for c in result["completed"])
    assert "build_app" in g.allowed_actions
