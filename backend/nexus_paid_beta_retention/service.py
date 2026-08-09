"""Retention facade — watchlist enrichment + alert→notification pipeline."""
from __future__ import annotations

from typing import Any, Optional

from backend.nexus_paid_beta_retention.alert_events import (
    build_alert_event,
    get_anti_spam,
    normalize_event_type,
)
from backend.nexus_paid_beta_retention.auth_census import auth_commercial_census
from backend.nexus_paid_beta_retention.billing_readiness import billing_readiness
from backend.nexus_paid_beta_retention.constants import (
    ALERT_EVENT_TYPES,
    HARD_BANS,
    MARKER,
    PACKAGE,
    SCHEMA,
)
from backend.nexus_paid_beta_retention.notifications import get_notification_center
from backend.nexus_paid_beta_retention.onboarding import get_onboarding_store
from backend.nexus_paid_beta_retention.since_last_visit import get_visit_tracker
from backend.nexus_paid_beta_retention.watchlist_store import get_watchlist_store


def _radar_index() -> dict[str, dict[str, Any]]:
    try:
        from backend.market.live_radar.full_market_radar_service import get_full_market_radar

        snap = get_full_market_radar().snapshot()
        rows = snap.get("rows") or snap.get("ranking") or []
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            sym = str(r.get("symbol") or "").upper()
            if sym:
                out[sym] = r
        return out
    except Exception:
        return {}


def enrich_watchlist(account_id: str) -> dict[str, Any]:
    base = get_watchlist_store().list_items(account_id)
    radar = _radar_index()
    enriched = []
    for item in base["items"]:
        sym = item["symbol"]
        rr = radar.get(sym) or {}
        enriched.append(
            {
                **item,
                "price": rr.get("last_price") or rr.get("price") or rr.get("currentPrice"),
                "change_24h_pct": rr.get("change_24h_pct") or rr.get("change24hPct"),
                "rank": rr.get("rank"),
                "rank_delta": rr.get("rank_delta") or rr.get("rankDelta") or rr.get("rank_move"),
                "state": rr.get("state") or rr.get("nex_state") or rr.get("stage"),
                "activity": rr.get("activity") or rr.get("activity_score"),
                "risk": rr.get("risk") or rr.get("risk_score") or rr.get("riskScore"),
                "radar": {
                    "in_radar": sym in radar,
                    "rank_event": rr.get("rank_event") or rr.get("last_event"),
                },
                "event": rr.get("last_event") or rr.get("rank_event"),
                "alerts": 0,
                "updated_at": rr.get("updated_at") or rr.get("timestamp") or base.get("updated_at"),
                "series_hint": "watchlist_24h",
            }
        )
    return {**base, "items": enriched, "marker": MARKER}


def ingest_alert(
    account_id: str,
    *,
    event_type: str,
    symbol: str,
    severity: str = "MEDIUM",
    headline: str,
    metric: Optional[dict[str, Any]] = None,
    source: str = "retention",
    link: Optional[str] = None,
) -> dict[str, Any]:
    event = build_alert_event(
        event_type=event_type,
        symbol=symbol,
        severity=severity,
        headline=headline,
        metric=metric,
        source=source,
        link=link,
    )
    ok, reason = get_anti_spam().allow(
        account_id,
        event_type=event["type"],
        symbol=event["symbol"],
        severity=event["severity"],
        dedup_key=str((metric or {}).get("dedup") or event["headline"]),
    )
    if not ok:
        return {"ok": False, "suppressed": True, "reason": reason, "event": event}
    note = get_notification_center().push(account_id, event)
    return {"ok": True, "suppressed": False, "event": event, "notification": note}


def foundation_status() -> dict[str, Any]:
    census = auth_commercial_census()
    return {
        "ok": True,
        "package": PACKAGE,
        "schema": SCHEMA,
        "marker": MARKER,
        "loop": ["DISCOVER", "WATCH", "ALERT", "RETURN", "EXPLAIN"],
        "alert_event_types": list(ALERT_EVENT_TYPES),
        "hard_bans": sorted(HARD_BANS),
        "delivery": {"in_app": True, "web_push": False, "email": False},
        "web_push_foundation": False,
        "web_push_reason": "no_safe_existing_vapid_infra",
        "auth_census": census["census"],
        "paid_beta_auth_blockers": census["paid_beta_auth_blockers"],
        "billing": billing_readiness(),
        "member_execution": 0,
        "production_billing": False,
    }


def since_last_visit(account_id: str) -> dict[str, Any]:
    visit = get_visit_tracker().snapshot(account_id)
    notes = get_notification_center().list_for(account_id, limit=30)
    since_ts = visit.get("previous_visit_at")
    if not visit.get("has_previous") or since_ts is None:
        return {
            **visit,
            "notifications_since": [],
            "count": 0,
            "insufficient_history": True,
            "empty": True,
            "fabricated": False,
            "explain": "No prior authenticated visit on record — honest empty, nothing fabricated.",
        }
    items = [n for n in notes["items"] if int(n.get("ts") or 0) >= int(since_ts)]
    try:
        from backend.nexus_product_analytics.events import record_event

        record_event("session_returned", account_id=account_id)
    except Exception:
        pass
    return {
        **visit,
        "notifications_since": items,
        "count": len(items),
        "insufficient_history": False,
        "empty": len(items) == 0,
        "fabricated": False,
        "explain": "Changes since previous authenticated visit (server clock).",
    }


def onboarding_status(account_id: str) -> dict[str, Any]:
    return get_onboarding_store().status(account_id)
