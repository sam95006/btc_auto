"""Phase 6.5 tests — funnel, feature seed, entitlements, shadow risk, stream, routing."""
from __future__ import annotations

import os

import pytest


def test_feature_seed_nonzero_definitions():
    import backend.nexus_research.features.registry as reg_mod
    from backend.nexus_research.features.feature_seed import seed_default_feature_definitions

    reg_mod._REGISTRY = None  # noqa: SLF001
    import backend.nexus_research.features.feature_seed as seed_mod

    seed_mod._SEEDED = False  # noqa: SLF001
    result = seed_default_feature_definitions(force=True, registry=reg_mod.get_feature_registry())
    registry = reg_mod.get_feature_registry()
    defs = registry.list_definitions()
    assert result["count"] > 0
    assert len(defs) >= 85
    names = {d.name for d in defs}
    assert "rsi_14" in names
    assert "funding_rate" in names
    assert "cvd" in names
    # Phase 6.5 features must not flip production usage
    for d in defs:
        assert "used_by_production=false" in (d.tags or []) or d.namespace == "SHADOW"
        if "used_by_shadow=true" in (d.tags or []):
            assert "used_by_production=false" in (d.tags or [])


def test_feature_seed_idempotent_three_boots():
    import backend.nexus_research.features.registry as reg_mod
    import backend.nexus_research.features.feature_seed as seed_mod
    from backend.nexus_research.features.feature_seed import seed_default_feature_definitions

    reg_mod._REGISTRY = None  # noqa: SLF001
    seed_mod._SEEDED = False  # noqa: SLF001
    b1 = seed_default_feature_definitions(force=True)["count"]
    seed_mod._SEEDED = False  # noqa: SLF001
    b2 = seed_default_feature_definitions(force=True)["count"]
    seed_mod._SEEDED = False  # noqa: SLF001
    b3 = seed_default_feature_definitions(force=True)["count"]
    assert b1 == b2 == b3
    assert b1 >= 85


def test_decision_funnel_shape():
    from backend.nexus_research.decision_funnel import build_decision_funnel, classify_block_reason

    assert classify_block_reason("Risk Critic blocked: spread too wide") == "RISK_CRITIC_REJECT"
    assert classify_block_reason("spread too wide for entry") == "SPREAD_TOO_WIDE"
    body = build_decision_funnel(window_hours=1.0)
    assert body["ok"] is True
    for key in (
        "candidateCount", "decisionCount", "riskPassCount", "riskBlockCount",
        "orderCount", "blockReasonCounts", "zeroOrderDiagnosis",
    ):
        assert key in body
    # Diagnosis must be a code derived from counts, not prose placeholder
    assert isinstance(body["zeroOrderDiagnosis"], str)
    assert body["zeroOrderDiagnosis"]


def test_zero_order_diagnosis_codes():
    from backend.nexus_research.decision_funnel import _zero_order_diagnosis
    from collections import Counter

    assert _zero_order_diagnosis(
        candidate_count=5, case_count=0, role_complete_count=0, decision_count=0,
        risk_pass_count=0, risk_block_count=0, allocation_pass_count=0,
        entry_eligible_count=0, order_count=0, block_counts=Counter(), pending={},
    ) == "CASE_INGESTION_BLOCKED"
    assert _zero_order_diagnosis(
        candidate_count=5, case_count=3, role_complete_count=2, decision_count=0,
        risk_pass_count=0, risk_block_count=0, allocation_pass_count=0,
        entry_eligible_count=0, order_count=0, block_counts=Counter(), pending={},
    ) == "DECISION_ORCHESTRATOR_NOT_PRODUCING"
    assert _zero_order_diagnosis(
        candidate_count=5, case_count=3, role_complete_count=2, decision_count=4,
        risk_pass_count=0, risk_block_count=4, allocation_pass_count=0,
        entry_eligible_count=0, order_count=0,
        block_counts=Counter({"RISK_CRITIC_REJECT": 4}), pending={},
    ).startswith("ALL_DECISIONS_RISK_BLOCKED")


def test_decision_ready_status_helper():
    from backend.nexus_research.paper_controller import _decision_ready_for_paper

    assert _decision_ready_for_paper({"decisionStatus": "READY_FOR_SIMULATION"}) is True
    assert _decision_ready_for_paper({"status": "READY_FOR_SIMULATION"}) is True
    assert _decision_ready_for_paper({
        "decisionStatus": "READY_FOR_SIMULATION",
        "status": "READY_FOR_SIMULATION",
    }) is True
    # Conflict → fail-closed
    assert _decision_ready_for_paper({
        "decisionStatus": "READY_FOR_SIMULATION",
        "status": "RISK_BLOCKED",
    }) is False
    assert _decision_ready_for_paper({"decisionStatus": "RISK_BLOCKED"}) is False
    assert _decision_ready_for_paper({}) is False
    assert _decision_ready_for_paper({"decisionStatus": "INVALID"}) is False


def test_processed_decision_ids_dedupe():
    from backend.nexus_research.paper_controller import _load_processed_decision_ids

    class FakeStore:
        def query(self, table, limit=500):
            return [
                {"decisionId": "d1", "outcome": "GUARD_BLOCKED"},
                {"decisionId": "d1", "outcome": "GUARD_BLOCKED"},
                {"decisionId": "d2", "outcome": "SIM_SUBMITTED"},
            ]

    ids = _load_processed_decision_ids(FakeStore())
    assert ids == {"d1", "d2"}


def test_shadow_dynamic_risk_no_production_mutation():
    from backend.nexus_research.shadow_dynamic_risk import (
        PRODUCTION_LEVERAGE_CAP,
        PRODUCTION_MARGIN_CAP_USD,
        PRODUCTION_MAX_POSITIONS,
        propose_dynamic_risk,
        run_stress_comparison,
    )

    p = propose_dynamic_risk(
        symbol="BTCUSDT",
        direction="LONG",
        confidence=75,
        volatility=0.02,
        atr_pct=1.0,
        spread_bps=3,
        depth_usd=500_000,
        funding_rate=0.0001,
        oi_change_pct=0.2,
    )
    assert p["shadowOnly"] is True
    assert p["productionUnchanged"] is True
    assert p["orderCreated"] is False
    assert PRODUCTION_LEVERAGE_CAP == 3
    assert PRODUCTION_MARGIN_CAP_USD == 20.0
    assert PRODUCTION_MAX_POSITIONS == 1
    stress = run_stress_comparison(p)
    assert stress["orderCreated"] is False


def test_production_default_anonymous(monkeypatch):
    from backend.governance.entitlements import PlanTier, resolve_actor_context

    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    monkeypatch.delenv("NEXUS_ENTITLEMENT_TEST_MODE", raising=False)
    actor = resolve_actor_context()
    assert actor.tier == PlanTier.ANONYMOUS
    assert actor.identity_source == "production_default_anonymous"


def test_local_test_founder_only_in_test_mode(monkeypatch):
    from backend.governance.entitlements import PlanTier, has_entitlement, resolve_actor_context

    monkeypatch.delenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", raising=False)
    monkeypatch.delenv("ZEABUR", raising=False)
    monkeypatch.delenv("ZEABUR_SERVICE_ID", raising=False)
    monkeypatch.setenv("NEXUS_ENTITLEMENT_TEST_MODE", "1")
    monkeypatch.setenv("NEXUS_MEMBERSHIP_TIER", "FOUNDER")
    actor = resolve_actor_context()
    assert actor.tier == PlanTier.FOUNDER
    assert has_entitlement(actor, "founder.production_control") is True


def test_entitlement_anonymous_denies_founder():
    from backend.governance.entitlements import ActorContext, PlanTier, has_entitlement

    anon = ActorContext(tier=PlanTier.ANONYMOUS, roles=["ANONYMOUS"], identity_source="production_default_anonymous")
    assert has_entitlement(anon, "founder.autonomous_execution") is False
    assert has_entitlement(anon, "market.realtime") is False
    assert has_entitlement(anon, "market.delayed") is True


def test_entitlement_free_denies_founder():
    from backend.governance.entitlements import ActorContext, PlanTier, has_entitlement

    free = ActorContext(tier=PlanTier.FREE, roles=["MEMBER"], identity_source="local_test_mode")
    assert has_entitlement(free, "founder.autonomous_execution") is False
    assert has_entitlement(free, "market.realtime") is False
    assert has_entitlement(free, "market.delayed") is True


def test_founder_route_denies_production(monkeypatch):
    from flask import Flask

    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    monkeypatch.delenv("NEXUS_ENTITLEMENT_TEST_MODE", raising=False)
    app = Flask(__name__)
    from backend.api.founder_private_routes import register_founder_private_routes

    register_founder_private_routes(app)
    client = app.test_client()
    r = client.get("/api/nexus/founder/status")
    assert r.status_code == 403
    assert r.get_json()["realExecutionEnabled"] is False


def test_founder_route_rejects_fake_header(monkeypatch):
    from flask import Flask

    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    app = Flask(__name__)
    from backend.api.founder_private_routes import register_founder_private_routes

    register_founder_private_routes(app)
    client = app.test_client()
    r = client.get("/api/nexus/founder/status", headers={"X-Nexus-Role": "FOUNDER"})
    assert r.status_code == 403
    assert "fake_header" in r.get_json()["error"]


def test_founder_route_rejects_fake_query(monkeypatch):
    from flask import Flask

    monkeypatch.setenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", "1")
    app = Flask(__name__)
    from backend.api.founder_private_routes import register_founder_private_routes

    register_founder_private_routes(app)
    client = app.test_client()
    r = client.get("/api/nexus/founder/status?tier=FOUNDER")
    assert r.status_code == 403
    assert "fake_query" in r.get_json()["error"]


def test_founder_execution_always_denied(monkeypatch):
    from flask import Flask

    monkeypatch.delenv("NEXUS_FORCE_PRODUCTION_ENTITLEMENTS", raising=False)
    monkeypatch.setenv("NEXUS_ENTITLEMENT_TEST_MODE", "1")
    monkeypatch.setenv("NEXUS_MEMBERSHIP_TIER", "FOUNDER")
    monkeypatch.setenv("NEXUS_FOUNDER_ROUTES_ENABLED", "1")
    app = Flask(__name__)
    from backend.api.founder_private_routes import register_founder_private_routes

    register_founder_private_routes(app)
    client = app.test_client()
    r = client.post(
        "/api/nexus/founder/autonomous-execution",
        json={"researchOnly": True},
    )
    assert r.status_code == 403
    assert "execution" in r.get_json()["error"].lower()


def test_market_stream_honesty():
    from backend.market.stream.market_stream import get_stream_status, record_stream_event

    record_stream_event("BTCUSDT", "kline_update", {"time": 1, "close": 100})
    st = get_stream_status("BTCUSDT")
    assert st["symbol"] == "BTCUSDT"
    assert st["streamMode"] == "HYBRID_POLLING"
    assert st["liveStreamReady"] is False
    assert st["streamState"] in ("HYBRID_POLLING", "DEGRADED", "STALE", "UNAVAILABLE")


def test_msi_components_builder():
    from backend.nexus_research.features.feature_observation_feed import build_msi_components_from_scanner

    comp = build_msi_components_from_scanner()
    assert isinstance(comp, dict)
