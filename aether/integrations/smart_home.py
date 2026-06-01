"""Smart home control via a local Home Assistant instance.

Home Assistant runs on your own network (local-first) and exposes a REST API.
Set HOMEASSISTANT_URL and HOMEASSISTANT_TOKEN (a long-lived access token) in .env.

This client can list devices, read states, and call services (turn things on/off,
set brightness, run scenes, etc.). It speaks plain HTTP so it has no heavy deps.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class SmartHome:
    def __init__(self, base_url: str = "", token: str = "", timeout: float = 8.0):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.base_url and self.token)

    def _request(self, method: str, path: str, body: Optional[Dict] = None) -> Any:
        url = f"{self.base_url}/api/{path.lstrip('/')}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    def ping(self) -> bool:
        if not self.is_configured():
            return False
        try:
            self._request("GET", "/")
            return True
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def states(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/states") or []

    def entities(self, domain: Optional[str] = None) -> List[Dict[str, str]]:
        """Simplified list of entities: id, name, state, domain."""
        out: List[Dict[str, str]] = []
        for s in self.states():
            entity_id = s.get("entity_id", "")
            dom = entity_id.split(".")[0] if "." in entity_id else ""
            if domain and dom != domain:
                continue
            out.append(
                {
                    "entity_id": entity_id,
                    "name": s.get("attributes", {}).get("friendly_name", entity_id),
                    "state": s.get("state", ""),
                    "domain": dom,
                }
            )
        return out

    def get_state(self, entity_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/states/{entity_id}")

    def call_service(self, domain: str, service: str, data: Optional[Dict] = None) -> Any:
        return self._request("POST", f"/services/{domain}/{service}", data or {})

    def turn_on(self, entity_id: str, **attrs: Any) -> Any:
        domain = entity_id.split(".")[0]
        return self.call_service(domain, "turn_on", {"entity_id": entity_id, **attrs})

    def turn_off(self, entity_id: str) -> Any:
        domain = entity_id.split(".")[0]
        return self.call_service(domain, "turn_off", {"entity_id": entity_id})

    def find_entity(self, query: str) -> Optional[Dict[str, str]]:
        """Fuzzy match an entity by friendly name or id."""
        q = query.lower().strip()
        candidates = self.entities()
        for e in candidates:
            if q == e["name"].lower() or q == e["entity_id"].lower():
                return e
        for e in candidates:
            if q in e["name"].lower() or q in e["entity_id"].lower():
                return e
        return None
