"""V12-E Evidence Reproducibility tests — fail-closed proof dimensions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_evidence_repro import (
    PROOF_DIMENSIONS,
    REPRO_SCHEMA,
    RISK_GATES_VERSION,
    ReproEnvelopeError,
    ReplayMismatchError,
    build_repro_envelope,
    resolve_version_pins,
    run_completed_simulated_lifecycle,
    verify_deterministic_replay,
    verify_repro_envelope,
)
from backend.nexus_evidence_repro.replay import build_seeded_evidence, simulated_ai_outputs
from backend.nexus_execution.cost_model import COST_MODEL_VERSION
from backend.nexus_checkpoint.constants import ENVELOPE_SCHEMA, ENVELOPE_SCHEMA_VERSION


def test_version_pins_bound(tmp_path: Path) -> None:
    # repo root is worktree; pins resolve against package parents.
    pins = resolve_version_pins(Path(__file__).resolve().parents[1])
    assert pins["cost_version"] == COST_MODEL_VERSION
    assert pins["risk_version"] == RISK_GATES_VERSION
    assert pins["checkpoint_version"]["schema"] == ENVELOPE_SCHEMA
    assert pins["checkpoint_version"]["schema_version"] == ENVELOPE_SCHEMA_VERSION
    assert pins["checkpoint_version_id"] == f"{ENVELOPE_SCHEMA}:{ENVELOPE_SCHEMA_VERSION}"
    assert pins["code_version"]
    assert pins["risk_gates_fingerprint"]
    assert len(pins["risk_gates_fingerprint"]) == 64


def test_completed_lifecycle_envelope_binds_all_dimensions(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    result = run_completed_simulated_lifecycle(
        tmp_path / "run",
        seed="unit-seed-1",
        repo_root=repo,
    )
    env = result["envelope"]
    assert env["schema"] == REPRO_SCHEMA
    assert env["terminal_status"] == "CLOSED"
    assert env["input_evidence_hashes"]["evidence_hashes"]
    assert env["code_version"]
    assert env["cost_version"] == COST_MODEL_VERSION
    assert env["risk_version"] == RISK_GATES_VERSION
    assert env["checkpoint_version_id"]
    assert env["ai_provider_model_identifiers"]
    for entry in env["ai_provider_model_identifiers"]:
        assert entry["provider"]
        assert entry["model"]
    assert env["classification_provenance"]["classification_label"] == (
        "lifecycle_closed_simulated"
    )
    assert env["classification_provenance"]["learning_proven"] is False
    assert env["classification_provenance"]["fabricated_learning_proof"] is False
    assert env["simulated_only"] is True
    assert env["exchange_write"] is False
    assert env["demo_order"] is False
    assert env["learning_claim"] is False
    assert env["profitability_claim"] is False
    assert set(PROOF_DIMENSIONS) <= set(env["proof_dimensions"])
    verify = verify_repro_envelope(env)
    assert verify["ok"] is True


def test_deterministic_replay_match(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    a = run_completed_simulated_lifecycle(
        tmp_path / "a", seed="replay-seed", repo_root=repo
    )
    b = run_completed_simulated_lifecycle(
        tmp_path / "b", seed="replay-seed", repo_root=repo
    )
    out = verify_deterministic_replay(a, b)
    assert out["match"] is True
    assert out["envelope"]["deterministic_replay_result"]["match"] is True
    post = verify_repro_envelope(out["envelope"])
    assert post["dimensions"]["deterministic_replay_result"] is True


def test_seed_divergence_fails_replay(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    a = run_completed_simulated_lifecycle(
        tmp_path / "a", seed="seed-a", repo_root=repo
    )
    b = run_completed_simulated_lifecycle(
        tmp_path / "b", seed="seed-b", repo_root=repo
    )
    with pytest.raises(ReplayMismatchError):
        verify_deterministic_replay(a, b)


def test_evidence_hash_tamper_fail_closed(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    result = run_completed_simulated_lifecycle(
        tmp_path / "t", seed="tamper", repo_root=repo
    )
    decision = dict(result["decision"])
    decision["evidence_hashes"] = ["0" * 64] * len(decision["evidence_hashes"])
    with pytest.raises(ReproEnvelopeError):
        build_repro_envelope(
            decision,
            evidence_blobs=result["evidence_blobs"],
            versions=result["versions"],
        )


def test_missing_ai_model_fail_closed(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    result = run_completed_simulated_lifecycle(
        tmp_path / "m", seed="model-miss", repo_root=repo
    )
    decision = dict(result["decision"])
    decision["AI_reasoner_outputs"] = [{"provider": "sim", "view": "x"}]
    decision["independent_critic_output"] = {"provider": "sim", "verdict": "pass"}
    with pytest.raises(ReproEnvelopeError, match="ai_model_empty"):
        build_repro_envelope(decision, versions=result["versions"])


def test_non_terminal_fail_closed(tmp_path: Path) -> None:
    pins = resolve_version_pins(Path(__file__).resolve().parents[1])
    ev = build_seeded_evidence("nt")
    reasoners, critic = simulated_ai_outputs("nt")
    decision = {
        "decision_id": "dec_nt",
        "candidate_id": "c",
        "decision_status": "MONITORING",
        "evidence_ids": ev["evidence_ids"],
        "evidence_hashes": ev["evidence_hashes"],
        "AI_reasoner_outputs": reasoners,
        "independent_critic_output": critic,
        "deterministic_risk_result": {
            "allowed": True,
            "authority": "backend.nexus_execution.risk_gates.evaluate_intent",
        },
        "transition_history": [],
        "rejection_reasons": [],
        "lesson_ids": [],
    }
    with pytest.raises(ReproEnvelopeError, match="decision_not_terminal"):
        build_repro_envelope(decision, versions=pins)


def test_hard_ban_flags_in_envelope(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    result = run_completed_simulated_lifecycle(
        tmp_path / "hb", seed="hardban", repo_root=repo
    )
    raw = json.dumps(result["envelope"])
    assert "profit" not in raw.lower() or result["envelope"]["profitability_claim"] is False
    assert result["envelope"]["learning_claim"] is False
    assert result["exchange_write_attempt_count"] == 0
