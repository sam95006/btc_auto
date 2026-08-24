"""Runtime-enforced bounded session lease (control-plane identity)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL

LEASE_ENV_JSON = "BOUNDED_SESSION_LEASE_JSON"
LEASE_ENV_PATH = "BOUNDED_SESSION_LEASE_PATH"
_FULL_SHA40 = re.compile(r"^[0-9a-f]{40}$")


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


def is_full_runtime_sha(value: str) -> bool:
    return bool(_FULL_SHA40.fullmatch(str(value or "").strip().lower()))


def runtime_sha() -> str:
    try:
        from backend.nexus_demo_execution.runtime_identity import read_container_baked_commit

        baked, _ = read_container_baked_commit()
        if baked:
            return baked
    except Exception:
        pass
    for key in (
        "GITHUB_SHA",
        "NEXUS_DEPLOYMENT_COMMIT",
        "NEXUS_SOURCE_COMMIT",
        "ZEABUR_GIT_COMMIT_SHA",
        "ZEABUR_ENV_GITHUB_SHA",
        "ZEABUR_ENV_ZEABUR_GIT_COMMIT_SHA",
        "SOURCE_COMMIT",
    ):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def validate_runtime_sha(*, expected: str, deployed: str) -> dict[str, Any]:
    expected = (expected or "").strip().lower()
    deployed = (deployed or "").strip().lower()
    if not expected:
        return {"ok": False, "reason": "expected_runtime_sha_missing"}
    if not deployed:
        return {"ok": False, "reason": "deployed_runtime_sha_missing"}
    if not is_full_runtime_sha(expected):
        return {"ok": False, "reason": "expected_runtime_sha_not_full_40_hex"}
    if not is_full_runtime_sha(deployed):
        return {"ok": False, "reason": "deployed_runtime_sha_not_full_40_hex"}
    if expected != deployed:
        return {"ok": False, "reason": "runtime_sha_mismatch"}
    return {"ok": True}


def lease_from_request(body: dict[str, Any] | None) -> RuntimeLease | None:
    if not isinstance(body, dict):
        return None
    lease_payload = body.get("lease")
    if isinstance(lease_payload, dict):
        return RuntimeLease.from_dict(lease_payload)
    return None


def load_runtime_lease_from_env() -> RuntimeLease | None:
    """Legacy/test-only env loader — production start uses signed POST body."""
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
    sha = validate_runtime_sha(expected=lease.expected_runtime_sha, deployed=runtime_sha())
    if not sha.get("ok"):
        return sha
    if not lease.session_id.startswith("NEXUS-DEMO-6H-V2-"):
        return {"ok": False, "reason": "runtime_session_id_prefix_mismatch"}
    return {"ok": True, "session_id": lease.session_id}


def lease_allows_new_entry(lease: RuntimeLease | None, *, learning_hold: bool = False) -> bool:
    if learning_hold:
        return False
    checked = validate_runtime_lease(lease)
    return bool(checked.get("ok"))
