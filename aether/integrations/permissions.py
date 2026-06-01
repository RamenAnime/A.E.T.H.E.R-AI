"""Permission gating for sensitive actions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Literal, Optional

Decision = Literal["always_approve", "always_deny", "unknown"]


class PermissionManager:
    def __init__(self, store_path: str = "./data/permissions.json", require: bool = True):
        self.store_path = Path(store_path)
        self.require = require
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._rules: Dict[str, str] = self._load()

    def _load(self) -> Dict[str, str]:
        if self.store_path.exists():
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        return {}

    def _save(self) -> None:
        self.store_path.write_text(json.dumps(self._rules, indent=2), encoding="utf-8")

    def check(self, permission_key: str) -> Decision:
        decision = self._rules.get(permission_key)
        if decision in ("always_approve", "always_deny"):
            return decision  # type: ignore[return-value]
        return "unknown"

    def request(
        self,
        permission_key: str,
        description: str,
        timeout_seconds: int = 30,
    ) -> bool:
        if not self.require:
            return True
        cached = self.check(permission_key)
        if cached == "always_approve":
            return True
        if cached == "always_deny":
            return False
        print(f"\n[Permission required] {permission_key}")
        print(description)
        print("Allow this action? [y/N/a=always yes/d=always no]")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                answer = input("> ").strip().lower()
            except EOFError:
                return False
            if answer in ("y", "yes"):
                return True
            if answer in ("a", "always"):
                self.remember(permission_key, "always_approve")
                return True
            if answer in ("d", "deny-always"):
                self.remember(permission_key, "always_deny")
                return False
            if answer in ("", "n", "no"):
                return False
        print("Permission timed out.")
        return False

    def remember(self, permission_key: str, decision: Decision) -> None:
        if decision == "unknown":
            return
        self._rules[permission_key] = decision
        self._save()
