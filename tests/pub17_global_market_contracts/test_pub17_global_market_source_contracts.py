"""PUB17-A Global Market Source Contracts — validation + honesty tests."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from backend.nexus_pub17_global_market_contracts import (
    HARD_BANS,
    REQUIRED_DOMAINS,
    FabricatedLiveValueError,
    GlobalMarketSourceRegistry,
    build_all_normalized_dtos,
    build_normalized_dto,
    build_schema,
    contract_ready_contracts,
    provider_required_contracts,
    run_gate,
    source_contracts,
    write_catalog_artifact,
    write_schema_artifact,
)
from backend.nexus_pub17_global_market_contracts.dto import validate_dto
from backend.nexus_pub17_global_market_contracts.registry import (
    GlobalMarketContractError,
    validate_catalog,
    validate_contract,
)


REPO = Path(__file__).resolve().parents[2]


def _by_domain(domain: str) -> dict:
    for c in source_contracts():
        if c["domain"] == domain:
            return deepcopy(c)
    raise KeyError(domain)


def test_required_domains_cover_founder_spec() -> None:
    assert set(REQUIRED_DOMAINS) == {
        "crypto",
        "us_equities",
        "asian_equities",
        "fx",
        "rates",
        "bonds",
        "commodities",
        "etf_flows",
        "macro_events",
        "regulatory_events",
        "security_incidents",
        "exchange_incidents",
        "ai_tech_sector",
    }
    assert len(REQUIRED_DOMAINS) == 13


def test_source_contracts_cover_each_domain_once() -> None:
    contracts = source_contracts()
    domains = [c["domain"] for c in contracts]
    assert sorted(domains) == sorted(REQUIRED_DOMAINS)
    assert len(domains) == len(set(domains))


def test_every_contract_validates() -> None:
    for c in source_contracts():
        assert validate_contract(c) == [], (c["domain"], validate_contract(c))


def test_provider_required_have_no_values_or_endpoints() -> None:
    for c in provider_required_contracts():
        assert c["status"] == "PROVIDER_REQUIRED"
        assert c["endpoint"] is None
        assert c["supports_live_bind"] is False
        dto = build_normalized_dto(c).to_public_dict()
        assert dto["value"] is None
        assert dto["mode"] == "PROVIDER_REQUIRED"
        assert dto["freshness"] == "PROVIDER_REQUIRED"
        assert dto["fabricated"] is False


def test_contract_ready_have_license_and_provenance() -> None:
    for c in contract_ready_contracts():
        assert c["endpoint"]
        assert c["provider"] != "none"
        vis = c["license_visibility"]
        assert vis["visibility"] == "PUBLIC_VISIBLE"
        assert vis["license_type"]
        assert c["provenance"]["origin"]
        dto = build_normalized_dto(c).to_public_dict()
        assert dto["mode"] == "CONTRACT"
        assert dto["freshness"] == "UNAVAILABLE"
        assert dto["availability"] == "CONTRACT_READY"
        assert dto["value"] is None
        assert dto["fabricated"] is False


def test_provider_required_count_is_five() -> None:
    # Honest: us_equities, asian_equities, commodities, etf_flows, ai_tech_sector
    pr = provider_required_contracts()
    assert {c["domain"] for c in pr} == {
        "us_equities",
        "asian_equities",
        "commodities",
        "etf_flows",
        "ai_tech_sector",
    }
    assert len(pr) == 5
    reg = GlobalMarketSourceRegistry()
    assert reg.provider_required_count() == 5
    assert reg.contract_ready_count() == 8


def test_normalized_dtos_validate() -> None:
    for dto in build_all_normalized_dtos(retrieved_at="2026-08-06T00:00:00Z"):
        assert validate_dto(dto) == [], (dto["domain"], validate_dto(dto))


def test_registry_document_validates() -> None:
    doc = GlobalMarketSourceRegistry().to_document(retrieved_at="2026-08-06T00:00:00Z")
    assert validate_catalog(doc) == []
    assert doc["provider_required_count"] == 5
    assert doc["fabricated_live_value_count"] == 0
    assert doc["exchange_write"] is False


def test_refuse_fake_live_on_provider_required() -> None:
    c = _by_domain("us_equities")
    with pytest.raises(FabricatedLiveValueError):
        build_normalized_dto(c, mode="LIVE", value=100.0, live_bind_attested=False)
    with pytest.raises(FabricatedLiveValueError):
        build_normalized_dto(c, value=1.23)


def test_refuse_fake_live_without_bind_on_contract_ready() -> None:
    c = _by_domain("crypto")
    with pytest.raises(FabricatedLiveValueError):
        build_normalized_dto(
            c,
            mode="LIVE",
            value=42000.0,
            freshness="LIVE",
            live_bind_attested=False,
        )


def test_real_live_bind_attested_allowed_for_contract_ready() -> None:
    c = _by_domain("crypto")
    dto = build_normalized_dto(
        c,
        mode="LIVE",
        value=42000.0,
        unit="USD",
        as_of="2026-08-06T00:00:00Z",
        freshness="LIVE",
        availability="AVAILABLE",
        live_bind_attested=True,
        retrieved_at="2026-08-06T00:00:01Z",
    )
    assert dto.mode == "LIVE"
    assert dto.value == 42000.0
    assert dto.fabricated is False


def test_hard_bans_include_founder_requirements() -> None:
    bans = set(HARD_BANS)
    assert "no_member_exchange_write" in bans
    assert "no_private_strategy_thresholds" in bans
    assert "no_fabricated_live_values" in bans
    assert "no_pr26_merge" in bans
    assert "no_pr27_merge" in bans
    assert "no_acceleration_report_edit" in bans


def test_artifacts_written() -> None:
    schema_path = write_schema_artifact(REPO)
    catalog_path = write_catalog_artifact(REPO, retrieved_at="2026-08-06T00:00:00Z")
    assert schema_path.is_file()
    assert catalog_path.is_file()
    schema = build_schema()
    assert schema["schema_name"] == "pub17_a_global_market_source_contracts_v1"


def test_duplicate_domain_rejected() -> None:
    reg = GlobalMarketSourceRegistry()
    with pytest.raises(GlobalMarketContractError, match="duplicate_domain"):
        reg.register(_by_domain("crypto"))


def test_gate_passes() -> None:
    result = run_gate(REPO)
    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["provider_required_count"] == 5
    assert result["fabricated_live_value_count"] == 0
    assert result["private_core_import_count"] == 0
    assert result["exchange_write"] is False
    assert result["acceleration_report_edited"] is False


def test_license_visibility_public_on_all_contracts() -> None:
    for c in source_contracts():
        assert c["license_visibility"]["visibility"] == "PUBLIC_VISIBLE"
        assert "license_type" in c["license_visibility"]
        assert "summary" in c["license_visibility"]


def test_all_contracts_read_only_no_exchange_write() -> None:
    for c in source_contracts():
        assert c["read_only"] is True
        assert c["exchange_write"] is False
