"""V17-A Data Source and License Registry — validation + policy tests."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from backend.nexus_data_source_registry import (
    HARD_BANS,
    REQUIRED_SOURCE_FIELDS,
    SOURCE_STATUSES,
    DataSourceRegistry,
    DataSourceRegistryError,
    build_fixture_registry_document,
    build_schema,
    fixture_sources,
    validate_registry_document,
    validate_source_record,
    write_fixture_artifact,
    write_schema_artifact,
)


REPO = Path(__file__).resolve().parents[2]


def _by_id(sid: str) -> dict:
    for s in fixture_sources():
        if s["source_id"] == sid:
            return deepcopy(s)
    raise KeyError(sid)


def test_required_fields_cover_founder_spec() -> None:
    expected = {
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
    }
    assert set(REQUIRED_SOURCE_FIELDS) == expected


def test_all_statuses_defined() -> None:
    assert set(SOURCE_STATUSES) == {
        "APPROVED_PUBLIC",
        "APPROVED_INTERNAL_ONLY",
        "LICENSE_REVIEW_REQUIRED",
        "REDISTRIBUTION_FORBIDDEN",
        "TRAINING_FORBIDDEN",
        "DEPRECATED",
        "UNAVAILABLE",
    }


def test_fixture_sources_validate() -> None:
    for src in fixture_sources():
        errors = validate_source_record(src)
        assert errors == [], (src["source_id"], errors)


def test_fixture_document_validates() -> None:
    doc = build_fixture_registry_document()
    assert validate_registry_document(doc) == []


def test_fixtures_cover_each_status() -> None:
    statuses = {s["status"] for s in fixture_sources()}
    assert statuses == set(SOURCE_STATUSES)


def test_schema_artifact_roundtrip() -> None:
    path = write_schema_artifact(REPO)
    assert path.is_file()
    schema = build_schema()
    assert schema["schema_name"] == "v17_a_data_source_license_registry_v1"
    assert "sources" in schema["properties"]


def test_fixture_artifact_written() -> None:
    path = write_fixture_artifact(REPO)
    assert path.is_file()


def test_registry_list_by_status() -> None:
    reg = DataSourceRegistry.from_fixtures()
    review = reg.list_by_status("LICENSE_REVIEW_REQUIRED")
    assert len(review) == 1
    assert review[0]["source_id"] == "vendor_x_metrics_api_review"
    public = reg.list_by_status("APPROVED_PUBLIC")
    assert {s["source_id"] for s in public} >= {
        "binance_spot_klines_1m",
        "bitcoin_core_blocks_self_hosted",
    }


def test_registry_duplicate_rejected() -> None:
    reg = DataSourceRegistry.from_fixtures()
    with pytest.raises(DataSourceRegistryError, match="duplicate_source_id"):
        reg.register(_by_id("binance_spot_klines_1m"))


def test_license_review_no_training() -> None:
    src = _by_id("vendor_x_metrics_api_review")
    src["training_allowed"] = True
    errors = validate_source_record(src)
    assert "license_review_training_forbidden" in errors


def test_license_review_no_public_display() -> None:
    src = _by_id("vendor_x_metrics_api_review")
    src["public_display_allowed"] = True
    errors = validate_source_record(src)
    assert "license_review_public_display_forbidden" in errors


def test_license_review_no_authorization_claim() -> None:
    src = _by_id("vendor_x_metrics_api_review")
    src["authorization_claimed"] = True
    errors = validate_source_record(src)
    assert "license_review_authorization_claim_forbidden" in errors


def test_license_review_adapter_contract_required() -> None:
    src = _by_id("vendor_x_metrics_api_review")
    src["adapter_contract_ok"] = False
    errors = validate_source_record(src)
    assert "license_review_adapter_contract_not_ok" in errors
    del src["adapter_contract_ok"]
    errors2 = validate_source_record(src)
    assert "license_review_requires_adapter_contract_ok" in errors2


def test_license_review_permission_helpers() -> None:
    reg = DataSourceRegistry.from_fixtures()
    sid = "vendor_x_metrics_api_review"
    assert reg.allows_training(sid) is False
    assert reg.allows_public_display(sid) is False
    assert reg.authorization_claimed(sid) is False


def test_hard_ban_glassnode_scrape() -> None:
    src = _by_id("binance_spot_klines_1m")
    src["source_id"] = "glassnode_scrape_ban"
    src["provider"] = "glassnode"
    src["access_method"] = "web_scrape"
    src["status"] = "APPROVED_INTERNAL_ONLY"
    src["public_display_allowed"] = False
    errors = validate_source_record(src)
    assert any("hard_ban" in e or "scrape" in e for e in errors)


def test_hard_ban_coinglass_scrape() -> None:
    src = _by_id("binance_spot_klines_1m")
    src["source_id"] = "coinglass_scrape_ban"
    src["provider"] = "coinglass"
    src["access_method"] = "paywall_scrape"
    errors = validate_source_record(src)
    assert any("scrape" in e or "hard_ban" in e for e in errors)


def test_hard_ban_messari_scrape() -> None:
    src = _by_id("binance_spot_klines_1m")
    src["source_id"] = "messari_scrape_ban"
    src["provider"] = "messari"
    src["access_method"] = "html_scrape"
    errors = validate_source_record(src)
    assert any("scrape" in e or "hard_ban" in e for e in errors)


def test_hard_ban_rate_limit_bypass() -> None:
    src = _by_id("binance_spot_klines_1m")
    src["rate_limit"] = "unlimited_bypass"
    errors = validate_source_record(src)
    assert "hard_ban_rate_limit_bypass" in errors


def test_training_forbidden_inconsistency() -> None:
    src = _by_id("research_corpus_no_training")
    src["training_allowed"] = True
    errors = validate_source_record(src)
    assert "training_forbidden_but_training_allowed_true" in errors


def test_redistribution_forbidden_inconsistency() -> None:
    src = _by_id("commercial_feed_no_redistribute")
    src["redistribution_allowed"] = True
    errors = validate_source_record(src)
    assert "redistribution_forbidden_but_redistribution_allowed_true" in errors


def test_missing_required_field() -> None:
    src = _by_id("binance_spot_klines_1m")
    del src["owner"]
    errors = validate_source_record(src)
    assert "missing_required:owner" in errors


def test_bad_status_rejected() -> None:
    src = _by_id("binance_spot_klines_1m")
    src["status"] = "PRODUCTION_SAFE_UNKNOWN_LICENSE"
    errors = validate_source_record(src)
    assert any(e.startswith("bad_status:") for e in errors)


def test_hard_bans_include_scrape_and_review_gates() -> None:
    bans = set(HARD_BANS)
    assert "no_glassnode_paywall_scrape" in bans
    assert "no_coinglass_paywall_scrape" in bans
    assert "no_messari_paywall_scrape" in bans
    assert "no_training_on_license_review" in bans
    assert "no_public_display_on_license_review" in bans
    assert "no_authorization_claim_on_license_review" in bans
    assert "no_acceleration_report_edit" in bans


def test_registry_to_document() -> None:
    reg = DataSourceRegistry.from_fixtures()
    doc = reg.to_document()
    assert doc["source_count"] == len(fixture_sources())
    assert sum(doc["status_counts"].values()) == doc["source_count"]
