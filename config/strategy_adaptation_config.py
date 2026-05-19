ADAPTIVE_MODE_NORMAL = "normal"
ADAPTIVE_MODE_CAUTIOUS = "cautious"
ADAPTIVE_MODE_RESTRICTED = "restricted"
ADAPTIVE_MODE_SUSPENDED = "suspended"

CAUTIOUS_PRESSURE_THRESHOLD = 0.35
RESTRICTED_PRESSURE_THRESHOLD = 0.6
SUSPENDED_PRESSURE_THRESHOLD = 0.82

CAUTIOUS_MIN_CONFIDENCE_FLOOR = 0.42
RESTRICTED_MIN_CONFIDENCE_FLOOR = 0.5
SUSPENDED_MIN_CONFIDENCE_FLOOR = 0.62

CAUTIOUS_AGGRESSION_CAP = 0.82
RESTRICTED_AGGRESSION_CAP = 0.66
SUSPENDED_AGGRESSION_CAP = 0.45

CAUTIOUS_POSITION_CAP = 0.85
RESTRICTED_POSITION_CAP = 0.62
SUSPENDED_POSITION_CAP = 0.4

CAUTIOUS_LEVERAGE_CAP = 20
RESTRICTED_LEVERAGE_CAP = 10
SUSPENDED_LEVERAGE_CAP = 3

PEPE_RESTRICTED_LEVERAGE_CAP = 8
PEPE_SUSPENDED_LEVERAGE_CAP = 3

PRESSURE_WEIGHTS = {
    "slippage_elevated": 0.22,
    "liquidity_unhealthy": 0.18,
    "oi_notional_weak": 0.16,
    "funding_elevated": 0.12,
    "basis_elevated": 0.12,
    "liquidation_elevated": 0.22,
    "liquidation_critical": 0.35,
    "news_conflict": 0.18,
    "whale_conflict": 0.18,
    "loss_rate_high": 0.15,
    "consecutive_losses_soft": 0.18,
    "consecutive_losses_hard": 0.35,
    "confidence_penalty_high": 0.14,
    "failure_focus_market_regime": 0.12,
    "failure_focus_low_liquidity": 0.12,
    "failure_focus_over_leverage": 0.15,
}
