"""End-to-end learn-then-build orchestration."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional

from aether.agents.cad import CadAgent
from aether.agents.deep_research import DeepResearchAgent
from aether.agents.engineering import EngineeringAgent
from aether.agents.memory import MemoryManager
from aether.agents.printer_ops import PrinterOpsAgent
from aether.config import Settings
from aether.harness import AgentHarness, AgentRole, Workflow
from aether.integrations.printer_factory import get_printer
from aether.integrations.printer_profiles import cad_constraints_text
from aether.knowledge.store import KnowledgeStore
from aether.traces.store import TraceStore


class MasterPipeline:
    """Learn a topic at graduate depth, then build CAD + BOM + printer handoff."""

    def __init__(
        self,
        llm: Any,
        settings: Settings,
        trace_store: Optional[TraceStore] = None,
        on_event: Optional[Callable[[str, Dict], None]] = None,
    ):
        self.llm = llm
        self.settings = settings
        self.traces = trace_store or TraceStore(settings.traces_db)
        self.knowledge = KnowledgeStore(settings.data_dir)
        self.on_event = on_event or (lambda _e, _d: None)
        self.printer = get_printer(settings)

    def _emit(self, event: str, data: Dict) -> None:
        self.on_event(event, data)
        self.traces.log(event, data.get("status", "info"), payload=str(data)[:400])

    async def learn(self, topic: str, depth: str = "graduate") -> Dict[str, Any]:
        self._emit("learn_start", {"topic": topic, "depth": depth})
        harness = AgentHarness(self.llm, trace_store=self.traces)
        harness.agent_classes[AgentRole.RESEARCH] = DeepResearchAgent

        wf = harness.create_workflow("learn_deep")
        wf.add_task(
            AgentRole.PLANNER,
            "graduate study plan",
            {"topic": topic, "depth": depth},
            task_key="plan",
        )
        wf.add_task(
            AgentRole.RESEARCH,
            "deep research passes",
            {"topic": topic, "depth": depth},
            depends_on=["plan"],
            task_key="research",
        )
        wf.add_task(
            AgentRole.VALIDATION,
            "validate",
            {"topic": topic},
            depends_on=["research"],
            task_key="validate",
        )
        wf.add_task(
            AgentRole.SYNTHESIZER,
            "master study sheet",
            {"topic": topic},
            depends_on=["validate"],
            task_key="synthesize",
        )

        result = await harness.execute_workflow(wf)
        ctx = result.get("shared_context", {})
        research = ctx.get("research_output", {})
        curriculum = research.get("curriculum", "") if isinstance(research, dict) else ""
        sheet = ctx.get("study_sheet", "") or ctx.get("synthesizer_output", {}).get("study_sheet", "")

        slug = self.knowledge.save_learned(
            topic,
            study_sheet=sheet,
            curriculum=curriculum,
            depth=depth,
            synthesis=research.get("synthesis") if isinstance(research, dict) else None,
        )

        mem = MemoryManager(self.llm, str(self.knowledge.memory_path))
        mem.execute(
            {
                "topic": topic,
                "study_sheet": sheet,
                "curriculum": curriculum,
                "depth": depth,
                "synthesizer_output": {"study_sheet": sheet},
            }
        )

        out = {
            "status": result.get("status", "complete"),
            "topic": topic,
            "slug": slug,
            "memory_file": str(self.knowledge.memory_path),
            "curriculum_chars": len(curriculum),
            "tasks_completed": result.get("tasks_completed", 0),
        }
        self._emit("learn_done", out)
        return out

    async def build(
        self,
        topic: str,
        project_description: str,
        *,
        send_to_printer: bool = False,
        auto_print: bool = False,
    ) -> Dict[str, Any]:
        self._emit("build_start", {"topic": topic, "project": project_description[:200]})

        entry = self.knowledge.get(topic)
        if not entry:
            topics = self.knowledge.list_topics()
            match = next((t for t in topics if topic.lower() in t.lower()), None)
            if match:
                topic = match
                entry = self.knowledge.get(topic)
        if not entry:
            learn_result = await self.learn(topic)
            entry = self.knowledge.get(topic)
            if not entry:
                return {"status": "failed", "error": "Could not learn topic first", "learn": learn_result}

        out_dir = self.knowledge.project_dir(topic)
        project_slug = project_description[:50].replace(" ", "_")
        build_dir = out_dir / "builds" / project_slug
        build_dir.mkdir(parents=True, exist_ok=True)

        base_input = {
            "topic": topic,
            "project_description": project_description,
            "curriculum": entry.get("curriculum", ""),
            "study_sheet": entry.get("study_sheet", ""),
            "output_dir": str(build_dir),
            "printer": self.printer,
            "auto_print": auto_print,
            "cad_constraints": cad_constraints_text(self.settings.printer_profile),
        }

        cad = await asyncio.to_thread(CadAgent(self.llm).execute, base_input)
        eng = await asyncio.to_thread(EngineeringAgent(self.llm).execute, base_input)

        stl_path = None
        if cad.output and isinstance(cad.output, dict):
            stl_path = cad.output.get("stl_path")

        printer_input = {**base_input, "stl_path": stl_path}
        pr = await asyncio.to_thread(PrinterOpsAgent(self.llm).execute, printer_input)

        print_readme = self.printer.write_slicer_readme(build_dir)

        artifacts = {
            "model_scad": str(build_dir / "model.scad"),
            "build_guide": str(build_dir / "build_guide.md"),
            "bom": str(build_dir / "bom.json"),
            "wiring": str(build_dir / "wiring.md"),
            "cad_readme": str(build_dir / "CAD_README.md"),
            "ender3_print_guide": str(print_readme),
        }
        if stl_path:
            artifacts["model_stl"] = stl_path

        self.knowledge.register_project(topic, project_description, artifacts)

        out = {
            "status": "complete",
            "topic": topic,
            "build_dir": str(build_dir),
            "artifacts": artifacts,
            "cad": cad.output,
            "engineering": eng.output,
            "printer": pr.output,
        }
        self._emit("build_done", out)
        return out
