import json
import math
import random
import time
from datetime import datetime
from urllib.parse import quote, urlencode
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

    MARKET_LABELS = {
        "twii": "台股加權",
        "spx": "標普 500",
        "dji": "道瓊工業",
        "nasdaq": "那斯達克",
        "gold": "黃金",
    }

    def __init__(self):
        self._mock_anchor = {
            "BTC": 64000.0,
            "ETH": 3200.0,
            "SOL": 145.0,
            "BNB": 620.0,
            "PEPE": 0.000008,
        }
        self.last_prices = {}
        self.last_market_overview = self._market_overview_fallback()

    def _mock_price(self, fleet):
        base = self._mock_anchor[fleet]
        wave = math.sin(time.time() / (12 + len(fleet))) * 0.004
        noise = random.uniform(-0.0025, 0.0025)
        return max(base * (1 + wave + noise), 0.00000001)

    def fetch_public_prices(self):
        encoded_symbols = json.dumps(list(SUPPORTED_SYMBOLS.values()), separators=(",", ":"))
        query = urlencode({"symbols": encoded_symbols})
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
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='=')}"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
        meta = ((payload.get("chart") or {}).get("result") or [{}])[0].get("meta") or {}
        price = meta.get("regularMarketPrice")
        previous_close = meta.get("previousClose")
        if price is None:
            raise ValueError(f"missing regularMarketPrice for {symbol}")

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
        }

    def fetch_market_overview(self):
        overview = self._market_overview_fallback()
        taipei_now = datetime.now(ZoneInfo("Asia/Taipei"))
        eastern_now = datetime.now(ZoneInfo("America/New_York"))
        try:
            for key, symbol in self.MARKET_SYMBOLS.items():
                data = self._fetch_yahoo_chart(symbol)
                change = data.get("change")
                if change is None or abs(change) < 1e-9:
                    direction = "平"
                else:
                    direction = "漲" if change > 0 else "跌"
                overview["indices"][key].update(
                    {
                        **data,
                        "label": self.MARKET_LABELS[key],
                        "direction": direction,
                        "session_status": self._session_status(key, taipei_now, eastern_now),
                    }
                )
            overview["source"] = "yahoo_chart"
        except Exception:
            pass
        self.last_market_overview = overview
        return overview

    def get_market_overview(self):
        return self.fetch_market_overview()
