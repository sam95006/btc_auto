"""Stage 4.13 fixed fleet read-only summary helpers."""
from __future__ import annotations

import os
from collections import Counter
from typing import Any, Dict, List, Set

DEFAULT_STAGE4_FLEET_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT")


def parse_stage4_symbols(raw: str | None = None) -> List[str]:
    """Parse comma-separated STAGE4_SYMBOLS (or explicit raw string)."""
    text = (raw if raw is not None else os.environ.get("STAGE4_SYMBOLS", "")).strip()
    if not text:
        return list(DEFAULT_STAGE4_FLEET_SYMBOLS)
    return [s.strip().upper() for s in text.split(",") if s.strip()]


def resolve_stage4_read_only_symbols() -> frozenset[str]:
    """Symbols allowed for read-only market context (fixed fleet default)."""
    raw = os.environ.get("STAGE4_READ_ONLY_SYMBOLS", "").strip()
    if raw:
        return frozenset(s.strip().upper() for s in raw.split(",") if s.strip())
    return frozenset(DEFAULT_STAGE4_FLEET_SYMBOLS)


def classify_market_context_failure(ctx: Dict[str, Any]) -> str | None:
    """Return error type when market context is unusable; None if ok/partial."""
    limitations = list(ctx.get("data_limitations") or [])
    for lim in limitations:
        if "symbol_not_in_read_allowlist" in str(lim):
            return "symbol_unavailable_or_market_context_failed"
    data_quality = str(ctx.get("data_quality") or "")
    last_price = float(ctx.get("last_price") or 0)
    if data_quality == "error" and last_price <= 0:
        if limitations:
            return "symbol_unavailable_or_market_context_failed"
    for lim in limitations:
        low = str(lim).lower()
        if "ticker_error" in low or "kline_error" in low or "category" in low:
            return "symbol_unavailable_or_market_context_failed"
    return None


def _empty_per_symbol_row() -> Dict[str, Any]:
    return {
        "effective_decision_count": 0,
        "decision_count": 0,
        "provider_chain_failed_count": 0,
        "parse_error_count": 0,
        "order_sent_count": 0,
        "mock_ai_used_count": 0,
        "decision_intent_distribution": {},
        "market_context_error": None,
    }


def build_per_symbol_summary(
    *,
    symbols_configured: List[str],
    decisions: List[Dict[str, Any]],
    symbols_with_market_context_error: Set[str] | None = None,
    per_symbol_chain_failed: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    """Aggregate per-symbol stats for Stage 4.13 fleet summary."""
    configured = [s.upper() for s in symbols_configured]
    per_symbol: Dict[str, Dict[str, Any]] = {sym: _empty_per_symbol_row() for sym in configured}
    market_errors = {s.upper() for s in (symbols_with_market_context_error or set())}
    chain_failed = per_symbol_chain_failed or {}

    for sym in configured:
        if sym in market_errors:
            per_symbol[sym]["market_context_error"] = "symbol_unavailable_or_market_context_failed"

    symbols_seen: Set[str] = set()
    for d in decisions:
        sym = str(d.get("symbol") or "").upper()
        if not sym:
            continue
        symbols_seen.add(sym)
        if sym not in per_symbol:
            per_symbol[sym] = _empty_per_symbol_row()
        row = per_symbol[sym]
        row["decision_count"] += 1
        if d.get("order_sent"):
            row["order_sent_count"] += 1
        if d.get("is_mock_ai"):
            row["mock_ai_used_count"] += 1
        if d.get("parse_error"):
            row["parse_error_count"] += 1
        else:
            if d.get("real_llm_used") and not d.get("is_mock_ai"):
                row["effective_decision_count"] += 1
        intent = str(d.get("decision_intent") or d.get("final_action") or "").strip().lower()
        if intent:
            dist = row["decision_intent_distribution"]
            dist[intent] = int(dist.get(intent) or 0) + 1

    for sym, count in chain_failed.items():
        up = sym.upper()
        if up not in per_symbol:
            per_symbol[up] = _empty_per_symbol_row()
        per_symbol[up]["provider_chain_failed_count"] = int(count)

    symbols_missing = [s for s in configured if s not in symbols_seen]
    return {
        "symbols_configured": configured,
        "symbols_seen": sorted(symbols_seen),
        "per_symbol": per_symbol,
        "symbols_missing": symbols_missing,
        "symbols_with_market_context_error": sorted(market_errors),
        "all_symbols_read_only": True,
    }


def per_symbol_decision_counts(per_symbol: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    return {sym: int(row.get("effective_decision_count") or 0) for sym, row in per_symbol.items()}


def per_symbol_chain_failed_counts(per_symbol: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    return {sym: int(row.get("provider_chain_failed_count") or 0) for sym, row in per_symbol.items()}


def per_symbol_intent_distributions(per_symbol: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    return {sym: dict(row.get("decision_intent_distribution") or {}) for sym, row in per_symbol.items()}
