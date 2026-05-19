TOTAL_CAPITAL = 1700.0
HQ_RESERVE = 1000.0
RADAR_BUDGET = 100.0

FUTURES_RESERVE_RATIO = 0.5

FLEET_ACTIVE_CAPITAL = {
    "BTC": 150.0,
    "ETH": 150.0,
    "SOL": 150.0,
    "PEPE": 150.0,
}

FLEET_ALLOCATION_WEIGHTS = {
    "BTC": 0.30,
    "ETH": 0.25,
    "SOL": 0.20,
    "PEPE": 0.15,
}

RADAR_ALLOCATION_WEIGHT = 0.10

HQ_SPOT_SYMBOLS = ("BTC", "ETH", "SOL", "BNB")

MIN_FUTURES_MARGIN = 20.0
MIN_FUTURES_LEVERAGE = 3.0
MAX_FUTURES_LEVERAGE = 100.0

LOAN_UNIT = 200.0
LOAN_INTEREST_DAILY = 0.05
LOAN_MAX = 600.0

SUPPORTED_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "BNB": "BNBUSDT",
    "PEPE": "PEPEUSDT",
}

RISK_LIMITS = {
    "min_leverage": MIN_FUTURES_LEVERAGE,
    "max_leverage": MAX_FUTURES_LEVERAGE,
    "max_margin_pct": 0.42,
    "max_position_notional_pct": 8.0,
    "fleet_max_loss": -45.0,
    "system_daily_max_loss": -120.0,
}
