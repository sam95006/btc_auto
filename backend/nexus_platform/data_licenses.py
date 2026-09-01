"""Data-licensing governance registry (NEXUS-EXPERIENCE-1A).

A dataset MUST NOT be exposed commercially until its license permits the intended
use. This registry is the single source of truth for that gate. Only the current
public exchange market feed is in use; every paid/derived provider is registered
as NOT licensed so the product honestly shows COMING_SOON instead of exposing
data we are not permitted to use. No provider secrets live here or in frontend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DatasetLicense:
    provider: str                 # canonical publisher identity (not an eng label)
    dataset: str                  # logical dataset id
    domain: str                   # data-domain this feeds
    license_status: str           # "in_use" | "evaluating" | "not_licensed"
    commercial_use: bool
    redistribution_allowed: bool
    attribution_required: bool
    cache_allowed: bool
    derived_data_allowed: bool
    retention_limit_days: Optional[int] = None
    rate_limit_per_min: Optional[int] = None
    plan_cost_usd_month: Optional[int] = None   # our cost, metadata only
    notes: str = ""

    def id(self) -> str:
        return f"{self.provider}:{self.dataset}"


# NOTE: user-facing source labels are canonical identities (Exchange market,
# Official, Institution, News, Social) — engineering/provider API names are only
# for governance/legal attribution, never shown in normal UI.
REGISTRY: tuple[DatasetLicense, ...] = (
    DatasetLicense(
        provider="Exchange market", dataset="usdm_public_ticker_ohlcv", domain="market",
        license_status="in_use", commercial_use=True, redistribution_allowed=False,
        attribution_required=False, cache_allowed=True, derived_data_allowed=True,
        rate_limit_per_min=1200, notes="Credential-free public exchange market data; derived intelligence only.",
    ),
    # Future paid/derived providers — registered but NOT licensed yet.
    DatasetLicense(provider="Derivatives analytics", dataset="oi_funding_liquidation", domain="derivatives",
                   license_status="not_licensed", commercial_use=False, redistribution_allowed=False,
                   attribution_required=True, cache_allowed=False, derived_data_allowed=False,
                   notes="OI / funding / liquidation / order-flow. Requires a commercial license."),
    DatasetLicense(provider="On-chain analytics", dataset="onchain_flows_metrics", domain="onchain",
                   license_status="not_licensed", commercial_use=False, redistribution_allowed=False,
                   attribution_required=True, cache_allowed=False, derived_data_allowed=False,
                   notes="Exchange netflow, whale, MVRV/SOPR etc. Requires a commercial license."),
    DatasetLicense(provider="Smart money analytics", dataset="entity_wallet_intelligence", domain="onchain",
                   license_status="not_licensed", commercial_use=False, redistribution_allowed=False,
                   attribution_required=True, cache_allowed=False, derived_data_allowed=False,
                   notes="Entity / wallet smart-money intelligence. Requires a commercial license."),
    DatasetLicense(provider="Social intelligence", dataset="creator_social_sentiment", domain="news_social",
                   license_status="not_licensed", commercial_use=False, redistribution_allowed=False,
                   attribution_required=True, cache_allowed=False, derived_data_allowed=False,
                   notes="Social / creator sentiment & track record. Personal-only; NEVER for Founder trading."),
    DatasetLicense(provider="News", dataset="market_news_feed", domain="news_social",
                   license_status="not_licensed", commercial_use=False, redistribution_allowed=False,
                   attribution_required=True, cache_allowed=False, derived_data_allowed=False,
                   notes="Licensed news feed. Requires a commercial license."),
)

_BY_ID = {d.id(): d for d in REGISTRY}
_BY_DATASET = {d.dataset: d for d in REGISTRY}


def get_license(dataset: str) -> Optional[DatasetLicense]:
    return _BY_DATASET.get(dataset)


def can_expose_commercially(dataset: str) -> bool:
    """Hard gate: only in-use, commercial-use-permitted datasets may be exposed."""
    lic = _BY_DATASET.get(dataset)
    return bool(lic and lic.license_status == "in_use" and lic.commercial_use)


def licensed_domains() -> set[str]:
    return {d.domain for d in REGISTRY if d.license_status == "in_use" and d.commercial_use}


def public_registry() -> list[dict]:
    return [{"provider": d.provider, "dataset": d.dataset, "domain": d.domain,
             "license_status": d.license_status, "commercial_use": d.commercial_use,
             "attribution_required": d.attribution_required} for d in REGISTRY]
