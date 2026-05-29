"""External market data providers (CoinGecko / CoinMarketCap / CryptoQuant / macro)."""

import os


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


EXTERNAL_MARKET_ENABLED = _env_bool("NEXUS_EXTERNAL_MARKET_ENABLED", True)

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()
COINGECKO_BASE_URL = os.getenv("COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3").strip().rstrip("/")
COINGECKO_TOP_N = int(os.getenv("NEXUS_COINGECKO_TOP_N", "50"))
COINGECKO_MIN_VOLUME_USD = float(os.getenv("NEXUS_COINGECKO_MIN_VOLUME_USD", "5000000"))
COINGECKO_REFRESH_SECONDS = int(os.getenv("NEXUS_COINGECKO_REFRESH_SECONDS", "1800"))

COINMARKETCAP_API_KEY = os.getenv("COINMARKETCAP_API_KEY", os.getenv("CMC_API_KEY", "")).strip()
COINMARKETCAP_BASE_URL = os.getenv(
    "COINMARKETCAP_BASE_URL", "https://pro-api.coinmarketcap.com/v1"
).strip().rstrip("/")
CMC_REFRESH_SECONDS = int(os.getenv("NEXUS_CMC_REFRESH_SECONDS", "900"))
CMC_BTC_DOMINANCE_ALT_REDUCE = float(os.getenv("NEXUS_CMC_BTC_DOMINANCE_ALT_REDUCE", "52.0"))
CMC_ALT_LEVERAGE_MULTIPLIER = float(os.getenv("NEXUS_CMC_ALT_LEVERAGE_MULTIPLIER", "0.65"))

CRYPTOQUANT_API_KEY = os.getenv(
    "CRYPTOQUANT_API_KEY", os.getenv("CRYPTOQUANT_ACCESS_TOKEN", "")
).strip()
CRYPTOQUANT_BASE_URL = os.getenv("CRYPTOQUANT_BASE_URL", "https://api.cryptoquant.com/v1").strip().rstrip("/")
CRYPTOQUANT_REFRESH_SECONDS = int(os.getenv("NEXUS_CRYPTOQUANT_REFRESH_SECONDS", "3600"))
CRYPTOQUANT_INFLOW_SPIKE_BTC = float(os.getenv("NEXUS_CRYPTOQUANT_INFLOW_SPIKE_BTC", "8000"))
CRYPTOQUANT_OUTFLOW_SPIKE_BTC = float(os.getenv("NEXUS_CRYPTOQUANT_OUTFLOW_SPIKE_BTC", "8000"))
CRYPTOQUANT_NETFLOW_BEARISH_BTC = float(os.getenv("NEXUS_CRYPTOQUANT_NETFLOW_BEARISH_BTC", "5000"))
CRYPTOQUANT_OI_STRESS_SCORE = float(os.getenv("NEXUS_CRYPTOQUANT_OI_STRESS_SCORE", "0.85"))

# Fear & Greed (Alternative.me — no API key)
FEAR_GREED_ENABLED = _env_bool("NEXUS_FEAR_GREED_ENABLED", True)
FEAR_GREED_BASE_URL = os.getenv("NEXUS_FEAR_GREED_BASE_URL", "https://api.alternative.me").strip().rstrip("/")
FEAR_GREED_REFRESH_SECONDS = int(os.getenv("NEXUS_FEAR_GREED_REFRESH_SECONDS", "3600"))
FEAR_GREED_EXTREME_FEAR = int(os.getenv("NEXUS_FEAR_GREED_EXTREME_FEAR", "25"))
FEAR_GREED_EXTREME_GREED = int(os.getenv("NEXUS_FEAR_GREED_EXTREME_GREED", "75"))

# Binance futures public metrics (long/short, taker flow, liquidations, spot-futures premium)
BINANCE_MACRO_ENABLED = _env_bool("NEXUS_BINANCE_MACRO_ENABLED", True)
BINANCE_MACRO_REFRESH_SECONDS = int(os.getenv("NEXUS_BINANCE_MACRO_REFRESH_SECONDS", "300"))
BINANCE_MACRO_SYMBOL = os.getenv("NEXUS_BINANCE_MACRO_SYMBOL", "BTCUSDT").strip().upper()
BINANCE_MACRO_LIQ_STRESS_COUNT = int(os.getenv("NEXUS_BINANCE_MACRO_LIQ_STRESS_COUNT", "12"))
BINANCE_MACRO_LONG_CROWDED = float(os.getenv("NEXUS_BINANCE_MACRO_LONG_CROWDED", "0.62"))
BINANCE_MACRO_SHORT_CROWDED = float(os.getenv("NEXUS_BINANCE_MACRO_SHORT_CROWDED", "0.38"))
BINANCE_MACRO_SPOT_PREMIUM_WARN_BPS = float(os.getenv("NEXUS_BINANCE_MACRO_SPOT_PREMIUM_WARN_BPS", "35"))

# Optional: block new longs in extreme greed (default off — advisory only)
BLOCK_EXTREME_GREED_LONGS = _env_bool("NEXUS_BLOCK_EXTREME_GREED_LONGS", False)
BLOCK_EXTREME_FEAR_SHORTS = _env_bool("NEXUS_BLOCK_EXTREME_FEAR_SHORTS", False)
