"""Wave 2 Global Market Six-role Shadow Intelligence (no Live execution)."""
from __future__ import annotations

SCHEMA_VERSION = "wave2.global.six_role.v1"
MAX_OPEN_POSITIONS = 2
MAX_PENDING_ORDERS = 2
RISK_PER_POSITION_MIN = 0.25
RISK_PER_POSITION_MAX = 0.50
PORTFOLIO_OPEN_RISK_MAX = 0.75
CORRELATION_GROUP_RISK_MAX = 0.50
HIGH_RISK_SMALL_MARKET_MAX_POSITIONS = 1

# Benchmark / fixture only — NEVER formal universe.
BENCHMARK_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT")
ALLOWED_MODES = frozenset({"SHADOW", "REPLAY", "FIXTURE", "PAPER"})
FORBIDDEN_MODES = frozenset({"DEMO_WRITE", "MAINNET", "REAL_MONEY", "LIVE_EXECUTION"})
