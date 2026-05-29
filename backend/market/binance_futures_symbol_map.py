"""Map CoinGecko ids/symbols to Binance USD-M perpetual symbols."""

from __future__ import annotations

COINGECKO_ID_TO_BINANCE: dict[str, str] = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "binancecoin": "BNBUSDT",
    "ripple": "XRPUSDT",
    "solana": "SOLUSDT",
    "dogecoin": "DOGEUSDT",
    "cardano": "ADAUSDT",
    "tron": "TRXUSDT",
    "chainlink": "LINKUSDT",
    "avalanche-2": "AVAXUSDT",
    "polkadot": "DOTUSDT",
    "litecoin": "LTCUSDT",
    "shiba-inu": "SHIBUSDT",
    "uniswap": "UNIUSDT",
    "near": "NEARUSDT",
    "sui": "SUIUSDT",
    "pepe": "1000PEPEUSDT",
    "the-open-network": "TONUSDT",
    "hedera-hashgraph": "HBARUSDT",
    "stellar": "XLMUSDT",
    "monero": "XMRUSDT",
    "bitcoin-cash": "BCHUSDT",
    "crypto-com-chain": "CROUSDT",
    "mantle": "MNTUSDT",
    "okb": "OKBUSDT",
    "world-liberty-financial": "WLFIUSDT",
    "hyperliquid": "HYPEUSDT",
    "zcash": "ZECUSDT",
    "bittensor": "TAOUSDT",
    "pax-gold": "PAXGUSDT",
    "tether-gold": "XAUTUSDT",
}

STABLE_OR_NON_FUTURES = frozenset(
    {
        "USDT",
        "USDC",
        "DAI",
        "FDUSD",
        "USDS",
        "TUSD",
        "USDE",
        "PYUSD",
        "USYC",
        "USD1",
    }
)

STABLE_COINGECKO_IDS = frozenset({"tether", "usd-coin", "dai", "paypal-usd", "usds"})


def coingecko_row_to_binance_symbol(row: dict) -> str:
    coin_id = str((row or {}).get("id") or "").lower().strip()
    if coin_id in STABLE_COINGECKO_IDS:
        return ""
    if coin_id in COINGECKO_ID_TO_BINANCE:
        return COINGECKO_ID_TO_BINANCE[coin_id]
    token = str((row or {}).get("symbol") or "").lower().strip()
    if not token or token in STABLE_OR_NON_FUTURES:
        return ""
    return f"{token.upper()}USDT"
