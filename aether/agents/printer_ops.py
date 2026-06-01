"""Send CAD to printer and report status."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from aether.agents.base import AgentResult, BaseAgent
class PrinterOpsAgent(BaseAgent):
    role_name = "printer_ops"

    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        def work() -> AgentResult:
            printer = input_data.get("printer")
            stl_path = input_data.get("stl_path")
            auto_print = input_data.get("auto_print", False)

            if not printer or not printer.is_configured():
                return self._ok(
                    {
                        "status": "skipped",
                        "message": "Printer not configured. Set OCTOPRINT_* or MOONRAKER_* in .env (see docs/ENDER3_V3.md)",
                    },
                    trust=1.0,
                )

            if not printer.ping():
                return self._ok(
                    {"status": "offline", "message": f"Cannot reach printer at {printer.base_url}"},
                    trust=0.5,
                )

            status = printer.status()
            result: Dict[str, Any] = {"status": "connected", "printer_status": status}

            if stl_path and Path(stl_path).exists():
                upload = printer.upload_stl(Path(stl_path), select=True)
                result["upload"] = upload
                result["message"] = (
                    f"Uploaded {Path(stl_path).name}. "
                    "Slice in Creality Print (Ender 3 V3) then print, or use OctoPrint start if G-code."
                )
                if auto_print:
                    try:
                        result["job"] = printer.start_print()
                        result["message"] += ": print started"
                    except Exception as exc:
                        result["message"] += f" (start skipped: {exc})"
            else:
                result["message"] = (
                    "Printer online. Install OpenSCAD to export STL, slice in Creality Print, then upload G-code."
                )

            return self._ok(result)

        return self._run_timed(work)
