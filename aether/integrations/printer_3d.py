"""3D printer control via OctoPrint-compatible API (OctoPrint, Moonraker+OctoPrint proxy)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class Printer3D:
    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        api_key: str = "",
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method: str, path: str, data: Optional[bytes] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Printer API error {exc.code}: {err_body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach printer at {self.base_url}: {exc}") from exc

    def is_configured(self) -> bool:
        return bool(self.base_url)

    def ping(self) -> bool:
        try:
            self._request("GET", "/api/version")
            return True
        except Exception:
            return False

    def status(self) -> Dict[str, Any]:
        job = self._request("GET", "/api/job")
        printer = self._request("GET", "/api/printer")
        temp = self._request("GET", "/api/printer/tool")
        return {
            "state": job.get("state", "unknown"),
            "progress": job.get("progress", {}),
            "printer": printer.get("state", {}),
            "temperature": temp,
            "online": True,
        }

    def upload_stl(self, stl_path: Path, select: bool = True) -> Dict[str, Any]:
        """Upload STL to OctoPrint files (multipart simplified via files API)."""
        import mimetypes
        from urllib.request import build_opener, HTTPCookieProcessor

        boundary = "----AetherBoundary"
        file_bytes = stl_path.read_bytes()
        filename = stl_path.name
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mimetypes.guess_type(filename)[0] or 'application/octet-stream'}\r\n\r\n"
        ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

        url = f"{self.base_url}/api/files/local"
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if select:
            self.select_file(filename)
        return result

    def select_file(self, filename: str) -> None:
        import urllib.parse

        enc = urllib.parse.quote(filename, safe="")
        self._request("POST", f"/api/files/local/{enc}", data=b'{"command":"select"}')

    def start_print(self) -> Dict[str, Any]:
        return self._request("POST", "/api/job", data=b'{"command":"start"}')

    def pause_print(self) -> Dict[str, Any]:
        return self._request("POST", "/api/job", data=b'{"command":"pause"}')

    def cancel_print(self) -> Dict[str, Any]:
        return self._request("POST", "/api/job", data=b'{"command":"cancel"}')
