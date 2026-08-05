"""PUB-A Intelligence Publishing Gateway — Pass-1 proofs."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_LIVE_BILLING", None)
os.environ["NEXUS_PUBLISHING_ENV"] = "LOCAL"

from backend.nexus_publishing_gateway.aggregation import (  # noqa: E402
    apply_public_aggregations,
    bucket_confidence,
    enforce_aggregation_threshold,
)
from backend.nexus_publishing_gateway.allowlist import serialize_allowlist  # noqa: E402
from backend.nexus_publishing_gateway.ast_guard import (  # noqa: E402
    assert_no_private_imports,
    run_ast_mutation_kills,
    scan_forbidden_imports,
)
from backend.nexus_publishing_gateway.constants import (  # noqa: E402
    ALLOWED_PUBLIC_FIELDS,
    DENIED_PRIVATE_FIELDS,
    HARD_BANS,
    SCHEMA,
)
from backend.nexus_publishing_gateway.deny_traps import (  # noqa: E402
    assert_no_denied_fields,
    find_denied_fields,
)
from backend.nexus_publishing_gateway.environment import (  # noqa: E402
    assert_local_or_staging,
)
from backend.nexus_publishing_gateway.exceptions import (  # noqa: E402
    AggregationThresholdError,
    DenyTrapError,
    EnvironmentGuardError,
    SchemaVersionError,
)
from backend.nexus_publishing_gateway.gateway import (  # noqa: E402
    hard_ban_inventory,
    publish_intelligence,
)
from backend.nexus_publishing_gateway.redaction import REDACTED, redact_payload  # noqa: E402
from backend.nexus_publishing_gateway.schema import (  # noqa: E402
    assert_schema_version,
    wrap_public_envelope,
)
from backend.nexus_publishing_gateway.side_channel import (  # noqa: E402
    SAFE_PUBLIC_SEED,
    run_side_channel_suite,
)

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "backend" / "nexus_publishing_gateway"


def test_schema_versioning_and_envelope():
    assert assert_schema_version(SCHEMA) == SCHEMA
    with pytest.raises(SchemaVersionError):
        assert_schema_version("private.core.v99")
    env = wrap_public_envelope({"market_state": "OPEN"}, environment="LOCAL")
    assert env["schema_version"] == SCHEMA
    assert env["environment"] == "LOCAL"
    assert "lineage_id" in env
    assert "published_at" in env


def test_allowlist_drops_unknown_and_keeps_public():
    raw = {
        "market_state": "OPEN",
        "mystery_private_blob": {"x": 1},
        "thesis_status": "ACTIVE",
        "not_allowed_field": "nope",
    }
    out = serialize_allowlist(raw)
    assert out["market_state"] == "OPEN"
    assert out["thesis_status"] == "ACTIVE"
    assert "mystery_private_blob" not in out
    assert "not_allowed_field" not in out
    assert set(out).issubset(ALLOWED_PUBLIC_FIELDS)


def test_deny_traps_block_forbidden_fields():
    for field in (
        "strategy_id",
        "strategy_parameters",
        "lesson_id",
        "prompt",
        "orders",
        "positions",
        "wallet_address",
        "api_secret",
        "execution_route",
        "private_risk",
    ):
        hits = find_denied_fields({field: "x", "market_state": "OPEN"})
        assert field in hits or any(field in h for h in hits)
        with pytest.raises(DenyTrapError):
            assert_no_denied_fields({field: "x"})


def test_publish_happy_path_public_dto():
    out = publish_intelligence(SAFE_PUBLIC_SEED, environment="LOCAL")
    assert out["schema_version"] == SCHEMA
    payload = out["payload"]
    assert payload["market_state"] == "OPEN"
    assert payload["confidence_band"] in {"LOW", "MEDIUM", "HIGH", "UNAVAILABLE"}
    blob = json.dumps(out)
    for banned in ("strategy_id", "lesson_id", "api_secret", "wallet_address", "order_id"):
        assert banned not in blob


def test_publish_denies_private_fields():
    dirty = {**SAFE_PUBLIC_SEED, "strategy_id": "S-1", "orders": [{"order_id": "o1"}]}
    with pytest.raises(DenyTrapError):
        publish_intelligence(dirty, environment="LOCAL")


def test_redaction_masks_secret_shaped_values():
    payload = {
        "market_state": "OPEN",
        "evidence_summary": "bearer sk-abcdefghijklmnopqrstuvwxyz012345",
    }
    red = redact_payload(payload)
    assert REDACTED in json.dumps(red)


def test_aggregation_thresholds():
    with pytest.raises(AggregationThresholdError):
        enforce_aggregation_threshold([1, 2], min_count=5, label="thin")
    assert len(enforce_aggregation_threshold([1, 2, 3, 4, 5], min_count=5)) == 5
    assert bucket_confidence(0.1) == "LOW"
    assert bucket_confidence(0.5) == "MEDIUM"
    assert bucket_confidence(0.9) == "HIGH"
    thin = apply_public_aggregations(
        {"risk_alerts": [{"alert_code": "A"}], "confidence_calibration": 0.8}
    )
    assert thin["risk_alerts"]["bucket"] == "SUPPRESSED_BELOW_THRESHOLD"
    assert thin["confidence_band"] == "HIGH"


def test_environment_guard_blocks_production():
    with pytest.raises(EnvironmentGuardError):
        assert_local_or_staging("PRODUCTION")
    assert assert_local_or_staging("LOCAL") == "LOCAL"
    assert assert_local_or_staging("STAGING") == "STAGING"


def test_hard_bans_inventory():
    inv = hard_ban_inventory()
    for ban in HARD_BANS:
        assert ban in inv["hard_bans"]
    assert inv["production_deploy"] is False
    assert inv["live_billing"] is False
    assert inv["exchange_write"] is False
    assert inv["PR26_merged"] is False
    assert inv["PR27_merged"] is False
    assert inv["read_only"] is True


def test_ast_no_private_imports():
    report = scan_forbidden_imports(PKG)
    assert report["violation_count"] == 0
    assert_no_private_imports(PKG)


def test_ast_mutation_kills():
    result = run_ast_mutation_kills(source_path=PKG / "gateway.py")
    assert result["survivors"] == 0
    assert result["passed"] is True
    assert result["killed"] >= 2


def test_side_channel_suite():
    suite = run_side_channel_suite()
    assert suite["passed"] is True
    assert suite["probe_count"] >= 3


def test_denied_field_set_covers_directive():
    required = {
        "strategy_id",
        "strategy_parameters",
        "lesson_id",
        "prompt",
        "orders",
        "positions",
        "wallet",
        "account",
        "api_key",
        "execution_route",
        "private_risk",
    }
    assert required.issubset(DENIED_PRIVATE_FIELDS)


def test_allowed_field_set_covers_directive():
    required = {
        "market_state",
        "market_timestamp",
        "data_freshness",
        "data_completeness",
        "evidence_summary",
        "contradicting_evidence",
        "risk_alerts",
        "thesis_status",
        "confidence_calibration",
        "decision_state",
        "outcome_review_classification",
        "system_availability",
    }
    assert required.issubset(ALLOWED_PUBLIC_FIELDS)
