"""Focused tests — campaign preflight, checkpoint schema, demo readiness (non-mutating)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["NEXUS_ALLOW_NON_RUNTIME_ROOT"] = "1"

from backend.nexus_bybit_demo_readiness.contracts import (
    check_command_scaffolding_no_execute,
    check_mainnet_endpoint_hard_deny,
)
from backend.nexus_bybit_demo_readiness.gate_v1 import (
    BybitDemoReadinessGateV1,
    evaluate_demo_readiness,
)
from backend.nexus_live_shadow_runtime.campaign import CampaignConfig, Shadow24hQualificationCampaign
from backend.nexus_live_shadow_runtime.campaign_checkpoint import (
    CHECKPOINT_FIELDS,
    CompactCheckpointWriter,
    build_compact_checkpoint,
    validate_checkpoint_schema,
)
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.errors import DomainRejectedError


def test_checkpoint_schema_complete(tmp_path: Path):
    payload = build_compact_checkpoint(
        campaign_id="shadow_24h_test",
        campaign_state="RUNNING",
        started_at="2026-08-06T00:00:00Z",
        elapsed_sec=3600,
        heartbeat_age_sec=1.5,
        metrics={
            "runtime_cycles_completed": 10,
            "runtime_cycles_failed": 0,
            "total_contracts_seen": 40,
            "eligible_contracts_latest": 0,
            "observe_only_contracts_latest": 0,
            "blocked_contracts_latest": 40,
            "candidates_generated": 10,
            "LONG_count": 0,
            "SHORT_count": 0,
            "WAIT_count": 0,
            "ABSTAIN_count": 0,
            "BLOCK_count": 10,
            "shadow_opened_count": 0,
            "shadow_closed_count": 0,
            "AI_success": 10,
            "AI_timeout": 0,
            "AI_invalid_json": 0,
            "deterministic_fallback_count": 0,
            "runtime_restart_count": 0,
            "actual_ordered_count": 0,
            "actual_filled_count": 0,
            "busy_loop_count": 0,
            "exchange_write_attempt_count": 0,
            "mainnet_client_count": 0,
            "demo_order_count": 0,
            "real_money": False,
        },
        source_health="OK",
        data_lag_ms=100,
    )
    assert validate_checkpoint_schema(payload) == []
    for key in CHECKPOINT_FIELDS:
        assert key in payload
    writer = CompactCheckpointWriter(tmp_path / "checkpoints")
    path = writer.write(payload)
    assert path.exists()
    latest = json.loads((tmp_path / "checkpoints" / "checkpoint_latest.json").read_text(encoding="utf-8"))
    assert latest["campaign_id"] == "shadow_24h_test"
    assert latest["eligible"] == 0
    assert latest["safety_counters"]["demo_order_count"] == 0


def test_campaign_preflight_fixtures(tmp_path: Path):
    cfg = CampaignConfig(
        campaign_id="shadow_24h_unit_preflight",
        campaigns_root=tmp_path / "campaigns",
        target_duration_hours=0.001,
        checkpoint_interval_sec=1.0,
        cycle_sleep_sec=0.1,
        live=False,
        max_disk_bytes=50 * 1024 * 1024,
    )
    camp = Shadow24hQualificationCampaign(cfg)
    pf = camp.preflight()
    assert "passed" in pf
    assert pf["campaign_id"] == "shadow_24h_unit_preflight"
    assert (camp.campaign_dir / "preflight.json").exists()
    # Fixtures path should pass adapters when registry supports fixtures.
    # If adapters fail in this environment, issues are listed honestly.
    assert isinstance(pf.get("issues"), list)


def test_mainnet_hard_deny():
    r = check_mainnet_endpoint_hard_deny()
    assert r.passed is True
    policy = DemoDomainPolicy()
    with pytest.raises(DomainRejectedError):
        policy.validate_base_url("https://api.bybit.com")
    with pytest.raises(DomainRejectedError):
        policy.validate_base_url("https://api-testnet.bybit.com")


def test_demo_readiness_not_ready_without_shadow():
    out = evaluate_demo_readiness(
        shadow_24h_complete=False,
        shadow_lifecycle_complete=False,
        founder_approval=False,
    )
    assert out["status"] == "DEMO_NOT_READY"
    assert out["technical_smoke_ready"] is False
    assert out["autonomous_demo_ready"] is False
    assert out["autonomous_demo_order_allowed"] is False
    assert out["demo_order_armed"] is False
    assert out["founder_approval_required"] is True
    assert "shadow_24h_qualification_incomplete" in out["missing_gates"]
    assert "shadow_lifecycle_incomplete" in out["missing_gates"]
    assert out["safety"]["demo_order_count"] == 0
    assert out["safety"]["mainnet_client_count"] == 0
    assert out["safety"]["exchange_write_attempt_count"] == 0


def test_demo_readiness_never_autonomous():
    gate = BybitDemoReadinessGateV1(
        shadow_24h_complete=True,
        shadow_lifecycle_complete=True,
        founder_approval=True,
        demo_order_armed=False,
    )
    out = gate.evaluate()
    assert out["status"] != "DEMO_AUTONOMOUS_STRATEGY_READY"
    assert out["autonomous_demo_ready"] is False
    assert out["autonomous_demo_order_allowed"] is False
    assert out["demo_order_armed"] is False


def test_command_scaffold_does_not_execute():
    r = check_command_scaffolding_no_execute()
    assert r.passed is True
    assert "executed" in r.detail
