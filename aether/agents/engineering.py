"""Bill of materials, wiring, and assembly instructions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from aether.agents.base import AgentResult, BaseAgent

ENG_SYSTEM = """You are a robotics systems engineer. Produce practical build documentation.
Return structured markdown with these sections:
# Bill of Materials (table: part, qty, spec, supplier hint, est cost)
# Wiring Guide (pin-by-pin, voltage, current, safety fuses)
# Assembly Steps (numbered)
# Tools Required
# Testing & Commissioning checklist
Be specific about motors, drivers, power distribution, sensors, and MCU (Arduino/ESP32/RPi)."""


class EngineeringAgent(BaseAgent):
    role_name = "engineering"

    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        def work() -> AgentResult:
            topic = input_data.get("topic", "")
            project = input_data.get("project_description", "")
            knowledge = str(
                input_data.get("curriculum", "") or input_data.get("study_sheet", "")
            )[:12000]
            out_dir = Path(input_data["output_dir"])

            user = (
                f"Topic knowledge: {topic}\nProject: {project}\n\n{knowledge}\n\n"
                "List exact parts to source and how to wire and test the system."
            )
            doc = self._llm_prompt(ENG_SYSTEM, user)
            md_path = out_dir / "build_guide.md"
            md_path.write_text(doc, encoding="utf-8")

            bom_path = out_dir / "bom.json"
            bom = _extract_bom_table(doc)
            bom_path.write_text(json.dumps(bom, indent=2), encoding="utf-8")

            wiring_path = out_dir / "wiring.md"
            wiring = _extract_section(doc, "Wiring")
            wiring_path.write_text(wiring or doc, encoding="utf-8")

            return self._ok(
                {
                    "build_guide": str(md_path),
                    "bom": str(bom_path),
                    "wiring": str(wiring_path),
                    "part_count": len(bom.get("items", [])),
                }
            )

        return self._run_timed(work)


def _extract_section(doc: str, name: str) -> str:
    lines = doc.splitlines()
    out = []
    capture = False
    for line in lines:
        if line.lower().startswith("#") and name.lower() in line.lower():
            capture = True
            out.append(line)
            continue
        if capture and line.startswith("# ") and name.lower() not in line.lower():
            break
        if capture:
            out.append(line)
    return "\n".join(out).strip()


def _extract_bom_table(doc: str) -> Dict[str, Any]:
    items = []
    in_bom = False
    for line in doc.splitlines():
        if "bill of materials" in line.lower():
            in_bom = True
            continue
        if in_bom and line.startswith("# ") and "bill" not in line.lower():
            break
        if in_bom and "|" in line and not line.strip().startswith("|---"):
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if len(cols) >= 2 and cols[0].lower() not in ("part", "item", "component"):
                items.append(
                    {
                        "part": cols[0] if len(cols) > 0 else "",
                        "qty": cols[1] if len(cols) > 1 else "1",
                        "spec": cols[2] if len(cols) > 2 else "",
                        "supplier": cols[3] if len(cols) > 3 else "",
                    }
                )
    return {"items": items}
