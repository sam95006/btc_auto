"""Public-safe alert and notification payload models (PUB-K)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from backend.nexus_public_mobile_notify.constants import (
    ALERT_KINDS,
    ALERT_PRIORITIES,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_public_mobile_notify.hard_bans import (
    HardBanViolation,
    assert_no_private_fields,
    refuse_fabricated_live_alert,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PublicAlertLineage:
    """Lineage attached to every public alert (no fabrication concealment)."""

    source_system: str
    source_endpoint: str
    as_of: str
    retrieved_at: str
    freshness: str  # FRESH | STALE | DEGRADED | UNAVAILABLE | DEMO_DATA
    completeness: str  # COMPLETE | PARTIAL | UNKNOWN | DEMO_DATA
    lineage_id: str
    mode: str  # LIVE | DEMO_DATA | MOCK_IN_MEMORY

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PublicAlert:
    """Member-facing alert envelope."""

    alert_id: str
    kind: str
    priority: str
    title: str
    body: str
    decision_id: str | None
    deep_link: str
    created_at: str
    lineage: PublicAlertLineage
    public_payload: dict[str, Any] = field(default_factory=dict)
    schema: str = SCHEMA
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        assert_no_private_fields(d)
        return d


def _validate_kind(kind: str) -> str:
    if kind not in ALERT_KINDS:
        raise ValueError(f"unsupported alert kind: {kind}")
    return kind


def _validate_priority(priority: str) -> str:
    if priority not in ALERT_PRIORITIES:
        raise ValueError(f"unsupported alert priority: {priority}")
    return priority


def build_alert(
    *,
    kind: str,
    title: str,
    body: str,
    priority: str = "NORMAL",
    decision_id: str | None = None,
    deep_link: str,
    lineage: PublicAlertLineage,
    public_payload: Mapping[str, Any] | None = None,
    alert_id: str | None = None,
) -> PublicAlert:
    """Build a public-safe alert; refuse private fields and live fabrication."""
    kind = _validate_kind(kind)
    priority = _validate_priority(priority)
    payload = dict(public_payload or {})
    assert_no_private_fields(payload)

    if lineage.mode == "LIVE" and lineage.freshness == "DEMO_DATA":
        refuse_fabricated_live_alert()
    if lineage.mode == "LIVE" and not lineage.source_system:
        refuse_fabricated_live_alert()

    alert = PublicAlert(
        alert_id=alert_id or f"alert_{uuid4().hex}",
        kind=kind,
        priority=priority,
        title=title,
        body=body,
        decision_id=decision_id,
        deep_link=deep_link,
        created_at=_utc_now_iso(),
        lineage=lineage,
        public_payload=payload,
    )
    alert.to_dict()  # boundary check
    return alert


def decision_status_alert(
    *,
    decision_id: str,
    status: str,
    title: str,
    body: str,
    deep_link: str,
    lineage: PublicAlertLineage,
    priority: str = "NORMAL",
) -> PublicAlert:
    return build_alert(
        kind="DECISION_STATUS",
        title=title,
        body=body,
        priority=priority,
        decision_id=decision_id,
        deep_link=deep_link,
        lineage=lineage,
        public_payload={"decision_status": status},
    )


def risk_alert(
    *,
    decision_id: str | None,
    risk_code: str,
    severity: str,
    title: str,
    body: str,
    deep_link: str,
    lineage: PublicAlertLineage,
    priority: str = "HIGH",
) -> PublicAlert:
    return build_alert(
        kind="RISK",
        title=title,
        body=body,
        priority=priority,
        decision_id=decision_id,
        deep_link=deep_link,
        lineage=lineage,
        public_payload={"risk_code": risk_code, "severity": severity},
    )


def data_stale_alert(
    *,
    dataset: str,
    stale_age_seconds: int,
    title: str,
    body: str,
    deep_link: str,
    lineage: PublicAlertLineage,
    priority: str = "NORMAL",
) -> PublicAlert:
    if lineage.freshness not in {"STALE", "DEGRADED", "UNAVAILABLE", "DEMO_DATA"} and lineage.mode == "LIVE":
        raise HardBanViolation(
            "HARD BAN: DATA_STALE alert requires STALE/DEGRADED/UNAVAILABLE freshness in LIVE mode"
        )
    return build_alert(
        kind="DATA_STALE",
        title=title,
        body=body,
        priority=priority,
        deep_link=deep_link,
        lineage=lineage,
        public_payload={"dataset": dataset, "stale_age_seconds": stale_age_seconds},
    )


def thesis_invalidated_alert(
    *,
    decision_id: str,
    thesis_id: str,
    reason_code: str,
    title: str,
    body: str,
    deep_link: str,
    lineage: PublicAlertLineage,
    priority: str = "HIGH",
) -> PublicAlert:
    return build_alert(
        kind="THESIS_INVALIDATED",
        title=title,
        body=body,
        priority=priority,
        decision_id=decision_id,
        deep_link=deep_link,
        lineage=lineage,
        public_payload={"thesis_id": thesis_id, "reason_code": reason_code},
    )


def market_anomaly_alert(
    *,
    symbol: str,
    anomaly_code: str,
    title: str,
    body: str,
    deep_link: str,
    lineage: PublicAlertLineage,
    priority: str = "HIGH",
) -> PublicAlert:
    return build_alert(
        kind="MARKET_ANOMALY",
        title=title,
        body=body,
        priority=priority,
        deep_link=deep_link,
        lineage=lineage,
        public_payload={"symbol": symbol, "anomaly_code": anomaly_code},
    )


def demo_lineage(*, lineage_id: str | None = None) -> PublicAlertLineage:
    now = _utc_now_iso()
    return PublicAlertLineage(
        source_system="DEMO_PREVIEW",
        source_endpoint="demo://alerts",
        as_of=now,
        retrieved_at=now,
        freshness="DEMO_DATA",
        completeness="DEMO_DATA",
        lineage_id=lineage_id or f"demo_{uuid4().hex[:12]}",
        mode="DEMO_DATA",
    )
