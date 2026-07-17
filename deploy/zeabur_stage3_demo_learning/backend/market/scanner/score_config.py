"""Centralized candidate score / stage / risk knobs (research-only)."""
from __future__ import annotations

CANDIDATE_SCORE_CONFIG = {
    "opportunity_price_weight": 0.35,
    "opportunity_oi_weight": 0.30,
    "opportunity_turnover_weight": 0.20,
    "opportunity_liquidity_weight": 0.15,
    "confirmation_align_bonus": 30.0,
    "confirmation_persist_bonus": 20.0,
    "confirmation_spread_bonus": 15.0,
    "confirmation_diverge_penalty": 15.0,
}

CANDIDATE_STAGE_CONFIG = {
    "confirmed_opportunity_min": 55.0,
    "confirmed_confirmation_min": 70.0,
    "awaiting_opportunity_min": 40.0,
    "awaiting_confirmation_min": 50.0,
    "building_opportunity_min": 35.0,
    "min_confirm_persist_sec": 40.0,
}

CANDIDATE_RISK_CONFIG = {
    "funding_crowd_abs": 0.0005,
    "overextend_5m_pct": 2.5,
    "wide_spread_bps": 12.0,
    "stale_risk_bonus": 20.0,
    "overextend_risk_bonus": 30.0,
    "funding_risk_bonus": 25.0,
}
