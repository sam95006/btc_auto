from backend.market.external_market_intel_service import ExternalMarketIntelService


class _FakeCoinGecko:
    def configured(self):
        return True

    def fetch_top_markets(self):
        return {
            "ok": True,
            "symbols": ["XRPUSDT", "SOLUSDT"],
            "by_symbol": {
                "ETHUSDT": {"rank": 2, "volume_24h_usd": 9_000_000, "liquidity_ok": True},
                "SOLUSDT": {"rank": 6, "volume_24h_usd": 100_000, "liquidity_ok": False},
            },
        }


class _FakeCmc:
    def configured(self):
        return True

    def fetch_global_metrics(self):
        return {
            "ok": True,
            "btc_dominance": 54.0,
            "alt_leverage_reduce": True,
            "hot_sectors": [{"name": "AI", "market_cap_change_24h_pct": 3.2}],
        }


class _FakeCq:
    def configured(self):
        return True

    def fetch_risk_signals(self):
        return {
            "ok": True,
            "whale_dump_alert": True,
            "oi_stress": True,
            "external_exit_pressure": 0.85,
            "btc_exchange_inflow": 9000,
        }


def test_external_intel_merges_into_market_context():
    service = ExternalMarketIntelService(_FakeCoinGecko(), _FakeCmc(), _FakeCq())
    service.refresh()
    contexts = service.apply_to_contexts(
        {
            "ETH": {"symbol": "ETHUSDT", "market_regime": "normal"},
            "SOL": {"symbol": "SOLUSDT", "market_regime": "normal"},
        }
    )
    assert contexts["ETH"]["coingecko_liquidity_ok"] is True
    assert contexts["SOL"]["coingecko_liquidity_ok"] is False
    assert contexts["ETH"]["btc_dominance"] == 54.0
    assert contexts["ETH"]["external_oi_stress"] is True


def test_external_intel_radar_symbols():
    service = ExternalMarketIntelService(_FakeCoinGecko(), _FakeCmc(), _FakeCq())
    service.refresh()
    symbols = service.top_radar_symbols(limit=10)
    assert "XRPUSDT" in symbols
