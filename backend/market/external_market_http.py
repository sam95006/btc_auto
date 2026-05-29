"""Minimal HTTP helper for external market APIs (no secrets in logs)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return float(default)


class ExternalMarketHttpError(RuntimeError):
    pass


class ExternalMarketHttp:
    def __init__(self, timeout: float = 12.0):
        self.timeout = float(timeout)

    def get_json(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        query = urllib.parse.urlencode(params or {}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        request = urllib.request.Request(full_url, headers=headers or {}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                message = payload.get("status", {}).get("error_message") or payload.get("msg") or str(payload)
            except Exception:
                message = str(exc)
            raise ExternalMarketHttpError(f"HTTP {exc.code}: {message}") from exc
        except Exception as exc:
            raise ExternalMarketHttpError(str(exc)) from exc


class TimedCache:
    def __init__(self, ttl_seconds: float):
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self._expires_at = 0.0
        self._payload: Any = None

    def get(self):
        if self._payload is not None and time.time() < self._expires_at:
            return self._payload
        return None

    def set(self, payload):
        self._payload = payload
        self._expires_at = time.time() + self.ttl_seconds
