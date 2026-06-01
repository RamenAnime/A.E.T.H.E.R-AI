"""Multi-agent task harness for A.E.T.H.E.R."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from aether.agents import (
    KnowledgeSynthesizer,
    MemoryManager,
    PlannerAgent,
    ResearchAgent,
    ValidationAgent,
)
from aether.agents.base import AgentResult
from aether.traces.store import TraceStore


class AgentRole(Enum):
    PLANNER = "planner"
    RESEARCH = "research"
    VALIDATION = "validation"
    SYNTHESIZER = "synthesizer"
    MEMORY = "memory"


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Task:
    id: str
    description: str
    role: AgentRole
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    retry_count: int = 0


@dataclass
class AgentInstance:
    id: str
    role: AgentRole
    name: str
    status: str = "idle"
    current_task: Optional[str] = None
    completed_tasks: int = 0
    failed_tasks: int = 0


class AgentHarness:
    def __init__(self, llm_client, voice_engine=None, trace_store: Optional[TraceStore] = None):
        self.llm = llm_client
        self.voice = voice_engine
        self.traces = trace_store or TraceStore()
        self.agents: Dict[str, AgentInstance] = {}
        self.agent_classes = {
            AgentRole.PLANNER: PlannerAgent,
            AgentRole.RESEARCH: ResearchAgent,
            AgentRole.VALIDATION: ValidationAgent,
            AgentRole.SYNTHESIZER: KnowledgeSynthesizer,
            AgentRole.MEMORY: MemoryManager,
        }
        self.tasks: Dict[str, Task] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.shared_context: Dict[str, Any] = {}
        self.callbacks: Dict[str, List[Callable]] = {}
        self.is_running = False
        self._worker_tasks: List[asyncio.Task] = []
        self._register_agents()

    def _register_agents(self) -> None:
        for role in self.agent_classes:
            agent_id = f"{role.value}_001"
            self.agents[agent_id] = AgentInstance(
                id=agent_id, role=role, name=f"{role.value.title()}Agent"
            )

    def create_workflow(self, name: str) -> "Workflow":
        return Workflow(name, self)

    async def execute_workflow(self, workflow: "Workflow") -> Dict[str, Any]:
        self._speak(f"Starting workflow {workflow.name}.")
        self.is_running = True
        worker_count = min(4, max(1, len(self.agents)))
        self._worker_tasks = [asyncio.create_task(self._worker_loop()) for _ in range(worker_count)]

        for task in workflow.tasks:
            self.tasks[task.id] = task
            await self.task_queue.put(task)

        while self._has_pending(workflow):
            await asyncio.sleep(0.3)
            self._notify("progress", self._progress(workflow))

        self.is_running = False
        for wt in self._worker_tasks:
            wt.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()

        results = {t.id: t.output_data for t in workflow.tasks if t.output_data}
        failed = len([t for t in workflow.tasks if t.status == TaskStatus.FAILED])
        self._speak(f"Workflow {workflow.name} finished.")
        return {
            "workflow": workflow.name,
            "status": "failed" if failed else "complete",
            "tasks_completed": len([t for t in workflow.tasks if t.status == TaskStatus.COMPLETED]),
            "tasks_failed": failed,
            "results": results,
            "shared_context": self.shared_context,
        }

    async def _worker_loop(self) -> None:
        while self.is_running:
            try:
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            if not self._dependencies_met(task):
                task.status = TaskStatus.BLOCKED
                await asyncio.sleep(0.25)
                await self.task_queue.put(task)
                continue
            agent = self._find_agent(task.role)
            if not agent:
                await asyncio.sleep(0.25)
                await self.task_queue.put(task)
                continue
            await self._execute_task(task, agent)

    async def _execute_task(self, task: Task, agent: AgentInstance) -> None:
        agent.status = "working"
        agent.current_task = task.id
        task.status = TaskStatus.RUNNING
        task.assigned_agent = agent.id
        task.started_at = time.time()
        self.traces.log("task", "started", task_id=task.id, agent=agent.name)
        try:
            cls = self.agent_classes[task.role]
            instance = cls(llm_client=self.llm)
            task_input = {**self.shared_context, **task.input_data}
            result: AgentResult = await asyncio.to_thread(instance.execute, task_input)
            task.output_data = {
                "agent": result.agent_name,
                "status": result.status,
                "output": result.output,
                "trust_score": result.trust_score,
                "processing_time": result.processing_time,
            }
            self._merge_context(task.role, result.output)
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            agent.completed_tasks += 1
            self.traces.log("task", "completed", task_id=task.id, agent=agent.name)
            self._speak(f"{agent.name} completed {task.description}.")
        except Exception as exc:
            task.error = str(exc)
            task.retry_count += 1
            agent.failed_tasks += 1
            self.traces.log("task", "failed", task_id=task.id, agent=agent.name, payload=str(exc))
            if task.retry_count < 3:
                task.status = TaskStatus.PENDING
                await self.task_queue.put(task)
            else:
                task.status = TaskStatus.FAILED
        finally:
            agent.status = "idle"
            agent.current_task = None

    def _merge_context(self, role: AgentRole, output: Any) -> None:
        key = f"{role.value}_output"
        self.shared_context[key] = output
        if role == AgentRole.PLANNER and isinstance(output, dict):
            self.shared_context["topic"] = output.get("topic", self.shared_context.get("topic"))
        if role == AgentRole.RESEARCH and isinstance(output, dict):
            self.shared_context["research_output"] = output
            if output.get("curriculum"):
                self.shared_context["curriculum"] = output["curriculum"]
        if role == AgentRole.VALIDATION and isinstance(output, dict):
            self.shared_context["validation_output"] = output
            self.shared_context["validated_facts"] = output.get("validated_facts", [])
        if role == AgentRole.SYNTHESIZER and isinstance(output, dict):
            self.shared_context["synthesizer_output"] = output
            self.shared_context["study_sheet"] = output.get("study_sheet", "")

    def _dependencies_met(self, task: Task) -> bool:
        for dep in task.dependencies:
            dep_task = self.tasks.get(dep)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        return True

    def _has_pending(self, workflow: "Workflow") -> bool:
        return any(
            t.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.BLOCKED)
            for t in workflow.tasks
        )

    def _find_agent(self, role: AgentRole) -> Optional[AgentInstance]:
        for agent in self.agents.values():
            if agent.role == role and agent.status == "idle":
                return agent
        return None

    def _progress(self, workflow: "Workflow") -> Dict[str, Any]:
        total = len(workflow.tasks)
        done = len([t for t in workflow.tasks if t.status == TaskStatus.COMPLETED])
        return {"workflow": workflow.name, "total": total, "completed": done, "percent": (done / total * 100) if total else 0}

    def _speak(self, text: str) -> None:
        if self.voice:
            self.voice.speak(text)

    def _notify(self, event: str, data: Any) -> None:
        for cb in self.callbacks.get(event, []):
            try:
                cb(data)
            except Exception:
                pass

    def register_callback(self, event: str, callback: Callable) -> None:
        self.callbacks.setdefault(event, []).append(callback)

    def get_team_status(self) -> Dict[str, Any]:
        return {
            "agents": [
                {
                    "id": a.id,
                    "name": a.name,
                    "role": a.role.value,
                    "status": a.status,
                    "completed": a.completed_tasks,
                    "failed": a.failed_tasks,
                }
                for a in self.agents.values()
            ],
            "tasks": {
                "total": len(self.tasks),
                "completed": sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED),
                "failed": sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED),
            },
        }


class Workflow:
    def __init__(self, name: str, harness: AgentHarness):
        self.name = name
        self.harness = harness
        self.tasks: List[Task] = []
        self._counter = 0
        self._id_map: Dict[str, str] = {}

    def add_task(
        self,
        role: AgentRole,
        description: str,
        input_data: Dict[str, Any],
        depends_on: Optional[List[str]] = None,
        task_key: Optional[str] = None,
    ) -> str:
        self._counter += 1
        task_id = f"{self.name}_task_{self._counter}"
        deps = []
        if depends_on:
            for key in depends_on:
                resolved = self._id_map.get(key, key)
                deps.append(resolved)
        task = Task(
            id=task_id,
            description=description,
            role=role,
            input_data=input_data,
            dependencies=deps,
        )
        self.tasks.append(task)
        if task_key:
            self._id_map[task_key] = task_id
        return task_id

    @classmethod
    def from_toml(cls, path: str, harness: AgentHarness, base_input: Optional[Dict] = None) -> "Workflow":
        from aether.workflow.loader import load_workflow_toml

        graph = load_workflow_toml(path)
        wf = cls(graph.name, harness)
        base = base_input or {}
        node_to_task: Dict[str, str] = {}
        for node in graph.nodes:
            role = AgentRole(node.role)
            tid = wf.add_task(
                role,
                node.description or node.id,
                {**base, **node.config},
                task_key=node.id,
            )
            node_to_task[node.id] = tid
        for edge in graph.edges:
            target = next(t for t in wf.tasks if t.id == node_to_task[edge.target])
            dep_id = node_to_task[edge.source]
            if dep_id not in target.dependencies:
                target.dependencies.append(dep_id)
        return wf
