"""Honest metric aggregation — observed counts only; never fabricate."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.nexus_public_product_analytics.constants import (
    EVENT_CATALOG,
    METRIC_IDS,
    NORTH_STAR,
    NORTH_STAR_METRIC_ID,
)
from backend.nexus_public_product_analytics.hard_bans import refuse_fabrication
from backend.nexus_public_product_analytics.store import LocalAnalyticsStore


def _empty_observation(metric_id: str) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "status": "NO_OBSERVATIONS",
        "value": None,
        "count": 0,
        "distinct_subjects": 0,
    }


def _observed(metric_id: str, *, count: int, distinct_subjects: int) -> dict[str, Any]:
    if count < 0 or distinct_subjects < 0:
        refuse_fabrication(f"negative counts for {metric_id}")
    if count == 0:
        return _empty_observation(metric_id)
    return {
        "metric_id": metric_id,
        "status": "OBSERVED",
        "value": count,
        "count": count,
        "distinct_subjects": distinct_subjects,
    }


def aggregate_metrics(store: LocalAnalyticsStore) -> dict[str, Any]:
    """Aggregate local events into product metrics without inventing values."""
    by_metric_events: dict[str, list] = defaultdict(list)
    for ev in store.events:
        meta = EVENT_CATALOG.get(ev.event_name)
        if not meta:
            continue
        by_metric_events[str(meta["metric_id"])].append(ev)

    metrics: dict[str, dict[str, Any]] = {}
    for mid in METRIC_IDS:
        events = by_metric_events.get(mid, [])
        subjects = {e.subject_hash for e in events}
        metrics[mid] = _observed(mid, count=len(events), distinct_subjects=len(subjects))

    # North star: scaffolding reports NO_OBSERVATIONS until real paid closed loops exist.
    # We intentionally do not invent a rate from empty or unpaid events.
    north_star = {
        "metric_id": NORTH_STAR_METRIC_ID,
        "name": NORTH_STAR,
        "status": "NO_OBSERVATIONS",
        "value": None,
        "count": 0,
        "note": (
            "Closed loops per active paid user require genuine paid cohort evidence; "
            "scaffolding refuses fabricated north-star rates."
        ),
    }
    # Only mark OBSERVED if decision_review_completion events exist AND upgrade_intent
    # paid signals exist — still no invented rate; value stays None until paid linkage.
    review = metrics.get("decision_review_completion", {})
    upgrade = metrics.get("upgrade_intent", {})
    if review.get("count", 0) > 0 and upgrade.get("count", 0) > 0:
        north_star = {
            **north_star,
            "status": "UNAVAILABLE",
            "value": None,
            "count": 0,
            "note": (
                "Review and upgrade-intent observations exist, but paid-user linkage "
                "and closed-loop verification are not available in scaffolding; "
                "value remains unset (not fabricated)."
            ),
        }

    return {
        "fabricated_results_forbidden": True,
        "north_star": north_star,
        "metrics": metrics,
        "event_total": len(store.events),
    }


def assert_no_fabricated_snapshot(snapshot: dict[str, Any]) -> None:
    """Guard: non-zero values require OBSERVED status and matching counts."""
    ns = snapshot.get("north_star") or {}
    if ns.get("value") is not None and ns.get("status") == "NO_OBSERVATIONS":
        refuse_fabrication("north_star value with NO_OBSERVATIONS")
    for mid, row in (snapshot.get("metrics") or {}).items():
        if row.get("status") == "NO_OBSERVATIONS" and (
            row.get("value") not in (None, 0) or int(row.get("count") or 0) != 0
        ):
            refuse_fabrication(f"metric {mid} claims value without observations")
        if row.get("status") == "OBSERVED" and int(row.get("count") or 0) <= 0:
            refuse_fabrication(f"metric {mid} OBSERVED with empty count")
