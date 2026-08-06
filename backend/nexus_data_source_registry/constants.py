"""V17-A Data Source and License Registry — constants and hard bans."""
from __future__ import annotations

SCHEMA = "v17_a_data_source_license_registry_v1"
SOURCE_SCHEMA = "v17_a_data_source_record_v1"
REGISTRY_SCHEMA = "v17_a_data_source_registry_document_v1"
SCHEMA_VERSION = 1
LANE = "V17-A"
LANE_NAME = "DATA_SOURCE_AND_LICENSE_REGISTRY"
BRANCH = "feature/v17-data-source-license-registry"
BASE_COMMIT = "66a0f7827d5709fc09bc8c7495e93a4089eb28de"
ARTIFACT_REL = "artifacts/readiness/immutable/v17_data_source_registry"
SCHEMA_REL = f"{ARTIFACT_REL}/data_source_registry.schema.json"
FIXTURES_REL = f"{ARTIFACT_REL}/fixture_sources.json"

SOURCE_STATUSES: tuple[str, ...] = (
    "APPROVED_PUBLIC",
    "APPROVED_INTERNAL_ONLY",
    "LICENSE_REVIEW_REQUIRED",
    "REDISTRIBUTION_FORBIDDEN",
    "TRAINING_FORBIDDEN",
    "DEPRECATED",
    "UNAVAILABLE",
)

REQUIRED_SOURCE_FIELDS: tuple[str, ...] = (
    "source_id",
    "provider",
    "dataset",
    "asset_class",
    "market_type",
    "exchange",
    "available_from",
    "available_until",
    "resolution",
    "access_method",
    "license_type",
    "commercial_use_allowed",
    "redistribution_allowed",
    "training_allowed",
    "retention_allowed",
    "revision_policy",
    "point_in_time_capable",
    "rate_limit",
    "cost_class",
    "owner",
    "last_verified_at",
    "status",
)

# Legal access methods only — no paywalled-web scrape.
LEGAL_ACCESS_METHODS: frozenset[str] = frozenset(
    {
        "official_rest_api",
        "official_websocket",
        "official_bulk_download",
        "founder_authorized_commercial_api",
        "self_hosted_node",
        "public_chain_rpc",
        "commercial_ok_dataset",
        "local_fixture",
    }
)

# Providers whose paywalled web UIs must never be scraped.
HARD_BAN_SCRAPE_PROVIDERS: frozenset[str] = frozenset(
    {
        "glassnode",
        "coinglass",
        "messari",
    }
)

SCRAPE_ACCESS_METHODS: frozenset[str] = frozenset(
    {
        "web_scrape",
        "scrape",
        "html_scrape",
        "paywall_scrape",
        "browser_scrape",
        "auth_bypass",
        "rate_limit_bypass",
    }
)

# license_type values that claim production authorization (forbidden under review).
AUTHORIZATION_CLAIM_LICENSE_TYPES: frozenset[str] = frozenset(
    {
        "authorized",
        "founder_authorized",
        "production_authorized",
        "fully_licensed",
        "cleared_for_production",
    }
)

COST_CLASSES: frozenset[str] = frozenset(
    {"free", "freemium", "paid", "enterprise", "self_hosted", "unknown"}
)

REVISION_POLICIES: frozenset[str] = frozenset(
    {
        "immutable_append",
        "vendor_may_revise",
        "exchange_may_correct",
        "unknown",
        "not_applicable",
    }
)

HARD_BANS: tuple[str, ...] = (
    "no_glassnode_paywall_scrape",
    "no_coinglass_paywall_scrape",
    "no_messari_paywall_scrape",
    "no_auth_bypass",
    "no_rate_limit_bypass",
    "no_third_party_piracy",
    "no_license_unknown_as_production_safe",
    "no_training_on_license_review",
    "no_public_display_on_license_review",
    "no_authorization_claim_on_license_review",
    "no_exchange_write",
    "no_mainnet",
    "no_real_money",
    "no_pr26_merge",
    "no_pr27_merge",
    "no_acceleration_report_edit",
)

OWNED_PATHS: tuple[str, ...] = (
    "backend/nexus_data_source_registry/",
    "tools/data_source_registry/",
    "tests/data_source_registry/",
    "artifacts/readiness/immutable/v17_data_source_registry/",
)
