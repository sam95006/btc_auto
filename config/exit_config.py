import os

CORE_FLEETS = ("BTC", "ETH", "SOL", "PEPE")

# 1R = margin × RISK_PCT (USD risk budget per trade)
RISK_PCT = float(os.getenv("NEXUS_RISK_PCT", "0.10"))

STOP_R = float(os.getenv("NEXUS_STOP_R", "1.0"))
BREAK_EVEN_AFTER_TP1 = os.getenv("NEXUS_BREAK_EVEN_AFTER_TP1", "1").strip().lower() in {"1", "true", "yes", "on"}

# Partial take-profit ladder (fractions of initial quantity)
TP_LADDER = (
    {"r": 1.0, "fraction": 0.30, "tag": "TP1", "move_stop_to_be": True},
    {"r": 2.0, "fraction": 0.30, "tag": "TP2", "move_stop_to_be": False},
    {"r": 3.0, "fraction": 1.0, "tag": "TP3", "move_stop_to_be": False},
)

# Opposite signal full exit threshold
SIGNAL_REVERSE_MIN_CONFIDENCE = float(os.getenv("NEXUS_SIGNAL_REVERSE_MIN_CONFIDENCE", "0.55"))
