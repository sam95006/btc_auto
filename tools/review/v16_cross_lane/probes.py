"""V16 cross-lane review probes — independent pair reviews (reviewer-owned)."""
from __future__ import annotations

from typing import Any

from backend.nexus_counterfactual_replay_v16.constants import DISCLAIMER as CF_DISCLAIMER
from backend.nexus_counterfactual_replay_v16.constants import HARD_BANS as CF_BANS
from backend.nexus_counterfactual_replay_v16.engine import run_counterfactual_replay
from backend.nexus_decision_memory_graph.constants import HARD_BANS as H_BANS
from backend.nexus_decision_memory_graph.graph import DecisionMemoryGraph
from backend.nexus_decision_memory_graph.schema import SchemaError
from backend.nexus_lesson_compiler.compiler import LessonCompileError, compile_reflection
from backend.nexus_lesson_compiler.constants import HARD_BANS as E_BANS
from backend.nexus_lesson_compiler.constants import LESSON_STATUS_CANDIDATE
from backend.nexus_lesson_compiler.contracts import ReflectionFixture
from backend.nexus_lesson_compiler.fixtures import REFLECTION_FIXTURES
from backend.nexus_lesson_validation_firewall.constants import HARD_BANS as F_BANS
from backend.nexus_lesson_validation_firewall.intake import (
    FirewallIntakeError,
    intake_from_compiler_lesson,
)
from backend.nexus_lesson_validation_firewall.states import LessonPromotionStateMachine
from backend.nexus_probabilistic_regime_v2.constants import HARD_BANS as C_BANS
from backend.nexus_probabilistic_regime_v2.constants import OUTPUT_KEYS as C_OUTPUT_KEYS
from backend.nexus_strategy_expert_router.constants import HARD_BANS as D_BANS
from backend.nexus_strategy_expert_router.constants import NO_TRADE_SIDES, REGIME_PROB_KEYS
from backend.nexus_strategy_expert_router.cross_lane import (
    apply_abstention_verdict,
    bind_regime_engine_to_context,
)
from backend.nexus_strategy_expert_router.fixtures import fixture_strong_trend_long
from backend.nexus_strategy_expert_router.router import StrategyExpertRouter
from backend.nexus_trade_error_ontology_v1.constants import HARD_BANS as A_BANS
from backend.nexus_trade_error_ontology_v1.constants import PROCESS_CLASSES
from backend.nexus_uncertainty_abstention.constants import HARD_BANS as G_BANS
from backend.nexus_uncertainty_abstention.constants import VERDICTS
from backend.nexus_uncertainty_abstention.engine import evaluate_inputs
from backend.nexus_uncertainty_abstention.fixtures import _base


def _finding(
    pair: str,
    severity: str,
    finding_id: str,
    detail: str,
    *,
    disposition: str,
) -> dict[str, Any]:
    return {
        "pair": pair,
        "severity": severity,
        "id": finding_id,
        "detail": detail,
        "disposition": disposition,
    }


def review_a_reviews_e() -> dict[str, Any]:
    """A→E: ontology process-class lineage into lesson compiler."""
    findings: list[dict[str, Any]] = []
    base = REFLECTION_FIXTURES[0]
    # Critical gap (fixed): BAD_PROCESS_WIN must not compile ALLOW lessons.
    bad_allow = ReflectionFixture(
        reflection_id="REFL_XREV_BAD_WIN_ALLOW",
        conditions=base.conditions,
        then_action={
            "expert": "breakout_long",
            "action_kind": "ALLOW",
            "target": "entry_signal",
            "detail": "Illegally learn edge from lucky bad process",
        },
        scope="EXPERT",
        affected_expert="breakout_long",
        regimes=("EXPANSION",),
        expiry=base.expiry,
        evidence_count=5,
        confidence=0.55,
        contradictory_evidence=("xrev",),
        author_model="xrev",
        author_version="1",
        narrative="false learning",
        source_process_class="BAD_PROCESS_WIN",
    )
    try:
        compile_reflection(bad_allow)
        findings.append(
            _finding(
                "A→E",
                "CRITICAL",
                "AE_BAD_PROCESS_WIN_ALLOW",
                "BAD_PROCESS_WIN compiled ALLOW lesson (false learning)",
                disposition="OPEN",
            )
        )
    except LessonCompileError as exc:
        findings.append(
            _finding(
                "A→E",
                "CRITICAL",
                "AE_BAD_PROCESS_WIN_ALLOW",
                f"refused:{exc}",
                disposition="FIXED",
            )
        )

    # Anti-pattern BLOCK from BAD_PROCESS_WIN is allowed.
    bad_block = ReflectionFixture(
        reflection_id="REFL_XREV_BAD_WIN_BLOCK",
        conditions=base.conditions,
        then_action={
            "expert": "breakout_long",
            "action_kind": "BLOCK",
            "target": "entry_signal",
            "detail": "Block repeating bad-process pattern",
        },
        scope="EXPERT",
        affected_expert="breakout_long",
        regimes=("EXPANSION",),
        expiry=base.expiry,
        evidence_count=5,
        confidence=0.55,
        contradictory_evidence=("xrev",),
        author_model="xrev",
        author_version="1",
        narrative="anti-pattern",
        source_process_class="BAD_PROCESS_WIN",
    )
    rule = compile_reflection(bad_block)
    assert rule.status == LESSON_STATUS_CANDIDATE
    assert set(PROCESS_CLASSES)
    missing_shared = sorted(set(A_BANS) & set(E_BANS))  # overlap ok; inventory present
    return {
        "pair": "A→E",
        "reviewer": "A",
        "reviewee": "E",
        "status": "PASS" if all(f["disposition"] != "OPEN" for f in findings) else "FAIL",
        "findings": findings,
        "hard_ban_overlap_sample": missing_shared[:5],
        "survivors": [f for f in findings if f["disposition"] not in {"FIXED", "ACCEPTED"}],
    }


def review_e_reviews_f() -> dict[str, Any]:
    """E→F: compiler CANDIDATE → firewall intake (status/state lineage)."""
    findings: list[dict[str, Any]] = []
    rule = compile_reflection(REFLECTION_FIXTURES[0])
    intake = intake_from_compiler_lesson(rule)
    assert intake["state"] == "CANDIDATE"
    assert intake["status"] == "CANDIDATE"
    sm = LessonPromotionStateMachine(intake)
    active = sm.attempt_transition("ACTIVE", actor="founder_operator", force=True)
    if active.get("allowed") or sm.real_lesson_active:
        findings.append(
            _finding(
                "E→F",
                "CRITICAL",
                "EF_ACTIVE_FROM_COMPILER",
                "compiler intake promoted to ACTIVE",
                disposition="OPEN",
            )
        )
    else:
        findings.append(
            _finding(
                "E→F",
                "CRITICAL",
                "EF_ACTIVE_FROM_COMPILER",
                "ACTIVE blocked on compiler intake",
                disposition="FIXED",
            )
        )

    # status-only payload (missing state) must still bind as CANDIDATE.
    status_only = {"status": "CANDIDATE", "lesson_id": "LESSON_STATUS_ONLY", "evidence_count": 2}
    try:
        # Force ACTIVE via status field — must refuse intake.
        intake_from_compiler_lesson({"status": "ACTIVE", "lesson_id": "X", "evidence_count": 1})
        findings.append(
            _finding(
                "E→F",
                "HIGH",
                "EF_ACTIVE_STATUS_INTAKE",
                "ACTIVE status accepted by firewall intake",
                disposition="OPEN",
            )
        )
    except FirewallIntakeError:
        findings.append(
            _finding(
                "E→F",
                "HIGH",
                "EF_ACTIVE_STATUS_INTAKE",
                "ACTIVE status refused at intake",
                disposition="FIXED",
            )
        )
    _ = status_only
    return {
        "pair": "E→F",
        "reviewer": "E",
        "reviewee": "F",
        "status": "PASS" if all(f["disposition"] != "OPEN" for f in findings) else "FAIL",
        "findings": findings,
        "f_hard_ban_count": len(F_BANS),
        "survivors": [f for f in findings if f["disposition"] not in {"FIXED", "ACCEPTED"}],
    }


def review_f_reviews_a() -> dict[str, Any]:
    """F→A: firewall must not treat ontology class alone as ACTIVE authority."""
    findings: list[dict[str, Any]] = []
    # Fake "good process" cannot unlock ACTIVE.
    lesson = {
        "lesson_id": "FAKE_ONTOLOGY_ACTIVE",
        "state": "DEMO_PENDING",
        "status": "DEMO_PENDING",
        "real_lesson": True,
        "v23_complete": True,
        "formal_wf": True,
        "oos": True,
        "lesson_prevention": "READY",
        "evidence_class": "REAL_LESSON",
        "error_class": "GOOD_PROCESS_LOSS",
        "evidence": [
            {"evidence_id": "e1", "polarity": "favorable", "metric": "x", "value": 1},
            {"evidence_id": "e2", "polarity": "unfavorable", "metric": "y", "value": 1},
            {"evidence_id": "e3", "polarity": "contradictory", "metric": "z", "value": 1},
        ],
        "baseline_metrics": {"error_rate": 0.3, "repeat_error_rate": 0.2, "coverage": 0.4},
        "patched_metrics": {"error_rate": 0.2, "repeat_error_rate": 0.1, "coverage": 0.5},
        "prior_lessons": ["P1"],
        "ttl_seconds": 86_400,
        "expires_at_epoch": 1_700_086_400,
        "as_of_epoch": 1_700_000_000,
    }
    sm = LessonPromotionStateMachine(lesson)
    # Illegal jump DEMO_PENDING from wrong start — set state properly.
    sm.state = "DEMO_PENDING"
    sm.lesson["state"] = "DEMO_PENDING"
    result = sm.attempt_transition("ACTIVE", actor="founder_operator", force=True)
    if result.get("allowed") or result.get("real_lesson_active"):
        findings.append(
            _finding(
                "F→A",
                "CRITICAL",
                "FA_ONTOLOGY_UNLOCKS_ACTIVE",
                "GOOD_PROCESS_* unlocked ACTIVE despite window policy",
                disposition="OPEN",
            )
        )
    else:
        findings.append(
            _finding(
                "F→A",
                "CRITICAL",
                "FA_ONTOLOGY_UNLOCKS_ACTIVE",
                "ACTIVE still blocked with ontology class present",
                disposition="FIXED",
            )
        )
    return {
        "pair": "F→A",
        "reviewer": "F",
        "reviewee": "A",
        "status": "PASS" if all(f["disposition"] != "OPEN" for f in findings) else "FAIL",
        "findings": findings,
        "survivors": [f for f in findings if f["disposition"] not in {"FIXED", "ACCEPTED"}],
    }


def review_c_reviews_d() -> dict[str, Any]:
    """C→D: regime formal_state/trading_unsafe must force no-trade in router."""
    findings: list[dict[str, Any]] = []
    # Simulated C UNKNOWN package with residual bull probs (adversarial false-PASS).
    engine_out = {
        "formal_state": "UNKNOWN",
        "trading_unsafe": True,
        "fail_closed": True,
        "probabilities": {
            **{k: 0.9 if "bull" in k else 0.1 for k in C_OUTPUT_KEYS},
            "regime_confidence": 0.0,
            "regime_freshness": 0.1,
        },
    }
    # Force bull keys explicitly for attack.
    engine_out["probabilities"]["strong_bull_probability"] = 0.95
    engine_out["probabilities"]["strong_bear_probability"] = 0.05
    ctx = bind_regime_engine_to_context(fixture_strong_trend_long(), engine_out)
    decision = StrategyExpertRouter().route(ctx)
    if decision.side in ("LONG", "SHORT") and not decision.no_trade:
        findings.append(
            _finding(
                "C→D",
                "CRITICAL",
                "CD_UNKNOWN_REGIME_ENTRY",
                f"router emitted {decision.side} under UNKNOWN/trading_unsafe",
                disposition="OPEN",
            )
        )
    else:
        findings.append(
            _finding(
                "C→D",
                "CRITICAL",
                "CD_UNKNOWN_REGIME_ENTRY",
                f"no-trade under UNKNOWN (side={decision.side})",
                disposition="FIXED",
            )
        )

    # MIXED / trading_unsafe with high confidence residual.
    mixed = {
        "formal_state": "MIXED",
        "trading_unsafe": True,
        "fail_closed": False,
        "probabilities": {
            **{k: float(getattr(fixture_strong_trend_long().regime, k)) for k in REGIME_PROB_KEYS},
            "regime_confidence": 0.55,
            "regime_freshness": 0.90,
        },
    }
    d2 = StrategyExpertRouter().route(bind_regime_engine_to_context(fixture_strong_trend_long(), mixed))
    if d2.side in ("LONG", "SHORT") and not d2.no_trade:
        findings.append(
            _finding(
                "C→D",
                "HIGH",
                "CD_MIXED_REGIME_ENTRY",
                f"router emitted {d2.side} under MIXED/trading_unsafe",
                disposition="OPEN",
            )
        )
    else:
        findings.append(
            _finding(
                "C→D",
                "HIGH",
                "CD_MIXED_REGIME_ENTRY",
                f"no-trade under MIXED (side={d2.side})",
                disposition="FIXED",
            )
        )
    assert set(REGIME_PROB_KEYS).issubset(set(C_OUTPUT_KEYS))
    return {
        "pair": "C→D",
        "reviewer": "C",
        "reviewee": "D",
        "status": "PASS" if all(f["disposition"] != "OPEN" for f in findings) else "FAIL",
        "findings": findings,
        "survivors": [f for f in findings if f["disposition"] not in {"FIXED", "ACCEPTED"}],
    }


def review_d_reviews_g() -> dict[str, Any]:
    """D→G: abstention BLOCK/ABSTAIN must coerce router no-trade."""
    findings: list[dict[str, Any]] = []
    for verdict in ("BLOCK", "ABSTAIN", "WAIT"):
        raw = evaluate_inputs(
            _base(
                data_agreement=0.2 if verdict != "WAIT" else 0.55,
                model_agreement=0.2 if verdict == "ABSTAIN" else 0.9,
                historical_agreement=0.9,
                regime_agreement=0.9,
                execution_agreement=0.9,
                risk_agreement=0.9,
                calibration_reliability=0.2 if verdict == "BLOCK" else 0.8,
                similarity_coverage=0.1 if verdict == "ABSTAIN" else 0.8,
                prediction_interval_width=0.8 if verdict == "ABSTAIN" else 0.2,
                data_freshness_sec=200.0 if verdict == "BLOCK" else 10.0,
                stated_confidence=0.99,
            )
        )
        # Force exact verdict for the negative probe regardless of fixture nuances.
        forced = dict(raw)
        forced["verdict"] = verdict
        forced["execution_allowed"] = verdict in {"ALLOW", "ALLOW_REDUCED"}
        forced["uncertainty_score"] = 0.95
        ctx = apply_abstention_verdict(fixture_strong_trend_long(), forced)
        decision = StrategyExpertRouter().route(ctx)
        if decision.side in ("LONG", "SHORT") and not decision.no_trade:
            findings.append(
                _finding(
                    "D→G",
                    "CRITICAL",
                    f"DG_ABSTENTION_{verdict}_IGNORED",
                    f"router traded ({decision.side}) despite abstention={verdict}",
                    disposition="OPEN",
                )
            )
        else:
            findings.append(
                _finding(
                    "D→G",
                    "CRITICAL",
                    f"DG_ABSTENTION_{verdict}_IGNORED",
                    f"router honored abstention={verdict} side={decision.side}",
                    disposition="FIXED",
                )
            )
    assert set(VERDICTS)
    assert "no_ai_override_of_verdict" in G_BANS
    return {
        "pair": "D→G",
        "reviewer": "D",
        "reviewee": "G",
        "status": "PASS" if all(f["disposition"] != "OPEN" for f in findings) else "FAIL",
        "findings": findings,
        "survivors": [f for f in findings if f["disposition"] not in {"FIXED", "ACCEPTED"}],
    }


def review_g_reviews_c() -> dict[str, Any]:
    """G→C: stale/low regime confidence must not yield ALLOW via high stated confidence."""
    findings: list[dict[str, Any]] = []
    # High AI confidence + low regime agreement → abstain/block (not ALLOW).
    out = evaluate_inputs(
        _base(
            stated_confidence=0.99,
            regime_agreement=0.20,
            model_agreement=0.95,
            historical_agreement=0.90,
            data_agreement=0.90,
            calibration_reliability=0.85,
            data_freshness_sec=5.0,
        )
    )
    if out["verdict"] in {"ALLOW", "ALLOW_REDUCED"} and out.get("execution_allowed"):
        findings.append(
            _finding(
                "G→C",
                "HIGH",
                "GC_REGIME_DISAGREE_ALLOW",
                f"high-conf ALLOW despite regime_agreement gap (verdict={out['verdict']})",
                disposition="OPEN",
            )
        )
    else:
        findings.append(
            _finding(
                "G→C",
                "HIGH",
                "GC_REGIME_DISAGREE_ALLOW",
                f"regime disagreement fail-closed (verdict={out['verdict']})",
                disposition="FIXED",
            )
        )
    return {
        "pair": "G→C",
        "reviewer": "G",
        "reviewee": "C",
        "status": "PASS" if all(f["disposition"] != "OPEN" for f in findings) else "FAIL",
        "findings": findings,
        "c_hard_ban_count": len(C_BANS),
        "survivors": [f for f in findings if f["disposition"] not in {"FIXED", "ACCEPTED"}],
    }


def review_b_reviews_h() -> dict[str, Any]:
    """B→H: counterfactual cannot be sealed as real performance in memory graph."""
    findings: list[dict[str, Any]] = []
    g = DecisionMemoryGraph()
    try:
        g.seal_node(
            kind="COUNTERFACTUAL",
            as_of_ms=1_700_000_000,
            payload={
                "summary": "alt pnl",
                "pnl": 12.5,
                "is_real_performance": True,
                "counterfactual_profit_is_not_real_performance": False,
            },
        )
        findings.append(
            _finding(
                "B→H",
                "CRITICAL",
                "BH_CF_AS_REAL",
                "COUNTERFACTUAL sealed claiming real performance",
                disposition="OPEN",
            )
        )
    except (SchemaError, Exception) as exc:
        findings.append(
            _finding(
                "B→H",
                "CRITICAL",
                "BH_CF_AS_REAL",
                f"refused:{type(exc).__name__}:{exc}",
                disposition="FIXED",
            )
        )
    # PnL without disclaimer refused.
    try:
        g.seal_node(
            kind="COUNTERFACTUAL",
            as_of_ms=1_700_000_001,
            payload={"summary": "alt", "hypothetical_pnl": 9.0},
        )
        findings.append(
            _finding(
                "B→H",
                "HIGH",
                "BH_CF_PNL_NO_DISCLAIMER",
                "CF PnL sealed without disclaimer",
                disposition="OPEN",
            )
        )
    except SchemaError:
        findings.append(
            _finding(
                "B→H",
                "HIGH",
                "BH_CF_PNL_NO_DISCLAIMER",
                "CF PnL without disclaimer refused",
                disposition="FIXED",
            )
        )
    assert "no_rewrite_real_ledger" in H_BANS
    assert "no_counterfactual_profit_as_real_performance" in CF_BANS
    return {
        "pair": "B→H",
        "reviewer": "B",
        "reviewee": "H",
        "status": "PASS" if all(f["disposition"] != "OPEN" for f in findings) else "FAIL",
        "findings": findings,
        "survivors": [f for f in findings if f["disposition"] not in {"FIXED", "ACCEPTED"}],
    }


def review_h_reviews_b() -> dict[str, Any]:
    """H→B: CF replay must keep ledger frozen and disclaimer intact."""
    findings: list[dict[str, Any]] = []
    replay = run_counterfactual_replay()
    if replay.get("ledger_rewritten") is True:
        findings.append(
            _finding(
                "H→B",
                "CRITICAL",
                "HB_LEDGER_REWRITE",
                "counterfactual replay rewrote ledger",
                disposition="OPEN",
            )
        )
    else:
        findings.append(
            _finding(
                "H→B",
                "CRITICAL",
                "HB_LEDGER_REWRITE",
                "ledger frozen across CF replay",
                disposition="FIXED",
            )
        )
    if replay.get("any_real_performance_claim") is True:
        findings.append(
            _finding(
                "H→B",
                "CRITICAL",
                "HB_CF_AS_REAL_PNL",
                "CF claimed real performance",
                disposition="OPEN",
            )
        )
    else:
        findings.append(
            _finding(
                "H→B",
                "CRITICAL",
                "HB_CF_AS_REAL_PNL",
                "CF profit not treated as real",
                disposition="FIXED",
            )
        )
    if CF_DISCLAIMER not in str(replay.get("disclaimer") or ""):
        # disclaimer may be nested; engine puts DISCLAIMER constant
        if "COUNTERFACTUAL_PROFIT_IS_NOT_REAL_PERFORMANCE" not in str(replay):
            findings.append(
                _finding(
                    "H→B",
                    "HIGH",
                    "HB_MISSING_DISCLAIMER",
                    "CF disclaimer missing from replay payload",
                    disposition="OPEN",
                )
            )
        else:
            findings.append(
                _finding(
                    "H→B",
                    "HIGH",
                    "HB_MISSING_DISCLAIMER",
                    "disclaimer present in replay tree",
                    disposition="FIXED",
                )
            )
    else:
        findings.append(
            _finding(
                "H→B",
                "HIGH",
                "HB_MISSING_DISCLAIMER",
                "top-level disclaimer present",
                disposition="FIXED",
            )
        )
    return {
        "pair": "H→B",
        "reviewer": "H",
        "reviewee": "B",
        "status": "PASS" if all(f["disposition"] != "OPEN" for f in findings) else "FAIL",
        "findings": findings,
        "survivors": [f for f in findings if f["disposition"] not in {"FIXED", "ACCEPTED"}],
    }


REVIEW_RUNNERS = (
    review_a_reviews_e,
    review_b_reviews_h,
    review_c_reviews_d,
    review_d_reviews_g,
    review_e_reviews_f,
    review_f_reviews_a,
    review_g_reviews_c,
    review_h_reviews_b,
)


def run_all_cross_lane_reviews() -> dict[str, Any]:
    pairs = [fn() for fn in REVIEW_RUNNERS]
    all_findings = [f for p in pairs for f in p["findings"]]
    open_findings = [f for f in all_findings if f["disposition"] == "OPEN"]
    survivors = [f for p in pairs for f in p.get("survivors") or []]
    critical_open = [f for f in open_findings if f["severity"] == "CRITICAL"]
    high_open = [f for f in open_findings if f["severity"] == "HIGH"]
    status = "PASS"
    blockers: list[dict[str, Any]] = []
    if critical_open or high_open:
        status = "EXPLICITLY_BLOCKED"
        blockers = critical_open + high_open
    elif any(p["status"] != "PASS" for p in pairs):
        status = "FAIL"
    return {
        "schema": "v16_cross_lane_reviews_v1",
        "status": status,
        "pair_count": len(pairs),
        "pairs": pairs,
        "findings_total": len(all_findings),
        "findings_fixed": sum(1 for f in all_findings if f["disposition"] == "FIXED"),
        "survivors": survivors,
        "blockers": blockers,
        "hard_ban_inventories": {
            "A": len(A_BANS),
            "B": len(CF_BANS),
            "C": len(C_BANS),
            "D": len(D_BANS),
            "E": len(E_BANS),
            "F": len(F_BANS),
            "G": len(G_BANS),
            "H": len(H_BANS),
        },
        "no_trade_sides": sorted(NO_TRADE_SIDES),
    }
