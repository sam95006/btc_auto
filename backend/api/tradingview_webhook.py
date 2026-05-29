"""TradingView alert webhook → NEXUS rule-signal proposal shape."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from config.execution_enhancements_config import TRADINGVIEW_WEBHOOK_ENABLED, TRADINGVIEW_WEBHOOK_SECRET


def _normalize_side(raw: str) -> str:
    value = str(raw or "").strip().upper()
    if value in {"BUY", "LONG", "BULL", "ENTER_LONG"}:
        return "BUY"
    if value in {"SELL", "SHORT", "BEAR", "ENTER_SHORT"}:
        return "SELL"
    return ""


def parse_tradingview_payload(payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any] | None, str]:
    if not TRADINGVIEW_WEBHOOK_ENABLED:
        return False, None, "webhook_disabled"

    payload = dict(payload or {})
    if TRADINGVIEW_WEBHOOK_SECRET:
        token = str(payload.get("secret") or payload.get("token") or "").strip()
        if token != TRADINGVIEW_WEBHOOK_SECRET:
            return False, None, "webhook_secret_mismatch"

    symbol = str(payload.get("symbol") or payload.get("ticker") or "").upper().replace(".P", "")
    if symbol and not symbol.endswith("USDT"):
        symbol = f"{symbol}USDT"
    side = _normalize_side(payload.get("side") or payload.get("action") or payload.get("order"))
    if not symbol or not side:
        return False, None, "invalid_symbol_or_side"

    confidence = 0.55
    try:
        confidence = float(payload.get("confidence") or payload.get("score") or confidence)
    except Exception:
        confidence = 0.55

    fleet = str(payload.get("fleet") or "RADAR").upper()
    proposal = {
        "fleet": fleet,
        "symbol": symbol,
        "symbol_override": symbol,
        "side": side,
        "price": float(payload.get("price") or 0.0),
        "margin": float(payload.get("margin") or 0.0),
        "leverage": float(payload.get("leverage") or 5.0),
        "reason": f"tradingview_webhook:{payload.get('strategy') or payload.get('message') or 'alert'}",
        "strategy_key": "tradingview_webhook",
        "market_type": "futures",
        "capital_pool": "radar" if fleet == "RADAR" else "fleet",
        "adjusted_confidence": confidence,
        "raw_confidence": confidence,
        "decision_source": "tradingview_webhook",
        "proposer": "tradingview_webhook",
    }
    return True, proposal, "ok"
