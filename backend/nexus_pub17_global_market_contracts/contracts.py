"""Source contract catalog for PUB17-A Global Market domains.

Honest legal sources only. Domains without a wired legal provider are
PROVIDER_REQUIRED with value=None — never fabricated Live numbers.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_pub17_global_market_contracts.constants import REQUIRED_DOMAINS


def _license(
    *,
    license_type: str,
    commercial_use_allowed: bool,
    redistribution_allowed: bool,
    public_display_allowed: bool,
    training_allowed: bool,
    summary: str,
) -> dict[str, Any]:
    return {
        "license_type": license_type,
        "commercial_use_allowed": commercial_use_allowed,
        "redistribution_allowed": redistribution_allowed,
        "public_display_allowed": public_display_allowed,
        "training_allowed": training_allowed,
        "summary": summary,
        "visibility": "PUBLIC_VISIBLE",
    }


def _provenance(
    *,
    origin: str,
    access_path: str,
    authority: str,
    verification: str,
) -> dict[str, Any]:
    return {
        "origin": origin,
        "access_path": access_path,
        "authority": authority,
        "verification": verification,
        "chain": [origin, access_path],
    }


def _contract(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "domain": "unknown",
        "source_id": "unknown",
        "provider": "unknown",
        "dataset": "unknown",
        "market_type": "unknown",
        "access_method": "official_rest_api",
        "status": "PROVIDER_REQUIRED",
        "license_type": "unknown",
        "license_visibility": _license(
            license_type="unknown",
            commercial_use_allowed=False,
            redistribution_allowed=False,
            public_display_allowed=False,
            training_allowed=False,
            summary="No legal source wired.",
        ),
        "commercial_use_allowed": False,
        "redistribution_allowed": False,
        "public_display_allowed": False,
        "provenance": _provenance(
            origin="none",
            access_path="none",
            authority="none",
            verification="unverified",
        ),
        "endpoint": None,
        "resolution": "unknown",
        "read_only": True,
        "exchange_write": False,
        "supports_live_bind": False,
        "notes": "",
    }
    base.update(overrides)
    # Keep top-level license flags aligned with license_visibility.
    vis = base["license_visibility"]
    if isinstance(vis, dict):
        base["license_type"] = vis.get("license_type", base["license_type"])
        base["commercial_use_allowed"] = bool(vis.get("commercial_use_allowed", False))
        base["redistribution_allowed"] = bool(vis.get("redistribution_allowed", False))
        base["public_display_allowed"] = bool(vis.get("public_display_allowed", False))
    return base


def source_contracts() -> list[dict[str, Any]]:
    """One contract per required domain. Legal sources only; else PROVIDER_REQUIRED."""
    contracts = [
        _contract(
            domain="crypto",
            source_id="bybit_public_linear_tickers",
            provider="bybit",
            dataset="linear_tickers",
            market_type="perpetual",
            access_method="official_rest_api",
            status="CONTRACT_READY",
            license_visibility=_license(
                license_type="exchange_public_api_tos",
                commercial_use_allowed=True,
                redistribution_allowed=False,
                public_display_allowed=True,
                training_allowed=True,
                summary="Bybit public market REST; ToS-bound; redistribution restricted.",
            ),
            provenance=_provenance(
                origin="bybit_public_rest",
                access_path="https://api.bybit.com/v5/market/tickers",
                authority="exchange_public_api",
                verification="official_endpoint_documented",
            ),
            endpoint="https://api.bybit.com/v5/market/tickers",
            resolution="ticker_snapshot",
            supports_live_bind=True,
            notes=(
                "Read-only public tickers. Contract defines binding surface only; "
                "this round does not fabricate Live values."
            ),
        ),
        _contract(
            domain="us_equities",
            source_id="us_equities_provider_required",
            provider="none",
            dataset="us_equity_quotes",
            market_type="equity",
            access_method="founder_authorized_commercial_api",
            status="PROVIDER_REQUIRED",
            license_visibility=_license(
                license_type="provider_required",
                commercial_use_allowed=False,
                redistribution_allowed=False,
                public_display_allowed=False,
                training_allowed=False,
                summary="No licensed US equity market-data provider wired.",
            ),
            provenance=_provenance(
                origin="unwired",
                access_path="none",
                authority="none",
                verification="provider_required",
            ),
            endpoint=None,
            resolution="n/a",
            supports_live_bind=False,
            notes=(
                "Exchange SIP / vendor license required. No scrape of Yahoo/Google finance. "
                "status=PROVIDER_REQUIRED; value remains null."
            ),
        ),
        _contract(
            domain="asian_equities",
            source_id="asian_equities_provider_required",
            provider="none",
            dataset="asian_equity_quotes",
            market_type="equity",
            access_method="founder_authorized_commercial_api",
            status="PROVIDER_REQUIRED",
            license_visibility=_license(
                license_type="provider_required",
                commercial_use_allowed=False,
                redistribution_allowed=False,
                public_display_allowed=False,
                training_allowed=False,
                summary="No licensed Asian equity market-data provider wired.",
            ),
            provenance=_provenance(
                origin="unwired",
                access_path="none",
                authority="none",
                verification="provider_required",
            ),
            endpoint=None,
            resolution="n/a",
            supports_live_bind=False,
            notes=(
                "TWSE/HKEX/TSE vendor or exchange license required. "
                "status=PROVIDER_REQUIRED; no fabricated quotes."
            ),
        ),
        _contract(
            domain="fx",
            source_id="ecb_euro_fx_reference_rates",
            provider="european_central_bank",
            dataset="euro_fx_reference_rates",
            market_type="fx_reference",
            access_method="central_bank_reference",
            status="CONTRACT_READY",
            license_visibility=_license(
                license_type="ecb_open_data",
                commercial_use_allowed=True,
                redistribution_allowed=True,
                public_display_allowed=True,
                training_allowed=True,
                summary="ECB euro foreign exchange reference rates; open data terms.",
            ),
            provenance=_provenance(
                origin="ecb_sdw",
                access_path="https://www.ecb.europa.eu/stats/eurofxref/",
                authority="central_bank",
                verification="official_public_reference",
            ),
            endpoint="https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
            resolution="daily_reference",
            supports_live_bind=True,
            notes=(
                "Daily reference rates — not tick Live FX. Contract ready; "
                "this round does not fabricate Live values."
            ),
        ),
        _contract(
            domain="rates",
            source_id="fred_us_interest_rates",
            provider="st_louis_fed",
            dataset="us_interest_rate_series",
            market_type="rates",
            access_method="government_open_data",
            status="CONTRACT_READY",
            license_visibility=_license(
                license_type="fred_open_data",
                commercial_use_allowed=True,
                redistribution_allowed=True,
                public_display_allowed=True,
                training_allowed=True,
                summary="FRED open data; attribution required per St. Louis Fed terms.",
            ),
            provenance=_provenance(
                origin="fred_api",
                access_path="https://fred.stlouisfed.org/docs/api/fred/",
                authority="us_federal_reserve_bank_st_louis",
                verification="official_open_api",
            ),
            endpoint="https://api.stlouisfed.org/fred/series/observations",
            resolution="series_observation",
            supports_live_bind=True,
            notes=(
                "Official FRED series contract. API key required at bind time; "
                "no fabricated series values in this round."
            ),
        ),
        _contract(
            domain="bonds",
            source_id="us_treasury_fiscaldata_yields",
            provider="us_treasury",
            dataset="daily_treasury_yield_curve",
            market_type="sovereign_bonds",
            access_method="government_open_data",
            status="CONTRACT_READY",
            license_visibility=_license(
                license_type="us_government_public_domain",
                commercial_use_allowed=True,
                redistribution_allowed=True,
                public_display_allowed=True,
                training_allowed=True,
                summary="US Treasury Fiscal Data; US government public information.",
            ),
            provenance=_provenance(
                origin="treasury_fiscaldata",
                access_path="https://fiscaldata.treasury.gov/",
                authority="us_department_of_the_treasury",
                verification="official_open_api",
            ),
            endpoint=(
                "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
                "v2/accounting/od/avg_interest_rates"
            ),
            resolution="daily",
            supports_live_bind=True,
            notes=(
                "Sovereign Treasury yields only. Corporate/credit bond tapes remain "
                "PROVIDER_REQUIRED (not claimed here)."
            ),
        ),
        _contract(
            domain="commodities",
            source_id="commodities_provider_required",
            provider="none",
            dataset="commodity_futures_prices",
            market_type="commodities",
            access_method="founder_authorized_commercial_api",
            status="PROVIDER_REQUIRED",
            license_visibility=_license(
                license_type="provider_required",
                commercial_use_allowed=False,
                redistribution_allowed=False,
                public_display_allowed=False,
                training_allowed=False,
                summary="No licensed commodities futures feed wired (CME/etc.).",
            ),
            provenance=_provenance(
                origin="unwired",
                access_path="none",
                authority="none",
                verification="provider_required",
            ),
            endpoint=None,
            resolution="n/a",
            supports_live_bind=False,
            notes=(
                "Exchange-licensed futures market data required. "
                "No fabricated commodity prices."
            ),
        ),
        _contract(
            domain="etf_flows",
            source_id="etf_flows_provider_required",
            provider="none",
            dataset="etf_fund_flows",
            market_type="etf_flows",
            access_method="founder_authorized_commercial_api",
            status="PROVIDER_REQUIRED",
            license_visibility=_license(
                license_type="provider_required",
                commercial_use_allowed=False,
                redistribution_allowed=False,
                public_display_allowed=False,
                training_allowed=False,
                summary="No licensed ETF flow / creation-redemption provider wired.",
            ),
            provenance=_provenance(
                origin="unwired",
                access_path="none",
                authority="none",
                verification="provider_required",
            ),
            endpoint=None,
            resolution="n/a",
            supports_live_bind=False,
            notes="ETF flow vendors require commercial license. status=PROVIDER_REQUIRED.",
        ),
        _contract(
            domain="macro_events",
            source_id="federal_reserve_fomc_calendar",
            provider="us_federal_reserve",
            dataset="fomc_meeting_calendar",
            market_type="macro_events",
            access_method="government_open_data",
            status="CONTRACT_READY",
            license_visibility=_license(
                license_type="us_government_public_domain",
                commercial_use_allowed=True,
                redistribution_allowed=True,
                public_display_allowed=True,
                training_allowed=True,
                summary="Federal Reserve public FOMC calendar; government public information.",
            ),
            provenance=_provenance(
                origin="federalreserve_gov",
                access_path="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                authority="board_of_governors_federal_reserve",
                verification="official_public_page",
            ),
            endpoint="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            resolution="event_calendar",
            supports_live_bind=True,
            notes=(
                "Macro event calendar contract. Full multi-country economic calendar "
                "vendors remain separate; no fabricated event surprises."
            ),
        ),
        _contract(
            domain="regulatory_events",
            source_id="sec_edgar_company_filings",
            provider="us_sec",
            dataset="edgar_submissions",
            market_type="regulatory_events",
            access_method="government_open_data",
            status="CONTRACT_READY",
            license_visibility=_license(
                license_type="sec_edgar_public_data",
                commercial_use_allowed=True,
                redistribution_allowed=True,
                public_display_allowed=True,
                training_allowed=True,
                summary="SEC EDGAR public filings; fair-access terms; no auth bypass.",
            ),
            provenance=_provenance(
                origin="sec_edgar",
                access_path="https://www.sec.gov/edgar/sec-api-documentation",
                authority="us_securities_and_exchange_commission",
                verification="official_open_api",
            ),
            endpoint="https://data.sec.gov/submissions/",
            resolution="filing_event",
            supports_live_bind=True,
            notes="Regulatory filing events. Respect SEC fair-access User-Agent and rate limits.",
        ),
        _contract(
            domain="security_incidents",
            source_id="cisa_known_exploited_vulnerabilities",
            provider="cisa",
            dataset="known_exploited_vulnerabilities_catalog",
            market_type="security_incidents",
            access_method="government_open_data",
            status="CONTRACT_READY",
            license_visibility=_license(
                license_type="us_government_public_domain",
                commercial_use_allowed=True,
                redistribution_allowed=True,
                public_display_allowed=True,
                training_allowed=True,
                summary="CISA KEV catalog; US government public cybersecurity data.",
            ),
            provenance=_provenance(
                origin="cisa_kev",
                access_path="https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                authority="cisa",
                verification="official_public_feed",
            ),
            endpoint="https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
            resolution="incident_catalog",
            supports_live_bind=True,
            notes=(
                "Cybersecurity incident catalog contract. Crypto-protocol exploit feeds "
                "without a legal provider stay PROVIDER_REQUIRED (not claimed here)."
            ),
        ),
        _contract(
            domain="exchange_incidents",
            source_id="bybit_public_announcements_status",
            provider="bybit",
            dataset="exchange_status_announcements",
            market_type="exchange_incidents",
            access_method="exchange_public_status",
            status="CONTRACT_READY",
            license_visibility=_license(
                license_type="exchange_public_api_tos",
                commercial_use_allowed=True,
                redistribution_allowed=False,
                public_display_allowed=True,
                training_allowed=True,
                summary="Exchange public announcements/status; ToS-bound; read-only.",
            ),
            provenance=_provenance(
                origin="bybit_public_announcements",
                access_path="https://api.bybit.com/v5/announcements/index",
                authority="exchange_public_api",
                verification="official_endpoint_documented",
            ),
            endpoint="https://api.bybit.com/v5/announcements/index",
            resolution="announcement_event",
            supports_live_bind=True,
            notes=(
                "Read-only incident/announcement surface. No exchange write. "
                "This round does not fabricate Live incident payloads."
            ),
        ),
        _contract(
            domain="ai_tech_sector",
            source_id="ai_tech_sector_provider_required",
            provider="none",
            dataset="ai_tech_sector_market_tape",
            market_type="equity_sector",
            access_method="founder_authorized_commercial_api",
            status="PROVIDER_REQUIRED",
            license_visibility=_license(
                license_type="provider_required",
                commercial_use_allowed=False,
                redistribution_allowed=False,
                public_display_allowed=False,
                training_allowed=False,
                summary="No licensed AI/tech sector market-data provider wired.",
            ),
            provenance=_provenance(
                origin="unwired",
                access_path="none",
                authority="none",
                verification="provider_required",
            ),
            endpoint=None,
            resolution="n/a",
            supports_live_bind=False,
            notes=(
                "Sector tape / constituents require equity vendor license. "
                "status=PROVIDER_REQUIRED; no fabricated sector numbers."
            ),
        ),
    ]
    domains = [c["domain"] for c in contracts]
    if sorted(domains) != sorted(REQUIRED_DOMAINS):
        missing = sorted(set(REQUIRED_DOMAINS) - set(domains))
        extra = sorted(set(domains) - set(REQUIRED_DOMAINS))
        raise RuntimeError(f"domain_coverage_error missing={missing} extra={extra}")
    return contracts


def contract_by_domain(domain: str) -> dict[str, Any] | None:
    for c in source_contracts():
        if c["domain"] == domain:
            return deepcopy(c)
    return None


def provider_required_contracts() -> list[dict[str, Any]]:
    return [deepcopy(c) for c in source_contracts() if c["status"] == "PROVIDER_REQUIRED"]


def contract_ready_contracts() -> list[dict[str, Any]]:
    return [deepcopy(c) for c in source_contracts() if c["status"] == "CONTRACT_READY"]
