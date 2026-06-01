"""Commander: routes a plain-language request to the right pipeline action.

Examples:
  "build me the backend of an inventory system" -> app builder
  "learn everything about robotics"             -> deep learn
  "design a printable drone frame"              -> CAD build
  "turn off the living room lights"              -> smart home
  "what's my CPU doing?"                        -> chat / status

Intent is classified with the local model (strict JSON). Keyword fallbacks
apply when the model response is missing or invalid.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional

from aether.config import Settings
from aether.llm.router import ModelRouter
from aether.persona import build_persona

INTENTS = ("build_app", "learn", "build_cad", "smart_home", "chat")

CLASSIFY_SYSTEM = """You route a user request to ONE action. Reply ONLY with compact JSON:
{"intent": "build_app|learn|build_cad|smart_home|chat",
 "spec": "what to build (for build_app)",
 "topic": "topic (for learn or build_cad)",
 "project": "what to design (for build_cad)",
 "device": "device/area name (for smart_home)",
 "command": "on|off|toggle|status (for smart_home)"}
Guidance:
- build_app: software, websites, APIs, backends, scripts, infrastructure, bots.
- learn: study/research a subject in depth.
- build_cad: physical/3D-printable objects, mechanical parts, robot bodies.
- smart_home: lights, switches, plugs, scenes, thermostats, locks.
- chat: questions, conversation, status, anything else.
Fill only the relevant fields; leave others empty."""


class Commander:
    def __init__(
        self,
        settings: Settings,
        llm: Optional[Any] = None,
        on_event: Optional[Callable[[str, Dict], None]] = None,
        approve: Optional[Callable[[Dict], bool]] = None,
    ):
        self.settings = settings
        self.router = llm if isinstance(llm, ModelRouter) else ModelRouter(settings, llm)
        self.on_event = on_event or (lambda _e, _d: None)
        self.approve = approve

    # ------------------------------------------------------------- classify
    def classify(self, text: str) -> Dict[str, Any]:
        try:
            raw = self.router.complete(text, system=CLASSIFY_SYSTEM, task="plan")
            parsed = _parse_json(raw)
            if parsed and parsed.get("intent") in INTENTS:
                return parsed
        except Exception:
            pass
        return _keyword_intent(text)

    # -------------------------------------------------------------- dispatch
    async def run(self, text: str) -> Dict[str, Any]:
        plan = self.classify(text)
        intent = plan.get("intent", "chat")
        self.on_event("intent", {"intent": intent, "request": text[:200]})

        if intent == "build_app":
            return await self._build_app(plan.get("spec") or text)
        if intent == "learn":
            return await self._learn(plan.get("topic") or text)
        if intent == "build_cad":
            return await self._build_cad(plan.get("topic") or text, plan.get("project") or text)
        if intent == "smart_home":
            return self._smart_home(plan.get("device", ""), plan.get("command", "status"), text)
        return self._chat(text)

    # ---------------------------------------------------------------- actions
    async def _build_app(self, spec: str) -> Dict[str, Any]:
        from aether.pipeline.app_builder import AppBuilderPipeline

        pipe = AppBuilderPipeline(self.router, self.settings, on_event=self.on_event)
        result = await pipe.build(spec, approve=self.approve)
        return {"intent": "build_app", **result}

    async def _learn(self, topic: str) -> Dict[str, Any]:
        from aether.pipeline.orchestrator import MasterPipeline

        pipe = MasterPipeline(self.router, self.settings, on_event=self.on_event)
        result = await pipe.learn(topic)
        return {"intent": "learn", **result}

    async def _build_cad(self, topic: str, project: str) -> Dict[str, Any]:
        from aether.pipeline.orchestrator import MasterPipeline

        pipe = MasterPipeline(self.router, self.settings, on_event=self.on_event)
        result = await pipe.build(topic, project)
        return {"intent": "build_cad", **result}

    def _smart_home(self, device: str, command: str, text: str) -> Dict[str, Any]:
        from aether.integrations.smart_home import SmartHome

        home = SmartHome(self.settings.homeassistant_url, self.settings.homeassistant_token)
        if not home.is_configured():
            return {
                "intent": "smart_home",
                "status": "not_configured",
                "message": "Set HOMEASSISTANT_URL and HOMEASSISTANT_TOKEN in .env to control devices.",
            }
        command = (command or _command_from_text(text)).lower()
        if not device or command == "status":
            return {"intent": "smart_home", "status": "ok", "entities": home.entities()[:50]}
        match = home.find_entity(device)
        if not match:
            return {"intent": "smart_home", "status": "not_found", "device": device}
        try:
            if command in ("on", "toggle") and match["state"] != "on":
                home.turn_on(match["entity_id"])
                action = "on"
            elif command in ("off", "toggle"):
                home.turn_off(match["entity_id"])
                action = "off"
            else:
                home.turn_on(match["entity_id"])
                action = "on"
            return {"intent": "smart_home", "status": "ok", "device": match["name"], "action": action}
        except Exception as exc:
            return {"intent": "smart_home", "status": "error", "error": str(exc)}

    def _chat(self, text: str) -> Dict[str, Any]:
        persona = build_persona(self.settings.persona, self.settings.assistant_name, self.settings.user_title)
        reply = self.router.complete(text, system=persona.system_prompt, task="chat")
        return {"intent": "chat", "status": "ok", "reply": reply}


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _command_from_text(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("turn off", "shut off", "switch off", "kill")):
        return "off"
    if any(w in t for w in ("turn on", "switch on", "enable", "activate")):
        return "on"
    if "toggle" in t:
        return "toggle"
    return "status"


def _keyword_intent(text: str) -> Dict[str, Any]:
    t = text.lower()
    if any(w in t for w in ("build", "engineer", "make me", "create", "scaffold", "backend", "api", "app", "website", "infrastructure")):
        if any(w in t for w in ("print", "3d", "cad", "robot body", "frame", "bracket", "enclosure", "mount")):
            return {"intent": "build_cad", "topic": text, "project": text}
        return {"intent": "build_app", "spec": text}
    if any(w in t for w in ("learn", "study", "research", "teach")):
        return {"intent": "learn", "topic": text}
    if any(w in t for w in ("light", "lamp", "plug", "switch", "thermostat", "lock", "scene", "living room", "bedroom")):
        return {"intent": "smart_home", "device": text, "command": _command_from_text(text)}
    return {"intent": "chat"}
