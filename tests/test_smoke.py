"""Smoke tests (no Ollama required)."""

from aether.config import Settings
from aether.harness import AgentHarness, AgentRole, Workflow
from aether.integrations.permissions import PermissionManager
from aether.traces.store import TraceStore
from aether.workflow.loader import load_workflow_toml
from pathlib import Path


def test_settings_load():
    s = Settings.from_env()
    assert s.ollama_model


def test_workflow_toml_load():
    path = Path(__file__).resolve().parents[1] / "workflows" / "learn_topic.toml"
    graph = load_workflow_toml(path)
    assert len(graph.nodes) == 5
    valid, _ = graph.validate()
    assert valid


def test_trace_store(tmp_path):
    db = tmp_path / "t.db"
    store = TraceStore(str(db))
    tid = store.log("test", "ok", payload="hello")
    assert tid
    assert store.recent(1)


def test_permission_remember(tmp_path):
    pm = PermissionManager(str(tmp_path / "p.json"), require=False)
    pm.remember("file_read:/tmp", "always_approve")
    assert pm.check("file_read:/tmp") == "always_approve"


class _FakeLLM:
    def complete(self, prompt: str, system: str = "", model=None) -> str:
        return f"fake response for: {prompt[:40]}"


def test_harness_workflow_offline(tmp_path):
    harness = AgentHarness(_FakeLLM(), trace_store=TraceStore(str(tmp_path / "h.db")))
    wf = harness.create_workflow("test")
    wf.add_task(AgentRole.PLANNER, "plan", {"topic": "test"}, task_key="plan")
    wf.add_task(AgentRole.VALIDATION, "validate", {"topic": "test"}, depends_on=["plan"])
    import asyncio

    result = asyncio.run(harness.execute_workflow(wf))
    assert result["tasks_completed"] >= 1
