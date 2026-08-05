"""Focused + adversarial tests for Decision Lifecycle Orchestrator V11.

Pass 1: contract, happy path, invalid transitions, evidence, idempotency, restart.
Pass 2: property, concurrency, evidence-loss, adversarial corrections.
"""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from backend.nexus_decision import (
    CANONICAL_STATES,
    DECISION_OBJECT_REQUIRED_FIELDS,
    DecisionLifecycleError,
    DecisionLifecycleOrchestrator,
    DecisionObject,
    InvalidTransitionError,
    SCHEMA_VERSION,
    VALID_TRANSITIONS,
)
from backend.nexus_decision.checkpoint import sanitize_checkpoint_payload
from backend.nexus_decision.evidence import (
    EvidenceValidationError,
    detect_evidence_loss,
    hash_evidence_blob,
    validate_evidence_completeness,
)
from backend.nexus_decision.state_machine import DecisionStateMachine


OWNED_PATHS = [
    "backend/nexus_decision",
    "tools/research/run_decision_lifecycle_v11.py",
    "tests/test_decision_lifecycle_v11.py",
    "artifacts/readiness/immutable/v11_decision_lifecycle",
]

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]


def _fresh_evidence(n: int = 2, age: float = 10.0) -> dict:
    blobs = {f"ev_{i}": f"blob-{i}-payload" for i in range(n)}
    ids = list(blobs.keys())
    hashes = [hash_evidence_blob(blobs[i]) for i in ids]
    return {
        "evidence_ids": ids,
        "evidence_hashes": hashes,
        "evidence_blobs": blobs,
        "data_freshness": {"age_seconds": age, "stale": False},
        "data_completeness": {
            "ratio": 1.0,
            "required_fields": ["mid", "spread", "ts"],
            "present_fields": ["mid", "spread", "ts"],
        },
    }


@pytest.fixture()
def orch(tmp_path: Path) -> DecisionLifecycleOrchestrator:
    return DecisionLifecycleOrchestrator(tmp_path)


def _observe(orch: DecisionLifecycleOrchestrator, key: str = "obs-1", **overrides):
    ev = _fresh_evidence()
    ev.update(overrides.pop("evidence", {}))
    return orch.observe(
        candidate_id=overrides.get("candidate_id", "cand_1"),
        market_context_id=overrides.get("market_context_id", "mctx_1"),
        point_in_time_timestamp=overrides.get("point_in_time_timestamp", "2026-08-05T00:00:00Z"),
        evidence_ids=ev["evidence_ids"],
        evidence_hashes=ev["evidence_hashes"],
        data_freshness=ev["data_freshness"],
        data_completeness=ev["data_completeness"],
        idempotency_key=key,
        evidence_blobs=ev.get("evidence_blobs"),
        decision_id=overrides.get("decision_id"),
    )


def _happy_to_closed(orch: DecisionLifecycleOrchestrator, key_prefix: str = "hp") -> str:
    out = _observe(orch, key=f"{key_prefix}-obs")
    did = out["decision"]["decision_id"]
    orch.understand(
        did,
        AI_reasoner_outputs=[{"provider": "sim", "view": "neutral"}],
        idempotency_key=f"{key_prefix}-u",
    )
    orch.challenge(
        did,
        independent_critic_output={"verdict": "pass", "score": 0.7},
        idempotency_key=f"{key_prefix}-c",
    )
    orch.decide(
        did,
        deterministic_risk_result={"allowed": True, "reasons": []},
        idempotency_key=f"{key_prefix}-d",
    )
    orch.record(did, idempotency_key=f"{key_prefix}-r")
    orch.monitor(did, exit=True, idempotency_key=f"{key_prefix}-m")
    orch.review(did, idempotency_key=f"{key_prefix}-rev")
    orch.calibrate(did, lesson_ids=["lesson_a"], idempotency_key=f"{key_prefix}-cal")
    orch.improve(did, idempotency_key=f"{key_prefix}-imp")
    return did


# ---------------------------------------------------------------------------
# Pass 1 — focused
# ---------------------------------------------------------------------------


def test_canonical_states_and_required_fields() -> None:
    required = {
        "OBSERVED",
        "UNDERSTANDING",
        "CHALLENGED",
        "RISK_REVIEWED",
        "APPROVED_SIMULATED",
        "REJECTED",
        "MONITORING",
        "EXITED",
        "UNDER_REVIEW",
        "CALIBRATED",
        "CLOSED",
        "BLOCKED_AMBIGUOUS",
    }
    assert set(CANONICAL_STATES) == required
    assert len(DECISION_OBJECT_REQUIRED_FIELDS) == 22
    assert SCHEMA_VERSION == "nexus_decision_object_v11"


def test_decision_object_has_all_required_fields(orch: DecisionLifecycleOrchestrator) -> None:
    out = _observe(orch)
    d = out["decision"]
    for field in DECISION_OBJECT_REQUIRED_FIELDS:
        assert field in d
    DecisionObject.from_dict(d)


def test_full_lifecycle_happy_path(orch: DecisionLifecycleOrchestrator) -> None:
    did = _happy_to_closed(orch)
    st = orch.get(did)
    assert st["state"] == "CLOSED"
    assert st["is_terminal"] is True
    d = st["decision"]
    assert d["intent_id"]
    assert d["position_id"]
    assert d["exit_id"]
    assert d["reflection_id"]
    assert "lesson_a" in d["lesson_ids"]
    assert len(d["ledger_event_ids"]) >= 5
    assert orch.order_attempt_count == 0
    assert orch.strategy_mutation_attempt_count == 0
    assert orch.exchange_write_attempt_count == 0


def test_reject_path(orch: DecisionLifecycleOrchestrator) -> None:
    out = _observe(orch, key="rej-obs")
    did = out["decision"]["decision_id"]
    orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="rej-u")
    orch.challenge(did, independent_critic_output={"verdict": "weak"}, idempotency_key="rej-c")
    decided = orch.decide(
        did,
        deterministic_risk_result={"allowed": False, "reasons": ["COST_DESTROYED"]},
        idempotency_key="rej-d",
    )
    assert decided["status"] == "REJECTED"
    assert "COST_DESTROYED" in decided["decision"]["rejection_reasons"]
    closed = orch.improve(did, idempotency_key="rej-close")
    assert closed["status"] == "CLOSED"


def test_invalid_transition_fail_closed(orch: DecisionLifecycleOrchestrator) -> None:
    out = _observe(orch, key="bad-obs")
    did = out["decision"]["decision_id"]
    with pytest.raises(DecisionLifecycleError):
        orch.record(did, idempotency_key="bad-rec")  # cannot skip to MONITORING
    assert orch.state_machine(did).state == "OBSERVED"
    with pytest.raises(DecisionLifecycleError):
        orch.improve(did, idempotency_key="bad-imp")
    with pytest.raises(InvalidTransitionError):
        orch.state_machine(did).transition(
            "NOT_A_STATE",
            stage="bogus",
            idempotency_key="bogus-key",
        )


def test_observe_rejects_stale_and_incomplete_evidence(orch: DecisionLifecycleOrchestrator) -> None:
    ev = _fresh_evidence(age=9999.0)
    with pytest.raises(DecisionLifecycleError):
        orch.observe(
            candidate_id="c",
            market_context_id="m",
            point_in_time_timestamp="2026-08-05T00:00:00Z",
            evidence_ids=ev["evidence_ids"],
            evidence_hashes=ev["evidence_hashes"],
            data_freshness=ev["data_freshness"],
            data_completeness=ev["data_completeness"],
            idempotency_key="stale-1",
            evidence_blobs=ev["evidence_blobs"],
        )
    ev2 = _fresh_evidence()
    ev2["data_completeness"]["ratio"] = 0.5
    with pytest.raises(DecisionLifecycleError):
        orch.observe(
            candidate_id="c",
            market_context_id="m",
            point_in_time_timestamp="2026-08-05T00:00:00Z",
            evidence_ids=ev2["evidence_ids"],
            evidence_hashes=ev2["evidence_hashes"],
            data_freshness=ev2["data_freshness"],
            data_completeness=ev2["data_completeness"],
            idempotency_key="inc-1",
            evidence_blobs=ev2["evidence_blobs"],
        )


def test_idempotent_observe(orch: DecisionLifecycleOrchestrator) -> None:
    a = _observe(orch, key="idem-obs")
    b = _observe(orch, key="idem-obs")
    assert b["duplicate"] is True
    assert a["decision"]["decision_id"] == b["decision"]["decision_id"]
    assert orch.status()["decision_count"] == 1


def test_idempotent_transition_replay(orch: DecisionLifecycleOrchestrator) -> None:
    out = _observe(orch, key="idem-t-obs")
    did = out["decision"]["decision_id"]
    orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="idem-t-u")
    again = orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="idem-t-u")
    assert again["status"] == "UNDERSTANDING"
    assert orch.state_machine(did).state == "UNDERSTANDING"
    hist = orch.state_machine(did).history()
    assert sum(1 for h in hist if h["idempotency_key"] == "idem-t-u") == 1


def test_checkpoint_and_restart_recovery(tmp_path: Path) -> None:
    orch = DecisionLifecycleOrchestrator(tmp_path)
    out = _observe(orch, key="rec-obs", decision_id="dec_recover_1")
    did = out["decision"]["decision_id"]
    orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="rec-u")
    orch.challenge(did, independent_critic_output={"verdict": "ok"}, idempotency_key="rec-c")
    orch.decide(did, deterministic_risk_result={"allowed": True}, idempotency_key="rec-d")
    assert orch.get(did)["state"] == "APPROVED_SIMULATED"

    # Simulate process restart: new orchestrator, same root.
    orch2 = DecisionLifecycleOrchestrator(tmp_path)
    recovered = orch2.recover(did)
    assert recovered["recovery_status"] == "RECOVERED"
    assert recovered["state"] == "APPROVED_SIMULATED"
    # Continue lifecycle after recovery.
    orch2.record(did, idempotency_key="rec-r")
    assert orch2.get(did)["state"] == "MONITORING"


def test_orders_and_strategy_mutation_forbidden(orch: DecisionLifecycleOrchestrator) -> None:
    _observe(orch, key="ban-obs")
    with pytest.raises(DecisionLifecycleError):
        orch.attempt_place_order(symbol="BTCUSDT", side="Buy")
    with pytest.raises(DecisionLifecycleError):
        orch.attempt_exchange_write("/v5/order/create")
    with pytest.raises(DecisionLifecycleError):
        orch.attempt_strategy_parameter_mutation({"leverage": 5, "stop_loss": 0.01})
    assert orch.order_attempt_count == 1
    assert orch.exchange_write_attempt_count == 1
    assert orch.strategy_mutation_attempt_count == 1


def test_ambiguous_decide_blocks(orch: DecisionLifecycleOrchestrator) -> None:
    out = _observe(orch, key="amb-obs")
    did = out["decision"]["decision_id"]
    orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="amb-u")
    orch.challenge(did, independent_critic_output={"verdict": "ok"}, idempotency_key="amb-c")
    blocked = orch.decide(
        did,
        deterministic_risk_result={"allowed": True, "ambiguous": True},
        idempotency_key="amb-d",
    )
    assert blocked["status"] == "BLOCKED_AMBIGUOUS"


def test_checkpoint_sanitizes_secrets() -> None:
    cleaned = sanitize_checkpoint_payload({"api_key": "LEAK", "decision_id": "x"})
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["decision_id"] == "x"


def test_secret_scan_owned_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    hits: list[str] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if not target.exists():
            continue
        files = (
            [p for p in target.rglob("*") if p.is_file()]
            if target.is_dir()
            else [target]
        )
        for path in files:
            if path.suffix.lower() not in {".py", ".json", ".md", ".yml", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(str(path.relative_to(root)))
                    break
    assert hits == [], f"secret_leak_count={len(hits)} hits={hits}"


# ---------------------------------------------------------------------------
# Pass 2 — adversarial / property / concurrency / evidence-loss
# ---------------------------------------------------------------------------


def test_property_transition_closure() -> None:
    """Every transition target and source must be a canonical state."""
    for src, targets in VALID_TRANSITIONS.items():
        assert src in CANONICAL_STATES
        for t in targets:
            assert t in CANONICAL_STATES
    # CLOSED is terminal.
    assert VALID_TRANSITIONS["CLOSED"] == frozenset()
    # Every non-terminal state can reach CLOSED (directly or via path).
    reachable_closed: set[str] = set()

    def dfs(state: str, seen: set[str]) -> bool:
        if state == "CLOSED":
            return True
        if state in seen:
            return False
        seen.add(state)
        return any(dfs(n, seen) for n in VALID_TRANSITIONS.get(state, frozenset()))

    for s in CANONICAL_STATES:
        if s == "CLOSED":
            reachable_closed.add(s)
            continue
        if dfs(s, set()):
            reachable_closed.add(s)
    assert reachable_closed == set(CANONICAL_STATES)


def test_property_random_invalid_pairs_fail(orch: DecisionLifecycleOrchestrator) -> None:
    out = _observe(orch, key="prop-obs")
    did = out["decision"]["decision_id"]
    sm = orch.state_machine(did)
    illegal = []
    for src in CANONICAL_STATES:
        for dst in CANONICAL_STATES:
            if dst not in VALID_TRANSITIONS.get(src, frozenset()) and src != dst:
                illegal.append((src, dst))
    # Sample a batch of illegal transitions from OBSERVED.
    samples = [p for p in illegal if p[0] == "OBSERVED"][:20]
    for i, (_src, dst) in enumerate(samples):
        with pytest.raises(InvalidTransitionError):
            sm.transition(dst, stage="fuzz", idempotency_key=f"fuzz-{i}-{dst}")
    assert sm.state == "OBSERVED"


def test_concurrency_parallel_observes_unique_keys(tmp_path: Path) -> None:
    orch = DecisionLifecycleOrchestrator(tmp_path)

    def worker(i: int) -> str:
        out = _observe(orch, key=f"conc-obs-{i}", decision_id=f"dec_conc_{i}")
        return out["decision"]["decision_id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(worker, range(40)))
    assert len(ids) == 40
    assert len(set(ids)) == 40
    assert orch.status()["decision_count"] == 40


def test_concurrency_idempotent_observe_race(tmp_path: Path) -> None:
    orch = DecisionLifecycleOrchestrator(tmp_path)
    results: list[dict] = []
    barrier = threading.Barrier(12)

    def worker() -> None:
        barrier.wait()
        results.append(_observe(orch, key="race-same-key"))

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 12
    decision_ids = {r["decision"]["decision_id"] for r in results}
    assert len(decision_ids) == 1
    assert orch.status()["decision_count"] == 1
    assert sum(1 for r in results if r.get("duplicate")) >= 11


def test_concurrency_parallel_stage_advances(tmp_path: Path) -> None:
    orch = DecisionLifecycleOrchestrator(tmp_path)
    out = _observe(orch, key="par-stage-obs")
    did = out["decision"]["decision_id"]
    errors: list[Exception] = []

    def try_understand(i: int) -> None:
        try:
            orch.understand(
                did,
                AI_reasoner_outputs=[{"v": i}],
                idempotency_key="par-stage-u",  # same key — idempotent
            )
        except Exception as exc:  # noqa: BLE001 — collect adversarial faults
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(try_understand, i) for i in range(20)]
        for f in as_completed(futs):
            f.result()
    assert errors == []
    assert orch.get(did)["state"] == "UNDERSTANDING"
    assert sum(1 for h in orch.state_machine(did).history() if h["idempotency_key"] == "par-stage-u") == 1


def test_evidence_loss_detected() -> None:
    losses = detect_evidence_loss(
        expected_ids=["a", "b"],
        expected_hashes=["0" * 64, "1" * 64],
        actual_ids=["a"],
        actual_hashes=["0" * 64],
    )
    assert any("missing_id:b" in x for x in losses)
    assert any("count_drop" in x for x in losses)


def test_evidence_hash_mismatch_fail_closed(orch: DecisionLifecycleOrchestrator) -> None:
    ev = _fresh_evidence()
    bad_hashes = list(ev["evidence_hashes"])
    bad_hashes[0] = "f" * 64
    with pytest.raises(DecisionLifecycleError):
        orch.observe(
            candidate_id="c",
            market_context_id="m",
            point_in_time_timestamp="2026-08-05T00:00:00Z",
            evidence_ids=ev["evidence_ids"],
            evidence_hashes=bad_hashes,
            data_freshness=ev["data_freshness"],
            data_completeness=ev["data_completeness"],
            idempotency_key="hash-bad",
            evidence_blobs=ev["evidence_blobs"],
        )


def test_evidence_loss_after_mutate_blocks_advance(orch: DecisionLifecycleOrchestrator) -> None:
    out = _observe(orch, key="eloss-obs")
    did = out["decision"]["decision_id"]
    # Adversarial: corrupt in-memory evidence after observe.
    obj = orch._decisions[did]  # noqa: SLF001 — intentional adversarial access
    obj.evidence_ids.pop()
    with pytest.raises(DecisionLifecycleError):
        orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="eloss-u")


def test_evidence_hash_tamper_binding_fail_closed(orch: DecisionLifecycleOrchestrator) -> None:
    """Pass-2 correction: hash rewrite without id drop must still fail closed."""
    out = _observe(orch, key="bind-obs")
    did = out["decision"]["decision_id"]
    obj = orch._decisions[did]  # noqa: SLF001
    obj.evidence_hashes[0] = "a" * 64
    with pytest.raises(DecisionLifecycleError, match="binding_hash_mismatch"):
        orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="bind-u")
    assert orch.state_machine(did).state == "OBSERVED"


def test_recover_rejects_tampered_checkpoint_evidence(tmp_path: Path) -> None:
    """Pass-2: checkpoint evidence rewrite is detected as evidence loss on recover path."""
    orch = DecisionLifecycleOrchestrator(tmp_path)
    out = _observe(orch, key="ckpt-tamper-obs", decision_id="dec_tamper_1")
    did = out["decision"]["decision_id"]
    orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="ckpt-tamper-u")
    latest = tmp_path / "checkpoints" / f"{did}.checkpoint.latest.json"
    payload = json.loads(latest.read_text(encoding="utf-8"))
    # Tamper hashes while keeping original binding hash → binding mismatch on recover.
    payload["decision"]["evidence_hashes"] = ["b" * 64] * len(payload["decision"]["evidence_hashes"])
    # Invalidate stored sha so verify fails closed (no silent load of tampered bytes).
    payload["checkpoint_sha256"] = "0" * 64
    latest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    orch2 = DecisionLifecycleOrchestrator(tmp_path)
    with pytest.raises(DecisionLifecycleError):
        orch2.recover(did)


def test_recover_binding_mismatch_inside_valid_envelope(tmp_path: Path) -> None:
    """Pass-2 correction: even if envelope hash is rewritten to match, binding must hold."""
    from backend.nexus_decision.checkpoint import DecisionCheckpointStore

    orch = DecisionLifecycleOrchestrator(tmp_path)
    out = _observe(orch, key="bind-rec-obs", decision_id="dec_bind_rec")
    did = out["decision"]["decision_id"]
    orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="bind-rec-u")
    store = DecisionCheckpointStore(tmp_path / "checkpoints")
    payload = store.load_latest(did)
    assert payload is not None
    # Mutate decision evidence but preserve stale binding hash, then re-seal checkpoint.
    decision = payload["decision"]
    binding = decision["evidence_binding_hash"]
    decision["evidence_hashes"] = ["c" * 64] * len(decision["evidence_hashes"])
    decision["evidence_binding_hash"] = binding
    payload["decision"] = decision
    # Re-save via store to get a valid envelope hash around tampered content.
    store._seq = int(payload.get("checkpoint_seq") or 0)  # noqa: SLF001
    store.save(did, {"schema": payload.get("schema"), "decision": decision, "state": "UNDERSTANDING", "transition_history": payload.get("transition_history")})
    orch2 = DecisionLifecycleOrchestrator(tmp_path)
    with pytest.raises(DecisionLifecycleError, match="binding_hash_mismatch"):
        orch2.recover(did)


def test_restart_after_partial_lifecycle_preserves_ledger(tmp_path: Path) -> None:
    orch = DecisionLifecycleOrchestrator(tmp_path)
    out = _observe(orch, key="led-obs", decision_id="dec_led_1")
    did = out["decision"]["decision_id"]
    orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="led-u")
    seq_before = orch.status()["ledger_sequence"]
    assert seq_before >= 2

    orch2 = DecisionLifecycleOrchestrator(tmp_path)
    orch2.recover(did)
    # Re-append with same key must be duplicate-ignored (ledger bootstrapped).
    from backend.nexus_decision.ledger_link import DecisionLedgerLink

    link = DecisionLedgerLink(tmp_path / "ledger")
    dup = link.append(
        decision_id=did,
        event_type="DECISION_UNDERSTANDING",
        payload={"decision_id": did, "status": "UNDERSTANDING", "reasoner_count": 1},
        idempotency_key="led-u",
    )
    assert dup["duplicate"] is True


def test_idempotency_conflict_on_different_target(orch: DecisionLifecycleOrchestrator) -> None:
    sm = DecisionStateMachine(initial="OBSERVED")
    sm.transition("UNDERSTANDING", stage="u", idempotency_key="same")
    with pytest.raises(InvalidTransitionError):
        sm.transition("REJECTED", stage="u", idempotency_key="same")


def test_blocked_then_close(orch: DecisionLifecycleOrchestrator) -> None:
    out = _observe(orch, key="blk-obs")
    did = out["decision"]["decision_id"]
    orch.block_ambiguous(did, reason="manual_ambiguous", idempotency_key="blk-1")
    assert orch.get(did)["state"] == "BLOCKED_AMBIGUOUS"
    orch.improve(did, idempotency_key="blk-close")
    assert orch.get(did)["state"] == "CLOSED"


def test_critic_ambiguous_blocks(orch: DecisionLifecycleOrchestrator) -> None:
    out = _observe(orch, key="crit-obs")
    did = out["decision"]["decision_id"]
    orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="crit-u")
    blocked = orch.challenge(
        did,
        independent_critic_output={"ambiguous": True, "verdict": "unclear"},
        idempotency_key="crit-c",
    )
    assert blocked["status"] == "BLOCKED_AMBIGUOUS"


def test_evidence_validation_unit() -> None:
    with pytest.raises(EvidenceValidationError):
        validate_evidence_completeness(
            evidence_ids=[],
            evidence_hashes=[],
            data_freshness={"age_seconds": 1},
            data_completeness={"ratio": 1.0},
        )
    ok = validate_evidence_completeness(
        evidence_ids=["a"],
        evidence_hashes=["a" * 64],
        data_freshness={"age_seconds": 1.0, "stale": False},
        data_completeness={"ratio": 1.0, "required_fields": [], "present_fields": []},
    )
    assert ok["ok"] is True


def test_stages_surface_complete(orch: DecisionLifecycleOrchestrator) -> None:
    required = {
        "observe",
        "understand",
        "challenge",
        "decide",
        "record",
        "monitor",
        "review",
        "calibrate",
        "improve",
    }
    assert set(orch.STAGES) == required
    for name in required:
        assert callable(getattr(orch, name))
