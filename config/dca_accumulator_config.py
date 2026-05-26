import os

from config.revenue_target_config import REVENUE_GROWTH_MODE


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return int(default)


DCA_ACCUMULATOR_ENABLED = _env_bool("NEXUS_DCA_ACCUMULATOR", True)
DCA_INTERVAL_SEC = _env_int("NEXUS_DCA_INTERVAL_SEC", 3600)
DCA_MARGIN_USD = _env_float("NEXUS_DCA_MARGIN_USD", 18.0)
DCA_MIN_CONFIDENCE = _env_float("NEXUS_DCA_MIN_CONFIDENCE", 0.46)
DCA_SYMBOLS = tuple(
    item.strip().upper()
    for item in str(os.getenv("NEXUS_DCA_SYMBOLS", "BTCUSDT,ETHUSDT") or "BTCUSDT,ETHUSDT").split(",")
    if item.strip()
)
DCA_FLEET_MAP = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
    "BNBUSDT": "BNB",
}
