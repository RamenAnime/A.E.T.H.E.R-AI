"""Pipeline tests with fake LLM (no Ollama)."""

import asyncio
from pathlib import Path

from aether.config import Settings
from aether.pipeline.orchestrator import MasterPipeline


class _FakeLLM:
    def complete(self, prompt: str, system: str = "", model=None) -> str:
        if "OpenSCAD" in system or "OpenSCAD" in prompt:
            return "// model\ncube([10,10,10]);"
        if "robotics systems" in system.lower() or "Bill of Materials" in system:
            return "# Bill of Materials\n| part | qty | spec |\n| bolt | 4 | M3 |\n# Wiring Guide\nConnect A to B.\n"
        if "professor" in system.lower() or "graduate" in prompt.lower():
            return "## foundations\n- concept one\n- fact one\n"
        return "Plan step 1\nPlan step 2\n"


def test_learn_and_build_offline(tmp_path):
    settings = Settings(data_dir=str(tmp_path), traces_db=str(tmp_path / "t.db"))
    pipe = MasterPipeline(_FakeLLM(), settings)
    learn = asyncio.run(pipe.learn("robotic engineering"))
    assert learn["status"] == "complete"
    build = asyncio.run(
        pipe.build(
            "robotic engineering",
            "habitable robot shell CAD",
            send_to_printer=False,
        )
    )
    assert build["status"] == "complete"
    scad = Path(build["artifacts"]["model_scad"])
    assert scad.exists()
    assert Path(build["artifacts"]["build_guide"]).exists()
