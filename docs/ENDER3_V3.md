# Creality Ender 3 V3 (all-metal) + A.E.T.H.E.R.

Your printer is pre-configured in A.E.T.H.E.R. as profile `ender3_v3` (220×220×250 mm bed).

## How A.E.T.H.E.R. connects

| Setup | Best for | `.env` |
|--------|----------|--------|
| **OctoPrint** on Raspberry Pi / PC | Stock firmware, USB to Pi | `PRINTER_TYPE=octoprint` |
| **Klipper + Moonraker** | If you flashed Klipper | `PRINTER_TYPE=moonraker` |
| **SD card only** | No network | Leave printer unset; use `ENDER3_V3_PRINT.md` in build folder |

Example `.env`:

```env
PRINTER_PROFILE=ender3_v3
PRINTER_TYPE=octoprint
OCTOPRINT_URL=http://192.168.1.50:5000
OCTOPRINT_API_KEY=your_key
```

Get the OctoPrint API key: Settings → API.

## Typical workflow

1. `aether learn "robotic engineering and 3D modeling"`
2. `aether build --topic "..." --project "robot frame sections" --printer`
3. Open `model.scad` → export STL (OpenSCAD) or use generated `model.stl`
4. **Slice in Creality Print** with the Ender 3 V3 profile (PLA ~210°C / 60°C bed)
5. Print from SD, or upload G-code through OctoPrint

A.E.T.H.E.R. uploads **STL** to OctoPrint; you still **slice to G-code** in Creality Print or OctoPrint’s slicer plugin unless you upload G-code yourself.

## OctoPrint on a Pi (recommended)

1. Install OctoPrint for Ender 3 (USB cable Pi ↔ printer).
2. Note the Pi IP (e.g. `192.168.1.50`).
3. Put that URL in `.env` on the PC running A.E.T.H.E.R.

## All-metal hotend

Use PLA/PETG temps from Creality; avoid sustained ABS without enclosure unless you know your limits.
