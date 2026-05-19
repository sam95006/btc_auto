MAX_TOTAL_NOTIONAL_UTILIZATION = 1.35
WARNING_TOTAL_NOTIONAL_UTILIZATION = 1.0
MAX_SINGLE_FLEET_SHARE = 0.42
MAX_SAME_SIDE_SHARE = 0.68
MAX_CORRELATED_GROUP_SHARE = 0.62
HEDGE_TRIGGER_UTILIZATION = 0.95
HEDGE_TRIGGER_CONCENTRATION = 0.78

FLEET_BASE_CAPITAL_MULTIPLIER = {
    "BTC": 1.0,
    "ETH": 1.0,
    "SOL": 0.9,
    "PEPE": 0.65,
}

REGIME_CAPITAL_MULTIPLIER = {
    "normal": 1.0,
    "wide_spread": 0.82,
    "thin_liquidity": 0.7,
    "low_open_interest": 0.82,
    "low_open_interest_notional": 0.72,
    "funding_dislocation": 0.7,
    "basis_dislocation": 0.72,
    "high_slippage": 0.68,
    "liquidation_risk": 0.55,
}

FLEET_CORRELATION_GROUPS = {
    "BTC": "majors",
    "ETH": "majors",
    "SOL": "alts",
    "PEPE": "memes",
}

FLEET_THEME_TAGS = {
    "BTC": ("store_of_value", "majors"),
    "ETH": ("smart_contracts", "majors"),
    "SOL": ("smart_contracts", "alts"),
    "PEPE": ("memes", "alts"),
}
