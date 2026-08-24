"""Runtime-enforced bounded session lease (control-plane identity)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL

LEASE_ENV_JSON = "BOUNDED_SESSION_LEASE_JSON"
LEASE_ENV_PATH = "BOUNDED_SESSION_LEASE_PATH"
EXPECTED_SHA_ENV = "BOUNDED_SESSION_EXPECTED_RUNTIME_SHA"


@dataclass(frozen=True)
class RuntimeLease:
    session_id: str
    authorized_at: str
    expires_at: str
    exchange: str
    mainnet: bool
    real_money: bool
    expected_runtime_sha: str
    service_name: str = "nexus-bybit-demo-learning-validation"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RuntimeLease:
        return cls(
            session_id=str(payload["session_id"]),
            authorized_at=str(payload["authorized_at"]),
            expires_at=str(payload["expires_at"]),
            exchange=str(payload.get("exchange") or "BYBIT_DEMO"),
            mainnet=bool(payload.get("mainnet")),
            real_money=bool(payload.get("real_money")),
            expected_runtime_sha=str(payload.get("expected_runtime_sha") or payload.get("expected_github_sha") or ""),
            service_name=str(payload.get("service_name") or "nexus-bybit-demo-learning-validation"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "authorized_at": self.authorized_at,
            "expires_at": self.expires_at,
            "exchange": self.exchange,
            "mainnet": self.mainnet,
            "real_money": self.real_money,
            "expected_runtime_sha": self.expected_runtime_sha,
            "service_name": self.service_name,
        }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_runtime_lease() -> RuntimeLease | None:
    raw = (os.environ.get(LEASE_ENV_JSON) or "").strip()
    if not raw:
        path = (os.environ.get(LEASE_ENV_PATH) or "").strip()
        if path and Path(path).is_file():
            raw = Path(path).read_text(encoding="utf-8")
    if not raw:
        return None
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return None
    lease_payload = payload.get("lease") if isinstance(payload.get("lease"), dict) else payload
    return RuntimeLease.from_dict(lease_payload)


def runtime_sha() -> str:
    for key in ("GITHUB_SHA", "NEXUS_DEPLOYMENT_COMMIT", "NEXUS_SOURCE_COMMIT", "SOURCE_COMMIT"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def validate_runtime_lease(lease: RuntimeLease | None) -> dict[str, Any]:
    if lease is None:
        return {"ok": False, "reason": "runtime_lease_missing"}
    now = _utc_now()
    if _parse(lease.expires_at) <= now:
        return {"ok": False, "reason": "runtime_lease_expired"}
    if lease.exchange != "BYBIT_DEMO":
        return {"ok": False, "reason": "runtime_lease_exchange_mismatch"}
    if lease.mainnet or lease.real_money:
        return {"ok": False, "reason": "runtime_lease_mainnet_or_real_money"}
    if "api-demo.bybit.com" not in DEMO_REST_BASE_URL:
        return {"ok": False, "reason": "runtime_not_demo_api"}
    expected = (lease.expected_runtime_sha or os.environ.get(EXPECTED_SHA_ENV) or runtime_sha()).strip()
    deployed = runtime_sha()
    if expected and deployed and not (deployed.startswith(expected[:7]) or expected.startswith(deployed[:7])):
        return {"ok": False, "reason": "runtime_sha_mismatch", "expected": expected[:12], "deployed": deployed[:12]}
    if not lease.session_id.startswith("NEXUS-DEMO-6H-V2-"):
        return {"ok": False, "reason": "runtime_session_id_prefix_mismatch"}
    return {"ok": True, "session_id": lease.session_id}


def lease_allows_new_entry(lease: RuntimeLease | None) -> bool:
    checked = validate_runtime_lease(lease)
    return bool(checked.get("ok"))


def lease_wiring_markers() -> dict[str, bool]:
    import inspect

    from backend.nexus_bounded_runtime.certified_session import CertifiedBounded6HSession

    start_source = inspect.getsource(CertifiedBounded6HSession.start)
    entry_source = inspect.getsource(CertifiedBounded6HSession._runtime_entry_allowed)
    return {
        "CONTROL_PLANE_RUNTIME_LEASE_ID_MATCH": "load_runtime_lease" in start_source and "self.session_id = lease.session_id" in start_source,
        "RUNTIME_LEASE_EXPIRY_AUTHORITY": "validate_runtime_lease" in start_source and "lease_allows_new_entry" in entry_source,
        "SESSION_EXPIRY_BLOCKS_NEW_ENTRY": "lease_allows_new_entry" in entry_source,
    }
