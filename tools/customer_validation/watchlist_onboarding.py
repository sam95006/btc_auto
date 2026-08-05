"""Watchlist onboarding for Concierge validation participants."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.customer_validation.hard_bans import HardBanViolation, refuse_fabrication
from tools.customer_validation.registry import list_participants
from tools.customer_validation.store import append_row, load_collection

MAX_WATCHLIST_SYMBOLS = 25
FORBIDDEN_ORDER_HINTS = (
    "place_order",
    "market_buy",
    "market_sell",
    "copy_trade",
    "auto_trade",
)


def list_watchlist_onboardings(workspace=None) -> list[dict[str, Any]]:
    return load_collection("watchlist_onboardings", workspace)


def watchlist_onboarding_count(workspace=None) -> int:
    return len(list_watchlist_onboardings(workspace))


def record_watchlist_onboarding(
    *,
    participant_id: str,
    symbols: list[str],
    thesis_links: list[str] | None = None,
    alert_preferences: dict[str, Any] | None = None,
    exchange_write_requested: bool = False,
    workspace=None,
) -> dict[str, Any]:
    known = {p["participant_id"] for p in list_participants(workspace)}
    if participant_id not in known:
        refuse_fabrication("watchlist onboarding refused for unknown participant_id")
    if exchange_write_requested:
        raise HardBanViolation(
            "HARD BAN: watchlist onboarding must not write to exchanges"
        )
    cleaned = []
    for raw in symbols or []:
        sym = str(raw or "").strip().upper()
        if not sym:
            continue
        lowered = sym.lower()
        if any(token in lowered for token in FORBIDDEN_ORDER_HINTS):
            raise HardBanViolation(f"HARD BAN: order-like watchlist symbol refused: {sym}")
        cleaned.append(sym)
    if not cleaned:
        refuse_fabrication("empty watchlist onboarding refused")
    if len(cleaned) > MAX_WATCHLIST_SYMBOLS:
        raise HardBanViolation(
            f"watchlist exceeds max symbols ({MAX_WATCHLIST_SYMBOLS})"
        )
    prefs = dict(alert_preferences or {})
    if prefs.get("auto_execute") or prefs.get("copy_trading"):
        raise HardBanViolation(
            "HARD BAN: auto-execute / copy-trading alert preferences refused"
        )
    row = {
        "participant_id": participant_id,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symbols": cleaned,
        "thesis_links": [str(x).strip() for x in (thesis_links or []) if str(x).strip()],
        "alert_preferences": {
            "integrity_alerts": bool(prefs.get("integrity_alerts", True)),
            "price_noise_suppressed": bool(prefs.get("price_noise_suppressed", True)),
            "auto_execute": False,
            "copy_trading": False,
        },
        "exchange_write": False,
        "fabricated": False,
    }
    return append_row("watchlist_onboardings", row, workspace)
