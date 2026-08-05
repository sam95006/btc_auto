"""Tests for UX-A Public Intelligence DTO V2."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_intelligence_dto_v2.constants import (
    AI_RECOMMENDATION_STATES,
    DECISION_LIFECYCLE_STATUSES,
    HARD_BANS,
    LESSON_APPLIED_LABELS,
    REGIME_PROBABILITY_KEYS,
    SCHEMA_VERSION,
    STRATEGY_EXPERT_LABELS,
)
from backend.nexus_public_intelligence_dto_v2.dto import (
    build_abstain_fixture,
    build_fixture_dto,
    publish_public_intelligence_dto,
)
from backend.nexus_public_intelligence_dto_v2.hard_bans import (
    HardBanViolation,
    refuse_exchange_write,
    refuse_internal_strategy_source,
    refuse_private_core_imports,
    refuse_private_execution_controls,
    refuse_proprietary_thresholds,
    refuse_raw_private_memory_graph,
    refuse_secrets,
    refuse_status_json,
    run_three_passes,
    scan_private_core_imports,
)
from backend.nexus_public_intelligence_dto_v2.registry import assert_registry_allowlisted
from backend.nexus_public_intelligence_dto_v2.sanitize import (
    ForbiddenPayloadKeyError,
    assert_no_forbidden_keys,
    serialize_allowlist,
)

ROOT = Path(__file__).resolve().parents[2]


def test_publish_contains_required_public_fields():
    payload = publish_public_intelligence_dto()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["private_core_import_count"] == 0
    assert payload["raw_memory_graph"] is False
    assert payload["private_fields_included"] is False
    assert set(payload["regime_probabilities"]) >= set(REGIME_PROBABILITY_KEYS)
    assert payload["ai_recommendation_state"] in AI_RECOMMENDATION_STATES
    assert isinstance(payload["supporting_evidence"], list)
    assert isinstance(payload["contradicting_evidence"], list)
    assert len(payload["supporting_evidence"]) >= 1
    assert len(payload["contradicting_evidence"]) >= 1
    assert "uncertainty" in payload
    assert payload["strategy_expert_label"] in STRATEGY_EXPERT_LABELS
    assert payload["lesson_applied_label"] in LESSON_APPLIED_LABELS
    assert payload["similar_case_summary"]["similar_case_summary"]
    assert payload["data_freshness"]
    assert payload["decision_lifecycle_status"] in DECISION_LIFECYCLE_STATUSES


def test_abstention_reason_surface():
    payload = publish_public_intelligence_dto(build_abstain_fixture())
    assert payload["ai_recommendation_state"] == "ABSTAIN"
    assert payload["abstention_reason"]
    assert payload["decision_lifecycle_status"] == "ABSTAINED"


def test_forbidden_private_fields_rejected():
    for poison in (
        {"api_key": "x"},
        {"strategy_source": "internal"},
        {"execution_controls": True},
        {"entry_threshold": 0.1},
        {"raw_memory_blob": {}},
        {"lesson_id": "L1"},
        {"order_id": "O1"},
    ):
        with pytest.raises(ForbiddenPayloadKeyError):
            assert_no_forbidden_keys(poison)


def test_allowlist_drops_private_keys():
    clean = publish_public_intelligence_dto()
    mixed = {**clean, "strategy_weights": {"a": 1}, "wallet_address": "0xdead", "secret": "nope"}
    filtered = serialize_allowlist(mixed)
    assert "strategy_weights" not in filtered
    assert "wallet_address" not in filtered
    assert "secret" not in filtered
    assert filtered["private_core_import_count"] == 0


def test_hard_ban_refusers():
    for fn in (
        refuse_secrets,
        refuse_internal_strategy_source,
        refuse_private_execution_controls,
        refuse_proprietary_thresholds,
        refuse_raw_private_memory_graph,
        refuse_exchange_write,
        refuse_private_core_imports,
        refuse_status_json,
    ):
        with pytest.raises(HardBanViolation):
            fn()


def test_private_core_import_count_is_zero():
    report = scan_private_core_imports(ROOT)
    assert report["private_core_import_count"] == 0
    assert report["ok"] is True


def test_registry_allowlisted():
    assert_registry_allowlisted()


def test_fixture_dto_roundtrip():
    dto = build_fixture_dto()
    assert dto.private_core_import_count == 0
    assert dto.raw_memory_graph is False
    pub = dto.to_public_dict()
    assert pub["schema_version"] == SCHEMA_VERSION
    assert "regime_probabilities" in pub


def test_three_passes():
    result = run_three_passes(ROOT)
    assert result["pass_count"] == 3
    assert result["ok"] is True
    assert result["three_pass_status"] == "PASS"
    assert result["hard_bans_intact"] is True
    assert result["private_core_import_count"] == 0
    assert result["exchange_write"] is False
    assert result["raw_memory_graph"] is False
    assert result["status_json_written"] is False
    assert result["acceleration_report_edited"] is False
    assert len(result["passes"]) == 3
    assert result["passes"][0]["pass_name"] == "implementation"
    assert result["passes"][1]["pass_name"] == "adversarial"
    assert result["passes"][2]["pass_name"] == "independent_break_attempts"
    assert set(HARD_BANS).issubset(set(result["passes"][0]["hard_bans"]))
    for p in result["passes"]:
        assert p["ok"] is True, p.get("findings")
        assert p.get("private_core_import_count", 0) == 0
