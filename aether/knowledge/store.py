"""Persistent knowledge and project artifacts per topic."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:80] or "topic"


class KnowledgeStore:
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.memory_path = self.data_dir / "memory.json"
        self.projects_dir = self.data_dir / "projects"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def _load_all(self) -> Dict[str, Any]:
        if self.memory_path.exists():
            return json.loads(self.memory_path.read_text(encoding="utf-8"))
        return {}

    def _save_all(self, data: Dict[str, Any]) -> None:
        self.memory_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_topics(self) -> List[str]:
        return list(self._load_all().keys())

    def get(self, topic: str) -> Optional[Dict[str, Any]]:
        return self._load_all().get(topic)

    def save_learned(
        self,
        topic: str,
        *,
        study_sheet: str,
        curriculum: str = "",
        depth: str = "graduate",
        synthesis: Optional[Dict[str, Any]] = None,
    ) -> str:
        data = self._load_all()
        slug = slugify(topic)
        data[topic] = {
            "topic": topic,
            "slug": slug,
            "depth": depth,
            "study_sheet": study_sheet,
            "curriculum": curriculum,
            "synthesis": synthesis or {},
            "projects": data.get(topic, {}).get("projects", []),
        }
        self._save_all(data)
        (self.projects_dir / slug).mkdir(parents=True, exist_ok=True)
        return slug

    def project_dir(self, topic: str) -> Path:
        entry = self.get(topic) or {}
        slug = entry.get("slug") or slugify(topic)
        path = self.projects_dir / slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    def register_project(self, topic: str, project_name: str, artifacts: Dict[str, str]) -> Dict[str, Any]:
        data = self._load_all()
        if topic not in data:
            data[topic] = {"topic": topic, "slug": slugify(topic), "projects": []}
        record = {
            "name": project_name,
            "artifacts": artifacts,
        }
        data[topic].setdefault("projects", []).append(record)
        self._save_all(data)
        return record
