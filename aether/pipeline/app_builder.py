"""App / infrastructure builder: spec in, runnable project on disk out.

Say "build me the backend of an inventory system" and this:
  1. asks the architect model for a concrete file plan
  2. generates each file with the code model
  3. writes a real project folder under the build dir
  4. drops a BUILD_REPORT.md with run instructions

Everything is local. Files are written only inside the configured build dir.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from aether.agents.software_engineer import ArchitectAgent, CodeWriterAgent
from aether.config import Settings
from aether.knowledge.store import slugify
from aether.llm.router import ModelRouter
from aether.traces.store import TraceStore

# Files we will never write, regardless of what the model proposes.
_BLOCKED_SUFFIXES = (".exe", ".dll", ".so", ".bin")
_MAX_FILES = 40


class AppBuilderPipeline:
    def __init__(
        self,
        llm: Any,
        settings: Settings,
        trace_store: Optional[TraceStore] = None,
        on_event: Optional[Callable[[str, Dict], None]] = None,
    ):
        # Accept a router or a plain client; wrap plain clients so .complete(task=) works.
        self.router = llm if isinstance(llm, ModelRouter) else _CompatRouter(llm)
        self.settings = settings
        self.traces = trace_store or TraceStore(settings.traces_db)
        self.on_event = on_event or (lambda _e, _d: None)

    def _emit(self, event: str, data: Dict) -> None:
        self.on_event(event, data)
        try:
            self.traces.log(f"app_{event}", data.get("status", "info"), payload=str(data)[:300], agent="app_builder")
        except Exception:
            pass

    async def build(
        self,
        spec: str,
        project_name: str = "",
        constraints: str = "",
        approve: Optional[Callable[[Dict], bool]] = None,
    ) -> Dict[str, Any]:
        self._emit("plan_start", {"spec": spec[:200], "status": "planning"})

        architect = ArchitectAgent(self.router)
        plan_result = await asyncio.to_thread(
            architect.execute, {"spec": spec, "constraints": constraints}
        )
        plan: Dict[str, Any] = plan_result.output or {}
        files: List[Dict[str, str]] = plan.get("files", [])[:_MAX_FILES]
        if not files:
            return {"status": "failed", "error": "Architect produced no file plan", "plan": plan}

        # Optional human-in-the-loop gate before anything is written to disk.
        if approve is not None:
            self._emit("await_approval", {"project": plan.get("project_name", ""), "file_count": len(files), "files": [f.get("path") for f in files], "stack": plan.get("stack", []), "status": "await_approval"})
            if inspect.iscoroutinefunction(approve):
                ok = await approve(plan)
            else:
                ok = await asyncio.to_thread(approve, plan)
            if not ok:
                self._emit("cancelled", {"status": "cancelled"})
                return {"status": "cancelled", "plan": plan, "files": []}

        name = slugify(project_name or plan.get("project_name") or spec[:40])
        out_dir = Path(self.settings.build_dir) / name
        out_dir.mkdir(parents=True, exist_ok=True)
        self._emit("planned", {"project": name, "file_count": len(files), "stack": plan.get("stack", []), "status": "planned"})

        manifest = ", ".join(f.get("path", "") for f in files)
        written: List[str] = []
        writer = CodeWriterAgent(self.router)

        for i, spec_file in enumerate(files, 1):
            rel = (spec_file.get("path") or "").strip().lstrip("/\\")
            if not rel or not _safe_rel(out_dir, rel):
                self._emit("skip", {"path": rel, "reason": "unsafe path", "status": "skip"})
                continue
            self._emit("file_start", {"path": rel, "i": i, "n": len(files), "status": "writing"})
            res = await asyncio.to_thread(
                writer.execute,
                {
                    "plan": plan,
                    "file_path": rel,
                    "purpose": spec_file.get("purpose", ""),
                    "manifest": manifest,
                },
            )
            content = (res.output or {}).get("content", "")
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(rel)
            self._emit("file_done", {"path": rel, "chars": len(content), "status": "ok"})

        report = _build_report(plan, written)
        (out_dir / "BUILD_REPORT.md").write_text(report, encoding="utf-8")
        (out_dir / "aether_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")

        out = {
            "status": "complete",
            "project": name,
            "dir": str(out_dir),
            "files": written,
            "stack": plan.get("stack", []),
            "run_command": plan.get("run_command", ""),
            "install_command": plan.get("install_command", ""),
            "summary": plan.get("summary", ""),
        }
        self._emit("build_done", out)
        return out


def _safe_rel(root: Path, rel: str) -> bool:
    if any(rel.endswith(s) for s in _BLOCKED_SUFFIXES):
        return False
    try:
        resolved = (root / rel).resolve()
        return root.resolve() in resolved.parents or resolved == root.resolve()
    except (OSError, ValueError):
        return False


def _build_report(plan: Dict[str, Any], written: List[str]) -> str:
    lines = [
        f"# {plan.get('project_name', 'app')}",
        "",
        plan.get("summary", ""),
        "",
        "## Stack",
        ", ".join(plan.get("stack", [])) or "n/a",
        "",
        "## Install",
        "```bash",
        plan.get("install_command", "(see README)"),
        "```",
        "",
        "## Run",
        "```bash",
        plan.get("run_command", "(see README)"),
        "```",
        "",
        "## Files generated",
        *[f"- `{f}`" for f in written],
        "",
        "_Generated locally by A.E.T.H.E.R. Review before running._",
    ]
    return "\n".join(lines)


class _CompatRouter:
    """Wraps a plain LLM client so callers can pass task= without errors."""

    def __init__(self, llm: Any):
        self._llm = llm

    def complete(self, prompt: str, system: str = "", task: str = "general", model: Optional[str] = None) -> str:
        try:
            return self._llm.complete(prompt, system=system, model=model)
        except TypeError:
            return self._llm.complete(prompt, system=system)

    def __getattr__(self, item):
        return getattr(self._llm, item)
