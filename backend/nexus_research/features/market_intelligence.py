"""NEXUS Phase 6.4 — Market Intelligence Composite Indices.

Provides:
- NEXUS Market Sentiment Index (MSI) — transparent weighted components
- NEXUS Altcoin Breadth Index (ABI) — equal-weight tracked universe
- NEXUS Overall Market Direction — long/neutral/short/confirmed/watch/risk-blocked

IMPORTANT NAMING POLICY:
  These are NEXUS-proprietary indices.
  They are NOT the "Official Fear & Greed Index" (crypto.com/research or others).
  They are NOT the "Altseason Index" or any external brand.
  All labels use the NEXUS-* prefix.

Research-only — no private API, no production mutations.
"""
from __future__ import annotations

import datetime
import time
from typing import Any, Optional


def _utc_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


# ─────────────────────────────────────────────────────────────────────────────
# NEXUS Market Sentiment Index (MSI)
# ─────────────────────────────────────────────────────────────────────────────

# Component weights must sum to 1.0
_MSI_WEIGHTS = {
    "price_momentum": 0.25,     # short-term price momentum (e.g. RSI + returns)
    "volume_momentum": 0.20,    # volume z-score + taker buy pressure
    "funding_rate": 0.20,       # normalized funding rate signal
    "open_interest_change": 0.15,  # OI trend direction
    "breadth": 0.20,            # altcoin breadth (from ABI)
}
assert abs(sum(_MSI_WEIGHTS.values()) - 1.0) < 1e-9, "MSI weights must sum to 1.0"


def build_market_sentiment_index(components: dict[str, Any]) -> dict[str, Any]:
    """Compute NEXUS Market Sentiment Index from normalized component scores.

    Parameters
    ----------
    components:
        Dict mapping component names to normalized scores in [-1.0, 1.0].
        Missing components set to UNAVAILABLE (not filled with 0).
        Keys: price_momentum, volume_momentum, funding_rate,
              open_interest_change, breadth.

    Returns
    -------
    dict with:
        value: float [-1, 1] or None
        label: EXTREME_GREED / GREED / NEUTRAL / FEAR / EXTREME_FEAR / UNAVAILABLE
        quality: COMPLETE / PARTIAL / UNAVAILABLE
        components: per-component breakdown
    """
    available_components: dict[str, float] = {}
    component_breakdown: dict[str, Any] = {}
    missing: list[str] = []

    for name, weight in _MSI_WEIGHTS.items():
        raw = components.get(name)
        if raw is None:
            component_breakdown[name] = {
                "value": None, "weight": weight, "quality": "UNAVAILABLE",
                "reason": "not_provided",
            }
            missing.append(name)
        else:
            val = float(raw) if not isinstance(raw, dict) else raw.get("value")
            if val is None:
                component_breakdown[name] = {
                    "value": None, "weight": weight, "quality": "UNAVAILABLE",
                    "reason": "null_value",
                }
                missing.append(name)
            else:
                # Clamp to [-1, 1]
                val = max(-1.0, min(1.0, val))
                available_components[name] = val
                component_breakdown[name] = {"value": val, "weight": weight, "quality": "COMPLETE"}

    if not available_components:
        return {
            "index": "NEXUS_MARKET_SENTIMENT_INDEX",
            "description": "NEXUS proprietary sentiment composite. NOT the official Fear & Greed Index.",
            "value": None,
            "label": "UNAVAILABLE",
            "quality": "UNAVAILABLE",
            "reason": "no_components_available",
            "components": component_breakdown,
            "researchOnly": True,
            "generatedAt": _utc_iso(),
        }

    # Reweight by available components
    available_weight = sum(_MSI_WEIGHTS[k] for k in available_components)
    weighted_sum = sum(available_components[k] * _MSI_WEIGHTS[k] for k in available_components)
    msi_score = weighted_sum / available_weight if available_weight > 0 else None
    quality = "COMPLETE" if not missing else "PARTIAL"
    label = _msi_label(msi_score)

    return {
        "index": "NEXUS_MARKET_SENTIMENT_INDEX",
        "description": "NEXUS proprietary sentiment composite. NOT the official Fear & Greed Index.",
        "value": msi_score,
        "label": label,
        "quality": quality,
        "missingComponents": missing,
        "components": component_breakdown,
        "weights": _MSI_WEIGHTS,
        "researchOnly": True,
        "generatedAt": _utc_iso(),
    }


def _msi_label(score: Optional[float]) -> str:
    if score is None:
        return "UNAVAILABLE"
    if score >= 0.6:
        return "EXTREME_GREED"
    if score >= 0.2:
        return "GREED"
    if score >= -0.2:
        return "NEUTRAL"
    if score >= -0.6:
        return "FEAR"
    return "EXTREME_FEAR"


# ─────────────────────────────────────────────────────────────────────────────
# NEXUS Altcoin Breadth Index (ABI)
# ─────────────────────────────────────────────────────────────────────────────

def build_altcoin_breadth_index(universe_states: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute NEXUS Altcoin Breadth Index.

    Uses equal weighting across a tracked universe of altcoins.
    Breadth = fraction of universe with positive 24h performance.

    Parameters
    ----------
    universe_states:
        List of dicts, each with keys:
          symbol, change24hPct (float or None), quality (optional)

    Returns
    -------
    dict with:
        index: NEXUS_ALTCOIN_BREADTH_INDEX
        breadth: [0, 1] fraction bullish
        label: STRONG_BREADTH / BROAD_BREADTH / MIXED / NARROW_BREADTH / WEAK_BREADTH
        universe_size: total tracked
        available_count: symbols with data
        bullish_count: symbols with positive 24h
    """
    if not universe_states:
        return {
            "index": "NEXUS_ALTCOIN_BREADTH_INDEX",
            "value": None,
            "label": "UNAVAILABLE",
            "quality": "UNAVAILABLE",
            "reason": "empty_universe",
            "researchOnly": True,
            "generatedAt": _utc_iso(),
        }

    bullish = 0
    bearish = 0
    missing = 0
    symbol_states: list[dict[str, Any]] = []

    for state in universe_states:
        sym = str(state.get("symbol") or "")
        chg = state.get("change24hPct")
        if chg is None:
            missing += 1
            symbol_states.append({"symbol": sym, "change24hPct": None, "direction": "UNAVAILABLE"})
        else:
            try:
                pct = float(chg)
            except (TypeError, ValueError):
                missing += 1
                symbol_states.append({"symbol": sym, "change24hPct": None, "direction": "UNAVAILABLE"})
                continue
            if pct > 0:
                bullish += 1
                direction = "UP"
            elif pct < 0:
                bearish += 1
                direction = "DOWN"
            else:
                bearish += 1  # flat counted as non-bullish
                direction = "FLAT"
            symbol_states.append({"symbol": sym, "change24hPct": pct, "direction": direction})

    available = bullish + bearish
    breadth = bullish / available if available > 0 else None
    quality = "COMPLETE" if missing == 0 else ("PARTIAL" if available > 0 else "UNAVAILABLE")
    label = _abi_label(breadth)

    return {
        "index": "NEXUS_ALTCOIN_BREADTH_INDEX",
        "description": "NEXUS equal-weight altcoin breadth across tracked universe. NOT the Altseason Index.",
        "value": breadth,
        "label": label,
        "quality": quality,
        "universeSize": len(universe_states),
        "availableCount": available,
        "bullishCount": bullish,
        "bearishCount": bearish,
        "missingCount": missing,
        "weighting": "equal_weight",
        "symbols": symbol_states,
        "researchOnly": True,
        "generatedAt": _utc_iso(),
    }


def _abi_label(breadth: Optional[float]) -> str:
    if breadth is None:
        return "UNAVAILABLE"
    if breadth >= 0.75:
        return "STRONG_BREADTH"
    if breadth >= 0.55:
        return "BROAD_BREADTH"
    if breadth >= 0.45:
        return "MIXED"
    if breadth >= 0.25:
        return "NARROW_BREADTH"
    return "WEAK_BREADTH"


# ─────────────────────────────────────────────────────────────────────────────
# NEXUS Overall Market Direction
# ─────────────────────────────────────────────────────────────────────────────

def build_overall_market_direction(candidate_states: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute NEXUS Overall Market Direction from candidate/symbol states.

    Parameters
    ----------
    candidate_states:
        List of dicts, each with keys:
          symbol, direction (long/short/neutral),
          confirmed (bool), watch (bool), risk_blocked (bool)

    Returns
    -------
    dict with counts for:
        long, short, neutral, confirmed, watch, risk_blocked
    and overall direction label:
        STRONG_LONG / LONG / NEUTRAL / SHORT / STRONG_SHORT / MIXED / UNAVAILABLE
    """
    if not candidate_states:
        return {
            "index": "NEXUS_OVERALL_MARKET_DIRECTION",
            "value": "UNAVAILABLE",
            "quality": "UNAVAILABLE",
            "reason": "no_candidates",
            "counts": {},
            "researchOnly": True,
            "generatedAt": _utc_iso(),
        }

    long_count = 0
    short_count = 0
    neutral_count = 0
    confirmed_count = 0
    watch_count = 0
    risk_blocked_count = 0

    for state in candidate_states:
        d = str(state.get("direction") or "neutral").lower()
        if d == "long":
            long_count += 1
        elif d == "short":
            short_count += 1
        else:
            neutral_count += 1
        if state.get("confirmed"):
            confirmed_count += 1
        if state.get("watch"):
            watch_count += 1
        if state.get("risk_blocked"):
            risk_blocked_count += 1

    total = long_count + short_count + neutral_count
    long_ratio = long_count / total if total > 0 else 0.0
    short_ratio = short_count / total if total > 0 else 0.0

    if long_ratio >= 0.65:
        label = "STRONG_LONG"
    elif long_ratio >= 0.50:
        label = "LONG"
    elif short_ratio >= 0.65:
        label = "STRONG_SHORT"
    elif short_ratio >= 0.50:
        label = "SHORT"
    elif abs(long_ratio - short_ratio) < 0.15:
        label = "NEUTRAL"
    else:
        label = "MIXED"

    return {
        "index": "NEXUS_OVERALL_MARKET_DIRECTION",
        "description": "NEXUS proprietary market direction composite from candidate pipeline.",
        "value": label,
        "quality": "COMPLETE",
        "counts": {
            "long": long_count,
            "short": short_count,
            "neutral": neutral_count,
            "confirmed": confirmed_count,
            "watch": watch_count,
            "risk_blocked": risk_blocked_count,
            "total": total,
        },
        "ratios": {
            "longRatio": long_ratio,
            "shortRatio": short_ratio,
        },
        "researchOnly": True,
        "generatedAt": _utc_iso(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

def build_market_intelligence_summary(
    msi_components: Optional[dict[str, Any]] = None,
    universe_states: Optional[list[dict[str, Any]]] = None,
    candidate_states: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build a combined market intelligence summary."""
    msi = build_market_sentiment_index(msi_components or {})
    abi = build_altcoin_breadth_index(universe_states or [])
    direction = build_overall_market_direction(candidate_states or [])
    return {
        "nexusMarketSentimentIndex": msi,
        "nexusAltcoinBreadthIndex": abi,
        "nexusOverallMarketDirection": direction,
        "researchOnly": True,
        "generatedAt": _utc_iso(),
    }
