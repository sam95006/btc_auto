"""Read-only federation HTTP client — GET only, host allowlist, SSRF-safe."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from backend.nexus_control_plane import (
    DATA_STATUS_LIVE,
    DATA_STATUS_SCHEMA_MISMATCH,
    DATA_STATUS_SERVICE_UNAVAILABLE,
    DATA_STATUS_STALE,
    DATA_STATUS_UNKNOWN,
)
from backend.nexus_control_plane import federation_counters as counters
from backend.nexus_control_plane.service_registry import ServiceRegistry

FORBIDDEN_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
DEFAULT_TIMEOUT_SEC = 8.0
DEFAULT_MAX_BYTES = 2_000_000
STALE_AFTER_SEC = 120.0
SECRET_MARKERS = ("api_key", "api_secret", "secret", "password", "token", "authorization", "signature")


class FederationSecurityError(RuntimeError):
    pass


def redact_secrets(payload: Any) -> Any:
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if any(m in str(k).lower() for m in SECRET_MARKERS):
                out[k] = "[REDACTED]"
                counters.incr("secret_redaction_count")
            else:
                out[k] = redact_secrets(v)
        return out
    if isinstance(payload, list):
        return [redact_secrets(x) for x in payload]
    return payload


@dataclass
class CircuitState:
    failures: int = 0
    open_until: float = 0.0

    def allow(self, now: float | None = None) -> bool:
        t = now or time.time()
        return t >= self.open_until

    def record_failure(self, *, threshold: int = 3, cooldown_sec: float = 30.0) -> None:
        self.failures += 1
        if self.failures >= threshold:
            self.open_until = time.time() + cooldown_sec

    def record_success(self) -> None:
        self.failures = 0
        self.open_until = 0.0


@dataclass
class FederationClient:
    registry: ServiceRegistry
    timeout_sec: float = DEFAULT_TIMEOUT_SEC
    max_bytes: int = DEFAULT_MAX_BYTES
    _circuits: dict[str, CircuitState] = field(default_factory=dict)

    def attempt_write(self, *_a: Any, **_k: Any) -> dict[str, Any]:
        """Explicitly rejected — Control Plane must never write via federation."""
        counters.incr("federation_write_attempt_count")
        return {
            "ok": False,
            "error": "CONTROL_PLANE_READ_ONLY",
            "data_status": DATA_STATUS_UNKNOWN,
            "payload": None,
        }

    def get_json(self, role: str, path: str) -> dict[str, Any]:
        """GET JSON from a registered service role. Never POST/PUT/PATCH/DELETE."""
        counters.incr("federation_get_count")
        rec = self.registry.get(role)
        if rec is None:
            return {
                "ok": False,
                "data_status": DATA_STATUS_UNKNOWN,
                "error": "unknown_service_role",
                "payload": None,
            }
        url = f"{rec.service_url.rstrip('/')}{path}"
        try:
            self._assert_url_allowed(url)
        except FederationSecurityError as exc:
            counters.incr("ssrf_block_count")
            return {
                "ok": False,
                "data_status": DATA_STATUS_UNKNOWN,
                "error": str(exc),
                "payload": None,
                "source_service": rec.service_name,
            }
        circuit = self._circuits.setdefault(role, CircuitState())
        if not circuit.allow():
            counters.incr("circuit_open_count")
            return {
                "ok": False,
                "data_status": DATA_STATUS_SERVICE_UNAVAILABLE,
                "error": "circuit_open",
                "payload": None,
                "source_service": rec.service_name,
                "source_url": rec.service_url,
            }
        try:
            req = Request(
                url,
                method="GET",
                headers={"User-Agent": "NEXUS-ControlPlane/1.0", "Accept": "application/json"},
            )
            with urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read(self.max_bytes + 1)
            if len(raw) > self.max_bytes:
                circuit.record_failure()
                counters.incr("schema_mismatch_count")
                return {
                    "ok": False,
                    "data_status": DATA_STATUS_SCHEMA_MISMATCH,
                    "error": "response_too_large",
                    "payload": None,
                    "source_service": rec.service_name,
                }
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                circuit.record_failure()
                counters.incr("schema_mismatch_count")
                return {
                    "ok": False,
                    "data_status": DATA_STATUS_SCHEMA_MISMATCH,
                    "error": "non_object_json",
                    "payload": None,
                    "source_service": rec.service_name,
                }
            circuit.record_success()
            fetched_at = time.time()
            return {
                "ok": True,
                "data_status": DATA_STATUS_LIVE,
                "error": "",
                "payload": redact_secrets(payload),
                "source_service": rec.service_name,
                "source_url": rec.service_url,
                "fetched_at": fetched_at,
                "freshness_sec": 0.0,
            }
        except HTTPError as exc:
            circuit.record_failure()
            return {
                "ok": False,
                "data_status": DATA_STATUS_SERVICE_UNAVAILABLE,
                "error": f"http_{exc.code}",
                "payload": None,
                "source_service": rec.service_name,
            }
        except TimeoutError:
            circuit.record_failure()
            counters.incr("service_timeout_count")
            return {
                "ok": False,
                "data_status": DATA_STATUS_SERVICE_UNAVAILABLE,
                "error": "TimeoutError",
                "payload": None,
                "source_service": rec.service_name,
            }
        except (URLError, json.JSONDecodeError) as exc:
            circuit.record_failure()
            if isinstance(exc, json.JSONDecodeError):
                counters.incr("schema_mismatch_count")
                status = DATA_STATUS_SCHEMA_MISMATCH
            else:
                status = DATA_STATUS_SERVICE_UNAVAILABLE
            return {
                "ok": False,
                "data_status": status,
                "error": type(exc).__name__,
                "payload": None,
                "source_service": rec.service_name if rec else role,
            }

    def _assert_url_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "http"}:
            raise FederationSecurityError("SECURITY_BLOCKED_UNKNOWN_SERVICE_HOST")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise FederationSecurityError("SECURITY_BLOCKED_INSECURE_SCHEME")
        host = (parsed.hostname or "").lower()
        if not host or host not in self.registry.allowed_hosts():
            raise FederationSecurityError("SECURITY_BLOCKED_UNKNOWN_SERVICE_HOST")
        if host in {"metadata.google.internal", "169.254.169.254"} or host.startswith("10."):
            raise FederationSecurityError("SECURITY_BLOCKED_UNKNOWN_SERVICE_HOST")
        if host.startswith("169.254.") or host in {"0.0.0.0"}:
            raise FederationSecurityError("SECURITY_BLOCKED_UNKNOWN_SERVICE_HOST")

    @staticmethod
    def mark_stale(result: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        out = dict(result)
        fetched = out.get("fetched_at")
        if fetched is None:
            return out
        age = (now or time.time()) - float(fetched)
        out["freshness_sec"] = age
        if out.get("ok") and age > STALE_AFTER_SEC:
            out["data_status"] = DATA_STATUS_STALE
        return out
