"""NEXUS Microstructure Data Foundation V1 — contracts (no strategies)."""
from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "microstructure_data_foundation_v1"

AGGRESSIVE_TRADE_EVENT_FIELDS = (
    "event_id",
    "exchange",
    "symbol",
    "trade_id",
    "exchange_timestamp",
    "receive_timestamp",
    "side",
    "price",
    "quantity",
    "notional",
    "aggressor_side_source",
    "sequence_or_dedup_key",
    "instrument_snapshot_id",
    "capture_session_id",
)

LIQUIDATION_EVENT_FIELDS = (
    "event_id",
    "exchange",
    "symbol",
    "exchange_timestamp",
    "receive_timestamp",
    "liquidation_side",
    "price",
    "quantity",
    "notional",
    "event_source",
    "sequence_or_dedup_key",
    "instrument_snapshot_id",
    "capture_session_id",
)

PARTITION_REPORT_FIELDS = (
    "record_count",
    "first_exchange_timestamp",
    "last_exchange_timestamp",
    "first_receive_timestamp",
    "last_receive_timestamp",
    "duplicate_count",
    "out_of_order_count",
    "parse_error_count",
    "gap_suspected_count",
    "reconnect_count",
    "checksum",
    "schema_version",
)


def data_contracts() -> dict[str, Any]:
    return {
        "schema": "NEXUS_MICROSTRUCTURE_DATA_FOUNDATION_V1_CONTRACTS",
        "schema_version": SCHEMA_VERSION,
        "selected_data_families": ["AGGRESSIVE_TRADE_FLOW", "LIQUIDATION_EVENTS"],
        "exchange_phase1": "BYBIT",
        "capture_mode": "PUBLIC_READONLY_WEBSOCKET",
        "authenticated_exchange_write_client": False,
        "contracts": {
            "AggressiveTradeEvent": {"required_fields": list(AGGRESSIVE_TRADE_EVENT_FIELDS)},
            "LiquidationEvent": {"required_fields": list(LIQUIDATION_EVENT_FIELDS)},
            "MicrostructurePartition": {"required_fields": list(PARTITION_REPORT_FIELDS)},
            "MicrostructureCaptureSession": {
                "required_fields": [
                    "capture_session_id",
                    "started_at",
                    "stopped_at",
                    "symbols",
                    "universe_snapshot_id",
                    "smoke_cohort_label",
                ]
            },
            "MicrostructureIntegrityReport": {
                "required_fields": [
                    "duplicate_count",
                    "out_of_order_count",
                    "parse_error_count",
                    "gap_suspected_count",
                    "reconnect_count",
                    "checksum_reproducible",
                ]
            },
        },
        "aggressor_side_rule": "Never invent; use UNKNOWN when official event lacks aggressor",
        "new_strategy_generation_allowed": False,
        "backtest_allowed": False,
        "formal_walk_forward_allowed": False,
        "oos_allowed": False,
        "demo_orders_allowed": False,
    }
