"""Safe file access within allowed directories."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from aether.integrations.permissions import PermissionManager


class FileSystemGuard:
    def __init__(
        self,
        allowed_roots: List[str],
        max_file_size: int = 10_485_760,
        permissions: Optional[PermissionManager] = None,
    ):
        self.allowed_roots = [Path(r).resolve() for r in allowed_roots]
        self.max_file_size = max_file_size
        self.permissions = permissions or PermissionManager(require=False)

    def _is_allowed(self, path: Path) -> bool:
        resolved = path.resolve()
        return any(
            resolved == root or root in resolved.parents for root in self.allowed_roots
        )

    def read_text(self, path: str) -> str:
        p = Path(path).expanduser()
        if not self._is_allowed(p):
            raise PermissionError(f"Path not allowed: {p}")
        if not self.permissions.request(
            f"file_read:{p.parent}",
            f"Read file {p}?",
        ):
            raise PermissionError("User denied file read")
        if p.stat().st_size > self.max_file_size:
            raise ValueError(f"File too large (max {self.max_file_size} bytes)")
        return p.read_text(encoding="utf-8", errors="replace")

    def write_text(self, path: str, content: str) -> None:
        p = Path(path).expanduser()
        if not self._is_allowed(p):
            raise PermissionError(f"Path not allowed: {p}")
        if not self.permissions.request(
            f"file_write:{p.parent}",
            f"Write file {p}?",
        ):
            raise PermissionError("User denied file write")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
