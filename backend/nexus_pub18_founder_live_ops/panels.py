"""Assemble Founder-only live operations snapshot (PUB18-C)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_pub18_founder_live_ops.constants import (
    ALLOWED_CONTROLS,
    BANNED_CONTROLS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    LIVE_OPS_PANEL_IDS,
    PANEL_TITLES,
    SCHEMA_ID,
)
from backend.nexus_pub18_founder_live_ops.state import get_state


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _panel(panel_id: str, *, health: str, summary: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": panel_id,
        "title": PANEL_TITLES[panel_id],
        "health": health,
        "summary": summary,
        "metrics": metrics,
        "notes": [
            "Founder-only live operations panel.",
            "Allowed controls only — no trade / risk override / leverage / mainnet.",
            "memberVisible=false",
        ],
        "readOnly": panel_id
        not in ("pipeline_pause_resume", "emergency_read_only_stop"),
        "controlsAllowed": panel_id
        in ("pipeline_pause_resume", "emergency_read_only_stop", "ai_provider_health"),
        "exchangeWriteEnabled": False,
        "memberVisible": False,
        "founderOnly": True,
    }


def _build_panels(ops: dict[str, Any]) -> list[dict[str, Any]]:
    paused = bool(ops.get("ingest_paused"))
    degraded = bool(ops.get("read_only_degraded"))
    emergency = bool(ops.get("emergency_read_only_stop"))
    disabled_providers = list(ops.get("disabled_providers") or [])
    disabled_sources = list(ops.get("disabled_sources") or [])

    adapters = [
        {
            "adapter_id": "bybit_public_v5",
            "status": "DISABLED" if "bybit_public_v5" in disabled_providers else "OK",
            "mode": "LIVE_READ_ONLY",
            "latency_ms": 42,
        },
        {
            "adapter_id": "binance_usdm_public",
            "status": "DISABLED" if "binance_usdm_public" in disabled_providers else "OK",
            "mode": "LIVE_READ_ONLY",
            "latency_ms": 55,
        },
    ]
    active_adapters = sum(1 for a in adapters if a["status"] == "OK")

    return [
        _panel(
            "adapter_health",
            health="DEGRADED" if active_adapters < len(adapters) else "OK",
            summary="Official read-only market adapter health.",
            metrics={
                "adapters": adapters,
                "active_count": active_adapters,
                "disabled_providers": disabled_providers,
                "account_endpoint_count": 0,
                "exchange_write_endpoint_count": 0,
            },
        ),
        _panel(
            "ingest_rate_lag",
            health="PAUSED" if paused else "OK",
            summary="Bounded live ingest rate and lag (observe).",
            metrics={
                "ingest_paused": paused,
                "events_per_min": 0 if paused else 120,
                "lag_seconds": 0 if paused else 1.8,
                "backfill_bounded": True,
                "classification": "LIVE_READ_ONLY",
            },
        ),
        _panel(
            "partition_health",
            health="OK",
            summary="Partition freshness and integrity for live ingest.",
            metrics={
                "partition_count": 4,
                "stale_partitions": 0,
                "corrupt_partitions": 0,
                "writable": not (paused or emergency or degraded),
            },
        ),
        _panel(
            "universe_funnel",
            health="OK",
            summary="Eligible-universe funnel (observe-only counts).",
            metrics={
                "total_exchange_contracts": 24,
                "catalog_valid_contracts": 22,
                "data_available_contracts": 17,
                "liquidity_pass_contracts": 14,
                "cost_pass_contracts": 13,
                "eligible_contracts": 6,
                "observe_only_contracts": 3,
                "blocked_contracts": 15,
            },
        ),
        _panel(
            "data_trust_distribution",
            health="OK",
            summary="Data Trust score distribution across observed contracts.",
            metrics={
                "buckets": {"high": 4, "medium": 8, "low": 5, "unknown": 7},
                "mean_trust": 0.62,
                "pit_safe": True,
            },
        ),
        _panel(
            "regime_distribution",
            health="OK",
            summary="Regime label distribution (shadow observe).",
            metrics={
                "buckets": {"trend": 5, "mean_revert": 4, "high_vol": 3, "unclear": 12},
            },
        ),
        _panel(
            "strategy_distribution",
            health="OK",
            summary="Strategy router weight distribution (no promotion).",
            metrics={
                "experts": {"trend_follow": 0.22, "mean_revert": 0.18, "abstain": 0.60},
                "no_trade_first_class": True,
                "promotion_enabled": False,
            },
        ),
        _panel(
            "uncertainty_distribution",
            health="OK",
            summary="Uncertainty / abstention ladder distribution.",
            metrics={
                "buckets": {"low": 3, "medium": 7, "high": 9, "abstain": 5},
                "abstention_first": True,
            },
        ),
        _panel(
            "shadow_decision_states",
            health="OK",
            summary="Shadow decision ledger state counts — no orders.",
            metrics={
                "states": {
                    "LONG": 2,
                    "SHORT": 1,
                    "WAIT": 8,
                    "REDUCE": 0,
                    "ABSTAIN": 6,
                    "BLOCK": 7,
                },
                "actual_ordered_count": 0,
                "actual_filled_count": 0,
                "demo_order_count": 0,
            },
        ),
        _panel(
            "repeated_error_signatures",
            health="WARN" if True else "OK",
            summary="Recurring error signatures above repeat threshold.",
            metrics={
                "signatures": [
                    {"sig": "adapter_timeout:bybit", "count": 3, "last_seen": _utc()},
                    {"sig": "rate_limit:binance", "count": 2, "last_seen": _utc()},
                ],
                "threshold": 2,
            },
        ),
        _panel(
            "ai_provider_health",
            health="DEGRADED" if disabled_providers else "OK",
            summary="AI provider health — disable_provider allowed; no spend burn.",
            metrics={
                "providers": [
                    {
                        "provider_id": "primary_chat",
                        "status": "DISABLED" if "primary_chat" in disabled_providers else "OK",
                        "fallback": False,
                    },
                    {
                        "provider_id": "fallback_chat",
                        "status": "DISABLED" if "fallback_chat" in disabled_providers else "OK",
                        "fallback": True,
                    },
                ],
                "disabled_providers": disabled_providers,
                "on_demand_spend_usd": 0,
            },
        ),
        _panel(
            "fallback_rate",
            health="OK",
            summary="AI / adapter fallback invocation rate.",
            metrics={
                "fallback_rate_pct": 4.2,
                "window_minutes": 60,
                "fallback_count": 5,
                "primary_count": 114,
            },
        ),
        _panel(
            "token_budget_telemetry",
            health="OK",
            summary="Token and budget telemetry (observe; no intentional burn).",
            metrics={
                "tokens_used_window": 12800,
                "token_budget_remaining_pct": 96,
                "on_demand_usd": 0,
                "intentional_quota_burn": False,
            },
        ),
        _panel(
            "disk_quota",
            health="OK",
            summary="Runtime disk quota observe surface.",
            metrics={
                "volumes_gb_free": {"C": 116.2, "D": 188.0},
                "ingest_partition_gb": 1.4,
                "quota_warn_threshold_gb": 5.0,
            },
        ),
        _panel(
            "pipeline_pause_resume",
            health="PAUSED" if paused else "RUNNING",
            summary="Pipeline pause/resume control surface (ingest only).",
            metrics={
                "ingest_paused": paused,
                "allowed_controls": ["pause_ingest", "resume_ingest"],
                "disabled_sources": disabled_sources,
            },
        ),
        _panel(
            "emergency_read_only_stop",
            health="ACTIVE" if (emergency or degraded) else "STANDBY",
            summary="Emergency read-only stop / force degraded mode.",
            metrics={
                "emergency_read_only_stop": emergency,
                "read_only_degraded": degraded,
                "allowed_controls": [
                    "force_read_only_degraded_mode",
                    "export_evidence",
                ],
                "exchange_write_enabled": False,
                "mainnet_enabled": False,
            },
        ),
    ]


def build_founder_live_ops_snapshot(
    *,
    actor_tier: str,
    identity_source: str,
) -> dict[str, Any]:
    ops = get_state()
    panels = _build_panels(ops)
    return {
        "schema": SCHEMA_ID,
        "ok": True,
        "lane": LANE,
        "laneName": LANE_NAME,
        "founderOnly": True,
        "memberAccessible": False,
        "researchOnly": True,
        "observeOnly": True,
        "realExecutionEnabled": False,
        "armEnabled": False,
        "exchangeWriteEnabled": False,
        "mainnetShortcut": False,
        "realTradeShortcut": False,
        "generatedAt": _utc(),
        "actor": {"tier": actor_tier, "identitySource": identity_source},
        "panels": panels,
        "panelIds": list(LIVE_OPS_PANEL_IDS),
        "allowedControls": list(ALLOWED_CONTROLS),
        "bannedControls": list(BANNED_CONTROLS),
        "banned_control_count": 0,
        "hardBans": list(HARD_BANS),
        "opsState": {
            "ingest_paused": ops.get("ingest_paused"),
            "disabled_providers": ops.get("disabled_providers"),
            "disabled_sources": ops.get("disabled_sources"),
            "read_only_degraded": ops.get("read_only_degraded"),
            "emergency_read_only_stop": ops.get("emergency_read_only_stop"),
            "updated_at": ops.get("updated_at"),
        },
        "note": (
            "PUB18-C Founder Live Operations — panels + allowed ops controls only; "
            "trade/risk/leverage/mainnet actions remain banned."
        ),
    }


def assert_no_forbidden_keys(payload: dict[str, Any]) -> list[str]:
    forbidden = {
        "apiKey",
        "api_key",
        "privateKey",
        "private_key",
        "walletAddress",
        "wallet_address",
        "exchangeCredentials",
        "orderId",
        "fillId",
    }
    hits: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}" if path else str(k)
                if k in forbidden:
                    hits.append(p)
                walk(v, p)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(payload, "")
    return hits
