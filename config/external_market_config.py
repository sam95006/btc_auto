"""External market data providers (CoinGecko / CoinMarketCap / CryptoQuant)."""

import os

EXTERNAL_MARKET_ENABLED = os.getenv("NEXUS_EXTERNAL_MARKET_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

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
CRYPTOQUANT_OI_STRESS_SCORE = float(os.getenv("NEXUS_CRYPTOQUANT_OI_STRESS_SCORE", "0.85"))
