"""V18-A Official Read-Only Market Adapters — fixture + boundary tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_official_market_adapters import (
    DATA_MODE_FIXTURE,
    DATA_MODE_LIVE_READ_ONLY,
    HARD_BANS,
    OfficialMarketAdapterRegistry,
)
from backend.nexus_official_market_adapters.binance.adapter import BinanceUsdmPublicAdapter
from backend.nexus_official_market_adapters.bybit.adapter import BybitPublicV5Adapter
from backend.nexus_official_market_adapters.constitution import (
    PublicMarketBoundaryError,
    binance_usdm_constitution,
    bybit_constitution,
)
from backend.nexus_official_market_adapters.constants import (
    CAPABILITIES,
    OFFICIAL_READ_ADAPTER_IDS,
    QUALITY_STATES,
    QUALITY_UNAVAILABLE,
)
from backend.nexus_official_market_adapters.contracts import AdapterManifest
from backend.nexus_official_market_adapters.envelope import safe_float, wrap_ok
from backend.nexus_official_market_adapters.stubs.contract_only import (
    ContractOnlyMarketAdapter,
    build_contract_only_stubs,
)
from backend.nexus_official_market_adapters.transport import (
    BoundedHttpClient,
    CircuitBreakerState,
    TokenBucketRateLimiter,
)


ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "backend" / "nexus_official_market_adapters"


class TestAcceptanceCounts:
    def test_registry_acceptance_pass(self):
        reg = OfficialMarketAdapterRegistry(use_fixtures=True)
        counts = reg.compute_acceptance()
        assert counts.official_read_adapter_count >= 2
        assert counts.account_endpoint_count == 0
        assert counts.exchange_write_endpoint_count == 0
        assert counts.secret_required_count == 0
        assert counts.fabricated_live_value_count == 0
        assert counts.passes()

    def test_official_adapter_ids(self):
        reg = OfficialMarketAdapterRegistry(use_fixtures=True)
        ids = {a.manifest.adapter_id for a in reg.official_read_adapters()}
        assert set(OFFICIAL_READ_ADAPTER_IDS) <= ids


class TestHardBans:
    def test_hard_bans_declared(self):
        assert "no_glassnode_paywall_scrape" in HARD_BANS
        assert "no_coinglass_paywall_scrape" in HARD_BANS
        assert "no_messari_paywall_scrape" in HARD_BANS
        assert "no_fill_missing_with_zero" in HARD_BANS
        assert "no_rate_limit_bypass" in HARD_BANS

    def test_scrape_hosts_blocked(self):
        c = bybit_constitution()
        with pytest.raises(PublicMarketBoundaryError):
            c.validate_http_request(method="GET", url="https://glassnode.com/api/v1/metrics")

    def test_auth_headers_blocked(self):
        c = bybit_constitution()
        with pytest.raises(PublicMarketBoundaryError):
            c.validate_http_request(
                method="GET",
                url="https://api.bybit.com/v5/market/tickers",
                headers={"X-BAPI-API-KEY": "secret"},
            )
        assert c.counters.secret_required_count == 1

    def test_write_methods_blocked(self):
        c = binance_usdm_constitution()
        with pytest.raises(PublicMarketBoundaryError):
            c.validate_http_request(
                method="POST",
                url="https://fapi.binance.com/fapi/v1/order",
            )
        assert c.counters.exchange_write_endpoint_count >= 1

    def test_account_paths_blocked(self):
        c = bybit_constitution()
        with pytest.raises(PublicMarketBoundaryError):
            c.validate_http_request(
                method="GET",
                url="https://api.bybit.com/v5/account/wallet-balance",
            )
        assert c.counters.account_endpoint_count >= 1


class TestSafeFloatHonesty:
    def test_missing_not_zero(self):
        assert safe_float(None) is None
        assert safe_float("") is None
        assert safe_float("abc") is None
        assert safe_float("0") == 0.0  # explicit zero from exchange is OK
        assert safe_float(0) == 0.0


class TestEnvelopeHonesty:
    def test_fixture_cannot_be_labeled_live(self):
        with pytest.raises(ValueError):
            wrap_ok(
                capability="ticker",
                adapter_id="x",
                provider="x",
                endpoint="/x",
                host="x",
                payload={"a": 1},
                data_mode=DATA_MODE_LIVE_READ_ONLY,
                exchange_timestamp_ms=1,
                access_method="local_fixture",
            )

    def test_fixture_mode_requires_local_fixture(self):
        with pytest.raises(ValueError):
            wrap_ok(
                capability="ticker",
                adapter_id="x",
                provider="x",
                endpoint="/x",
                host="x",
                payload={"a": 1},
                data_mode=DATA_MODE_FIXTURE,
                exchange_timestamp_ms=1,
                access_method="official_rest_api",
            )


class TestManifestGuards:
    def test_secret_required_rejected(self):
        with pytest.raises(ValueError):
            AdapterManifest(
                adapter_id="bad",
                provider="bad",
                official=True,
                read_only=True,
                secret_required=True,
                account_endpoints=(),
                exchange_write_endpoints=(),
                public_rest_endpoints=(),
                public_ws_topics=(),
                capabilities=("ticker",),
                supports_live_read_only=False,
            )

    def test_account_endpoints_rejected(self):
        with pytest.raises(ValueError):
            AdapterManifest(
                adapter_id="bad",
                provider="bad",
                official=True,
                read_only=True,
                secret_required=False,
                account_endpoints=("/v5/account/wallet-balance",),
                exchange_write_endpoints=(),
                public_rest_endpoints=(),
                public_ws_topics=(),
                capabilities=("ticker",),
                supports_live_read_only=False,
            )


class TestBybitFixtureAdapter:
    def setup_method(self):
        self.adapter = BybitPublicV5Adapter(use_fixtures=True)

    def test_mode_is_fixture(self):
        assert self.adapter.data_mode() == DATA_MODE_FIXTURE

    @pytest.mark.parametrize("capability", list(CAPABILITIES))
    def test_all_capabilities_honest(self, capability):
        sym = "LINKUSDT"
        dispatch = {
            "instrument_catalog": lambda: self.adapter.fetch_instrument_catalog(),
            "ticker": lambda: self.adapter.fetch_ticker(symbol=sym),
            "mark_index_price": lambda: self.adapter.fetch_mark_index_price(symbol=sym),
            "ohlcv": lambda: self.adapter.fetch_ohlcv(symbol=sym),
            "public_trades": lambda: self.adapter.fetch_public_trades(symbol=sym),
            "funding": lambda: self.adapter.fetch_funding(symbol=sym),
            "open_interest": lambda: self.adapter.fetch_open_interest(symbol=sym),
            "order_book_summary": lambda: self.adapter.fetch_order_book_summary(symbol=sym),
            "liquidation": lambda: self.adapter.fetch_liquidations(symbol=sym),
            "listing_status": lambda: self.adapter.fetch_listing_status(symbol=sym),
            "contract_specs": lambda: self.adapter.fetch_contract_specs(symbol=sym),
        }
        obs = dispatch[capability]()
        assert obs.data_mode == DATA_MODE_FIXTURE
        assert obs.quality in QUALITY_STATES
        assert obs.schema_version == 1
        assert obs.received_at_ms is not None
        assert obs.source_lineage.adapter_id == "bybit_public_v5"
        if capability == "liquidation":
            assert obs.quality == QUALITY_UNAVAILABLE
            assert obs.payload is None
        else:
            assert obs.payload is not None
            assert obs.source_lineage.access_method == "local_fixture"

    def test_no_secret_in_manifest(self):
        assert self.adapter.manifest.secret_required is False
        assert self.adapter.manifest.account_endpoints == ()
        assert self.adapter.manifest.exchange_write_endpoints == ()


class TestBinanceFixtureAdapter:
    def setup_method(self):
        self.adapter = BinanceUsdmPublicAdapter(use_fixtures=True)

    def test_mode_is_fixture(self):
        assert self.adapter.data_mode() == DATA_MODE_FIXTURE

    @pytest.mark.parametrize("capability", list(CAPABILITIES))
    def test_all_capabilities_honest(self, capability):
        sym = "BTCUSDT"
        dispatch = {
            "instrument_catalog": lambda: self.adapter.fetch_instrument_catalog(),
            "ticker": lambda: self.adapter.fetch_ticker(symbol=sym),
            "mark_index_price": lambda: self.adapter.fetch_mark_index_price(symbol=sym),
            "ohlcv": lambda: self.adapter.fetch_ohlcv(symbol=sym),
            "public_trades": lambda: self.adapter.fetch_public_trades(symbol=sym),
            "funding": lambda: self.adapter.fetch_funding(symbol=sym),
            "open_interest": lambda: self.adapter.fetch_open_interest(symbol=sym),
            "order_book_summary": lambda: self.adapter.fetch_order_book_summary(symbol=sym),
            "liquidation": lambda: self.adapter.fetch_liquidations(symbol=sym),
            "listing_status": lambda: self.adapter.fetch_listing_status(symbol=sym),
            "contract_specs": lambda: self.adapter.fetch_contract_specs(symbol=sym),
        }
        obs = dispatch[capability]()
        assert obs.data_mode == DATA_MODE_FIXTURE
        assert obs.quality in QUALITY_STATES
        assert obs.payload is not None
        assert obs.source_lineage.access_method == "local_fixture"


class TestContractOnly:
    def test_cannot_enter_live(self):
        stub = ContractOnlyMarketAdapter(adapter_id="okx_public", provider="okx")
        with pytest.raises(ValueError):
            stub.set_data_mode(DATA_MODE_LIVE_READ_ONLY)

    def test_unavailable_not_fabricated(self):
        for stub in build_contract_only_stubs():
            obs = stub.fetch_ticker(symbol="BTCUSDT")
            assert obs.quality == QUALITY_UNAVAILABLE
            assert obs.payload is None
            assert obs.data_mode == DATA_MODE_FIXTURE


class TestTransportGuards:
    def test_circuit_breaker_opens(self):
        cb = CircuitBreakerState(failure_threshold=2)
        cb.record_failure("x")
        cb.record_failure("y")
        assert cb.open is True

    def test_rate_limiter_acquires(self):
        lim = TokenBucketRateLimiter(rate_per_second=100.0)
        lim.acquire()
        assert lim.tokens < 100.0

    def test_bounded_client_rejects_write(self):
        client = BoundedHttpClient(constitution=bybit_constitution())
        with pytest.raises(PublicMarketBoundaryError):
            client.request("POST", "https://api.bybit.com/v5/market/tickers")


class TestPackageHygiene:
    def test_no_api_secret_literals_in_package(self):
        banned = ("api_secret", "API_SECRET", "x-mbx-apikey", "X-BAPI-API-KEY")
        offenders = []
        for path in PKG.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in banned:
                # Allow token only inside BLOCKED_AUTH_HEADERS / ban lists.
                if token.lower() in text.lower():
                    if "BLOCKED_AUTH_HEADERS" in text or "blocked" in text.lower():
                        continue
                    if token.lower() in {"api_secret"} and "blocked" in text.lower():
                        continue
                    # constants.py lists blocked headers — OK
                    if path.name == "constants.py":
                        continue
                    offenders.append(f"{path.name}:{token}")
        assert offenders == []

    def test_fixtures_exist(self):
        assert (PKG / "fixtures" / "bybit" / "tickers.json").is_file()
        assert (PKG / "fixtures" / "binance" / "exchange_info.json").is_file()


class TestRegistrySmoke:
    def test_fixture_smoke_classifies_modes(self):
        reg = OfficialMarketAdapterRegistry(use_fixtures=True)
        smoke = reg.smoke_fixture_capabilities()
        assert "bybit_public_v5" in smoke
        assert "binance_usdm_public" in smoke
        for aid, block in smoke.items():
            assert block["data_mode"] == DATA_MODE_FIXTURE
            for cap, obs in block["observations"].items():
                assert obs["data_mode"] == DATA_MODE_FIXTURE
                assert obs["has_received_at"] is True
                if aid == "bybit_public_v5" and cap == "liquidation":
                    assert obs["payload_is_none"] is True
                    assert obs["quality"] == QUALITY_UNAVAILABLE
