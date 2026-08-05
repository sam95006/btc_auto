"""Read-only Public Decision Cloud service (PUB-B).

Serves local/staging Decision Integrity surfaces from fixtures.
Never places orders, never calls exchange APIs, never imports private core.

PUB2-H: decision lookups use opaque denies + timing pad to blunt enumeration
and existence oracles for org-scoped / missing IDs.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from backend.nexus_publishing_gateway.timing import timing_pad
from backend.nexus_public_decision_cloud.constants import (
    BASE_COMMIT,
    BRANCH,
    DECISION_LOOKUP_TIMING_PAD_MS,
    FRESHNESS_FRESH_SECONDS,
    FRESHNESS_STALE_SECONDS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OPAQUE_DECISION_DENY,
    PACKAGE,
    SCHEMA_VERSION,
    SURFACES,
)
from backend.nexus_public_decision_cloud.sanitize import (
    assert_no_forbidden_keys,
    scrub_forbidden_keys,
)
from backend.nexus_public_decision_cloud.store import get_decision, list_decisions, load_catalog


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(**payload: Any) -> dict[str, Any]:
    body = {
        "ok": True,
        "schema": SCHEMA_VERSION,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "package": PACKAGE,
        "base_commit": BASE_COMMIT,
        "read_only": True,
        "customer_trading": False,
        "exchange_api_used": False,
        "private_core_imported": False,
        "hard_bans": list(HARD_BANS),
        "as_of": _utc(),
        **payload,
    }
    assert_no_forbidden_keys(body)
    return body


def _opaque_deny() -> dict[str, Any]:
    return dict(OPAQUE_DECISION_DENY)


def freshness_band(seconds: float | int | None) -> str:
    if seconds is None:
        return "unknown"
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "unknown"
    if value <= FRESHNESS_FRESH_SECONDS:
        return "fresh"
    if value <= FRESHNESS_STALE_SECONDS:
        return "aging"
    return "stale"


def _visibility(row: dict[str, Any]) -> str:
    return str(row.get("visibility") or "public").lower()


def _org_id(row: dict[str, Any]) -> Optional[str]:
    raw = row.get("org_id")
    return str(raw) if raw else None


def _caller_may_view(
    row: dict[str, Any],
    *,
    caller_account_id: Optional[str] = None,
    caller_org_ids: Optional[set[str]] = None,
) -> bool:
    vis = _visibility(row)
    if vis in {"public", "fixture_public", ""}:
        return True
    if vis in {"org", "org_scoped", "private_org"}:
        org = _org_id(row)
        if not org:
            return False
        allowed = caller_org_ids or set()
        return org in allowed
    # Unknown visibility → fail closed.
    return False


def _public_feed_rows(
    *,
    caller_org_ids: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    rows = []
    for row in list_decisions():
        if _caller_may_view(row, caller_org_ids=caller_org_ids):
            rows.append(scrub_forbidden_keys(row))
    return rows


def resolve_decision(
    decision_id: str,
    *,
    caller_account_id: Optional[str] = None,
    caller_org_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Lookup with timing pad + opaque deny (missing ≈ unauthorized)."""
    with timing_pad(DECISION_LOOKUP_TIMING_PAD_MS):
        row = get_decision(decision_id)
        if row is None:
            return _opaque_deny()
        if not _caller_may_view(
            row, caller_account_id=caller_account_id, caller_org_ids=caller_org_ids
        ):
            return _opaque_deny()
        cleaned = scrub_forbidden_keys(deepcopy(row))
        return _envelope(surface="decision_detail", decision=cleaned)


def service_meta() -> dict[str, Any]:
    return _envelope(
        surfaces=list(SURFACES),
        environment="local_staging",
        methods_allowed=["GET", "HEAD", "OPTIONS"],
    )


def market_overview() -> dict[str, Any]:
    catalog = load_catalog()
    overview = scrub_forbidden_keys(catalog.get("market_overview") or {})
    return _envelope(
        surface="market_overview",
        market_overview=overview,
        note="Fixture marks only — no exchange API calls.",
    )


def decision_feed(
    *,
    status: str | None = None,
    caller_org_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    rows = _public_feed_rows(caller_org_ids=caller_org_ids)
    if status:
        rows = [r for r in rows if str(r.get("status")) == status]
    feed = [
        {
            "decision_id": r.get("decision_id"),
            "status": r.get("status"),
            "visibility": _visibility(r),
            "symbols": (r.get("context") or {}).get("symbols"),
            "posture": (r.get("decision") or {}).get("posture"),
            "thesis_statement": (r.get("thesis") or {}).get("statement"),
            "updated_at": r.get("updated_at"),
            "freshness_seconds": (r.get("context") or {}).get("data_freshness_seconds"),
            "freshness_band": freshness_band((r.get("context") or {}).get("data_freshness_seconds")),
        }
        for r in rows
    ]
    return _envelope(surface="decision_feed", count=len(feed), decisions=feed)


def decision_detail(
    decision_id: str,
    *,
    caller_account_id: Optional[str] = None,
    caller_org_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    return resolve_decision(
        decision_id,
        caller_account_id=caller_account_id,
        caller_org_ids=caller_org_ids,
    )


def evidence_for(
    decision_id: str,
    *,
    caller_org_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    resolved = resolve_decision(decision_id, caller_org_ids=caller_org_ids)
    if not resolved.get("ok"):
        return resolved
    row = resolved["decision"]
    items = list(row.get("evidence") or [])
    for item in items:
        if isinstance(item, dict):
            item["freshness_band"] = freshness_band(item.get("freshness_seconds"))
    return _envelope(surface="evidence", decision_id=decision_id, evidence=items)


def counter_evidence_for(
    decision_id: str,
    *,
    caller_org_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    resolved = resolve_decision(decision_id, caller_org_ids=caller_org_ids)
    if not resolved.get("ok"):
        return resolved
    row = resolved["decision"]
    items = list(row.get("counter_evidence") or [])
    for item in items:
        if isinstance(item, dict):
            item["freshness_band"] = freshness_band(item.get("freshness_seconds"))
    return _envelope(
        surface="counter_evidence",
        decision_id=decision_id,
        counter_evidence=items,
    )


def risk_for(
    decision_id: str,
    *,
    caller_org_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    resolved = resolve_decision(decision_id, caller_org_ids=caller_org_ids)
    if not resolved.get("ok"):
        return resolved
    row = resolved["decision"]
    return _envelope(
        surface="risk",
        decision_id=decision_id,
        risk=row.get("risk") or {},
        advisory_only=True,
    )


def thesis_monitor() -> dict[str, Any]:
    catalog = load_catalog()
    monitors = scrub_forbidden_keys(catalog.get("thesis_monitor") or [])
    return _envelope(
        surface="thesis_monitor",
        monitors=monitors,
        auto_trades=False,
        note="Alerts are advisory; never auto-trade.",
    )


def decision_memory() -> dict[str, Any]:
    catalog = load_catalog()
    memory = catalog.get("decision_memory") or []
    cleaned = []
    for item in memory:
        if not isinstance(item, dict):
            continue
        row = scrub_forbidden_keys(dict(item))
        row["private_lesson_memory"] = False
        cleaned.append(row)
    return _envelope(
        surface="decision_memory",
        memory=cleaned,
        private_lesson_memory=False,
    )


def outcome_review(
    *,
    decision_id: str | None = None,
    caller_org_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    rows = _public_feed_rows(caller_org_ids=caller_org_ids)
    reviews = []
    for row in rows:
        if decision_id and str(row.get("decision_id")) != decision_id:
            continue
        reviews.append(
            {
                "decision_id": row.get("decision_id"),
                "outcome": row.get("outcome") or {},
                "review": row.get("review") or {},
            }
        )
    return _envelope(surface="outcome_review", count=len(reviews), reviews=reviews)


def alerts() -> dict[str, Any]:
    catalog = load_catalog()
    rows = scrub_forbidden_keys(catalog.get("alerts") or [])
    for row in rows:
        if isinstance(row, dict):
            row["actionable_trade"] = False
    return _envelope(surface="alerts", count=len(rows), alerts=rows)


def freshness_report(*, caller_org_ids: Optional[set[str]] = None) -> dict[str, Any]:
    rows = _public_feed_rows(caller_org_ids=caller_org_ids)
    items = []
    for row in rows:
        ctx = row.get("context") or {}
        secs = ctx.get("data_freshness_seconds")
        evidence = list(row.get("evidence") or []) + list(row.get("counter_evidence") or [])
        evidence_bands = [
            freshness_band(e.get("freshness_seconds"))
            for e in evidence
            if isinstance(e, dict)
        ]
        items.append(
            {
                "decision_id": row.get("decision_id"),
                "context_freshness_seconds": secs,
                "context_freshness_band": freshness_band(secs),
                "evidence_freshness_bands": evidence_bands,
            }
        )
    return _envelope(
        surface="freshness",
        thresholds={
            "fresh_seconds": FRESHNESS_FRESH_SECONDS,
            "stale_seconds": FRESHNESS_STALE_SECONDS,
        },
        items=items,
    )


def refuse_exchange_write_path() -> None:
    """Public Decision Cloud never exposes an exchange-write path."""
    from backend.nexus_public_decision_cloud.hard_bans import HardBanViolation

    raise HardBanViolation("HARD BAN: public exchange-write path refused")
