"""Generate parametric OpenSCAD models (export to STL with OpenSCAD installed)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict

from aether.agents.base import AgentResult, BaseAgent

CAD_SYSTEM = """You are an expert mechanical CAD engineer using OpenSCAD.
Output ONLY valid OpenSCAD code (no markdown fences).
Design modular, printable parts with sensible wall thickness (2-4mm), bolt holes,
and union/difference structure. Add comments explaining each module.
Scale in millimeters."""


class CadAgent(BaseAgent):
    role_name = "cad"

    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        def work() -> AgentResult:
            topic = input_data.get("topic", "")
            project = input_data.get("project_description", input_data.get("project", ""))
            knowledge = input_data.get("curriculum", "") or input_data.get("study_sheet", "")
            knowledge = str(knowledge)[:12000]
            out_dir = Path(input_data["output_dir"])

            constraints = input_data.get("cad_constraints", "")
            user = (
                f"Learning context topic: {topic}\n"
                f"Build request: {project}\n"
                f"Printer constraints: {constraints}\n\n"
                f"Relevant knowledge:\n{knowledge}\n\n"
                "Create an OpenSCAD model for the primary structural assembly described. "
                "Use modules for sub-assemblies. Split into bed-sized parts if needed. "
                "Start with a simplified but printable concept."
            )
            scad = self._llm_prompt(CAD_SYSTEM, user)
            scad = _strip_fences(scad)
            scad_path = out_dir / "model.scad"
            scad_path.write_text(scad, encoding="utf-8")

            stl_path = out_dir / "model.stl"
            stl_ok, stl_msg = _try_export_stl(scad_path, stl_path)
            readme = out_dir / "CAD_README.md"
            readme.write_text(
                f"# CAD output\n\n"
                f"- **OpenSCAD source:** `{scad_path.name}`\n"
                f"- **STL export:** {'OK: ' + str(stl_path) if stl_ok else stl_msg}\n\n"
                "Open in OpenSCAD or FreeCAD (import SCAD/STL). "
                "Large habitable structures require engineering review before printing.\n",
                encoding="utf-8",
            )
            return self._ok(
                {
                    "scad_path": str(scad_path),
                    "stl_path": str(stl_path) if stl_ok else None,
                    "stl_export": stl_msg,
                }
            )

        return self._run_timed(work)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _try_export_stl(scad_path: Path, stl_path: Path) -> tuple[bool, str]:
    try:
        subprocess.run(
            ["openscad", "-o", str(stl_path), str(scad_path)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        if stl_path.exists():
            return True, "Exported with OpenSCAD"
        return False, "OpenSCAD ran but STL not found"
    except FileNotFoundError:
        return False, "Install OpenSCAD, then run: openscad -o model.stl model.scad"
    except subprocess.CalledProcessError as exc:
        return False, f"OpenSCAD error: {exc.stderr.decode(errors='replace')[:500]}"
