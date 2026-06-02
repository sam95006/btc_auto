import unittest

from backend.market.universe_filter_service import UniverseFilterService


class _FuturesClient:
    def __init__(self, tickers=None, tradable=None):
        self._tickers = list(tickers or [])
        self._tradable = {str(s).upper() for s in (tradable or [])}

    def is_configured(self):
        return True

    def fetch_24h_tickers(self):
        return list(self._tickers)

    def is_tradable_symbol(self, symbol):
        if not self._tradable:
            return True
        return str(symbol).upper() in self._tradable


class PureAiUniverseFilterTests(unittest.TestCase):
    def test_core_symbols_always_first(self):
        svc = UniverseFilterService()
        client = _FuturesClient(
            tickers=[
                {"symbol": "XRPUSDT", "quoteVolume": 9_000_000},
                {"symbol": "BNBUSDT", "quoteVolume": 8_000_000},
            ]
        )
        uni = svc.resolve_pure_ai_universe(futures_client=client, radar_scan={}, max_symbols=6, include_core_first=True)
        # Core includes BTC/ETH/SOL/PEPE variants (we only assert these are present early)
        self.assertIn("BTCUSDT", uni[:4])
        self.assertIn("ETHUSDT", uni[:4])
        # SOL may appear slightly later if PEPE has two tradable variants
        self.assertIn("SOLUSDT", uni)

    def test_radar_candidates_fill_after_core(self):
        svc = UniverseFilterService()
        client = _FuturesClient(
            tickers=[
                {"symbol": "XRPUSDT", "quoteVolume": 9_000_000},
                {"symbol": "BNBUSDT", "quoteVolume": 8_000_000},
            ]
        )
        radar_scan = {"candidates": [{"symbol": "AVAXUSDT"}, {"symbol": "LINKUSDT"}]}
        uni = svc.resolve_pure_ai_universe(
            futures_client=client, radar_scan=radar_scan, max_symbols=7, include_core_first=True
        )
        self.assertIn("AVAXUSDT", uni)
        self.assertIn("LINKUSDT", uni)

    def test_respects_tradable_filter(self):
        svc = UniverseFilterService()
        client = _FuturesClient(
            tickers=[{"symbol": "XRPUSDT", "quoteVolume": 9_000_000}],
            tradable=["BTCUSDT", "ETHUSDT", "SOLUSDT", "1000PEPEUSDT"],
        )
        radar_scan = {"candidates": [{"symbol": "XRPUSDT"}]}
        uni = svc.resolve_pure_ai_universe(futures_client=client, radar_scan=radar_scan, max_symbols=6, include_core_first=True)
        self.assertNotIn("XRPUSDT", uni)


if __name__ == "__main__":
    unittest.main()

