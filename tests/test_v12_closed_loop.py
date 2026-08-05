"""Focused tests for V12-A founder-private closed-loop proof."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_system.closed_loop_v12 import (
    CANONICAL_PATH,
    FROZEN_SEED,
    PASS_STATUS,
    REQUIRED_ONTOLOGY,
    TARGET_COMPLETED_LIFECYCLES,
    build_historical_candidates,
    campaign_digest,
    run_v12_closed_loop_campaign,
)


def test_historical_candidates_deterministic():
    a = build_historical_candidates(count=20, seed=FROZEN_SEED)
    b = build_historical_candidates(count=20, seed=FROZEN_SEED)
    assert a == b
    assert len(a) == 20
    assert a[0]["historical"] is True
    assert a[0]["point_in_time_timestamp"].startswith("2024-")


def test_smoke_campaign_completes_and_zero_exchange_writes(tmp_path: Path):
    # Scale down for unit speed; full 1000 run is the readiness campaign.
    report = run_v12_closed_loop_campaign(
        root=tmp_path / "cl",
        candidate_count=12,
        seed=FROZEN_SEED,
        keep_root=True,
    )
    assert report["candidate_count"] == 12
    assert report["completed_lifecycle_count"] >= 7
    assert report["exchange_write_attempt_count"] == 0
    assert report["invariants"]["decorative_id_violations"] == 0
    assert report["lesson_gate_summary"]["policy_effect_allowed_count"] == 0
    for sample in report["sample_completed"]:
        assert all(s in sample["stages"] for s in CANONICAL_PATH)
        assert sample["ontology"] == list(REQUIRED_ONTOLOGY)
        assert sample["intent_id"]
        assert sample["position_id"]
        assert not str(sample["intent_id"]).startswith("intent_")
        assert not str(sample["position_id"]).startswith("pos_")


def test_digest_stable_across_timestamp():
    base = {
        "schema": "v12_founder_private_closed_loop",
        "seed": 1,
        "candidate_count": 10,
        "completed_lifecycle_count": 7,
        "rejected_count": 3,
        "blocked_count": 0,
        "error_count": 0,
        "exchange_write_attempt_count": 0,
        "canonical_path": list(CANONICAL_PATH),
        "ontology": list(REQUIRED_ONTOLOGY),
        "bridge_schema": "nexus_decision_execution_bridge_v11_1",
        "invariants": {"x": 1},
        "lesson_gate_summary": {"applied_count": 7},
        "created_at": "A",
    }
    other = dict(base)
    other["created_at"] = "B"
    assert campaign_digest(base) == campaign_digest(other)


def test_canonical_exports():
    assert PASS_STATUS.startswith("NEXUS_V12")
    assert TARGET_COMPLETED_LIFECYCLES == 500
    assert "MONITORING" in REQUIRED_ONTOLOGY
    assert "CLOSED" in REQUIRED_ONTOLOGY
