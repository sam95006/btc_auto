"""Public-safe projection fixtures for PUB18-A.

Shapes mirror private tip contracts (12f8cd8…) but NEVER import private modules.
Counts are sealed projections / control fixtures — labeled honestly.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_pub18_live_funnel.constants import FUNNEL_STAGE_IDS, PRIVATE_CONTRACT_TIP

FIXTURE_AS_OF = "2026-08-06T03:02:00Z"
LIVE_BOUNDED_AS_OF = "2026-08-06T03:06:00Z"

# Sealed public projection of private V18-C control fixture funnel
# (evidence_class=CONTROL_FIXTURE_FROM_PUBLIC_CATALOG_SHAPE).
_FIXTURE_FUNNEL_COUNTS = {
    "scanned": 22,
    "data_available": 17,
    "liquidity": 14,
    "data_trust": 13,
    "candidate": 6,
    "ai_review": 4,
    "cost_blocked": 1,
    "risk_blocked": 3,
    "shadow_decisions": 1,
}

# Sealed public projection of private V18-C live catalog smoke
# (LIVE_READ_ONLY_PUBLIC_CATALOG; missing fields → fail-closed zeros are REAL).
_LIVE_FUNNEL_COUNTS = {
    "scanned": 35,
    "data_available": 0,
    "liquidity": 0,
    "data_trust": 0,
    "candidate": 0,
    "ai_review": 0,
    "cost_blocked": 0,
    "risk_blocked": 40,
    "shadow_decisions": 0,
}


def _stages(counts: dict[str, int], *, available: bool) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for stage_id in FUNNEL_STAGE_IDS:
        if available:
            out[stage_id] = {"count": int(counts[stage_id]), "available": True}
        else:
            out[stage_id] = {"count": None, "available": False}
    return out


def catalog() -> list[dict[str, Any]]:
    """Deterministic first-screen + funnel cases with honest data-class labels."""
    return [
        {
            "case_id": "pub18_fixture_wait",
            "data_class": "FIXTURE",
            "chrome_label": "FIXTURE",
            "as_of": FIXTURE_AS_OF,
            "private_contract_tip": PRIVATE_CONTRACT_TIP,
            "projection_note": "Sealed control fixture funnel shape from private tip contracts",
            "funnel": _stages(_FIXTURE_FUNNEL_COUNTS, available=True),
            "global_market_state": {
                "summary": "Mixed risk appetite · crypto breadth soft (fixture)",
                "regime_label": "MIXED",
                "availability": "FIXTURE",
            },
            "crypto_derivatives_risk": {
                "summary": "Funding elevated · OI divergence watch (fixture)",
                "risk_band": "ELEVATED",
                "availability": "FIXTURE",
                "metrics": {
                    "funding": {"available": False, "provider_required": True, "value": None},
                    "open_interest": {"available": False, "provider_required": True, "value": None},
                },
            },
            "top_3": [
                {
                    "rank": 1,
                    "market": "BTCUSDT",
                    "contract": "BTCUSDT.PERP",
                    "side_hint": "WAIT",
                    "note": "Shadow observatory — not an order",
                },
                {
                    "rank": 2,
                    "market": "ETHUSDT",
                    "contract": "ETHUSDT.PERP",
                    "side_hint": "WAIT",
                    "note": "Derivatives risk elevated vs spot",
                },
                {
                    "rank": 3,
                    "market": "SOLUSDT",
                    "contract": "SOLUSDT.PERP",
                    "side_hint": "ABSTAIN",
                    "note": "Insufficient confirmation",
                },
            ],
            "ai_posture": "WAIT",
            "supporting_evidence": [
                {"summary": "Breadth not confirming breakout", "polarity": "SUPPORTING"},
                {"summary": "Volatility expansion risk flagged", "polarity": "SUPPORTING"},
            ],
            "counter_evidence": [
                {"summary": "Short-term momentum still positive", "polarity": "CONTRADICTING"},
            ],
            "invalidation": {
                "summary": "Invalidate WAIT if breadth confirms with fresh derivatives feed",
                "status": "INTACT",
            },
            "data_freshness": "FIXTURE",
            "actually_traded": False,
            "trade_buttons": False,
        },
        {
            "case_id": "pub18_live_read_only_bounded",
            "data_class": "LIVE_READ_ONLY",
            "chrome_label": "LIVE_READ_ONLY",
            "as_of": LIVE_BOUNDED_AS_OF,
            "private_contract_tip": PRIVATE_CONTRACT_TIP,
            "projection_note": (
                "Bounded LIVE_READ_ONLY public catalog projection; "
                "zero counts are fail-closed real zeros when fields missing — not fabricated Live zeros"
            ),
            "funnel": _stages(_LIVE_FUNNEL_COUNTS, available=True),
            "global_market_state": {
                "summary": "Official public catalog read-only · eligibility fail-closed",
                "regime_label": "OBSERVE",
                "availability": "LIVE_READ_ONLY",
            },
            "crypto_derivatives_risk": {
                "summary": "Derivatives metrics incomplete on bounded sample — not fabricated",
                "risk_band": "UNAVAILABLE",
                "availability": "LIVE_READ_ONLY",
                "metrics": {
                    "funding": {"available": False, "provider_required": False, "value": None},
                    "open_interest": {"available": False, "provider_required": False, "value": None},
                },
            },
            "top_3": [
                {
                    "rank": 1,
                    "market": "BTCUSDT",
                    "contract": "BTCUSDT.PERP",
                    "side_hint": "ABSTAIN",
                    "note": "Live catalog visible · candidate fail-closed",
                },
                {
                    "rank": 2,
                    "market": "ETHUSDT",
                    "contract": "ETHUSDT.PERP",
                    "side_hint": "ABSTAIN",
                    "note": "Data Trust incomplete — observe only",
                },
                {
                    "rank": 3,
                    "market": "BNBUSDT",
                    "contract": "BNBUSDT.PERP",
                    "side_hint": "WAIT",
                    "note": "Await data completeness",
                },
            ],
            "ai_posture": "ABSTAIN",
            "supporting_evidence": [
                {"summary": "Official Bybit/Binance public catalog reachable", "polarity": "SUPPORTING"},
            ],
            "counter_evidence": [
                {
                    "summary": "Feature fields missing → eligible=0 fail-closed",
                    "polarity": "CONTRADICTING",
                },
            ],
            "invalidation": {
                "summary": "Invalidate ABSTAIN only when Data Trust + liquidity gates pass",
                "status": "INTACT",
            },
            "data_freshness": "LIVE_READ_ONLY",
            "actually_traded": False,
            "trade_buttons": False,
        },
        {
            "case_id": "pub18_stale",
            "data_class": "STALE",
            "chrome_label": "STALE",
            "as_of": "2026-08-05T12:00:00Z",
            "private_contract_tip": PRIVATE_CONTRACT_TIP,
            "projection_note": "Stale projection — counts withheld, not zero-filled as Live",
            "funnel": _stages(_FIXTURE_FUNNEL_COUNTS, available=False),
            "global_market_state": {
                "summary": "STALE",
                "regime_label": "STALE",
                "availability": "STALE",
            },
            "crypto_derivatives_risk": {
                "summary": "STALE",
                "risk_band": "STALE",
                "availability": "STALE",
                "metrics": {
                    "funding": {"available": False, "provider_required": False, "value": None},
                    "open_interest": {"available": False, "provider_required": False, "value": None},
                },
            },
            "top_3": [],
            "ai_posture": "ABSTAIN",
            "supporting_evidence": [],
            "counter_evidence": [],
            "invalidation": {"summary": "STALE", "status": "STALE"},
            "data_freshness": "STALE",
            "actually_traded": False,
            "trade_buttons": False,
        },
        {
            "case_id": "pub18_unavailable",
            "data_class": "UNAVAILABLE",
            "chrome_label": "UNAVAILABLE",
            "as_of": None,
            "private_contract_tip": PRIVATE_CONTRACT_TIP,
            "projection_note": "Unavailable — never rendered as Live zeros",
            "funnel": _stages(_FIXTURE_FUNNEL_COUNTS, available=False),
            "global_market_state": {
                "summary": "UNAVAILABLE",
                "regime_label": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
            },
            "crypto_derivatives_risk": {
                "summary": "UNAVAILABLE",
                "risk_band": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
                "metrics": {
                    "funding": {"available": False, "provider_required": False, "value": None},
                    "open_interest": {"available": False, "provider_required": False, "value": None},
                },
            },
            "top_3": [],
            "ai_posture": "ABSTAIN",
            "supporting_evidence": [],
            "counter_evidence": [],
            "invalidation": {"summary": "UNAVAILABLE", "status": "UNAVAILABLE"},
            "data_freshness": "UNAVAILABLE",
            "actually_traded": False,
            "trade_buttons": False,
        },
        {
            "case_id": "pub18_fixture_long_observe",
            "data_class": "FIXTURE",
            "chrome_label": "FIXTURE",
            "as_of": FIXTURE_AS_OF,
            "private_contract_tip": PRIVATE_CONTRACT_TIP,
            "projection_note": "Fixture LONG observe — analysis only, no trade button",
            "funnel": _stages(_FIXTURE_FUNNEL_COUNTS, available=True),
            "global_market_state": {
                "summary": "Constructive crypto bias · equity risk-on soft (fixture)",
                "regime_label": "RISK_ON_SOFT",
                "availability": "FIXTURE",
            },
            "crypto_derivatives_risk": {
                "summary": "Crowding moderate · basis stable (fixture)",
                "risk_band": "MODERATE",
                "availability": "FIXTURE",
                "metrics": {
                    "funding": {"available": False, "provider_required": True, "value": None},
                    "open_interest": {"available": False, "provider_required": True, "value": None},
                },
            },
            "top_3": [
                {
                    "rank": 1,
                    "market": "BTCUSDT",
                    "contract": "BTCUSDT.PERP",
                    "side_hint": "LONG",
                    "note": "Public suggestion only — Shadow Decision, not a fill",
                },
                {
                    "rank": 2,
                    "market": "ETHUSDT",
                    "contract": "ETHUSDT.PERP",
                    "side_hint": "WAIT",
                    "note": "Await confirmation",
                },
                {
                    "rank": 3,
                    "market": "BNBUSDT",
                    "contract": "BNBUSDT.PERP",
                    "side_hint": "WAIT",
                    "note": "Secondary watch",
                },
            ],
            "ai_posture": "LONG",
            "supporting_evidence": [
                {
                    "summary": "Higher-high structure intact on public timeframe",
                    "polarity": "SUPPORTING",
                },
            ],
            "counter_evidence": [
                {
                    "summary": "Derivatives provider still required for funding confirmation",
                    "polarity": "CONTRADICTING",
                },
            ],
            "invalidation": {
                "summary": "Invalidate LONG bias if structure breaks and risk band rises",
                "status": "INTACT",
            },
            "data_freshness": "FIXTURE",
            "actually_traded": False,
            "trade_buttons": False,
        },
    ]
