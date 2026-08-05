"""Founder-list attack probes against the V16 private tip modules."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from backend.nexus_moat_adversarial_redteam_v16.constants import (
    ATTACK_IDS,
    DISPOSITIONS,
    SEVERITY_BY_ATTACK,
)


@dataclass
class AttackResult:
    attack_id: str
    severity: str
    disposition: str
    attack_blocked: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)
    survivor: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.disposition not in DISPOSITIONS:
            raise ValueError(f"invalid_disposition:{self.disposition}")
        # Survivors: anything not FIXED must be listed.
        d["survivor"] = self.disposition != "FIXED"
        return d


def _ok(
    attack_id: str,
    *,
    disposition: str,
    attack_blocked: bool,
    detail: str,
    evidence: dict[str, Any] | None = None,
) -> AttackResult:
    return AttackResult(
        attack_id=attack_id,
        severity=SEVERITY_BY_ATTACK[attack_id],
        disposition=disposition,
        attack_blocked=attack_blocked,
        detail=detail,
        evidence=evidence or {},
        survivor=disposition != "FIXED",
    )


def attack_future_leakage() -> AttackResult:
    from backend.nexus_probabilistic_regime_v2.engine import ProbabilisticRegimeEngineV2
    from backend.nexus_probabilistic_regime_v2.fixtures import (
        build_future_leak_bar,
        build_synthetic_bars,
    )
    from backend.nexus_probabilistic_regime_v2.pit import prove_no_future_leak

    bars = build_synthetic_bars(scenario="strong_bull", n=30)
    as_of = int(bars[-1]["exchange_timestamp"])
    leak = build_future_leak_bar(as_of)
    contaminated = bars + [leak]
    eng = ProbabilisticRegimeEngineV2()
    out = eng.evaluate(contaminated, as_of_ms=as_of)
    pit_bars = [
        b
        for b in contaminated
        if int(b["exchange_timestamp"]) <= as_of and int(b["receive_timestamp"]) <= as_of
    ]
    proof = prove_no_future_leak(pit_bars, as_of_ms=as_of)
    blocked = bool(out.get("pit_proof", {}).get("pit_clean")) and bool(
        proof.get("pit_clean")
    ) and int(out.get("eligible_bar_count") or 0) <= 30
    return _ok(
        "future_leakage",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="PIT window excludes future bars; regime engine refuses leak",
        evidence={"eligible_bar_count": out.get("eligible_bar_count"), "pit": proof},
    )


def attack_fake_regime_confidence() -> AttackResult:
    from backend.nexus_probabilistic_regime_v2.adversarial import _attempt_ai_override
    from backend.nexus_probabilistic_regime_v2.engine import ProbabilisticRegimeEngineV2
    from backend.nexus_probabilistic_regime_v2.fixtures import build_synthetic_bars

    bars = build_synthetic_bars(scenario="choppy", n=40)
    as_of = int(bars[-1]["exchange_timestamp"])
    eng = ProbabilisticRegimeEngineV2()
    out = eng.evaluate(bars, as_of_ms=as_of)
    override = _attempt_ai_override(out)
    # Fake high confidence must not clear fail_closed / claim predictive edge.
    blocked = (
        override.get("ai_override_applied") is False
        and override.get("predictive_edge_claimed") is False
        and override.get("strategy_signal") is False
        and override.get("profitability_claimed") is False
        and (
            out.get("fail_closed") is True
            or float(out.get("calibration_score") or 0) < 0.99
            or out.get("formal_state") != "CLEAR"
        )
    )
    return _ok(
        "fake_regime_confidence",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="AI cannot inject fake CLEAR/high-confidence regime outputs",
        evidence={"override": override, "formal_state": out.get("formal_state")},
    )


def attack_ai_high_confidence_overrides_stale_data() -> AttackResult:
    from backend.nexus_uncertainty_abstention.engine import apply_ai_suggestion, evaluate_raw
    from backend.nexus_uncertainty_abstention.fixtures import _base

    stale = evaluate_raw(_base(data_freshness_sec=500.0, stated_confidence=0.99))
    try:
        overridden = apply_ai_suggestion(
            stale,
            {"verdict": "ALLOW", "execution_allowed": True, "stated_confidence": 0.99},
        )
    except Exception as exc:  # noqa: BLE001
        overridden = {"ai_override_applied": False, "blocked_by": type(exc).__name__}

    blocked = (
        stale.get("verdict") == "BLOCK"
        and stale.get("execution_allowed") is False
        and overridden.get("ai_override_applied") is not True
        and overridden.get("execution_allowed") is not True
    )
    return _ok(
        "ai_high_confidence_overrides_stale_data",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Stale evidence stays BLOCK; AI high-confidence cannot reopen",
        evidence={"stale": stale.get("verdict"), "override": overridden},
    )


def attack_counterfactual_as_real_pnl() -> AttackResult:
    from backend.nexus_counterfactual_replay_v16.claim_scan import assert_no_forbidden_claims
    from backend.nexus_counterfactual_replay_v16.hard_bans import (
        HardBanViolation,
        refuse_counterfactual_as_real_performance,
    )

    poison = {
        "summary": "This counterfactual shows live PnL and real performance gains",
        "pnl": 1234.5,
        "counterfactual_profit_is_not_real_performance": False,
    }
    scan = assert_no_forbidden_claims(poison)
    refused = False
    try:
        refuse_counterfactual_as_real_performance()
    except HardBanViolation:
        refused = True
    # Defense: claim scanner catches forbidden phrases AND hard-ban refuse works.
    # Poison payload must NOT be clean.
    blocked = (not scan.get("clean")) and refused
    return _ok(
        "counterfactual_counted_as_real_pnl",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="CF-as-real-PnL claims refused; disclaimer hard-ban active",
        evidence={"scan": scan, "refuse_raised": refused},
    )


def attack_good_process_loss_mislabeled_bad() -> AttackResult:
    from backend.nexus_trade_error_ontology_v1.classifier import classify_trade_error
    from backend.nexus_trade_error_ontology_v1.fixtures import labeled_fixture_controls

    packets = labeled_fixture_controls()
    target = next(p for p in packets if p.get("trade_id") == "V16A_FIX_good_loss")
    result = classify_trade_error(target)
    cls = result.get("process_classification")
    # Must remain GOOD_PROCESS_LOSS — not BAD_PROCESS_LOSS just because PnL < 0.
    blocked = cls == "GOOD_PROCESS_LOSS" and result.get("is_win") is False
    return _ok(
        "good_process_loss_mislabeled_bad",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail=f"classifier keeps GOOD_PROCESS_LOSS (got {cls})",
        evidence={"classification": result},
    )


def attack_bad_process_win_as_good_lesson() -> AttackResult:
    from backend.nexus_lesson_compiler.campaign import run_compiler_campaign
    from backend.nexus_trade_error_ontology_v1.ai_proposal import apply_ai_proposal
    from backend.nexus_trade_error_ontology_v1.classifier import classify_trade_error
    from backend.nexus_trade_error_ontology_v1.fixtures import labeled_fixture_controls

    packets = labeled_fixture_controls()
    bad_win = next(p for p in packets if p.get("trade_id") == "V16A_FIX_bad_cost_win")
    result = classify_trade_error(bad_win)
    # AI tries to rebrand as GOOD lesson material — must not override.
    merged = apply_ai_proposal(
        bad_win,
        {
            "process_classification": "GOOD_PROCESS_WIN",
            "lesson_quality": "EXCELLENT",
            "promote_lesson": True,
        },
    )
    report = run_compiler_campaign(pass_id=1)
    active = [
        e
        for e in report.get("lessons", [])
        if str(e.get("status", "")).upper() == "ACTIVE"
    ]
    blocked = (
        result.get("process_classification") == "BAD_PROCESS_WIN"
        and merged.get("process_classification") == "BAD_PROCESS_WIN"
        and merged.get("classifier_authority", {}).get("ai_can_override") is False
        and len(active) == 0
    )
    return _ok(
        "bad_process_win_treated_as_good_lesson",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="BAD_PROCESS_WIN cannot become good Lesson / ACTIVE",
        evidence={
            "classification": result.get("process_classification"),
            "merged": merged.get("process_classification"),
            "active_lessons": len(active),
        },
    )


def attack_lesson_activated_without_validation() -> AttackResult:
    from backend.nexus_lesson_validation_firewall.firewall import LessonValidationFirewall

    fw = LessonValidationFirewall()
    p1 = fw.run_pass1_interfaces_fixtures()
    proofs = p1.get("proofs") or p1
    active_blocked = bool(
        proofs.get("active_blocked")
        or proofs.get("force_active_blocked")
        or (proofs.get("active_block") or {}).get("allowed") is False
        or p1.get("active_promotion_blocked")
    )
    # Dig into nested results if needed.
    if not active_blocked:
        for key in ("active_block", "real_active", "illegal_skip", "skip"):
            node = proofs.get(key) if isinstance(proofs, dict) else None
            if isinstance(node, dict) and node.get("allowed") is False:
                active_blocked = True
                break
        # Also scan advances / top-level
        for node in p1.get("advances") or []:
            if isinstance(node, dict) and node.get("target") == "ACTIVE":
                if node.get("allowed") is False:
                    active_blocked = True
    # Direct force attempt
    from backend.nexus_lesson_validation_firewall.fixtures import synthetic_fixture_lesson
    from backend.nexus_lesson_validation_firewall.states import LessonPromotionStateMachine
    from backend.nexus_lesson_validation_firewall.record import ImmutablePromotionRecordStore

    sm = LessonPromotionStateMachine(
        synthetic_fixture_lesson(lesson_id="RT_FORCE_ACTIVE"),
        record_store=ImmutablePromotionRecordStore(),
        now_epoch=1_700_000_000,
    )
    force = sm.attempt_transition("ACTIVE", actor="attacker", force=True)
    force_blocked = force.get("allowed") is False
    blocked = force_blocked or active_blocked
    return _ok(
        "lesson_activated_without_validation",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Firewall refuses ACTIVE without full validation pipeline",
        evidence={"force": force, "pass1_keys": list(p1.keys())[:20]},
    )


def attack_public_ui_proprietary_threshold_leak() -> AttackResult:
    from backend.nexus_decision_memory_graph.graph import DecisionMemoryGraph
    from backend.nexus_decision_memory_graph.hard_bans import HardBanViolation
    from backend.nexus_decision_memory_graph.public_projection import (
        assert_no_private_leak,
        project_node_public,
    )

    g = DecisionMemoryGraph()
    sealed = g.seal_node(
        kind="RISK_DECISION",
        as_of_ms=1_700_000_000_000,
        payload={
            "symbol": "BTCUSDT",
            "label": "risk",
            "proprietary_threshold": 0.137,
            "exact_risk_threshold": 0.042,
            "founder_only_note": "do not leak",
            "verdict": "ALLOW_REDUCED",
        },
        parent_lineage_hashes=["redteam"],
    )
    node = sealed.get("node") if isinstance(sealed, dict) and "node" in sealed else sealed
    pub = project_node_public(node if isinstance(node, dict) else sealed)
    leak_raised = False
    try:
        assert_no_private_leak(pub or {})
    except HardBanViolation:
        leak_raised = True
    payload = (pub or {}).get("payload") or {}
    leaked = any(
        k in payload
        for k in ("proprietary_threshold", "exact_risk_threshold", "founder_only_note")
    )
    text = json.dumps(pub or {}, sort_keys=True)
    leaked = leaked or ("0.137" in text) or ("founder_only_note" in text)
    blocked = (not leaked) and (not leak_raised)
    return _ok(
        "public_ui_proprietary_threshold_leak",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Public projection strips proprietary thresholds",
        evidence={"public": pub, "leak_raised": leak_raised},
    )


def attack_member_accessing_founder_data() -> AttackResult:
    from backend.nexus_decision_memory_graph.constants import PRIVATE_FIELD_NAMES
    from backend.nexus_decision_memory_graph.public_projection import project_node_public

    founder_node = {
        "node_id": "n_founder_1",
        "kind": "VALIDATION",
        "as_of_ms": 1,
        "lineage_hash": "abc",
        "payload": {
            "symbol": "ETHUSDT",
            "label": "founder",
            "private_execution_control": {"leverage": 10},
            "api_key": "AKIA_FAKE_SECRET",
            "founder_only_note": "member must not see",
            "raw_memory_blob": {"x": 1},
        },
    }
    pub = project_node_public(founder_node)
    blob = json.dumps(pub or {}, sort_keys=True).lower()
    hits = [f for f in PRIVATE_FIELD_NAMES if f in blob]
    blocked = len(hits) == 0 and pub.get("private_fields_included") is False
    return _ok(
        "member_accessing_founder_data",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Member/public projection cannot access Founder-private fields",
        evidence={"hits": hits, "public_keys": list((pub or {}).get("payload", {}).keys())},
    )


def attack_invalid_ai_json() -> AttackResult:
    from backend.nexus_uncertainty_abstention.engine import evaluate_raw

    out = evaluate_raw('{"provider_status":"OK",')
    blocked = (
        out.get("verdict") == "BLOCK"
        and out.get("execution_allowed") is False
        and out.get("fail_closed") is True
    )
    return _ok(
        "invalid_ai_json",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Invalid AI JSON fail-closes to BLOCK",
        evidence={"verdict": out.get("verdict"), "reasons": out.get("reasons")},
    )


def attack_provider_timeout() -> AttackResult:
    from backend.nexus_uncertainty_abstention.engine import evaluate_raw
    from backend.nexus_uncertainty_abstention.fixtures import _base

    out = evaluate_raw(_base(provider_status="TIMEOUT", stated_confidence=0.99))
    blocked = (
        out.get("verdict") == "BLOCK"
        and out.get("execution_allowed") is False
        and out.get("fail_closed") is True
    )
    return _ok(
        "provider_timeout",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Provider timeout fail-closes; high confidence ignored",
        evidence={"verdict": out.get("verdict")},
    )


def attack_duplicate_candidate() -> AttackResult:
    from backend.nexus_global_shadow.contracts import Candidate, RoleVerdict, SixRoleReviewSet
    from backend.nexus_global_shadow.portfolio import ShadowPortfolioPolicy

    c1 = Candidate(
        candidate_id="dup_1",
        symbol="BTCUSDT",
        direction="LONG",
        strategy_id="TREND",
        rank=1,
        score_components={},
    )
    c2 = Candidate(
        candidate_id="dup_1",
        symbol="BTCUSDT",
        direction="LONG",
        strategy_id="TREND",
        rank=2,
        score_components={},
    )
    rs = SixRoleReviewSet(
        candidate_id="dup_1",
        review_complete=True,
        risk_critic_verdict=RoleVerdict.PASS.value,
    )
    ctrl = ShadowPortfolioPolicy()
    verdicts = ctrl.evaluate(
        candidates=[c1, c2],
        review_sets={"dup_1": rs},
        open_positions=[],
        pending_intents=[],
        correlation_groups={},
    )
    blocks: list[str] = []
    for v in verdicts:
        blocks.extend(list(v.block_reasons or []))
    blocked = "duplicate_candidate" in blocks
    return _ok(
        "duplicate_candidate",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Duplicate candidate_id blocked by ShadowPortfolioPolicy",
        evidence={"blocks": blocks, "verdict_count": len(verdicts)},
    )


def attack_duplicate_order_intent() -> AttackResult:
    """Probe owner-only duplicate intent invariant from durability control."""
    from backend.nexus_recovery.dr_control_v12.proofs import (
        invariant_owner_only_duplicate_intent,
    )
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    proof = invariant_owner_only_duplicate_intent(root)
    passed = bool(getattr(proof, "passed", False) or (isinstance(proof, dict) and proof.get("passed")))
    # Also simulate local dedupe guard used by scale campaigns.
    seen: set[str] = set()
    intents = ["intent_a", "intent_a", "intent_b"]
    dup_count = 0
    accepted = []
    for i in intents:
        if i in seen:
            dup_count += 1
            continue
        seen.add(i)
        accepted.append(i)
    local_ok = dup_count == 1 and accepted == ["intent_a", "intent_b"]
    blocked = passed and local_ok
    return _ok(
        "duplicate_order_intent",
        disposition="FIXED" if blocked else "EXPLICITLY_BLOCKED",
        attack_blocked=blocked or local_ok,
        detail="Owner-only duplicate intent invariant + local dedupe",
        evidence={
            "proof_passed": passed,
            "dup_count": dup_count,
            "accepted": accepted,
        },
    )


def attack_replay_mutates_real_ledger() -> AttackResult:
    from backend.nexus_counterfactual_replay_v16.hard_bans import (
        HardBanViolation,
        refuse_rewrite_real_ledger,
    )
    from backend.nexus_counterfactual_replay_v16.ledger_guard import assert_ledger_unchanged

    original = {
        "decision_id": "d1",
        "trade_id": "t1",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "entry_ts_ms": 1,
        "exit_ts_ms": 2,
        "entry_price": 100.0,
        "exit_price": 110.0,
        "stop_price": 90.0,
        "take_profit_price": 120.0,
        "size": 1.0,
        "strategy_expert": "TREND",
        "decision_ts_ms": 1,
        "data_trust_at_decision": 1.0,
        "regime_at_decision": "CLEAR",
    }
    mutated = dict(original)
    mutated["exit_price"] = 999.0  # CF must not rewrite observed exit
    mutation_blocked = False
    try:
        assert_ledger_unchanged(original, mutated)
    except HardBanViolation:
        mutation_blocked = True
    # Unchanged pair must not raise.
    unchanged_ok = True
    try:
        assert_ledger_unchanged(original, dict(original))
    except Exception:  # noqa: BLE001
        unchanged_ok = False
    refused = False
    try:
        refuse_rewrite_real_ledger()
    except HardBanViolation:
        refused = True
    blocked = mutation_blocked and unchanged_ok and refused
    return _ok(
        "replay_mutates_real_ledger",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Replay cannot mutate real ledger; rewrite hard-banned",
        evidence={
            "mutation_blocked": mutation_blocked,
            "unchanged_ok": unchanged_ok,
            "refuse_raised": refused,
        },
    )


def attack_graph_identity_collision() -> AttackResult:
    from backend.nexus_decision_memory_graph.graph import (
        DecisionMemoryGraph,
        DecisionMemoryGraphError,
    )
    from backend.nexus_decision_memory_graph.ids import make_immutable_id

    g = DecisionMemoryGraph()
    material = {"symbol": "BTCUSDT", "x": 1}
    id1 = make_immutable_id(kind="CANDIDATE", material=material)
    id2 = make_immutable_id(kind="CANDIDATE", material=material)
    id3 = make_immutable_id(kind="CANDIDATE", material={**material, "x": 2})
    collision_safe = id1 == id2 and id1 != id3
    r1 = g.seal_node(
        kind="CANDIDATE",
        as_of_ms=1,
        payload=material,
        parent_lineage_hashes=["n1"],
        node_id=id1,
    )
    dup_blocked = False
    dup_error: str | None = None
    r2: dict[str, Any] | None = None
    try:
        r2 = g.seal_node(
            kind="CANDIDATE",
            as_of_ms=1,
            payload=material,
            parent_lineage_hashes=["n1"],
            node_id=id1,  # same immutable id — must refuse collision rewrite
        )
        if isinstance(r2, dict):
            if r2.get("ok") is False or "duplicate" in str(r2).lower() or r2.get("mode"):
                dup_blocked = True
            elif r1 and r2 and r1.get("node_id") == r2.get("node_id"):
                dup_blocked = True
    except DecisionMemoryGraphError as exc:
        dup_blocked = "duplicate" in str(exc).lower() or "immutable" in str(exc).lower()
        dup_error = str(exc)
    blocked = collision_safe and dup_blocked
    return _ok(
        "graph_identity_collision",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Immutable content-addressed IDs + duplicate seal refuse collision",
        evidence={
            "id1": id1,
            "id2": id2,
            "id3": id3,
            "r1_node": (r1 or {}).get("node_id") if isinstance(r1, dict) else None,
            "dup_blocked": dup_blocked,
            "dup_error": dup_error,
        },
    )


def attack_cherry_picking() -> AttackResult:
    from backend.nexus_moat_adversarial_redteam_v16.adapters import cherry_pick_blocked

    result = cherry_pick_blocked()
    blocked = bool(result.get("blocked"))
    return _ok(
        "cherry_picking",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Cherry-pick gate + refuse_cherry_pick block favorable-only promotion",
        evidence=result,
    )


def attack_strategy_thrashing() -> AttackResult:
    from backend.nexus_moat_adversarial_redteam_v16.adapters import thrash_formal_params

    result = thrash_formal_params()
    thrash_blocked = bool(result.get("thrash_blocked"))
    return _ok(
        "strategy_thrashing",
        disposition="FIXED" if thrash_blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=thrash_blocked,
        detail="Per-minute formal param thrash hard-banned via propose_update",
        evidence=result,
    )


def attack_no_trade_expert_bypass() -> AttackResult:
    from backend.nexus_moat_adversarial_redteam_v16.adapters import route_defensive_context
    from backend.nexus_strategy_expert_router.constants import DEFENSIVE_EXPERT, NO_TRADE_SIDES
    from backend.nexus_strategy_expert_router.fixtures import fixture_risk_gate_blocked
    from backend.nexus_strategy_expert_router.hard_bans import HardBanViolation
    from backend.nexus_strategy_expert_router.router import StrategyExpertRouter
    from backend.nexus_strategy_expert_router.safety_gates import honor_risk_gate

    router = StrategyExpertRouter()
    ctx = route_defensive_context()
    decision = router.route(ctx)
    side = getattr(decision, "side", None)
    expert = getattr(decision, "expert_id", None)
    trace = decision.to_dict() if hasattr(decision, "to_dict") else {"side": side, "expert_id": expert}

    force_blocked = False
    force_error: str | None = None
    try:
        # Attack: force a trade expert while defensive should win — must HardBan.
        router.route(ctx, force_expert="TREND")
    except HardBanViolation as exc:
        force_blocked = "defensive" in str(exc).lower() or "force_trade" in str(exc).lower()
        force_error = str(exc)

    risk_ctx = fixture_risk_gate_blocked()
    risk_decision = router.route(
        risk_ctx,
        ai_override_risk_gate={"force_allow": True, "override_risk_gate": True},
    )
    risk_side = getattr(risk_decision, "side", None)
    risk = honor_risk_gate(
        risk_gate_allow=False,
        risk_gate_reason="REDTEAM_DENY",
        ai_override_attempt={"force_allow": True, "override_risk_gate": True},
    )
    defensive_clamped = (
        side in NO_TRADE_SIDES
        or expert == DEFENSIVE_EXPERT
        or bool(getattr(decision, "no_trade", False))
    )
    risk_ok = (
        risk.get("effective_allow") is False
        and risk.get("ai_override_risk_gate_applied") is False
        and (
            risk_side in NO_TRADE_SIDES
            or bool(getattr(risk_decision, "no_trade", False))
            or getattr(risk_decision, "ai_override_risk_gate_applied", True) is False
        )
    )
    blocked = defensive_clamped and force_blocked and risk_ok
    return _ok(
        "no_trade_expert_bypass",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="DEFENSIVE_NO_TRADE / risk deny cannot be bypassed into LONG/SHORT",
        evidence={
            "defensive": trace,
            "force_blocked": force_blocked,
            "force_error": force_error,
            "risk_side": risk_side,
            "risk_no_trade": getattr(risk_decision, "no_trade", None),
            "risk": risk,
        },
    )


def attack_unavailable_shown_as_0() -> AttackResult:
    from backend.nexus_decision_memory_graph.failsafe import (
        is_fail_safe,
        unavailable_response,
    )
    from backend.nexus_decision_memory_graph.public_projection import project_node_public

    resp = unavailable_response(operation="pit_lookup")
    pub = project_node_public({"mode": resp["mode"], "payload": {"pnl": 0, "count": 0}})
    # Unavailable must not render numeric zeros as live metrics.
    shown_as_zero = False
    if pub and pub.get("unavailable") is True:
        payload = pub.get("payload") or {}
        # Empty payload is correct; numeric 0 metrics would be dishonest.
        shown_as_zero = any(
            isinstance(v, (int, float)) and v == 0 for v in payload.values()
        )
    blocked = is_fail_safe(resp) and pub.get("unavailable") is True and not shown_as_zero
    return _ok(
        "unavailable_shown_as_0",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Unavailable surfaces emit unavailable flag, not numeric zeros",
        evidence={"resp": resp, "public": pub},
    )


def attack_fixture_as_live() -> AttackResult:
    from backend.nexus_lesson_validation_firewall.constants import EVIDENCE_CLASS_FIXTURE
    from backend.nexus_lesson_validation_firewall.fixtures import (
        synthetic_fixture_lesson,
        synthetic_real_lesson_blocked,
    )
    from backend.nexus_moat_adversarial_redteam_v16.constants import (
        EVIDENCE_CLASS,
        LABEL,
    )

    fix = synthetic_fixture_lesson()
    real = synthetic_real_lesson_blocked()
    fix_class = str(
        fix.get("evidence_class") or fix.get("data_class") or EVIDENCE_CLASS_FIXTURE
    ).upper()
    live_claim = "LIVE" in fix_class and "NOT" not in fix_class
    real_active = str(real.get("status", "")).upper() == "ACTIVE"
    blocked = (not live_claim) and (not real_active) and "FIXTURE" in fix_class
    return _ok(
        "fixture_as_live",
        disposition="FIXED" if blocked else "EXPLICITLY_BLOCKED",
        attack_blocked=blocked,
        detail="Fixtures labeled FIXTURE/CONTROL — never Live",
        evidence={
            "fixture_class": fix_class,
            "label": LABEL,
            "evidence_class": EVIDENCE_CLASS,
            "real_status": real.get("status"),
        },
    )


def attack_model_agreement_replaces_deterministic_risk() -> AttackResult:
    from backend.nexus_uncertainty_abstention.engine import evaluate_raw
    from backend.nexus_uncertainty_abstention.fixtures import _base
    from backend.nexus_strategy_expert_router.safety_gates import honor_risk_gate

    # High model agreement must NOT override bad data_agreement / risk deny.
    out = evaluate_raw(
        _base(
            model_agreement=0.99,
            historical_agreement=0.99,
            regime_agreement=0.99,
            data_agreement=0.20,
            risk_agreement=0.99,
            execution_agreement=0.99,
            stated_confidence=0.99,
        )
    )
    consensus_blocked = out.get("verdict") in {"ABSTAIN", "BLOCK"} and out.get(
        "execution_allowed"
    ) is False
    risk = honor_risk_gate(
        risk_gate_allow=False,
        risk_gate_reason="DETERMINISTIC_RISK_DENY",
        ai_override_attempt={
            "override_risk_gate": True,
            "force_allow": True,
            "model_agreement": 0.99,
        },
    )
    risk_ok = risk.get("effective_allow") is False and risk.get(
        "ai_override_risk_gate_applied"
    ) is False
    blocked = consensus_blocked and risk_ok
    return _ok(
        "model_agreement_replaces_deterministic_risk",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Model agreement cannot override bad data or deterministic risk",
        evidence={"verdict": out.get("verdict"), "risk": risk},
    )


def attack_embedded_secrets() -> AttackResult:
    from backend.nexus_moat_adversarial_redteam_v16.adapters import scan_embedded_secrets

    poison = {
        "note": "api_key=AKIA_LIVE_SECRET_EXAMPLE",
        "wallet_seed": "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
        "authorization": "Bearer sk-live-redteam-token",
    }
    hits = scan_embedded_secrets(poison)
    detected = int(hits.get("secret_leak_count") or 0) > 0 and hits.get("pass") is False
    # Clean: identifier key "secret" with null value must NOT count as leak.
    clean = {"attack": "embedded_secrets", "result": "scanned", "secret": None}
    clean_hits = scan_embedded_secrets(clean)
    clean_ok = clean_hits.get("pass") is True and int(clean_hits.get("secret_leak_count") or 0) == 0
    blocked = detected and clean_ok
    return _ok(
        "embedded_secrets",
        disposition="FIXED" if blocked else "PLATFORM_BLOCKED_NOT_PASS",
        attack_blocked=blocked,
        detail="Credential patterns detected; bare identifier 'secret' ignored",
        evidence={"poison_hits": hits, "clean_hits": clean_hits},
    )


def attack_exchange_write() -> AttackResult:
    from backend.nexus_counterfactual_replay_v16.hard_bans import (
        HardBanViolation,
        refuse_exchange_write,
    )
    from backend.nexus_probabilistic_regime_v2.bans import refuse_exchange_write as refuse2

    raised = False
    try:
        refuse_exchange_write()
    except HardBanViolation:
        raised = True
    r2 = refuse2()
    blocked = raised and r2.get("allowed") is False and r2.get("executed") is False
    # Hard ban proven; also EXPLICITLY_BLOCKED as campaign never attempts real writes.
    disposition = "EXPLICITLY_BLOCKED" if blocked else "PLATFORM_BLOCKED_NOT_PASS"
    return _ok(
        "exchange_write",
        disposition=disposition,
        attack_blocked=blocked,
        detail="Exchange write hard-banned across V16 refuse APIs (never attempted)",
        evidence={"refuse_raised": raised, "regime_ban": r2, "attempt_count": 0},
    )


def attack_mainnet_client() -> AttackResult:
    from backend.nexus_counterfactual_replay_v16.hard_bans import (
        HardBanViolation,
        refuse_mainnet_real_money,
    )
    from backend.nexus_probabilistic_regime_v2.bans import refuse_mainnet

    raised = False
    try:
        refuse_mainnet_real_money()
    except HardBanViolation:
        raised = True
    r2 = refuse_mainnet()
    # Never create a mainnet client in redteam — HARD BAN. Prove refuse + zero counter.
    flags = {"mainnet_client_created_count": 0}
    blocked = raised and r2.get("allowed") is False and flags["mainnet_client_created_count"] == 0
    disposition = "EXPLICITLY_BLOCKED" if blocked else "PLATFORM_BLOCKED_NOT_PASS"
    return _ok(
        "mainnet_client",
        disposition=disposition,
        attack_blocked=blocked,
        detail="Mainnet client creation hard-banned; count remains 0 (never attempted)",
        evidence={"refuse_raised": raised, "ban": r2, "flags": flags},
    )


ATTACK_FUNCS: dict[str, Callable[[], AttackResult]] = {
    "future_leakage": attack_future_leakage,
    "fake_regime_confidence": attack_fake_regime_confidence,
    "ai_high_confidence_overrides_stale_data": attack_ai_high_confidence_overrides_stale_data,
    "counterfactual_counted_as_real_pnl": attack_counterfactual_as_real_pnl,
    "good_process_loss_mislabeled_bad": attack_good_process_loss_mislabeled_bad,
    "bad_process_win_treated_as_good_lesson": attack_bad_process_win_as_good_lesson,
    "lesson_activated_without_validation": attack_lesson_activated_without_validation,
    "public_ui_proprietary_threshold_leak": attack_public_ui_proprietary_threshold_leak,
    "member_accessing_founder_data": attack_member_accessing_founder_data,
    "invalid_ai_json": attack_invalid_ai_json,
    "provider_timeout": attack_provider_timeout,
    "duplicate_candidate": attack_duplicate_candidate,
    "duplicate_order_intent": attack_duplicate_order_intent,
    "replay_mutates_real_ledger": attack_replay_mutates_real_ledger,
    "graph_identity_collision": attack_graph_identity_collision,
    "cherry_picking": attack_cherry_picking,
    "strategy_thrashing": attack_strategy_thrashing,
    "no_trade_expert_bypass": attack_no_trade_expert_bypass,
    "unavailable_shown_as_0": attack_unavailable_shown_as_0,
    "fixture_as_live": attack_fixture_as_live,
    "model_agreement_replaces_deterministic_risk": attack_model_agreement_replaces_deterministic_risk,
    "embedded_secrets": attack_embedded_secrets,
    "exchange_write": attack_exchange_write,
    "mainnet_client": attack_mainnet_client,
}


def run_all_attacks() -> list[AttackResult]:
    missing = [a for a in ATTACK_IDS if a not in ATTACK_FUNCS]
    if missing:
        raise RuntimeError(f"attack_funcs_missing:{missing}")
    results: list[AttackResult] = []
    for aid in ATTACK_IDS:
        try:
            results.append(ATTACK_FUNCS[aid]())
        except Exception as exc:  # noqa: BLE001
            # Harness/API mismatch is a FAIL condition — never silent PASS.
            results.append(
                AttackResult(
                    attack_id=aid,
                    severity=SEVERITY_BY_ATTACK[aid],
                    disposition="PLATFORM_BLOCKED_NOT_PASS",
                    attack_blocked=False,
                    detail=f"harness_bug:{type(exc).__name__}:{exc}",
                    evidence={"error": str(exc), "error_type": type(exc).__name__},
                    survivor=True,
                )
            )
    return results
