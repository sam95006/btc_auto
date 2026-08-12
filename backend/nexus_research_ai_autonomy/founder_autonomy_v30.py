"""V18.2.30 Founder autonomy visibility helpers (shared shape for live feed)."""

from __future__ import annotations

from typing import Any


def empty_autonomy() -> dict[str, Any]:
    return {
        "service_status": None,
        "last_cycle": None,
        "next_cycle": None,
        "cycles_24h": None,
        "errors_24h": None,
        "open_position": None,
        "exchange_connectivity": None,
        "market_data_health": None,
    }


def map_autonomy(raw: dict[str, Any]) -> dict[str, Any]:
    out = empty_autonomy()
    block = raw.get("autonomy") if isinstance(raw.get("autonomy"), dict) else {}
    nested = raw.get("AUTONOMY SERVICE") if isinstance(raw.get("AUTONOMY SERVICE"), dict) else {}
    src = block or nested
    health = src.get("health") if isinstance(src.get("health"), dict) else {}
    out["service_status"] = src.get("service_status") or health.get("service_status")
    out["last_cycle"] = src.get("last_cycle") or health.get("last_cycle_completed_at")
    out["next_cycle"] = src.get("next_cycle") or health.get("next_cycle_due_at")
    out["cycles_24h"] = src.get("cycles_24h") if src.get("cycles_24h") is not None else health.get("cycles_24h")
    out["errors_24h"] = src.get("errors_24h") if src.get("errors_24h") is not None else health.get("errors_24h")
    out["open_position"] = (
        src.get("open_position") if src.get("open_position") is not None else health.get("open_position")
    )
    out["exchange_connectivity"] = src.get("exchange_connectivity") or health.get("exchange_connectivity")
    out["market_data_health"] = src.get("market_data_health") or health.get("market_data_health")
    return out
