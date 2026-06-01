"""Kill switch and pause control for autonomous runs.

Two ways to stop a run:
1. In-process: call control.stop() (the web Stop button / CLI Ctrl-C handler).
2. From anywhere: create a file named STOP in the data dir
   (e.g. `aether stop`, or just create data/STOP). Checked every loop.

This means even if the UI is unreachable, dropping a STOP file halts the agent.
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from pathlib import Path
from typing import Dict, List


class ControlState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"


class AutonomyControl:
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.stop_file = self.data_dir / "STOP"
        self.pause_file = self.data_dir / "PAUSE"
        self._lock = threading.Lock()
        self._state = ControlState.IDLE
        self._activity: List[Dict] = []
        self._pending_approval: Dict | None = None
        self._approval_event = threading.Event()
        self._approval_result = False
        # Clear any stale sentinels from a previous crash.
        self._clear_sentinels()

    def _clear_sentinels(self) -> None:
        for f in (self.stop_file, self.pause_file):
            try:
                f.unlink()
            except FileNotFoundError:
                pass

    # ----------------------------------------------------------------- state
    @property
    def state(self) -> ControlState:
        with self._lock:
            return self._state

    def set_state(self, state: ControlState) -> None:
        with self._lock:
            self._state = state

    def start(self) -> None:
        self._clear_sentinels()
        self._approval_event.clear()
        self.set_state(ControlState.RUNNING)
        self.log("control", "Autonomous run started")

    def stop(self, reason: str = "user requested") -> None:
        self.set_state(ControlState.STOPPING)
        try:
            self.stop_file.write_text(reason, encoding="utf-8")
        except OSError:
            pass
        # Unblock anyone waiting on approval.
        self._approval_result = False
        self._approval_event.set()
        self.log("control", f"STOP requested: {reason}")

    def pause(self) -> None:
        try:
            self.pause_file.write_text("paused", encoding="utf-8")
        except OSError:
            pass
        self.set_state(ControlState.PAUSED)
        self.log("control", "Paused")

    def resume(self) -> None:
        try:
            self.pause_file.unlink()
        except FileNotFoundError:
            pass
        self.set_state(ControlState.RUNNING)
        self.log("control", "Resumed")

    def finish(self) -> None:
        self.set_state(ControlState.STOPPED)
        self._clear_sentinels()

    # ----------------------------------------------------------------- checks
    def should_stop(self) -> bool:
        if self.state in (ControlState.STOPPING, ControlState.STOPPED):
            return True
        return self.stop_file.exists()

    def is_paused(self) -> bool:
        return self.state == ControlState.PAUSED or self.pause_file.exists()

    def wait_while_paused(self, poll: float = 0.5, timeout: float = 600) -> None:
        waited = 0.0
        while self.is_paused() and not self.should_stop() and waited < timeout:
            time.sleep(poll)
            waited += poll

    # -------------------------------------------------------------- approvals
    def request_approval(self, action: Dict, timeout: float = 120) -> bool:
        """Block the loop until the user approves/denies, or timeout (deny)."""
        with self._lock:
            self._pending_approval = action
            self._approval_event.clear()
        self.log("approval_request", f"Waiting for approval: {action.get('description', '')[:120]}")
        got = self._approval_event.wait(timeout=timeout)
        with self._lock:
            self._pending_approval = None
        if not got:
            self.log("approval_timeout", "No response; denied by default")
            return False
        return self._approval_result

    def submit_approval(self, approved: bool) -> None:
        self._approval_result = approved
        self._approval_event.set()
        self.log("approval_response", "approved" if approved else "denied")

    @property
    def pending_approval(self) -> Dict | None:
        with self._lock:
            return self._pending_approval

    # ------------------------------------------------------------- activity
    def log(self, kind: str, message: str, data: Dict | None = None) -> Dict:
        entry = {"ts": time.time(), "kind": kind, "message": message, "data": data or {}}
        with self._lock:
            self._activity.append(entry)
            self._activity = self._activity[-500:]
        return entry

    def activity(self, limit: int = 100) -> List[Dict]:
        with self._lock:
            return list(self._activity[-limit:])

    def status(self) -> Dict:
        return {
            "state": self.state.value,
            "should_stop": self.should_stop(),
            "paused": self.is_paused(),
            "pending_approval": self.pending_approval,
            "activity_count": len(self._activity),
        }
