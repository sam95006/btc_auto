"""Per-symbol Stage 4 dry-run summary aggregation."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List


def _empty_symbol_stats() -> Dict[str, Any]:
    return {
        "effective_decision_count": 0,
        "real_llm_decision_count": 0,
        "context_unavailable_count": 0,
        "provider_chain_failed_count": 0,
        "parse_error_count": 0,
        "order_sent_count": 0,
        "mock_ai_used_count": 0,
        "decision_intent_distribution": {},
        "market_context_error": None,
    }


def build_per_symbol_summary(
    decisions: List[Dict[str, Any]],
    *,
    symbols_configured: List[str],
    symbols_with_market_context_error: List[str] | None = None,
) -> Dict[str, Any]:
    configured = [s.upper() for s in symbols_configured]
    per_symbol: Dict[str, Dict[str, Any]] = {sym: _empty_symbol_stats() for sym in configured}
    ctx_errors = {s.upper() for s in (symbols_with_market_context_error or [])}

    for sym in ctx_errors:
        if sym in per_symbol:
            per_symbol[sym]["market_context_error"] = "symbol_unavailable_or_market_context_failed"
            per_symbol[sym]["context_unavailable_count"] = per_symbol[sym].get("context_unavailable_count", 0)

    for decision in decisions:
        sym = str(decision.get("symbol") or "").upper()
        if not sym:
            continue
        if sym not in per_symbol:
            per_symbol[sym] = _empty_symbol_stats()
        row = per_symbol[sym]
        if decision.get("market_context_unavailable"):
            row["context_unavailable_count"] += 1
            row["market_context_error"] = str(
                decision.get("market_context_error") or "symbol_unavailable_or_market_context_failed"
            )
            continue
        if decision.get("parse_error"):
            row["parse_error_count"] += 1
        elif decision.get("real_llm_used"):
            row["real_llm_decision_count"] += 1
            row["effective_decision_count"] += 1
        if decision.get("is_mock_ai"):
            row["mock_ai_used_count"] += 1
        if decision.get("order_sent"):
            row["order_sent_count"] += 1
        attempts = decision.get("provider_attempts") or []
        if any(a.get("error_type") == "provider_chain_failed" for a in attempts):
            row["provider_chain_failed_count"] += 1
        intent = str(decision.get("decision_intent") or "unknown")
        dist = row["decision_intent_distribution"]
        dist[intent] = int(dist.get(intent) or 0) + 1

    symbols_seen = sorted({str(d.get("symbol") or "").upper() for d in decisions if d.get("symbol")})
    symbols_missing = [s for s in configured if s not in symbols_seen]
    merged_ctx_errors = sorted(ctx_errors | {s for s, r in per_symbol.items() if r.get("market_context_error")})

    return {
        "symbols_configured": configured,
        "symbols_seen": symbols_seen,
        "per_symbol": per_symbol,
        "symbols_missing": symbols_missing,
        "symbols_with_market_context_error": merged_ctx_errors,
        "all_symbols_read_only": True,
    }


def per_symbol_decision_counts(summary: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for sym, row in (summary.get("per_symbol") or {}).items():
        out[sym] = int(row.get("effective_decision_count") or 0) + int(row.get("context_unavailable_count") or 0)
    return out
