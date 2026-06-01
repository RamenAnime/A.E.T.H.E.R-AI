"""Printer hardware profiles for CAD limits and slicer hints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class PrinterProfile:
    id: str
    name: str
    build_x_mm: float
    build_y_mm: float
    build_z_mm: float
    nozzle_mm: float
    max_speed_mm_s: float
    pla_nozzle_c: int
    pla_bed_c: int
    notes: str


PROFILES: Dict[str, PrinterProfile] = {
    "ender3_v3": PrinterProfile(
        id="ender3_v3",
        name="Creality Ender 3 V3 (all-metal)",
        build_x_mm=220,
        build_y_mm=220,
        build_z_mm=250,
        nozzle_mm=0.4,
        max_speed_mm_s=300,
        pla_nozzle_c=210,
        pla_bed_c=60,
        notes=(
            "Direct drive, all-metal hotend. Use Creality Print or Cura with Ender 3 V3 profile. "
            "For remote control: OctoPrint on a Pi, or Klipper + Moonraker if you flashed firmware."
        ),
    ),
}


def get_profile(profile_id: str) -> PrinterProfile:
    return PROFILES.get(profile_id, PROFILES["ender3_v3"])


def cad_constraints_text(profile_id: str) -> str:
    p = get_profile(profile_id)
    return (
        f"Printer: {p.name}. Build volume {p.build_x_mm}x{p.build_y_mm}x{p.build_z_mm} mm. "
        f"Nozzle {p.nozzle_mm} mm. Split large assemblies into parts that fit the bed."
    )
