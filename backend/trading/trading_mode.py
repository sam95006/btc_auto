import os


ALLOWED_TRADING_MODES = {"paper", "binance_testnet"}


class TradingModeSafetyError(RuntimeError):
    pass


def get_trading_mode():
    mode = str(os.getenv("NEXUS_TRADING_MODE", "paper") or "paper").strip().lower()
    if mode == "live":
        raise TradingModeSafetyError("NEXUS_TRADING_MODE=live is forbidden")
    if mode not in ALLOWED_TRADING_MODES:
        return "paper"
    return mode


def require_testnet_credentials():
    spot_key = str(os.getenv("BINANCE_SPOT_TESTNET_API_KEY", "")).strip()
    spot_secret = str(os.getenv("BINANCE_SPOT_TESTNET_SECRET_KEY", "")).strip()
    futures_key = str(os.getenv("BINANCE_FUTURES_TESTNET_API_KEY", "")).strip()
    futures_secret = str(os.getenv("BINANCE_FUTURES_TESTNET_SECRET_KEY", "")).strip()
    missing = []
    if not spot_key or not spot_secret:
        missing.append("spot")
    if not futures_key or not futures_secret:
        missing.append("futures")
    return missing
