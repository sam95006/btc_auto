"""Official Activity Metric V2 — isolated package.

Computes trade_count_window from Bybit public trades (REST + WS stubs).
Does NOT silently substitute volume24h/turnover24h for trade_count_24h.
Does NOT lower eligibility gates or wire into running Shadow campaigns.
"""
from __future__ import annotations

from backend.nexus_activity_metric_v2.checkpoint import ActivityCheckpointStore
from backend.nexus_activity_metric_v2.constants import (
    ACTIVITY_QUALITY_STATES,
    HARD_BANS,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_activity_metric_v2.gate_contract import (
    assert_no_silent_substitution,
    explicit_proxy_binding,
    gate_intent_document,
)
from backend.nexus_activity_metric_v2.models import ActivityMetrics, TradeEvent
from backend.nexus_activity_metric_v2.provider import OfficialTradeActivityProvider
from backend.nexus_activity_metric_v2.quality import evaluate_quality_state
from backend.nexus_activity_metric_v2.window import RollingActivityWindow

__all__ = [
    "ACTIVITY_QUALITY_STATES",
    "ActivityCheckpointStore",
    "ActivityMetrics",
    "HARD_BANS",
    "OfficialTradeActivityProvider",
    "RollingActivityWindow",
    "SCHEMA",
    "SCHEMA_VERSION",
    "TradeEvent",
    "assert_no_silent_substitution",
    "evaluate_quality_state",
    "explicit_proxy_binding",
    "gate_intent_document",
]
