"""PUB18 Alert Engine — read-only envelope model + builders."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from backend.nexus_pub18_alert_engine.constants import (
    ALERT_KIND_LABELS,
    ALERT_KINDS,
    DATA_CLASS_LABELS,
    FRESHNESS_STATES,
    SCHEMA,
    SCHEMA_VERSION,
    SEVERITIES,
)
from backend.nexus_pub18_alert_engine.hard_bans import (
    HardBanViolation,
    assert_no_forbidden_keys,
    assert_no_hype_phrases,
    assert_public_safe,
    assert_stale_has_indicator,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class AlertEnvelope:
    """Shared web/mobile read-only alert envelope."""

    alert_id: str
    kind: str
    source: str
    as_of: str
    freshness: str
    data_class: str
    decision_id: str | None
    reason: str
    severity: str
    public_safe: bool
    title: str
    body: str
    label: str
    schema: str = SCHEMA
    schema_version: str = SCHEMA_VERSION
    read_only: bool = True
    actionable_trade: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        assert_no_forbidden_keys(payload)
        assert_public_safe(payload)
        assert_no_hype_phrases(payload.get("title", ""), payload.get("body", ""), payload.get("reason", ""))
        assert_stale_has_indicator(
            freshness=str(payload.get("freshness") or ""),
            data_class=str(payload.get("data_class") or ""),
        )
        if payload.get("data_class") == "LIVE_READ_ONLY" and payload.get("freshness") in {
            "DEMO_DATA",
            "FIXTURE",
            "UNAVAILABLE",
        }:
            raise HardBanViolation(
                "HARD BAN: fabricated Live alert — LIVE_READ_ONLY cannot pair with "
                f"freshness={payload.get('freshness')}"
            )
        return payload


def _validate_kind(kind: str) -> str:
    if kind not in ALERT_KINDS:
        raise ValueError(f"unsupported alert kind: {kind}")
    return kind


def _validate_severity(severity: str) -> str:
    if severity not in SEVERITIES:
        raise ValueError(f"unsupported severity: {severity}")
    return severity


def _validate_freshness(freshness: str) -> str:
    if freshness not in FRESHNESS_STATES:
        raise ValueError(f"unsupported freshness: {freshness}")
    return freshness


def _validate_data_class(data_class: str) -> str:
    if data_class not in DATA_CLASS_LABELS:
        raise ValueError(f"unsupported data_class: {data_class}")
    return data_class


def build_readonly_alert(
    *,
    kind: str,
    source: str,
    reason: str,
    severity: str,
    freshness: str,
    data_class: str,
    title: str,
    body: str,
    decision_id: str | None = None,
    as_of: str | None = None,
    alert_id: str | None = None,
    public_safe: bool = True,
) -> AlertEnvelope:
    """Build a public-safe read-only alert; refuse hype and private fields."""
    kind = _validate_kind(kind)
    severity = _validate_severity(severity)
    freshness = _validate_freshness(freshness)
    data_class = _validate_data_class(data_class)
    if not public_safe:
        raise HardBanViolation("HARD BAN: public_safe must be true for Alert Engine emissions")
    if not source or not str(source).strip():
        raise HardBanViolation("HARD BAN: alert source is required")
    if data_class == "UNAVAILABLE" and isinstance(reason, (int, float)) and reason == 0:
        raise HardBanViolation("HARD BAN: unavailable-as-zero refused in alert reason")

    envelope = AlertEnvelope(
        alert_id=alert_id or f"pub18_alert_{uuid4().hex[:16]}",
        kind=kind,
        source=str(source),
        as_of=as_of or _utc_now_iso(),
        freshness=freshness,
        data_class=data_class,
        decision_id=decision_id,
        reason=str(reason),
        severity=severity,
        public_safe=True,
        title=title,
        body=body,
        label=ALERT_KIND_LABELS[kind],
    )
    envelope.to_dict()
    return envelope


def fixture_alert_catalog() -> list[dict[str, Any]]:
    """One fixture alert per kind — DEMO_DATA / FIXTURE only (never fabricated Live)."""
    now = _utc_now_iso()
    defaults: list[Mapping[str, Any]] = [
        {
            "kind": "OPPORTUNITY_READY",
            "severity": "MEDIUM",
            "title": "Opportunity marked READY",
            "body": "Shadow research marks an opportunity READY for review. Not an order.",
            "reason": "candidate_passed_public_readiness_checks",
            "decision_id": "dec_fixture_ready_1",
        },
        {
            "kind": "POSTURE_CHANGE",
            "severity": "MEDIUM",
            "title": "AI posture changed",
            "body": "Public posture moved WAIT → ABSTAIN. Research suggestion only.",
            "reason": "posture_transition_wait_to_abstain",
            "decision_id": "dec_fixture_posture_1",
        },
        {
            "kind": "DATA_TRUST_DEGRADED",
            "severity": "HIGH",
            "title": "Data Trust degraded",
            "body": "Data Trust score degraded for the active symbol scope.",
            "reason": "data_trust_band_degraded",
            "decision_id": None,
            "freshness": "DEGRADED",
            "data_class": "STALE",
        },
        {
            "kind": "REGIME_TRANSITION",
            "severity": "MEDIUM",
            "title": "Regime transition observed",
            "body": "Public regime label transitioned. Informational only.",
            "reason": "regime_label_changed",
            "decision_id": "dec_fixture_regime_1",
        },
        {
            "kind": "INVALIDATION",
            "severity": "HIGH",
            "title": "Thesis invalidation",
            "body": "Supporting thesis condition invalidated under public rules.",
            "reason": "invalidation_condition_met",
            "decision_id": "dec_fixture_invalid_1",
        },
        {
            "kind": "SHADOW_CLOSED",
            "severity": "INFO",
            "title": "Shadow decision closed",
            "body": "Shadow ledger entry closed. Informational only — no exchange write.",
            "reason": "shadow_lifecycle_closed",
            "decision_id": "dec_fixture_shadow_1",
        },
        {
            "kind": "PROVIDER_DEGRADED",
            "severity": "HIGH",
            "title": "Provider degraded",
            "body": "Upstream provider health degraded; values may be stale.",
            "reason": "provider_health_degraded",
            "decision_id": None,
            "freshness": "DEGRADED",
            "data_class": "STALE",
        },
        {
            "kind": "MARKET_ANOMALY",
            "severity": "HIGH",
            "title": "Market anomaly flagged",
            "body": "Public anomaly detector flagged unusual market conditions.",
            "reason": "anomaly_signature_matched",
            "decision_id": "dec_fixture_anomaly_1",
        },
        {
            "kind": "MAJOR_RISK",
            "severity": "CRITICAL",
            "title": "Major risk notice",
            "body": "Major risk condition raised for member awareness. Read-only.",
            "reason": "major_risk_band_triggered",
            "decision_id": "dec_fixture_risk_1",
        },
    ]
    out: list[dict[str, Any]] = []
    for row in defaults:
        alert = build_readonly_alert(
            kind=str(row["kind"]),
            source="fixture://pub18_alert_engine",
            reason=str(row["reason"]),
            severity=str(row["severity"]),
            freshness=str(row.get("freshness") or "FIXTURE"),
            data_class=str(row.get("data_class") or "FIXTURE"),
            title=str(row["title"]),
            body=str(row["body"]),
            decision_id=row.get("decision_id"),  # type: ignore[arg-type]
            as_of=now,
            alert_id=f"fixture_{row['kind'].lower()}",
        )
        out.append(alert.to_dict())
    return out
