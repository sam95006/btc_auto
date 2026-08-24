"""Founder-approved bounded Bybit Demo session lease (6H max)."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL
from backend.nexus_demo_execution.session_limits import SESSION_DURATION_SEC

SESSION_DURATION_HOURS = SESSION_DURATION_SEC // 3600
FOUNDER_PHRASE = "START_NEXUS_BYBIT_DEMO_BOUNDED_6H_SESSION"
EXCHANGE = "BYBIT_DEMO"


@dataclass(frozen=True)
class BoundedSessionLease:
    session_id: str
    authorized_at: str
    expires_at: str
    exchange: str
    mainnet: bool
    real_money: bool
    founder_phrase_hash: str
    service_name: str = "nexus-bybit-demo-learning-validation"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BoundedSessionLease:
        return cls(
            session_id=str(payload["session_id"]),
            authorized_at=str(payload["authorized_at"]),
            expires_at=str(payload["expires_at"]),
            exchange=str(payload.get("exchange") or EXCHANGE),
            mainnet=bool(payload.get("mainnet")),
            real_money=bool(payload.get("real_money")),
            founder_phrase_hash=str(payload["founder_phrase_hash"]),
            service_name=str(payload.get("service_name") or "nexus-bybit-demo-learning-validation"),
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _phrase_hash(phrase: str) -> str:
    return hashlib.sha256(phrase.encode("utf-8")).hexdigest()


def create_lease(*, founder_phrase: str, now: datetime | None = None) -> BoundedSessionLease:
    if founder_phrase.strip() != FOUNDER_PHRASE:
        raise ValueError("founder_phrase_invalid")
    start = now or _utc_now()
    end = start + timedelta(seconds=SESSION_DURATION_SEC)
    nonce = uuid.uuid4().hex[:8]
    session_id = f"NEXUS-BOUNDED-DEMO-6H-{start.strftime('%Y%m%dT%H%M%SZ')}-{nonce}"
    return BoundedSessionLease(
        session_id=session_id,
        authorized_at=_fmt(start),
        expires_at=_fmt(end),
        exchange=EXCHANGE,
        mainnet=False,
        real_money=False,
        founder_phrase_hash=_phrase_hash(FOUNDER_PHRASE),
    )


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_expired(lease: BoundedSessionLease, *, now: datetime | None = None) -> bool:
    return (now or _utc_now()) >= parse_utc(lease.expires_at)


def lease_valid(
    lease: BoundedSessionLease,
    *,
    now: datetime | None = None,
    kill_switch_engaged: bool = False,
    unresolved_intent_count: int = 0,
) -> bool:
    if kill_switch_engaged:
        return False
    if unresolved_intent_count > 0:
        return False
    if lease.mainnet or lease.real_money:
        return False
    if lease.exchange != EXCHANGE:
        return False
    if lease.founder_phrase_hash != _phrase_hash(FOUNDER_PHRASE):
        return False
    return not is_expired(lease, now=now)


def writes_allowed(
    lease: BoundedSessionLease,
    *,
    now: datetime | None = None,
    kill_switch_engaged: bool = False,
    unresolved_intent_count: int = 0,
    risk_engine_allows: bool = True,
) -> bool:
    return lease_valid(
        lease,
        now=now,
        kill_switch_engaged=kill_switch_engaged,
        unresolved_intent_count=unresolved_intent_count,
    ) and risk_engine_allows


def expiry_blocks_new_entry(lease: BoundedSessionLease, *, now: datetime | None = None) -> bool:
    return is_expired(lease, now=now)


def save_lease(lease: BoundedSessionLease, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lease.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


def load_lease(path: Path) -> BoundedSessionLease | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return BoundedSessionLease.from_dict(payload)


def demo_api_base_ok(base_url: str) -> bool:
    return "api-demo.bybit.com" in base_url or base_url.rstrip("/") == DEMO_REST_BASE_URL.rstrip("/")
