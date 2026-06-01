"""Create the configured printer backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from aether.config import Settings
from aether.integrations.moonraker import MoonrakerClient
from aether.integrations.printer_3d import Printer3D
from aether.integrations.printer_profiles import get_profile


class PrinterBackend(Protocol):
    base_url: str

    def ping(self) -> bool: ...
    def status(self) -> dict: ...
    def upload_stl(self, stl_path: Path, select: bool = True) -> dict: ...
    def start_print(self) -> dict: ...


class UnifiedPrinter:
    """Wraps OctoPrint or Moonraker with one interface."""

    def __init__(self, settings: Settings):
        self.profile = get_profile(settings.printer_profile)
        self.backend_type = settings.printer_type.lower()
        self._octo: Printer3D | None = None
        self._moon: MoonrakerClient | None = None

        if self.backend_type == "moonraker" and settings.moonraker_url:
            self._moon = MoonrakerClient(settings.moonraker_url, settings.moonraker_api_key)
            self.base_url = settings.moonraker_url
        elif settings.octoprint_url:
            self.backend_type = "octoprint"
            self._octo = Printer3D(settings.octoprint_url, settings.octoprint_api_key)
            self.base_url = settings.octoprint_url
        else:
            self.base_url = ""

    def is_configured(self) -> bool:
        return bool(self._octo or self._moon)

    def ping(self) -> bool:
        if self._moon:
            return self._moon.ping()
        if self._octo:
            return self._octo.ping()
        return False

    def status(self) -> dict:
        base = {"profile": self.profile.id, "name": self.profile.name, "backend": self.backend_type}
        if self._moon:
            return {**base, **self._moon.status()}
        if self._octo:
            return {**base, **self._octo.status()}
        return {**base, "online": False, "message": "Printer not configured"}

    def upload_stl(self, stl_path: Path, select: bool = True) -> dict:
        if self._moon:
            return self._moon.upload_stl(stl_path, start=False)
        if self._octo:
            return self._octo.upload_stl(stl_path, select=select)
        raise RuntimeError("No printer backend configured")

    def start_print(self) -> dict:
        if self._moon:
            raise RuntimeError("Slice G-code in Mainsail first, then start from Fluidd/Mainsail")
        if self._octo:
            return self._octo.start_print()
        raise RuntimeError("No printer backend configured")

    def write_slicer_readme(self, build_dir: Path) -> Path:
        p = self.profile
        text = f"""# Ender 3 V3: print this project

Printer: **{p.name}**
Build volume: {p.build_x_mm} x {p.build_y_mm} x {p.build_z_mm} mm

## Steps
1. Open `model.scad` in OpenSCAD → Export STL (or use `model.stl` if generated).
2. Slice in **Creality Print** (Ender 3 V3 profile) or Cura.
3. Suggested PLA: nozzle {p.pla_nozzle_c}°C, bed {p.pla_bed_c}°C, 0.2 mm layer, 15% infill for prototypes.
4. Copy G-code to SD card, **or** upload via OctoPrint/Moonraker from A.E.T.H.E.R.

{p.notes}
"""
        path = build_dir / "ENDER3_V3_PRINT.md"
        path.write_text(text, encoding="utf-8")
        return path


def get_printer(settings: Settings) -> UnifiedPrinter:
    return UnifiedPrinter(settings)
