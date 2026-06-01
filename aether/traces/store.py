"""SQLite trace logging for tasks and chat."""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


class TraceStore:
    def __init__(self, db_path: str = "./data/traces.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL,
                    agent TEXT,
                    task_id TEXT,
                    status TEXT,
                    payload TEXT,
                    created_at REAL NOT NULL
                );
                """
            )

    def log(
        self,
        kind: str,
        status: str,
        payload: str = "",
        agent: str = "",
        task_id: str = "",
        trace_id: Optional[str] = None,
    ) -> str:
        tid = trace_id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO traces
                (trace_id, kind, agent, task_id, status, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (tid, kind, agent, task_id, status, payload, time.time()),
            )
        return tid

    def recent(self, limit: int = 20, kind: Optional[str] = None) -> list[Dict[str, Any]]:
        with self._connect() as conn:
            if kind:
                rows = conn.execute(
                    "SELECT * FROM traces WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM traces ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]
