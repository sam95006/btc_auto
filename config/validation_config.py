import os

from config.growth_mode_config import BOLD_TESTNET_ENABLED
from config.revenue_target_config import REVENUE_GROWTH_MODE


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return int(default)


BACKTEST_MIN_SAMPLE_SIZE = 6
BACKTEST_MIN_WIN_RATE = 0.35
BACKTEST_MAX_ALLOWED_RECENT_LOSSES = 4
BACKTEST_MAX_NEGATIVE_AVG_PNL = -2.5

SIMULATION_MAX_SPREAD_BPS = 18.0
SIMULATION_MIN_TOP5_NOTIONAL = 15000.0
SIMULATION_BLOCKED_REGIMES = {
    "extreme_volatility",
    "crash",
    "news_shock",
    "alert_red",
}

PAPER_MAX_RECENT_EXECUTION_ERRORS = _env_int("NEXUS_PAPER_MAX_EXECUTION_ERRORS", 3)
_default_paper_blocks = 24 if REVENUE_GROWTH_MODE else (10 if BOLD_TESTNET_ENABLED else 4)
PAPER_MAX_RECENT_VALIDATION_BLOCKS = _env_int("NEXUS_PAPER_MAX_VALIDATION_BLOCKS", _default_paper_blocks)
PAPER_VALIDATION_WINDOW_SECONDS = _env_int("NEXUS_PAPER_VALIDATION_WINDOW_SEC", 900)
PAPER_BOOTSTRAP_SKIP_BLOCKS = REVENUE_GROWTH_MODE

VALIDATION_MIN_APPROVAL_SCORE = (
    float(os.getenv("NEXUS_VALIDATION_MIN_APPROVAL_SCORE", "0.44" if REVENUE_GROWTH_MODE else "0.52") or 0.44)
    if REVENUE_GROWTH_MODE
    else float(os.getenv("NEXUS_VALIDATION_MIN_APPROVAL_SCORE", "0.52") or 0.52)
)
