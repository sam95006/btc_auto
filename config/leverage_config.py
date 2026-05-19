MIN_FUTURES_LEVERAGE = 3
MAX_SYSTEM_LEVERAGE = 100

CONFIDENCE_LEVERAGE_TABLE = [
    {"min": 0.35, "max": 0.50, "leverage": 3},
    {"min": 0.50, "max": 0.65, "leverage": 5},
    {"min": 0.65, "max": 0.75, "leverage": 10},
    {"min": 0.75, "max": 0.85, "leverage": 20},
    {"min": 0.85, "max": 0.92, "leverage": 50},
    {"min": 0.92, "max": 1.01, "leverage": 100},
]

FLEET_LEVERAGE_CAPS = {
    "BTC": 100,
    "ETH": 75,
    "SOL": 50,
    "PEPE": 20,
}

RISK_EVENT_LEVERAGE_CAP = 3
CONSECUTIVE_LOSS_CAP = 3
PEPE_DEFAULT_MAX_LEVERAGE = 20
