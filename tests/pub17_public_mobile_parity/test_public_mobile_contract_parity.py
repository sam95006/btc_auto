"""V17 deep — public/mobile contract parity tests."""
from __future__ import annotations

import json
from pathlib import Path

from backend.nexus_pub17_global_market_contracts.constants import REQUIRED_DTO_FIELDS
from backend.nexus_pub17_global_market_contracts.dto import (
    FabricatedLiveValueError,
    build_all_normalized_dtos,
    build_normalized_dto,
    validate_dto,
)
from backend.nexus_pub17_global_market_contracts.contracts import (
    provider_required_contracts,
    source_contracts,
)
from backend.nexus_pub17_market_pulse.constants import FIRST_SCREEN_ANSWER_IDS
from backend.nexus_pub17_market_pulse.fixtures import catalog as pulse_catalog
from backend.nexus_pub17_market_pulse.service import build_first_screen
from backend.nexus_pub17_public_mobile_parity.constants import (
    MOBILE_MARKET_PULSE_REQUIRED_FIELDS,
    MOBILE_REQUIRED_PAGE_LABELS,
    PUBLIC_MARKET_PULSE_ANSWER_IDS,
    PUBLIC_NORMALIZED_SOURCE_DTO_FIELDS,
    PUBLIC_TO_MOBILE_SEMANTIC_MAP,
    SHARED_BUYABLE_PRODUCT_LABELS,
    SHARED_FORBIDDEN_PRODUCT_LABELS,
    SHARED_FRESHNESS_STATES,
)
from backend.nexus_pub17_public_mobile_parity.contract import (
    assert_provider_required_payload,
    assert_semantic_map_complete,
    assert_zero_trade_capabilities,
    build_parity_contract,
    load_parity_contract,
    validate_mobile_field_set,
    write_parity_contract_artifact,
)
from backend.nexus_pub17_public_mobile_parity.gate import run_parity_gate
from backend.nexus_pub17_public_mobile_parity.surface_scan import scan_member_control_surfaces
from backend.nexus_public_subscription_boundary.constants import (
    MEMBER_BUYABLE_PRODUCT_LABELS,
    MEMBER_FORBIDDEN_PRODUCT_LABELS,
)

ROOT = Path(__file__).resolve().parents[2]


def test_semantic_map_covers_all_public_answers():
    errors = assert_semantic_map_complete()
    assert errors == [], errors
    assert list(PUBLIC_TO_MOBILE_SEMANTIC_MAP) == list(PUBLIC_MARKET_PULSE_ANSWER_IDS)


def test_public_pulse_answer_ids_match_frozen_contract():
    assert list(FIRST_SCREEN_ANSWER_IDS) == list(PUBLIC_MARKET_PULSE_ANSWER_IDS)
    contract = build_parity_contract()
    assert contract["public_market_pulse_answer_ids"] == list(PUBLIC_MARKET_PULSE_ANSWER_IDS)


def test_normalized_dto_field_set_parity():
    assert list(REQUIRED_DTO_FIELDS) == list(PUBLIC_NORMALIZED_SOURCE_DTO_FIELDS)
    assert "freshness" in REQUIRED_DTO_FIELDS
    assert "status" in REQUIRED_DTO_FIELDS
    assert "availability" in REQUIRED_DTO_FIELDS


def test_mobile_required_field_set_frozen():
    missing = validate_mobile_field_set(MOBILE_MARKET_PULSE_REQUIRED_FIELDS)
    assert missing == []
    assert "provider_status" in MOBILE_MARKET_PULSE_REQUIRED_FIELDS
    assert "data_freshness" in MOBILE_MARKET_PULSE_REQUIRED_FIELDS
    assert "execution_control_count" in MOBILE_MARKET_PULSE_REQUIRED_FIELDS
    assert "stale_indicator" in MOBILE_MARKET_PULSE_REQUIRED_FIELDS


def test_provider_required_source_dtos_refuse_fake_live():
    pr = provider_required_contracts()
    assert len(pr) >= 1
    for contract in pr:
        dto = build_normalized_dto(contract, retrieved_at="2026-08-06T02:00:00Z")
        payload = dto.to_public_dict()
        assert payload["status"] == "PROVIDER_REQUIRED"
        assert payload["value"] is None
        assert payload["mode"] != "LIVE"
        assert payload["freshness"] != "LIVE"
        assert validate_dto(payload) == []
        assert assert_provider_required_payload(payload) == []
        try:
            build_normalized_dto(
                contract,
                retrieved_at="2026-08-06T02:00:00Z",
                mode="LIVE",
                value=123.45,
                live_bind_attested=False,
            )
            raise AssertionError("expected FabricatedLiveValueError")
        except FabricatedLiveValueError:
            pass


def test_provider_required_pulse_fixture_honesty():
    cases = [c for c in pulse_catalog() if c.get("mode") == "PROVIDER_REQUIRED"]
    assert cases, "expected PROVIDER_REQUIRED pulse fixture"
    for case in cases:
        screen = build_first_screen(case)
        assert screen["chrome_label"] == "PROVIDER_REQUIRED"
        assert screen["data_freshness"] == "PROVIDER_REQUIRED"
        assert str(screen.get("chrome_label")).upper() != "LIVE"
        for answer in screen["answers"]:
            if answer["id"] == "top_3_markets_contracts":
                assert answer["answer"] == "PROVIDER_REQUIRED"
                assert not answer.get("markets")
            if answer["id"] == "analysis_vs_actual_trading":
                assert answer.get("actually_traded") is False
                assert answer.get("exchange_write") is False


def test_shared_freshness_vocab_includes_provider_required():
    assert "PROVIDER_REQUIRED" in SHARED_FRESHNESS_STATES
    assert "STALE" in SHARED_FRESHNESS_STATES
    assert "DEMO_DATA" in SHARED_FRESHNESS_STATES
    assert "LIVE" in SHARED_FRESHNESS_STATES


def test_subscription_product_labels_match_mobile_defaults():
    assert set(MEMBER_BUYABLE_PRODUCT_LABELS) == set(SHARED_BUYABLE_PRODUCT_LABELS)
    assert set(MEMBER_FORBIDDEN_PRODUCT_LABELS) == set(SHARED_FORBIDDEN_PRODUCT_LABELS)
    # Mobile SubscriptionAccessDto.default* mirrors these exact labels.
    assert "Copy Trading" in SHARED_FORBIDDEN_PRODUCT_LABELS
    assert "Auto Trading" in SHARED_FORBIDDEN_PRODUCT_LABELS
    assert "Exchange Execution" in SHARED_FORBIDDEN_PRODUCT_LABELS


def test_mobile_required_pages_frozen():
    assert len(MOBILE_REQUIRED_PAGE_LABELS) == 11
    assert "Market Pulse" in MOBILE_REQUIRED_PAGE_LABELS
    assert "Subscription Access" in MOBILE_REQUIRED_PAGE_LABELS
    assert "Data Freshness" in MOBILE_REQUIRED_PAGE_LABELS


def test_no_trade_copy_exchange_controls_on_public_surfaces():
    scan = scan_member_control_surfaces(ROOT)
    assert scan["survivor_count"] == 0, scan["survivors"]
    assert scan["status"] == "PASS"


def test_all_source_dtos_zero_trade_capabilities():
    for dto in build_all_normalized_dtos(retrieved_at="2026-08-06T02:00:00Z"):
        assert dto.get("exchange_write") is False
        assert dto.get("member_exchange_write") is False
        assert dto.get("read_only") is True
        assert assert_zero_trade_capabilities(
            {
                "execution_control_count": 0,
                "exchange_write_capability": 0,
                "customer_trading_capability_count": 0,
            }
        ) == []


def test_parity_gate_pass_and_artifact():
    result = run_parity_gate(ROOT)
    assert result["status"] == "PASS", result["errors"]
    assert result["surface_scan"]["survivor_count"] == 0
    artifact = Path(result["artifact"])
    assert artifact.is_file()
    loaded = load_parity_contract(ROOT)
    assert loaded["schema"] == "pub17_public_mobile_parity_contract_v1"
    # Artifact round-trip equals builder.
    rebuilt = build_parity_contract()
    assert loaded["public_market_pulse_answer_ids"] == rebuilt["public_market_pulse_answer_ids"]
    assert loaded["mobile_market_pulse_required_fields"] == rebuilt["mobile_market_pulse_required_fields"]


def test_write_parity_contract_artifact_idempotent():
    path = write_parity_contract_artifact(ROOT)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["provider_required_rules"]["value_must_be_null"] is True
    assert len(source_contracts()) >= 13
