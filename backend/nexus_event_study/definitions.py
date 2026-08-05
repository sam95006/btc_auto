"""V14-B Event Study Engine — event definition catalog."""
from __future__ import annotations

from typing import Any

from backend.nexus_event_study.constants import (
    DEFAULT_CONTROL_WINDOW_BARS,
    DEFAULT_OVERLAP_EXCLUSION_BARS,
    DEFAULT_POST_WINDOW_BARS,
    DEFAULT_PRE_WINDOW_BARS,
    EVENT_DEFINITION_IDS,
)
from backend.nexus_event_study.types import EventDefinition

_DEFS: dict[str, EventDefinition] = {
    "aggressive_flow_burst": EventDefinition(
        event_id="aggressive_flow_burst",
        family="ORDER_FLOW",
        economic_rationale="Burst of same-side aggressive notional relative to recent baseline.",
        required_fields=("symbol", "side", "notional", "exchange_ts_ms", "receive_ts_ms"),
        pre_window_bars=DEFAULT_PRE_WINDOW_BARS,
        post_window_bars=DEFAULT_POST_WINDOW_BARS,
        control_window_bars=DEFAULT_CONTROL_WINDOW_BARS,
        overlap_exclusion_bars=DEFAULT_OVERLAP_EXCLUSION_BARS,
        pit_rule="exchange_ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms",
        missing_policy="EXCLUDE_WITH_REASON",
    ),
    "liquidation_cascade_onset": EventDefinition(
        event_id="liquidation_cascade_onset",
        family="LIQUIDATION",
        economic_rationale="Clustered forced liquidations exceeding intensity threshold.",
        required_fields=("symbol", "side", "liq_notional", "exchange_ts_ms", "receive_ts_ms"),
        pre_window_bars=DEFAULT_PRE_WINDOW_BARS,
        post_window_bars=DEFAULT_POST_WINDOW_BARS,
        control_window_bars=DEFAULT_CONTROL_WINDOW_BARS,
        overlap_exclusion_bars=DEFAULT_OVERLAP_EXCLUSION_BARS,
        pit_rule="exchange_ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms",
        missing_policy="EXCLUDE_WITH_REASON",
    ),
    "spread_shock": EventDefinition(
        event_id="spread_shock",
        family="MICROSTRUCTURE",
        economic_rationale="Abrupt widening of quoted spread relative to rolling median.",
        required_fields=("symbol", "spread_bps", "exchange_ts_ms", "receive_ts_ms"),
        pre_window_bars=DEFAULT_PRE_WINDOW_BARS,
        post_window_bars=DEFAULT_POST_WINDOW_BARS,
        control_window_bars=DEFAULT_CONTROL_WINDOW_BARS,
        overlap_exclusion_bars=DEFAULT_OVERLAP_EXCLUSION_BARS,
        pit_rule="exchange_ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms",
        missing_policy="EXCLUDE_WITH_REASON",
    ),
    "funding_dislocation": EventDefinition(
        event_id="funding_dislocation",
        family="DERIVATIVES",
        economic_rationale="Funding rate deviation from cross-sectional median.",
        required_fields=("symbol", "funding_rate", "exchange_ts_ms", "receive_ts_ms"),
        pre_window_bars=DEFAULT_PRE_WINDOW_BARS,
        post_window_bars=DEFAULT_POST_WINDOW_BARS,
        control_window_bars=DEFAULT_CONTROL_WINDOW_BARS,
        overlap_exclusion_bars=DEFAULT_OVERLAP_EXCLUSION_BARS,
        pit_rule="exchange_ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms",
        missing_policy="EXCLUDE_WITH_REASON",
    ),
    "basis_dislocation": EventDefinition(
        event_id="basis_dislocation",
        family="DERIVATIVES",
        economic_rationale="Mark-index basis shock beyond recent volatility band.",
        required_fields=("symbol", "basis_bps", "exchange_ts_ms", "receive_ts_ms"),
        pre_window_bars=DEFAULT_PRE_WINDOW_BARS,
        post_window_bars=DEFAULT_POST_WINDOW_BARS,
        control_window_bars=DEFAULT_CONTROL_WINDOW_BARS,
        overlap_exclusion_bars=DEFAULT_OVERLAP_EXCLUSION_BARS,
        pit_rule="exchange_ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms",
        missing_policy="EXCLUDE_WITH_REASON",
    ),
    "oi_step_change": EventDefinition(
        event_id="oi_step_change",
        family="DERIVATIVES",
        economic_rationale="Open-interest step change coinciding with aggressive flow.",
        required_fields=("symbol", "oi_delta", "exchange_ts_ms", "receive_ts_ms"),
        pre_window_bars=DEFAULT_PRE_WINDOW_BARS,
        post_window_bars=DEFAULT_POST_WINDOW_BARS,
        control_window_bars=DEFAULT_CONTROL_WINDOW_BARS,
        overlap_exclusion_bars=DEFAULT_OVERLAP_EXCLUSION_BARS,
        pit_rule="exchange_ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms",
        missing_policy="EXCLUDE_WITH_REASON",
    ),
    "absorption_print": EventDefinition(
        event_id="absorption_print",
        family="ORDER_FLOW",
        economic_rationale="High aggressive volume with muted price displacement (absorption).",
        required_fields=("symbol", "side", "notional", "price_delta", "exchange_ts_ms", "receive_ts_ms"),
        pre_window_bars=DEFAULT_PRE_WINDOW_BARS,
        post_window_bars=DEFAULT_POST_WINDOW_BARS,
        control_window_bars=DEFAULT_CONTROL_WINDOW_BARS,
        overlap_exclusion_bars=DEFAULT_OVERLAP_EXCLUSION_BARS,
        pit_rule="exchange_ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms",
        missing_policy="EXCLUDE_WITH_REASON",
    ),
    "liquidity_withdrawal": EventDefinition(
        event_id="liquidity_withdrawal",
        family="MICROSTRUCTURE",
        economic_rationale="Sudden reduction in near-touch liquidity depth.",
        required_fields=("symbol", "depth_delta", "exchange_ts_ms", "receive_ts_ms"),
        pre_window_bars=DEFAULT_PRE_WINDOW_BARS,
        post_window_bars=DEFAULT_POST_WINDOW_BARS,
        control_window_bars=DEFAULT_CONTROL_WINDOW_BARS,
        overlap_exclusion_bars=DEFAULT_OVERLAP_EXCLUSION_BARS,
        pit_rule="exchange_ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms",
        missing_policy="EXCLUDE_WITH_REASON",
    ),
}


def require_definition(event_id: str) -> EventDefinition:
    if event_id not in _DEFS:
        raise KeyError(f"unknown_event_definition:{event_id}")
    return _DEFS[event_id]


def list_definitions() -> list[EventDefinition]:
    return [_DEFS[eid] for eid in EVENT_DEFINITION_IDS]


def definition_catalog() -> dict[str, Any]:
    defs = list_definitions()
    return {
        "schema": "v14_b_event_definition_catalog",
        "definition_count": len(defs),
        "event_ids": list(EVENT_DEFINITION_IDS),
        "definitions": {d.event_id: d.to_dict() for d in defs},
        "predictive_edge_claimed": False,
        "is_trade": False,
        "real_event_study_execution": False,
    }
