"""Autonomous self-learning agent.

Given a mission and your typed restrictions, it loops:
    1. decide the next best goal (LLM, informed by what it already knows)
    2. run guardrails (hard rules + optional LLM safety review)
    3. if approval is required, pause and ask you
    4. act (learn a topic, or build a project)
    5. reflect and record what was learned
    6. check the kill switch / pause / budgets, then repeat

It never exceeds max_iterations or max_runtime_minutes, and a STOP file
(or the Stop button) halts it immediately.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional

from aether.autonomy.control import AutonomyControl, ControlState
from aether.autonomy.guardrails import Guardrails
from aether.config import Settings
from aether.knowledge.store import KnowledgeStore
from aether.pipeline.orchestrator import MasterPipeline
from aether.traces.store import TraceStore

PLANNER_SYSTEM = """You are the planning brain of an autonomous engineering agent.
Given the mission, the restrictions, and the list of topics already learned,
choose the single best next step. Reply ONLY with compact JSON:
{"action": "learn"|"build"|"build_app"|"stop", "topic": "...", "project": "...", "spec": "...", "why": "short"}
- Use "learn" to study a new topic that advances the mission.
- Use "build" to produce a physical/3D-printable design from a learned topic.
- Use "build_app" to engineer software/a backend/infrastructure (put the full
  build request in "spec"). For a multi-service system, build one service per step.
- Use "stop" when the mission is satisfied or nothing safe/useful remains.
Keep steps specific. Do not repeat work already completed this run."""


class AutonomousAgent:
    def __init__(
        self,
        llm: Any,
        settings: Settings,
        guardrails: Guardrails,
        control: Optional[AutonomyControl] = None,
        on_event: Optional[Callable[[str, Dict], None]] = None,
    ):
        self.llm = llm
        self.settings = settings
        self.guardrails = guardrails
        self.control = control or AutonomyControl(settings.data_dir)
        self.knowledge = KnowledgeStore(settings.data_dir)
        self.traces = TraceStore(settings.traces_db)
        self._external_event = on_event

    def _emit(self, kind: str, message: str, data: Dict | None = None) -> None:
        entry = self.control.log(kind, message, data)
        self.traces.log(f"auto_{kind}", "info", payload=message[:400], agent="autonomy")
        if self._external_event:
            self._external_event(kind, entry)

    # ------------------------------------------------------------------- run
    def run(self, mission: str) -> Dict[str, Any]:
        self.control.start()
        self._emit("mission", f"Mission: {mission}", {"guardrails": self.guardrails.to_dict()})
        start = time.time()
        deadline = start + self.guardrails.max_runtime_minutes * 60
        completed: List[Dict] = []
        iteration = 0

        while True:
            if self.control.should_stop():
                self._emit("stopped", "Kill switch engaged: halting.")
                break
            if iteration >= self.guardrails.max_iterations:
                self._emit("limit", f"Reached max iterations ({self.guardrails.max_iterations}).")
                break
            if time.time() >= deadline:
                self._emit("limit", f"Reached time budget ({self.guardrails.max_runtime_minutes} min).")
                break

            self.control.wait_while_paused()
            if self.control.should_stop():
                self._emit("stopped", "Stopped while paused.")
                break

            iteration += 1
            self._emit("iteration", f"Iteration {iteration}/{self.guardrails.max_iterations}")

            decision = self._decide(mission, completed)
            action = (decision.get("action") or "stop").lower()
            topic = (decision.get("topic") or "").strip()
            project = (decision.get("project") or "").strip()
            spec = (decision.get("spec") or "").strip()
            why = decision.get("why", "")

            if action == "stop":
                self._emit("done", f"Agent decided to stop: {why}")
                break

            description = (spec or f"{topic} {project}").strip() or why
            verdict = self.guardrails.evaluate(self.llm, action, description)
            self._emit(
                "guardrail",
                f"{action} -> {'ALLOW' if verdict.allowed else 'BLOCK'}: {verdict.reason}",
                verdict.to_dict(),
            )

            if not verdict.allowed:
                self._emit("blocked", f"Skipped '{action}' on '{description[:80]}'.")
                completed.append({"action": action, "topic": topic, "blocked": True})
                continue

            if verdict.needs_approval:
                approved = self.control.request_approval(
                    {"action": action, "topic": topic, "project": project, "description": description}
                )
                if not approved:
                    self._emit("denied", f"You denied '{action}' on '{description[:80]}'.")
                    completed.append({"action": action, "topic": topic, "denied": True})
                    continue

            try:
                result = self._act(action, topic, project, spec)
                completed.append({"action": action, "topic": topic, "project": project, "spec": spec, "ok": True})
                self._emit("acted", f"Completed {action}: {spec or topic or project}", {"summary": _short(result)})
            except Exception as exc:
                self._emit("error", f"Action failed: {exc}")
                completed.append({"action": action, "topic": topic, "error": str(exc)})

        self.control.finish()
        summary = {
            "mission": mission,
            "iterations": iteration,
            "completed": completed,
            "elapsed_seconds": round(time.time() - start, 1),
            "state": self.control.state.value,
        }
        self._emit("summary", "Run finished.", summary)
        return summary

    # --------------------------------------------------------------- helpers
    def _decide(self, mission: str, completed: List[Dict]) -> Dict[str, Any]:
        learned = self.knowledge.list_topics()
        user = (
            f"MISSION:\n{mission}\n\n"
            f"RESTRICTIONS:\n{self.guardrails.restrictions_text or '(none)'}\n\n"
            f"ALREADY LEARNED TOPICS: {learned or '(none yet)'}\n"
            f"STEPS DONE THIS RUN: {json.dumps(completed)[:1500]}\n\n"
            "Choose the next step."
        )
        try:
            raw = self.llm.complete(user, system=PLANNER_SYSTEM)
            parsed = _parse_json(raw)
            if parsed:
                return parsed
        except Exception as exc:
            self._emit("plan_error", f"Planning failed: {exc}")
        # Fallback: learn the mission itself once, else stop.
        if not learned:
            return {"action": "learn", "topic": mission[:80], "why": "bootstrap from mission"}
        return {"action": "stop", "why": "no plan produced"}

    def _act(self, action: str, topic: str, project: str, spec: str = "") -> Dict[str, Any]:
        import asyncio

        if action == "build_app":
            from aether.pipeline.app_builder import AppBuilderPipeline

            app_pipe = AppBuilderPipeline(
                self.llm,
                self.settings,
                trace_store=self.traces,
                on_event=lambda e, d: self._emit(f"app_{e}", str(d.get("status", e))[:80], {}),
            )
            return asyncio.run(app_pipe.build(spec or project or topic))

        pipe = MasterPipeline(
            self.llm,
            self.settings,
            trace_store=self.traces,
            on_event=lambda e, d: self._emit(f"pipe_{e}", str(d.get("status", e))[:80], {}),
        )
        if action == "learn":
            return asyncio.run(pipe.learn(topic or project))
        if action == "build":
            allow_print = self.guardrails.allow_printing
            return asyncio.run(
                pipe.build(topic or project, project or topic, send_to_printer=allow_print, auto_print=False)
            )
        return {"status": "noop"}


def _short(result: Dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return str(result)[:160]
    for key in ("status", "topic", "build_dir", "slug"):
        if key in result:
            return f"{key}={result[key]}"
    return "ok"


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
