import json
import math
import random
import time
from datetime import datetime
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from backend.config.capital_config import SUPPORTED_SYMBOLS


class MarketPriceFeedService:
    MARKET_SYMBOLS = {
        "twii": "^TWII",
        "spx": "^GSPC",
        "dji": "^DJI",
        "nasdaq": "^IXIC",
        "gold": "GC=F",
    }

    STOOQ_SYMBOLS = {
        "spx": "^spx",
        "dji": "^dji",
        "nasdaq": "^ndq",
        "gold": "gc.f",
    }

    YAHOO_HOSTS = (
        "https://query2.finance.yahoo.com/v8/finance/chart/",
        "https://query1.finance.yahoo.com/v8/finance/chart/",
    )

    MARKET_LABELS = {
        "twii": "台股加權",
        "spx": "標普 500",
        "dji": "道瓊工業",
        "nasdaq": "那斯達克",
        "gold": "黃金",
    }

    def __init__(self):
        self._last_overview_at = 0.0
        self._mock_anchor = {
            "BTC": 64000.0,
            "ETH": 3200.0,
            "SOL": 145.0,
            "BNB": 620.0,
            "PEPE": 0.000008,
        }
        self.last_prices = {}
        self._index_cache = {}
        self.last_market_overview = self._market_overview_fallback()

    def _mock_price(self, fleet):
        base = self._mock_anchor[fleet]
        wave = math.sin(time.time() / (12 + len(fleet))) * 0.004
        noise = random.uniform(-0.0025, 0.0025)
        return max(base * (1 + wave + noise), 0.00000001)

    def fetch_public_prices(self):
        encoded_symbols = json.dumps(list(SUPPORTED_SYMBOLS.values()), separators=(",", ":"))
        query = f"symbols={quote(encoded_symbols)}"
        url = f"https://api.binance.com/api/v3/ticker/price?{query}"
        try:
            raw_response = urlopen(url, timeout=5).read().decode("utf-8")
            raw = {item["symbol"]: float(item["price"]) for item in json.loads(raw_response)}
            return {
                fleet: {
                    "symbol": f"{fleet}/USDT",
                    "price": raw[pair],
                    "time": datetime.now().isoformat(timespec="milliseconds"),
                    "source": "binance_public",
                }
                for fleet, pair in SUPPORTED_SYMBOLS.items()
                if pair in raw
            }
        except Exception:
            return {}

    def get_prices(self):
        prices = self.fetch_public_prices()
        for fleet in SUPPORTED_SYMBOLS:
            if fleet not in prices:
                prices[fleet] = {
                    "symbol": f"{fleet}/USDT",
                    "price": self._mock_price(fleet),
                    "time": datetime.now().isoformat(timespec="milliseconds"),
                    "source": "mock_fallback",
                }
        self.last_prices = prices
        return prices

    def _session_status(self, key, taipei_now, eastern_now):
        weekday_tw = taipei_now.weekday()
        weekday_us = eastern_now.weekday()

        if key == "twii":
            is_open = weekday_tw < 5 and ((taipei_now.hour, taipei_now.minute) >= (9, 0)) and ((taipei_now.hour, taipei_now.minute) < (13, 30))
            return "開盤" if is_open else "休市"

        if key in {"spx", "dji", "nasdaq"}:
            is_open = weekday_us < 5 and ((eastern_now.hour, eastern_now.minute) >= (9, 30)) and ((eastern_now.hour, eastern_now.minute) < (16, 0))
            return "開盤" if is_open else "休市"

        if key == "gold":
            if weekday_us == 5:
                return "休市"
            if weekday_us == 6 and (eastern_now.hour, eastern_now.minute) < (18, 0):
                return "休市"
            if weekday_us == 4 and (eastern_now.hour, eastern_now.minute) >= (17, 0):
                return "休市"
            if (eastern_now.hour, eastern_now.minute) >= (17, 0) and (eastern_now.hour, eastern_now.minute) < (18, 0):
                return "休市"
            return "開盤"

        return "--"

    def _direction_from_change(self, change):
        if change is None or abs(change) < 1e-9:
            return "平"
        return "漲" if change > 0 else "跌"

    def _market_overview_fallback(self):
        taipei_now = datetime.now(ZoneInfo("Asia/Taipei"))
        eastern_now = datetime.now(ZoneInfo("America/New_York"))
        return {
            "updated_at": taipei_now.isoformat(timespec="seconds"),
            "times": {
                "taipei": taipei_now.strftime("%Y-%m-%d %H:%M:%S"),
                "eastern": eastern_now.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "indices": {
                key: {
                    "label": self.MARKET_LABELS[key],
                    "price": None,
                    "change": None,
                    "change_pct": None,
                    "direction": "平",
                    "session_status": self._session_status(key, taipei_now, eastern_now),
                }
                for key in self.MARKET_SYMBOLS
            },
            "source": "fallback",
        }

    def _fetch_yahoo_chart(self, symbol):
        last_error = None
        for host in self.YAHOO_HOSTS:
            url = f"{host}{quote(symbol, safe='=')}"
            request = Request(url, headers={"User-Agent": "Mozilla/5.0 (NEXUS Market Feed)"})
            try:
                with urlopen(request, timeout=8) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                last_error = exc
                continue
            meta = ((payload.get("chart") or {}).get("result") or [{}])[0].get("meta") or {}
            price = meta.get("regularMarketPrice")
            previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
            if price is None:
                last_error = ValueError(f"missing regularMarketPrice for {symbol}")
                continue

            change = None
            change_pct = None
            if previous_close not in (None, 0):
                change = float(price) - float(previous_close)
                change_pct = (change / float(previous_close)) * 100.0

            return {
                "price": float(price),
                "change": None if change is None else round(change, 4),
                "change_pct": None if change_pct is None else round(change_pct, 3),
                "market_time": meta.get("regularMarketTime"),
                "quote_source": "yahoo_chart",
            }
        raise last_error or ValueError(f"yahoo fetch failed for {symbol}")

    def _fetch_stooq_quote(self, symbol):
        url = f"https://stooq.pl/q/l/?s={quote(symbol, safe='')}&f=sd2t2ohlcv&h&e=csv"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 (NEXUS Market Feed)"})
        with urlopen(request, timeout=8) as response:
            lines = [line.strip() for line in response.read().decode("utf-8").splitlines() if line.strip()]
        if len(lines) < 2:
            raise ValueError(f"stooq empty response for {symbol}")
        parts = lines[-1].split(",")
        if len(parts) < 7:
            raise ValueError(f"stooq malformed row for {symbol}")
        if parts[1] in {"B/D", "N/D", ""} or parts[6] in {"B/D", "N/D", ""}:
            raise ValueError(f"stooq missing quote for {symbol}")

        close = float(parts[6])
        open_price = float(parts[3])
        change = close - open_price
        change_pct = (change / open_price) * 100.0 if open_price else None
        return {
            "price": close,
            "change": round(change, 4),
            "change_pct": None if change_pct is None else round(change_pct, 3),
            "market_time": parts[1] if len(parts) > 1 else None,
            "quote_source": "stooq",
        }

    def _fetch_index_quote(self, key, yahoo_symbol):
        errors = []
        for fetcher, symbol in (
            (self._fetch_yahoo_chart, yahoo_symbol),
            (self._fetch_stooq_quote, self.STOOQ_SYMBOLS.get(key)),
        ):
            if not symbol:
                continue
            try:
                return fetcher(symbol)
            except Exception as exc:
                errors.append(str(exc))
                continue
        cached = self._index_cache.get(key)
        if cached and cached.get("price") is not None:
            cached = dict(cached)
            cached["quote_source"] = f"{cached.get('quote_source', 'cache')}_stale"
            return cached
        if errors:
            raise ValueError("; ".join(errors[-2:]))
        raise ValueError(f"no quote providers for {key}")

    def seed_index_cache(self, indices):
        if not isinstance(indices, dict):
            return
        for key, payload in indices.items():
            if isinstance(payload, dict) and payload.get("price") is not None:
                self._index_cache[key] = dict(payload)

    def fetch_market_overview(self):
        overview = self._market_overview_fallback()
        taipei_now = datetime.now(ZoneInfo("Asia/Taipei"))
        eastern_now = datetime.now(ZoneInfo("America/New_York"))
        sources = set()
        for key, symbol in self.MARKET_SYMBOLS.items():
            try:
                data = self._fetch_index_quote(key, symbol)
                change = data.get("change")
                payload = {
                    **data,
                    "label": self.MARKET_LABELS[key],
                    "direction": self._direction_from_change(change),
                    "session_status": self._session_status(key, taipei_now, eastern_now),
                }
                overview["indices"][key].update(payload)
                self._index_cache[key] = dict(payload)
                sources.add(data.get("quote_source", "unknown"))
            except Exception:
                cached = self._index_cache.get(key)
                if cached:
                    overview["indices"][key].update(
                        {
                            **cached,
                            "label": self.MARKET_LABELS[key],
                            "session_status": self._session_status(key, taipei_now, eastern_now),
                        }
                    )
                    sources.add("cache_stale")
        overview["source"] = "+".join(sorted(sources)) if sources else "fallback"
        self.last_market_overview = overview
        return overview

    def get_market_overview(self, max_age_seconds=0, force=False):
        now = time.time()
        if (
            not force
            and max_age_seconds > 0
            and self.last_market_overview
            and self._last_overview_at
            and (now - self._last_overview_at) < max_age_seconds
        ):
            return self.last_market_overview
        overview = self.fetch_market_overview()
        self._last_overview_at = time.time()
        return overview
