"""Customer-safe Decision Product journey (PUB2-A).

Walks Market Observation → … → Decision Memory using Public Decision Cloud
staging fixtures. Never places orders or exposes execution controls.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from backend.nexus_public_decision_cloud import service as cloud
from backend.nexus_public_decision_product.constants import (
    BASE_COMMIT,
    BRANCH,
    EXCLUDED_STAGES,
    FLOW_STAGE_IDS,
    FLOW_STAGES,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    SCHEMA_VERSION,
)
from backend.nexus_public_decision_product.sanitize import (
    assert_no_execution_controls,
    assert_no_forbidden_keys,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class JourneyError(RuntimeError):
    """Raised when the customer journey cannot advance safely."""


def _pick_decision_id(requested: str | None) -> str:
    feed = cloud.decision_feed()
    rows = feed.get("decisions") or []
    if not rows:
        raise JourneyError("no staging decisions available for E2E journey")
    if requested:
        for row in rows:
            if str(row.get("decision_id")) == requested:
                return requested
        raise JourneyError(f"decision_not_found:{requested}")
    return str(rows[0]["decision_id"])


def _stage_market_observation(decision_id: str) -> dict[str, Any]:
    body = cloud.market_overview()
    overview = body.get("market_overview") or {}
    return {
        "decision_id": decision_id,
        "source": overview.get("source"),
        "symbols": [s.get("symbol") for s in (overview.get("symbols") or []) if isinstance(s, dict)],
        "exchange_api_used": bool(overview.get("exchange_api_used", False)),
        "places_orders": False,
        "note": "Market observation from staging fixtures only.",
    }


def _stage_public_evidence(decision_id: str) -> dict[str, Any]:
    body = cloud.evidence_for(decision_id)
    items = body.get("evidence") or []
    return {
        "decision_id": decision_id,
        "count": len(items),
        "evidence_ids": [i.get("evidence_id") for i in items if isinstance(i, dict)],
        "places_orders": False,
        "customer_trading": False,
    }


def _stage_counter_evidence(decision_id: str) -> dict[str, Any]:
    body = cloud.counter_evidence_for(decision_id)
    items = body.get("counter_evidence") or []
    return {
        "decision_id": decision_id,
        "count": len(items),
        "evidence_ids": [i.get("evidence_id") for i in items if isinstance(i, dict)],
        "places_orders": False,
        "customer_trading": False,
    }


def _stage_risk_conditions(decision_id: str) -> dict[str, Any]:
    body = cloud.risk_for(decision_id)
    risk = body.get("risk") or {}
    return {
        "decision_id": decision_id,
        "advisory_only": bool(body.get("advisory_only", True)),
        "invalidation_conditions": list(risk.get("invalidation_conditions") or []),
        "places_orders": False,
        "execution_controls": None,
    }


def _stage_public_decision_object(decision_id: str) -> dict[str, Any]:
    body = cloud.decision_detail(decision_id)
    decision = body.get("decision") or {}
    decision_block = decision.get("decision") or {}
    return {
        "decision_id": decision_id,
        "status": decision.get("status"),
        "posture": decision_block.get("posture"),
        "places_orders": bool(decision_block.get("places_orders", False)),
        "thesis": (decision.get("thesis") or {}).get("statement"),
        "schema_version": decision.get("schema_version"),
        "customer_trading": False,
        "execution_controls": None,
    }


def _stage_thesis_monitor(decision_id: str) -> dict[str, Any]:
    body = cloud.thesis_monitor()
    monitors = body.get("monitors") or []
    matched = [m for m in monitors if isinstance(m, dict) and m.get("decision_id") == decision_id]
    return {
        "decision_id": decision_id,
        "monitor_count": len(monitors),
        "matched_count": len(matched),
        "auto_trades": bool(body.get("auto_trades", False)),
        "places_orders": False,
        "note": body.get("note"),
    }


def _stage_outcome_review(decision_id: str) -> dict[str, Any]:
    body = cloud.outcome_review(decision_id=decision_id)
    reviews = body.get("reviews") or []
    return {
        "decision_id": decision_id,
        "count": len(reviews),
        "reviews": reviews,
        "places_orders": False,
        "private_account_used": False,
    }


def _stage_decision_memory(decision_id: str) -> dict[str, Any]:
    body = cloud.decision_memory()
    memory = body.get("memory") or []
    return {
        "decision_id": decision_id,
        "memory_count": len(memory),
        "private_lesson_memory": bool(body.get("private_lesson_memory", False)),
        "places_orders": False,
        "customer_trading": False,
    }


_STAGE_HANDLERS: dict[str, Callable[[str], dict[str, Any]]] = {
    "market_observation": _stage_market_observation,
    "public_evidence": _stage_public_evidence,
    "counter_evidence": _stage_counter_evidence,
    "risk_conditions": _stage_risk_conditions,
    "public_decision_object": _stage_public_decision_object,
    "thesis_monitor": _stage_thesis_monitor,
    "outcome_review": _stage_outcome_review,
    "decision_memory": _stage_decision_memory,
}


def refuse_execution_stage(stage_id: str) -> None:
    """Hard ban: execution / trading stages are not part of the product journey."""
    normalized = stage_id.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in EXCLUDED_STAGES or "execution" in normalized or "order" in normalized:
        raise JourneyError(f"HARD BAN: execution stage refused: {stage_id}")


def run_customer_journey(*, decision_id: str | None = None) -> dict[str, Any]:
    """Execute the full customer-safe Decision Product E2E flow."""
    selected = _pick_decision_id(decision_id)
    stages_out: list[dict[str, Any]] = []
    for stage_id, label in FLOW_STAGES:
        refuse_execution_stage(stage_id)
        handler = _STAGE_HANDLERS[stage_id]
        payload = handler(selected)
        payload["stage_id"] = stage_id
        payload["stage_label"] = label
        payload["execution_controls"] = None
        payload["read_only"] = True
        assert_no_forbidden_keys(payload)
        assert_no_execution_controls(payload)
        if payload.get("places_orders") is True:
            raise JourneyError(f"stage {stage_id} attempted order placement")
        if payload.get("auto_trades") is True:
            raise JourneyError(f"stage {stage_id} enabled auto trades")
        if payload.get("private_lesson_memory") is True:
            raise JourneyError(f"stage {stage_id} exposed private lesson memory")
        stages_out.append(payload)

    result = {
        "ok": True,
        "schema": SCHEMA_VERSION,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "package": PACKAGE,
        "base_commit": BASE_COMMIT,
        "as_of": _utc(),
        "decision_id": selected,
        "flow": list(FLOW_STAGE_IDS),
        "flow_labels": [label for _, label in FLOW_STAGES],
        "stage_count": len(stages_out),
        "stages": stages_out,
        "execution_controls": False,
        "customer_trading": False,
        "exchange_api_used": False,
        "private_core_imported": False,
        "fabricated_customers": False,
        "fabricated_metrics": False,
        "read_only": True,
        "hard_bans": list(HARD_BANS),
        "excluded_stages": list(EXCLUDED_STAGES),
        "source": "public_decision_cloud_staging_fixtures",
    }
    assert_no_forbidden_keys(result)
    assert_no_execution_controls(result)
    return result


def journey_meta() -> dict[str, Any]:
    return {
        "ok": True,
        "schema": SCHEMA_VERSION,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "package": PACKAGE,
        "base_commit": BASE_COMMIT,
        "flow": list(FLOW_STAGE_IDS),
        "flow_labels": [label for _, label in FLOW_STAGES],
        "excluded_stages": list(EXCLUDED_STAGES),
        "execution_controls": False,
        "customer_trading": False,
        "exchange_api_used": False,
        "private_core_imported": False,
        "fabricated_customers": False,
        "fabricated_metrics": False,
        "read_only": True,
        "hard_bans": list(HARD_BANS),
        "methods_allowed": ["GET", "HEAD", "OPTIONS"],
        "as_of": _utc(),
    }
