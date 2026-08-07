"""Gate contract for trade_count_24h vs Activity Metric V2.

Original Gate (backend.nexus_eligible_universe.gates.gate_trade_frequency):
  - Field: InstrumentSnapshot.trade_count_24h
  - Missing (None) → TRADE_COUNT_UNKNOWN, fail-closed (known=False)
  - Present but < MIN_TRADE_COUNT_24H → TRADE_FREQ_TOO_LOW
  - Bybit public linear ticker does NOT publish trade_count_24h
  - volume24h / turnover24h MUST NOT be written into trade_count_24h

This package exposes trade_count_window as an EXPLICIT, VERSIONED proxy.
Any wiring into Eligible Universe must:
  1. Use a versioned adapter (activity_metric_v2)
  2. Record proxy_source in evidence
  3. Never silently rename volume/turnover into trade_count_24h
"""
from __future__ import annotations

from typing import Any

from backend.nexus_activity_metric_v2.constants import (
    GATE_FIELD_TRADE_COUNT_24H,
    METRIC_TRADE_COUNT_WINDOW,
    PROXY_FORBIDDEN_SAME_FIELD,
    PROXY_METRIC_VERSION,
)
from backend.nexus_activity_metric_v2.models import ActivityMetrics


FORBIDDEN_PROXY_SOURCES = frozenset(
    {
        "volume24h",
        "volume_24h",
        "turnover24h",
        "turnover_24h",
        "volume24hUsd",
    }
)


def assert_no_silent_substitution(
    *,
    proposed_gate_value: Any,
    source_field: str | None,
) -> None:
    """Raise if a forbidden volume/turnover proxy is proposed under trade_count_24h."""
    if source_field and source_field in FORBIDDEN_PROXY_SOURCES:
        raise ValueError(
            f"silent_substitution_forbidden: cannot map {source_field} "
            f"into {GATE_FIELD_TRADE_COUNT_24H}"
        )
    if PROXY_FORBIDDEN_SAME_FIELD and source_field in FORBIDDEN_PROXY_SOURCES:
        raise ValueError("proxy_same_field_forbidden")


def explicit_proxy_binding(metrics: ActivityMetrics) -> dict[str, Any]:
    """Versioned, auditable binding — does not mutate Gate snapshot."""
    return {
        "gate_field": GATE_FIELD_TRADE_COUNT_24H,
        "proxy_metric": METRIC_TRADE_COUNT_WINDOW,
        "proxy_version": PROXY_METRIC_VERSION,
        "proxy_value": int(metrics.trade_count_window),
        "quality_state": metrics.quality_state,
        "warmup_complete": bool(metrics.warmup_complete),
        "eligible_for_gate_injection": bool(
            metrics.warmup_complete and metrics.quality_state == "LIVE"
        ),
        "silent_substitution": False,
        "forbidden_sources": sorted(FORBIDDEN_PROXY_SOURCES),
        "note": (
            "Injection into InstrumentSnapshot.trade_count_24h requires an "
            "explicit versioned wiring change; this package does not auto-wire."
        ),
    }


def gate_intent_document() -> dict[str, Any]:
    return {
        "original_gate": "gate_trade_frequency",
        "module": "backend.nexus_eligible_universe.gates",
        "field": GATE_FIELD_TRADE_COUNT_24H,
        "bybit_public_ticker_publishes_trade_count_24h": False,
        "fail_closed_when_missing": True,
        "thresholds_unchanged": True,
        "activity_metric_v2_role": (
            "Compute official trade_count_window from public trades; "
            "optional EXPLICIT versioned proxy only — never hide volume/turnover substitution."
        ),
        "proxy_version": PROXY_METRIC_VERSION,
    }
