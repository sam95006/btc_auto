"""Fixtures for PUB17-B Market Pulse first screen (DEMO / PROVIDER_REQUIRED only)."""
from __future__ import annotations

from typing import Any

FIXTURE_AS_OF = "2026-08-06T01:00:00Z"


def catalog() -> list[dict[str, Any]]:
    """Deterministic first-screen fixtures. Never labeled LIVE."""
    return [
        {
            "case_id": "pulse_demo_wait",
            "mode": "DEMO_DATA",
            "chrome_label": "DEMO_DATA",
            "global_market_state": {
                "summary": "Mixed risk appetite · crypto leading breadth soft",
                "regime_label": "MIXED",
                "availability": "DEMO_DATA",
                "provider_required": False,
            },
            "crypto_derivatives_risk": {
                "summary": "Funding elevated · OI divergence watch",
                "risk_band": "ELEVATED",
                "availability": "DEMO_DATA",
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
                    "note": "Structure observatory — not an order",
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
                {
                    "summary": "Breadth not confirming breakout",
                    "polarity": "SUPPORTING",
                    "freshness": "DEMO_DATA",
                },
                {
                    "summary": "Volatility expansion risk flagged",
                    "polarity": "SUPPORTING",
                    "freshness": "DEMO_DATA",
                },
            ],
            "counter_evidence": [
                {
                    "summary": "Short-term momentum still positive",
                    "polarity": "CONTRADICTING",
                    "freshness": "DEMO_DATA",
                }
            ],
            "invalidation": {
                "summary": "Invalidate WAIT if breadth confirms with fresh derivatives feed",
                "status": "INTACT",
                "availability": "DEMO_DATA",
            },
            "data_freshness": "DEMO_DATA",
            "analysis_vs_actual_trading": "ANALYSIS_ONLY",
            "actually_traded": False,
        },
        {
            "case_id": "pulse_provider_required",
            "mode": "PROVIDER_REQUIRED",
            "chrome_label": "PROVIDER_REQUIRED",
            "global_market_state": {
                "summary": "PROVIDER_REQUIRED",
                "regime_label": "PROVIDER_REQUIRED",
                "availability": "PROVIDER_REQUIRED",
                "provider_required": True,
            },
            "crypto_derivatives_risk": {
                "summary": "PROVIDER_REQUIRED",
                "risk_band": "PROVIDER_REQUIRED",
                "availability": "PROVIDER_REQUIRED",
                "metrics": {
                    "funding": {"available": False, "provider_required": True, "value": None},
                    "open_interest": {"available": False, "provider_required": True, "value": None},
                },
            },
            "top_3": [],
            "ai_posture": "ABSTAIN",
            "supporting_evidence": [],
            "counter_evidence": [],
            "invalidation": {
                "summary": "PROVIDER_REQUIRED",
                "status": "UNAVAILABLE",
                "availability": "PROVIDER_REQUIRED",
            },
            "data_freshness": "PROVIDER_REQUIRED",
            "analysis_vs_actual_trading": "PROVIDER_REQUIRED",
            "actually_traded": False,
        },
        {
            "case_id": "pulse_unavailable",
            "mode": "UNAVAILABLE",
            "chrome_label": "UNAVAILABLE",
            "global_market_state": {
                "summary": "UNAVAILABLE",
                "regime_label": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
                "provider_required": False,
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
            "invalidation": {
                "summary": "UNAVAILABLE",
                "status": "UNAVAILABLE",
                "availability": "UNAVAILABLE",
            },
            "data_freshness": "UNAVAILABLE",
            "analysis_vs_actual_trading": "UNAVAILABLE",
            "actually_traded": False,
        },
        {
            "case_id": "pulse_demo_long_observe",
            "mode": "DEMO_DATA",
            "chrome_label": "DEMO_DATA",
            "global_market_state": {
                "summary": "Constructive crypto bias · equity risk-on soft",
                "regime_label": "RISK_ON_SOFT",
                "availability": "DEMO_DATA",
                "provider_required": False,
            },
            "crypto_derivatives_risk": {
                "summary": "Crowding moderate · basis stable (fixture)",
                "risk_band": "MODERATE",
                "availability": "DEMO_DATA",
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
                    "note": "Public suggestion only — analysis, not a fill",
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
                    "freshness": "DEMO_DATA",
                }
            ],
            "counter_evidence": [
                {
                    "summary": "Derivatives provider still required for funding confirmation",
                    "polarity": "CONTRADICTING",
                    "freshness": "PROVIDER_REQUIRED",
                }
            ],
            "invalidation": {
                "summary": "Invalidate LONG bias if structure breaks and risk band rises",
                "status": "INTACT",
                "availability": "DEMO_DATA",
            },
            "data_freshness": "DEMO_DATA",
            "analysis_vs_actual_trading": "NOT_ACTUAL_TRADING",
            "actually_traded": False,
        },
    ]
