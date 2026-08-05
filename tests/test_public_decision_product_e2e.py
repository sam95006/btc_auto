"""Tests for PUB2-A Public Decision Product E2E (customer-safe flow)."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_decision_product.constants import (
    EXCLUDED_STAGES,
    FLOW_STAGE_IDS,
    FLOW_STAGE_LABELS,
    HARD_BANS,
)
from backend.nexus_public_decision_product.hard_bans import (
    HardBanViolation,
    refuse_customer_trading,
    refuse_exchange_write,
    refuse_fabricated_customers,
    refuse_private_core_exposure,
    refuse_status_json,
    run_three_passes,
)
from backend.nexus_public_decision_product.journey import (
    JourneyError,
    refuse_execution_stage,
    run_customer_journey,
)
from backend.nexus_public_decision_product.routes import register_public_decision_product_routes
from backend.nexus_public_decision_product.sanitize import (
    ForbiddenPayloadKeyError,
    assert_no_forbidden_keys,
)

ROOT = Path(__file__).resolve().parents[1]


def test_flow_covers_directive_order():
    assert list(FLOW_STAGE_LABELS) == [
        "Market Observation",
        "Public Evidence",
        "Counter Evidence",
        "Risk Conditions",
        "Public Decision Object",
        "Thesis Monitor",
        "Outcome Review",
        "Decision Memory",
    ]
    assert len(FLOW_STAGE_IDS) == 8
    assert "execution" not in FLOW_STAGE_IDS
    assert set(EXCLUDED_STAGES).isdisjoint(set(FLOW_STAGE_IDS))


def test_customer_journey_e2e_happy_path():
    result = run_customer_journey()
    assert result["ok"] is True
    assert result["stage_count"] == 8
    assert result["execution_controls"] is False
    assert result["customer_trading"] is False
    assert result["exchange_api_used"] is False
    assert result["private_core_imported"] is False
    assert result["fabricated_customers"] is False
    assert result["fabricated_metrics"] is False
    assert result["source"] == "public_decision_cloud_staging_fixtures"
    stage_ids = [s["stage_id"] for s in result["stages"]]
    assert stage_ids == list(FLOW_STAGE_IDS)
    for stage in result["stages"]:
        assert stage.get("places_orders") is not True
        assert stage.get("execution_controls") in (None, False)
        assert stage.get("read_only") is True


def test_journey_rejects_unknown_decision():
    with pytest.raises(JourneyError):
        run_customer_journey(decision_id="dec_does_not_exist_xyz")


def test_refuse_execution_stages():
    for banned in ("execution", "order_placement", "demo_orders", "shadow_orders", "mainnet_trading"):
        with pytest.raises(JourneyError):
            refuse_execution_stage(banned)


def test_sanitize_blocks_secrets_and_fabrications():
    with pytest.raises(ForbiddenPayloadKeyError):
        assert_no_forbidden_keys({"api_key": "x"})
    with pytest.raises(ForbiddenPayloadKeyError):
        assert_no_forbidden_keys({"paid_pilot_count": 1})
    with pytest.raises(ForbiddenPayloadKeyError):
        assert_no_forbidden_keys({"fabricated_customer": "x"})


def test_hard_ban_refusers():
    with pytest.raises(HardBanViolation):
        refuse_customer_trading()
    with pytest.raises(HardBanViolation):
        refuse_exchange_write()
    with pytest.raises(HardBanViolation):
        refuse_private_core_exposure()
    with pytest.raises(HardBanViolation):
        refuse_fabricated_customers()
    with pytest.raises(HardBanViolation):
        refuse_status_json()


def test_three_passes():
    result = run_three_passes(ROOT)
    assert result["pass_count"] == 3
    assert result["ok"] is True
    assert result["hard_bans_intact"] is True
    assert result["execution_controls"] is False
    assert result["fabricated_customers"] is False
    assert len(result["passes"]) == 3
    assert result["passes"][0]["pass_name"] == "implementation"
    assert result["passes"][1]["pass_name"] == "adversarial"
    assert result["passes"][2]["pass_name"] == "independent_break_attempts"
    assert set(HARD_BANS).issubset(set(result["passes"][0]["hard_bans"]))
    for p in result["passes"]:
        assert p["ok"] is True, p.get("findings")


def test_flask_routes_read_only():
    flask = pytest.importorskip("flask")
    app = flask.Flask("test_decision_product")
    register_public_decision_product_routes(app)
    client = app.test_client()

    meta = client.get("/api/public/decision-product/meta")
    assert meta.status_code == 200
    payload = meta.get_json()
    assert payload["read_only"] is True
    assert payload["execution_controls"] is False
    assert payload["flow_labels"][0] == "Market Observation"
    assert payload["flow_labels"][-1] == "Decision Memory"

    e2e = client.get("/api/public/decision-product/e2e")
    assert e2e.status_code == 200
    body = e2e.get_json()
    assert body["ok"] is True
    assert body["stage_count"] == 8
    assert e2e.headers.get("X-NEXUS-Execution-Controls") == "false"
    assert e2e.headers.get("X-NEXUS-Customer-Trading") == "false"

    passes = client.get("/api/public/decision-product/passes")
    assert passes.status_code == 200
    assert passes.get_json()["pass_count"] == 3
    assert passes.get_json()["ok"] is True

    banned = client.post("/api/public/decision-product/e2e", json={"x": 1})
    assert banned.status_code == 405
    assert banned.get_json()["execution_controls"] is False

    missing = client.get("/api/public/decision-product/e2e?decision_id=dec_missing")
    assert missing.status_code == 404


def test_no_status_json_in_owned_package():
    owned = ROOT / "backend" / "nexus_public_decision_product"
    hits = list(owned.rglob("*_status.json")) + list(owned.rglob("status.json"))
    assert hits == []


def test_hard_bans_include_core_directives():
    required = {
        "no_customer_trading",
        "no_exchange_write",
        "no_demo_orders",
        "no_shadow_orders",
        "no_mainnet",
        "no_private_core_exposure",
        "no_execution_controls",
        "no_fabricated_customers",
        "no_fabricated_metrics",
        "no_human_facing_status_json",
        "no_pr26_pr27_merge",
    }
    assert required.issubset(set(HARD_BANS))
