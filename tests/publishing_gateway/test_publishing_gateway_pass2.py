"""PUB-A Pass 2 adversarial hardening proofs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["NEXUS_PUBLISHING_ENV"] = "LOCAL"

from backend.nexus_publishing_gateway.allowlist import serialize_allowlist  # noqa: E402
from backend.nexus_publishing_gateway.ast_guard import (  # noqa: E402
    assert_no_private_imports,
    run_ast_mutation_kills,
    scan_forbidden_imports,
)
from backend.nexus_publishing_gateway.deny_traps import (  # noqa: E402
    find_denied_fields,
    normalize_field_name,
)
from backend.nexus_publishing_gateway.exceptions import (  # noqa: E402
    DenyTrapError,
    EnvironmentGuardError,
)
from backend.nexus_publishing_gateway.gateway import publish_intelligence  # noqa: E402
from backend.nexus_publishing_gateway.side_channel import SAFE_PUBLIC_SEED  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "backend" / "nexus_publishing_gateway"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("strategyId", "strategy_id"),
        ("strategy_id", "strategy_id"),
        ("apiKey", "api_key"),
        ("APIKey", "api_key"),
        ("walletAddress", "wallet_address"),
        ("executionRoute", "execution_route"),
        ("marketState", "market_state"),
        ("lesson-id", "lesson_id"),
    ],
)
def test_pass2_normalize_camel_and_kebab(raw: str, expected: str):
    assert normalize_field_name(raw) == expected


def test_pass2_deny_camelcase_strategy_id():
    hits = find_denied_fields({"strategyId": "S-9", "marketState": "OPEN"})
    assert "strategy_id" in hits
    with pytest.raises(DenyTrapError):
        publish_intelligence(
            {**SAFE_PUBLIC_SEED, "strategyId": "S-9"},
            environment="LOCAL",
        )


def test_pass2_allowlist_accepts_camelcase_public_fields():
    out = serialize_allowlist(
        {
            "marketState": "OPEN",
            "thesisStatus": "ACTIVE",
            "dataFreshness": "FRESH",
            "mysteryField": 1,
        }
    )
    assert out["market_state"] == "OPEN"
    assert out["thesis_status"] == "ACTIVE"
    assert out["data_freshness"] == "FRESH"
    assert "mystery_field" not in out


def test_pass2_no_false_positive_on_order_value_text():
    """Short deny tokens must not trip on benign public string values."""
    payload = {
        **SAFE_PUBLIC_SEED,
        "evidence_summary": "awaiting market order flow review",
        "alert_message": "no route change required",
    }
    # Strip keys not in allowlist seed shape — alert_message alone is allowed.
    safe = {
        "market_state": "OPEN",
        "market_timestamp": SAFE_PUBLIC_SEED["market_timestamp"],
        "data_freshness": "FRESH",
        "data_completeness": "COMPLETE",
        "evidence_summary": "awaiting market order flow review",
        "thesis_status": "ACTIVE",
        "confidence_calibration": 0.5,
        "decision_state": "HOLD",
        "outcome_review_classification": "PENDING",
        "system_availability": "AVAILABLE",
        "risk_alerts": SAFE_PUBLIC_SEED["risk_alerts"],
        "contradicting_evidence": SAFE_PUBLIC_SEED["contradicting_evidence"],
    }
    hits = find_denied_fields(safe)
    assert "order" not in hits
    assert "route" not in hits
    out = publish_intelligence(safe, environment="LOCAL")
    assert out["payload"]["evidence_summary"].startswith("awaiting market")


def test_pass2_production_env_blocked_even_if_requested():
    with pytest.raises(EnvironmentGuardError):
        publish_intelligence(SAFE_PUBLIC_SEED, environment="PRODUCTION")


def test_pass2_ast_blocks_dynamic_imports_and_kills_mutants():
    report = scan_forbidden_imports(PKG)
    assert report["violation_count"] == 0
    assert report["dynamic_import_count"] == 0
    assert_no_private_imports(PKG)
    result = run_ast_mutation_kills(source_path=PKG / "gateway.py")
    assert result["passed"] is True
    assert result["survivors"] == 0
    assert result["killed"] >= 4
    assert result["semantic_dual_bypass"]["would_leak"] is True


def test_pass2_nested_private_under_public_key_denied():
    dirty = {
        **SAFE_PUBLIC_SEED,
        "evidence_summary": {"text": "x", "strategy_parameters": {"w": 1}},
    }
    with pytest.raises(DenyTrapError):
        publish_intelligence(dirty, environment="LOCAL")
