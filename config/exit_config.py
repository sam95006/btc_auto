import os

CORE_FLEETS = ("BTC", "ETH", "SOL", "PEPE")

# 1R = margin × RISK_PCT (USD risk budget per trade)
RISK_PCT = float(os.getenv("NEXUS_RISK_PCT", "0.10"))

STOP_R = float(os.getenv("NEXUS_STOP_R", "1.0"))
BREAK_EVEN_AFTER_TP1 = os.getenv("NEXUS_BREAK_EVEN_AFTER_TP1", "1").strip().lower() in {"1", "true", "yes", "on"}

TP1_R = float(os.getenv("NEXUS_TP1_R", "1.0"))
TP2_R = float(os.getenv("NEXUS_TP2_R", "2.0"))
TP3_R = float(os.getenv("NEXUS_TP3_R", "3.0"))
TP1_FRACTION = float(os.getenv("NEXUS_TP1_FRACTION", "0.30"))
TP2_FRACTION = float(os.getenv("NEXUS_TP2_FRACTION", "0.30"))

# Partial take-profit ladder (R multiples of margin × RISK_PCT, monitored every tick)
TP_LADDER = (
    {"r": TP1_R, "fraction": TP1_FRACTION, "tag": "TP1", "move_stop_to_be": True},
    {"r": TP2_R, "fraction": TP2_FRACTION, "tag": "TP2", "move_stop_to_be": False},
    {"r": TP3_R, "fraction": 1.0, "tag": "TP3", "move_stop_to_be": False},
)

# Opposite signal full exit threshold
SIGNAL_REVERSE_MIN_CONFIDENCE = float(os.getenv("NEXUS_SIGNAL_REVERSE_MIN_CONFIDENCE", "0.55"))
