"""A single source of truth for what A.E.T.H.E.R. can do, and whether it is ready."""

from __future__ import annotations

from typing import Any, Dict, List

from aether.config import Settings


def describe_capabilities(settings: Settings) -> List[Dict[str, Any]]:
    has_printer = bool(
        settings.octoprint_api_key or (settings.printer_type == "moonraker" and settings.moonraker_url)
    )
    has_home = bool(settings.homeassistant_url and settings.homeassistant_token)
    has_voice_cloud = bool(settings.elevenlabs_api_key)

    return [
        {
            "id": "chat",
            "name": "Conversational assistant (A.E.T.H.E.R. persona)",
            "description": "Local chat with time-based greetings, on desktop and phone.",
            "how": 'aether chat "..."  or the web app',
            "available": True,
        },
        {
            "id": "voice",
            "name": "Hands-free voice (wake word + speech)",
            "description": "Say the wake word, speak a command, hear the reply. Browser or native app.",
            "how": "Voice button in the web app, or aether-app on Linux",
            "available": True,
            "enhanced": has_voice_cloud,
        },
        {
            "id": "japanese",
            "name": "Deep Japanese language learning",
            "description": "Six-pass graduate curriculum: scripts, grammar, vocabulary, communication, JLPT depth.",
            "how": 'aether learn "Japanese language" or aether do "learn everything about Japanese"',
            "available": True,
        },
        {
            "id": "build_app",
            "name": "Software / infrastructure engineering",
            "description": "Generate a full local application or backend from a plain-language spec, written to disk.",
            "how": 'aether build-app "FastAPI backend for inventory" or aether do "build me ..."',
            "available": True,
        },
        {
            "id": "learn",
            "name": "Deep learning (graduate-depth research)",
            "description": "Multi-pass research that builds a curriculum and study sheet on any topic.",
            "how": 'aether learn "robotic engineering"',
            "available": True,
        },
        {
            "id": "build_cad",
            "name": "CAD + parts + wiring generation",
            "description": "Turn a learned topic into a printable 3D model, bill of materials, and wiring guide.",
            "how": 'aether build --topic "..." --project "..."',
            "available": True,
        },
        {
            "id": "printer",
            "name": "3D printer control (Ender 3 V3)",
            "description": "Upload and monitor prints via OctoPrint or Moonraker.",
            "how": "Set OCTOPRINT_* or MOONRAKER_* in .env",
            "available": has_printer,
        },
        {
            "id": "smart_home",
            "name": "Smart home control",
            "description": "List devices and turn lights/plugs/scenes on or off via local Home Assistant.",
            "how": "Set HOMEASSISTANT_URL + HOMEASSISTANT_TOKEN, then 'aether home list'",
            "available": has_home,
        },
        {
            "id": "autonomy",
            "name": "Autonomous self-learning (with guardrails + kill switch)",
            "description": "Give a mission and typed restrictions; it learns/builds on its own. Stop anytime.",
            "how": 'aether auto "..." --restrictions "..."  /  aether stop',
            "available": True,
        },
        {
            "id": "multi_llm",
            "name": "Multi-model routing (local)",
            "description": "Routes each task to the best local model (general, code, embeddings, AirLLM).",
            "how": "Configure OLLAMA_* models; USE_AIRLLM=true for big quantized models",
            "available": True,
            "enhanced": settings.use_airllm,
        },
        {
            "id": "mobile",
            "name": "Phone app (installable PWA)",
            "description": "Install the web app on Android/iOS and use it over your Wi-Fi.",
            "how": "aether web --lan, then Add to Home screen",
            "available": True,
        },
        {
            "id": "desktop",
            "name": "Native desktop app (Linux/Manjaro)",
            "description": "Runs the whole AI in one window, no browser, with offline voice in/out.",
            "how": "aether app (install: pip install -e '.[desktop,stt]')",
            "available": True,
        },
    ]
