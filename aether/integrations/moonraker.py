"""Moonraker API (Klipper): popular on modded Ender 3 setups."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class MoonrakerClient:
    def __init__(self, base_url: str = "http://localhost:7125", api_key: str = "", timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self, content_type: str = "application/json") -> Dict[str, str]:
        h = {}
        if content_type:
            h["Content-Type"] = content_type
        if self.api_key:
            h["X-Api-Key"] = self.api_key
        return h

    def _request(self, method: str, path: str, data: Optional[bytes] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
                parsed = json.loads(body) if body else {}
                if isinstance(parsed, dict) and "result" in parsed:
                    return parsed["result"] if parsed["result"] is not None else parsed
                return parsed
        except HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Moonraker error {exc.code}: {err}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach Moonraker at {self.base_url}: {exc}") from exc

    def ping(self) -> bool:
        try:
            self._request("GET", "/server/info")
            return True
        except Exception:
            return False

    def status(self) -> Dict[str, Any]:
        q = self._request(
            "GET",
            "/printer/objects/query?print_stats&display_status&heater_bed&extruder",
        )
        return {"online": True, "objects": q.get("status", q)}

    def upload_gcode(self, path: Path, start: bool = False) -> Dict[str, Any]:
        boundary = "----AetherMoon"
        file_bytes = path.read_bytes()
        filename = path.name
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mimetypes.guess_type(filename)[0] or 'application/octet-stream'}\r\n\r\n"
        ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

        url = f"{self.base_url}/server/files/upload"
        req = Request(
            url,
            data=body,
            headers=self._headers(f"multipart/form-data; boundary={boundary}"),
            method="POST",
        )
        with urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        item = result.get("item", result)
        root = item.get("root", "gcodes") if isinstance(item, dict) else "gcodes"
        name = item.get("path", filename) if isinstance(item, dict) else filename
        if start:
            self.start_print(f"{root}/{name}" if root else name)
        return result

    def upload_stl(self, stl_path: Path, start: bool = False) -> Dict[str, Any]:
        """Upload STL; user must slice in Mainsail/Fluidd or use pre-sliced gcode."""
        return self.upload_gcode(stl_path, start=False)

    def start_print(self, filename: str) -> Dict[str, Any]:
        enc = quote(filename, safe="")
        return self._request("POST", f"/printer/print/start?filename={enc}")

    def pause_print(self) -> Dict[str, Any]:
        return self._request("POST", "/printer/print/pause")

    def cancel_print(self) -> Dict[str, Any]:
        return self._request("POST", "/printer/print/cancel")
