"""Alert truth — emit only from real runtime snapshot signals (never fixture→LIVE)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.nexus_runtime_snapshot_v18_1.constants import (
    BANNED_ALERT_PHRASES,
    LIVE_ALERT_KINDS,
)


class AlertTruthError(RuntimeError):
    """Raised when an alert would violate Phase B alert truth rules."""


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _assert_no_hype(*texts: str) -> None:
    blob = " ".join(texts).upper()
    for phrase in BANNED_ALERT_PHRASES:
        if phrase in blob:
            raise AlertTruthError(f"banned_alert_phrase:{phrase}")


def _alert(
    *,
    kind: str,
    reason: str,
    title: str,
    body: str,
    severity: str,
    freshness: str,
    data_class: str,
    decision_id: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    if kind not in LIVE_ALERT_KINDS:
        raise AlertTruthError(f"unsupported_live_alert_kind:{kind}")
    # Never emit LIVE data_class for non-live freshness.
    if data_class in {"LIVE_READ_ONLY", "LIVE_PARTIAL_DEGRADED", "LIVE"} and freshness in {
        "FIXTURE",
        "DEMO_DATA",
        "RUNTIME_STOPPED",
        "STALE",
        "UNAVAILABLE",
    }:
        raise AlertTruthError("fixture_or_stopped_as_live_alert")
    if freshness == "FIXTURE" and data_class in {"LIVE_READ_ONLY", "LIVE"}:
        raise AlertTruthError("fixture_as_live_alert")
    _assert_no_hype(title, body, reason)
    return {
        "alert_id": f"v18_1_rt_{uuid4().hex[:12]}",
        "kind": kind,
        "source": "runtime://live_shadow_runtime",
        "as_of": as_of or _utc(),
        "freshness": freshness,
        "data_class": data_class,
        "decision_id": decision_id,
        "reason": reason,
        "severity": severity,
        "public_safe": True,
        "title": title,
        "body": body,
        "read_only": True,
        "actionable_trade": False,
    }


def build_runtime_alerts(snap: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive alerts from a loaded runtime snapshot only (no fixture LIVE)."""
    alerts: list[dict[str, Any]] = []
    runtime_state = str(snap.get("runtime_state") or "UNAVAILABLE")
    freshness = str(snap.get("data_freshness") or "UNAVAILABLE")
    data_class = str(snap.get("data_class") or freshness)
    as_of = str(snap.get("as_of") or _utc())
    is_live = bool(snap.get("is_live_view"))
    shadow = snap.get("shadow_status") or {}
    funnel = snap.get("universe_funnel") or {}
    source = snap.get("source_health") or {}
    ai = snap.get("AI_gateway_status") or {}
    reasons = list(snap.get("degraded_reasons") or [])
    decision_id = None
    # lineage is public-safe id, not order id
    lineage = snap.get("lineage_id")

    # Fixture→LIVE ban: if binding claims fixture chrome, refuse live-class alerts.
    if str(snap.get("binding_mode")) == "fixture" and is_live:
        raise AlertTruthError("fixture_binding_marked_live")

    if runtime_state == "STOPPED" or freshness == "RUNTIME_STOPPED":
        alerts.append(
            _alert(
                kind="RUNTIME_STOPPED",
                reason="runtime_state_stopped",
                title="Runtime stopped",
                body="Live Shadow Runtime is STOPPED. Historical projection is not Live.",
                severity="HIGH",
                freshness="RUNTIME_STOPPED",
                data_class="RUNTIME_STOPPED",
                decision_id=None,
                as_of=as_of,
            )
        )

    if "eligible_zero_fail_closed" in reasons or (
        source.get("status") in {"DEGRADED", "PARTIAL"}
    ):
        alerts.append(
            _alert(
                kind="DATA_TRUST_DEGRADED",
                reason="data_trust_or_eligibility_degraded",
                title="Data Trust degraded",
                body="Eligibility / source health indicates degraded trust. Fail-closed.",
                severity="HIGH",
                freshness=freshness if freshness != "FRESH" else "STALE",
                data_class=data_class if not is_live else "LIVE_PARTIAL_DEGRADED",
                as_of=as_of,
            )
        )

    if source.get("status") == "DEGRADED" or int(ai.get("provider_capacity_blocked_count") or 0) > 0:
        alerts.append(
            _alert(
                kind="PROVIDER_DEGRADED",
                reason="provider_or_source_degraded",
                title="Provider degraded",
                body="Upstream provider / source health degraded. Values may be incomplete.",
                severity="HIGH",
                freshness="DEGRADED" if is_live else freshness,
                data_class=data_class if data_class != "LIVE_READ_ONLY" else "LIVE_PARTIAL_DEGRADED",
                as_of=as_of,
            )
        )

    candidates = funnel.get("candidates")
    if isinstance(candidates, int) and candidates > 0 and is_live:
        alerts.append(
            _alert(
                kind="CANDIDATE_CREATED",
                reason="candidates_generated",
                title="Shadow candidate created",
                body=f"{candidates} candidate(s) generated in shadow research. Not an order.",
                severity="MEDIUM",
                freshness=freshness,
                data_class=data_class,
                decision_id=str(lineage) if lineage else None,
                as_of=as_of,
            )
        )

    last_decision = shadow.get("last_decision")
    if last_decision and is_live:
        alerts.append(
            _alert(
                kind="POSTURE_CHANGED",
                reason=f"shadow_decision_{last_decision}",
                title="Shadow posture observed",
                body=f"Latest shadow decision={last_decision}. Research only — not a fill.",
                severity="INFO",
                freshness=freshness,
                data_class=data_class,
                decision_id=str(lineage) if lineage else None,
                as_of=as_of,
            )
        )

    if int(shadow.get("shadow_opened_count") or 0) > 0 and is_live:
        alerts.append(
            _alert(
                kind="SHADOW_OPENED",
                reason="shadow_opened_count",
                title="Shadow opened",
                body="Shadow research position opened count > 0. Not an exchange order.",
                severity="INFO",
                freshness=freshness,
                data_class=data_class,
                as_of=as_of,
            )
        )

    if int(shadow.get("shadow_closed_count") or 0) > 0:
        alerts.append(
            _alert(
                kind="SHADOW_CLOSED",
                reason="shadow_closed_count",
                title="Shadow closed",
                body="Shadow research position closed count > 0. Informational only.",
                severity="INFO",
                freshness=freshness if not is_live else freshness,
                data_class=data_class,
                as_of=as_of,
            )
        )

    if not is_live and runtime_state not in {"STOPPED", "UNAVAILABLE"}:
        # PAUSED / STALE path
        alerts.append(
            _alert(
                kind="INVALIDATION_TRIGGERED",
                reason="live_view_invalidated",
                title="Live view invalidated",
                body="Runtime projection is not Live; prior values must not be shown as Live.",
                severity="HIGH",
                freshness=freshness,
                data_class=data_class,
                as_of=as_of,
            )
        )

    # Deduplicate by kind (keep first).
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in alerts:
        if row["kind"] in seen:
            continue
        seen.add(row["kind"])
        out.append(row)
    return out


def fixture_as_live_count(alerts: list[dict[str, Any]]) -> int:
    """Count alerts that illegally pair FIXTURE/DEMO with LIVE class."""
    n = 0
    for a in alerts:
        freshness = str(a.get("freshness") or "").upper()
        data_class = str(a.get("data_class") or "").upper()
        source = str(a.get("source") or "")
        if freshness in {"FIXTURE", "DEMO_DATA"} and data_class.startswith("LIVE"):
            n += 1
        if source.startswith("fixture://") and data_class.startswith("LIVE"):
            n += 1
    return n
