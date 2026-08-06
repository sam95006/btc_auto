"""Fixtures for PUB17-C private-to-public projection tests."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def private_core_fixture(
    *,
    entry_threshold: float = 0.73,
    exit_threshold: float = 0.31,
    founder_capital: float = 1_250_000.0,
    suggestion: str = "WAIT",
    risk: str = "MEDIUM",
    trust: str = "TRUSTED",
) -> dict[str, Any]:
    """Private core blob containing banned fields + public-safe nest."""
    return {
        "as_of": "2026-08-06T01:00:00Z",
        "lineage_id": "pub17c-fixture-lineage",
        "symbol": "BTCUSDT",
        # --- banned private surface ---
        "entry_threshold": entry_threshold,
        "exit_threshold": exit_threshold,
        "proprietary_threshold": entry_threshold,
        "proprietary_thresholds": {"entry": entry_threshold, "exit": exit_threshold},
        "strategy_parameters": {"lookback": 48, "weight": 0.42},
        "strategy_params": {"alpha": 0.17},
        "founder_capital": founder_capital,
        "exact_private_position": {"side": "LONG", "size": 3.5, "leverage": 5},
        "position": {"size": 3.5, "entry_price": 64000.0},
        "leverage": 5,
        "exchange_credentials": {"api_key": "AK_SECRET", "api_secret": "SK_SECRET"},
        "private_trade_ledger": [{"order_id": "oid-1", "qty": 0.1}],
        "private_lesson_text": "Never chase funding spikes after 02:00 UTC.",
        "lesson_memory": {"text": "secret lesson"},
        "raw_decision_memory_graph_nodes": [
            {"node_id": "n1", "payload": {"private": True}}
        ],
        "graph_nodes_raw": [{"node_id": "n1"}],
        "execution_controls": {"place_order": True, "leverage_control": True},
        "execution_route": "bybit_mainnet",
        # --- public-safe nest ---
        "public": {
            "symbol": "BTCUSDT",
            "market_state": "MIXED_VOLATILITY",
            "regime_summary": "Elevated event risk with orderly liquidity",
            "ai_public_suggestion": suggestion,
            "risk_category": risk,
            "evidence_summary": "Public momentum alignment across short horizons",
            "counter_evidence_summary": "Elevated event-risk window approaching",
            "abstention_reason": None,
            "data_trust": trust,
            "historical_similarity_aggregate": {
                "overlap_band": "MEDIUM",
                "similar_case_count": 7,
            },
            "delayed_aggregated_performance": {
                "value": 0.041,
                "window_label": "30D_DELAYED",
            },
        },
    }


def private_core_threshold_variant(threshold: float) -> dict[str, Any]:
    """Same public nest; only private thresholds differ (inference probe)."""
    core = private_core_fixture(entry_threshold=threshold, exit_threshold=1.0 - threshold)
    core["proprietary_threshold"] = threshold
    core["proprietary_thresholds"] = {"entry": threshold, "exit": 1.0 - threshold}
    return core


def adversarial_dirty_payload() -> dict[str, Any]:
    """Dirty mix attempting to smuggle banned keys through projection."""
    core = private_core_fixture()
    dirty = deepcopy(core)
    dirty["public"] = {
        **core["public"],
        "entry_threshold": 0.55,
        "execution_controls": {"place_order": True},
        "founder_capital": 999999,
        "private_lesson_text": "leak me",
    }
    return dirty
