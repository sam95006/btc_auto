"""Consent-aware analytics event contract — NO_OBSERVATIONS default."""
from __future__ import annotations

from typing import Any

ALLOWED_EVENTS = frozenset(
    {
        "page_viewed",
        "opportunity_opened",
        "scanner_filter_used",
        "evidence_expanded",
        "invalidation_viewed",
        "alert_created",
        "watchlist_added",
        "ai_question_submitted",
        "upgrade_gate_viewed",
        "plan_compared",
        "enterprise_contact_requested",
    }
)


def analytics_contract_snapshot() -> dict[str, Any]:
    return {
        "schema": "public_analytics_contract_v18_2",
        "consent_required": True,
        "default_observations": "NO_OBSERVATIONS",
        "allowed_events": sorted(ALLOWED_EVENTS),
        "forbidden": ["fake_conversion", "fake_retention", "fake_member_counts"],
    }
