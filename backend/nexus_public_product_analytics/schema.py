"""Declarative metric schema for PUB2-I (definitions only; no fabricated values)."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_product_analytics.constants import (
    CLOSED_DECISION_LOOP_REQUIRES,
    CONSENT_PURPOSE,
    EVENT_CATALOG,
    METRIC_IDS,
    NORTH_STAR,
    NORTH_STAR_METRIC_ID,
    PACKAGE,
    SCHEMA,
    SCHEMA_VERSION,
)


def metric_definitions() -> list[dict[str, Any]]:
    """Return one schema entry per product metric (empty observation baseline)."""
    by_id: dict[str, dict[str, Any]] = {}
    for event_name, meta in EVENT_CATALOG.items():
        mid = str(meta["metric_id"])
        entry = by_id.setdefault(
            mid,
            {
                "metric_id": mid,
                "events": [],
                "description": str(meta["description"]),
                "consent_purpose": CONSENT_PURPOSE,
                "aggregation": "count_distinct_subject_or_event",
                "value_policy": "observed_only_never_fabricated",
                "empty_observation": {
                    "status": "NO_OBSERVATIONS",
                    "value": None,
                    "count": 0,
                },
            },
        )
        entry["events"].append(
            {
                "event_name": event_name,
                "allowed_props": list(meta["allowed_props"]),  # type: ignore[arg-type]
            }
        )
    # Stable order matching METRIC_IDS
    return [by_id[mid] for mid in METRIC_IDS if mid in by_id]


def build_metric_schema() -> dict[str, Any]:
    """Canonical JSON-serializable metric schema document."""
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "package": PACKAGE,
        "lane": "PUB2-I",
        "privacy": {
            "consent_purpose": CONSENT_PURPOSE,
            "default_consent": "denied",
            "subject_id_policy": "hmac_sha256_salted_pseudonym",
            "pii_props_forbidden": True,
            "production_customer_database": False,
            "live_billing": False,
        },
        "north_star": {
            "metric_id": NORTH_STAR_METRIC_ID,
            "name": NORTH_STAR,
            "definition": (
                "Closed Decision loops per active paid user. "
                "A closed loop requires all closed_decision_loop_requires steps."
            ),
            "closed_decision_loop_requires": list(CLOSED_DECISION_LOOP_REQUIRES),
            "value_policy": "observed_only_never_fabricated",
            "current_observation": {
                "status": "NO_OBSERVATIONS",
                "value": None,
                "count": 0,
                "note": "Scaffolding only — no fabricated north-star value",
            },
        },
        "metrics": metric_definitions(),
        "fabricated_results_forbidden": True,
        "status_json_forbidden": True,
    }


def validate_schema_document(doc: dict[str, Any]) -> list[str]:
    """Return validation errors (empty list means ok)."""
    errors: list[str] = []
    if doc.get("schema") != SCHEMA:
        errors.append("schema_mismatch")
    if doc.get("fabricated_results_forbidden") is not True:
        errors.append("fabrication_flag_missing")
    if doc.get("status_json_forbidden") is not True:
        errors.append("status_json_flag_missing")
    ns = doc.get("north_star") or {}
    obs = ns.get("current_observation") or {}
    if obs.get("status") != "NO_OBSERVATIONS" and obs.get("value") is not None:
        # Allow OBSERVED only if count > 0; scaffolding must not claim values.
        if int(obs.get("count") or 0) <= 0:
            errors.append("north_star_fabricated_value")
    metrics = doc.get("metrics") or []
    seen = {m.get("metric_id") for m in metrics}
    for mid in METRIC_IDS:
        if mid not in seen:
            errors.append(f"missing_metric:{mid}")
    return errors
