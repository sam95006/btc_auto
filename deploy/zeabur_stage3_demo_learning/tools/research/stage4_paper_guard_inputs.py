"""Stage 4.18-E paper guard MAE source selection — offline/paper path only."""
from __future__ import annotations

from typing import Any, Dict, Tuple

MAE_REASONABLE_UPPER_BOUND = 5.0
MAE_SOURCE_LLM = "llm_mae_risk_estimate_pct"
MAE_SOURCE_LEGACY = "legacy_market_proxy"
MAE_SOURCE_MISSING = "missing"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _volatility_level(decision: Dict[str, Any]) -> str:
    mc = decision.get("market_context") or {}
    level = str(mc.get("volatility_level") or "unknown").lower()
    if level in {"low", "medium", "high"}:
        return level
    return "unknown"


def legacy_market_mae_proxy_pct(decision: Dict[str, Any]) -> float:
    """Legacy MAE estimate from market volatility (pre-4.18-E)."""
    mc = decision.get("market_context") or {}
    vol15 = mc.get("volatility_15m")
    if vol15 is not None:
        v = abs(_safe_float(vol15))
        return v * 100.0 if v < 1.0 else v
    mapping = {"high": 0.30, "medium": 0.15, "low": 0.06, "unknown": 0.10}
    return mapping.get(_volatility_level(decision), 0.10)


def _llm_mae_valid(decision: Dict[str, Any]) -> Tuple[bool, float]:
    raw = decision.get("mae_risk_estimate_pct")
    if raw is None:
        return False, 0.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return False, 0.0
    if value < 0 or value > MAE_REASONABLE_UPPER_BOUND:
        return False, 0.0
    return True, value


def get_paper_mae_pct(
    decision: Dict[str, Any],
    *,
    mae_source_mode: str = "llm_mae_primary",
) -> Tuple[float, str]:
    """
    Return (mae_pct, source).

    source:
      - llm_mae_risk_estimate_pct
      - legacy_market_proxy
      - missing (only when legacy cannot be computed — rare)
    """
    llm_ok, llm_val = _llm_mae_valid(decision)
    legacy_val = legacy_market_mae_proxy_pct(decision)

    if mae_source_mode == "legacy_proxy_primary":
        if legacy_val > 0:
            return legacy_val, MAE_SOURCE_LEGACY
        return 0.0, MAE_SOURCE_MISSING

    if mae_source_mode in {"llm_mae_primary", "compare_llm_vs_proxy"}:
        if llm_ok:
            return llm_val, MAE_SOURCE_LLM
        if legacy_val > 0:
            return legacy_val, MAE_SOURCE_LEGACY
        return 0.0, MAE_SOURCE_MISSING

    if llm_ok:
        return llm_val, MAE_SOURCE_LLM
    if legacy_val > 0:
        return legacy_val, MAE_SOURCE_LEGACY
    return 0.0, MAE_SOURCE_MISSING


def llm_mae_risk_estimate_pct(decision: Dict[str, Any]) -> float:
    ok, val = _llm_mae_valid(decision)
    return val if ok else 0.0


__all__ = [
    "MAE_REASONABLE_UPPER_BOUND",
    "MAE_SOURCE_LEGACY",
    "MAE_SOURCE_LLM",
    "MAE_SOURCE_MISSING",
    "get_paper_mae_pct",
    "legacy_market_mae_proxy_pct",
    "llm_mae_risk_estimate_pct",
]
