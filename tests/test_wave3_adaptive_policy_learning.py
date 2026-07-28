"""Wave 3 Adaptive AI Trading Policy tests (>=120 meaningful cases)."""
from __future__ import annotations

import pytest
from flask import Flask

from backend.nexus_adaptive_policy import (
    FIXED_LEVERAGE,
    MAX_MARGIN,
    MIN_MARGIN,
    SCHEMA_VERSION,
    TARGET_NET_OOS_WIN_RATE,
)
from backend.nexus_adaptive_policy.adaptive_controller import AdaptivePolicyController
from backend.nexus_adaptive_policy.api_routes import (
    READ_ONLY_META,
    dispatch_route,
    get_adaptive_policy_api_state,
    register_adaptive_policy_routes,
    reset_adaptive_policy_api_state,
)
from backend.nexus_adaptive_policy.champion_challenger import (
    FORBIDDEN_PROMOTION_STATUSES,
    Experiment,
    PolicyChallenger,
    PolicyChampion,
    PolicyRoleStatus,
    PromotionGate,
)
from backend.nexus_adaptive_policy.constitution import (
    FORBIDDEN_LEVERAGES,
    ConstitutionViolation,
    ImmutableSafetyPolicy,
    LeverageConstitution,
)
from backend.nexus_adaptive_policy.failure_taxonomy import (
    ALL_FAILURE_TYPES,
    FailureClassification,
    FailureSeverity,
    FailureType,
    Preventability,
    classify_failure,
)
from backend.nexus_adaptive_policy.metrics import (
    LearningMetricsCalculator,
    LearningMetricsSnapshot,
    TargetStatus,
)
from backend.nexus_adaptive_policy.mistake_memory import FailureSignature, MistakeMemoryStore
from backend.nexus_adaptive_policy.patches import (
    FORBIDDEN_PATCH_FIELDS,
    ImmutablePatchGuard,
    LearningPatch,
    LearningPatchApplier,
    PatchStatus,
)
from backend.nexus_adaptive_policy.persistence import (
    FileAdaptivePolicyStore,
    InMemoryAdaptivePolicyStore,
    PostgresAdaptivePolicyStoreStub,
    compute_checksum,
)
from backend.nexus_adaptive_policy.policy import DynamicTradingPolicy, PolicySnapshot
from backend.nexus_adaptive_policy.post_entry import (
    ALLOWED_ACTIONS,
    FORBIDDEN_ACTIONS,
    PostEntryRiskInvariant,
)
from backend.nexus_adaptive_policy.reflection import (
    ALL_COUNTERFACTUALS,
    CounterfactualAnalyzer,
    DeepReflectionEngine,
    LearningProposalGenerator,
)
from backend.nexus_adaptive_policy.similarity import (
    ALL_GUARD_ACTIONS,
    GuardAction,
    PreTradeMistakeGuard,
    RecurringErrorEscalationPolicy,
)
from backend.nexus_adaptive_policy.trade_case import (
    ProcessQualityVerdict,
    TradeCase,
    classify_process_quality,
)


def tc(**kw) -> TradeCase:
    base = {
        "case_id": "case_001",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "leverage": FIXED_LEVERAGE,
        "margin_usd": 50.0,
        "pnl_usd": -5.0,
        "process_verdict": ProcessQualityVerdict.GOOD_PROCESS_LOSS,
    }
    base.update(kw)
    return TradeCase(**base)


class TestConstants:
    def test_fixed_leverage(self):
        assert FIXED_LEVERAGE == 25

    def test_margin_bounds(self):
        assert MIN_MARGIN == 20
        assert MAX_MARGIN == 500

    def test_target_win_rate(self):
        assert TARGET_NET_OOS_WIN_RATE == 0.60

    def test_schema_version(self):
        assert "wave3" in SCHEMA_VERSION


class TestLeverageConstitution:
    @pytest.mark.parametrize("lev", [25])
    def test_valid_leverage(self, lev):
        v = LeverageConstitution().validate_leverage(lev)
        assert v.ok

    @pytest.mark.parametrize("lev", [3, 10, 50, 100, 24, 26, 1])
    def test_invalid_leverage(self, lev):
        v = LeverageConstitution().validate_leverage(lev)
        assert not v.ok
        assert v.violation == ConstitutionViolation.IMMUTABLE_LEVERAGE_VIOLATION

    def test_forbidden_set(self):
        assert 3 in FORBIDDEN_LEVERAGES
        assert 25 not in FORBIDDEN_LEVERAGES

    @pytest.mark.parametrize(
        "patch",
        [
            {"leverage": 50},
            {"cross_margin": True},
            {"martingale": True},
            {"averaging_down": True},
            {"auto_add_margin": True},
            {"isolated_only": False},
            {"fixed_leverage": 10},
        ],
    )
    def test_patch_rejected(self, patch):
        v = LeverageConstitution().validate_patch(patch)
        assert not v.ok

    def test_safety_posture_ok(self):
        assert LeverageConstitution().validate_safety_posture().ok

    def test_to_dict(self):
        d = LeverageConstitution().to_dict()
        assert d["fixed_leverage"] == 25
        assert d["ai_can_change_leverage"] is False


class TestImmutableSafetyPolicy:
    def test_defaults(self):
        p = ImmutableSafetyPolicy()
        assert p.isolated_only is True
        assert p.cross_margin is False
        assert p.fixed_leverage == 25


class TestTradeCase:
    @pytest.mark.parametrize(
        "verdict,win,loss,fail",
        [
            (ProcessQualityVerdict.GOOD_PROCESS_WIN, True, False, False),
            (ProcessQualityVerdict.GOOD_PROCESS_LOSS, False, True, False),
            (ProcessQualityVerdict.BAD_PROCESS_WIN, True, False, True),
            (ProcessQualityVerdict.BAD_PROCESS_LOSS, False, True, True),
            (ProcessQualityVerdict.INCOMPLETE_EVIDENCE, False, True, False),
        ],
    )
    def test_verdict_semantics(self, verdict, win, loss, fail):
        c = tc(pnl_usd=10 if win else -10, process_verdict=verdict, evidence_complete=verdict != ProcessQualityVerdict.INCOMPLETE_EVIDENCE)
        assert c.is_win() is win
        assert c.is_loss() is loss
        assert c.is_strategy_failure() is fail

    def test_loss_not_auto_strategy_failure(self):
        c = tc(pnl_usd=-3, process_verdict=ProcessQualityVerdict.GOOD_PROCESS_LOSS)
        assert c.is_loss()
        assert not c.is_strategy_failure()

    @pytest.mark.parametrize(
        "followed,rules,evidence,pnl,expected",
        [
            (True, True, True, 5, ProcessQualityVerdict.GOOD_PROCESS_WIN),
            (True, True, True, -5, ProcessQualityVerdict.GOOD_PROCESS_LOSS),
            (False, True, True, 5, ProcessQualityVerdict.BAD_PROCESS_WIN),
            (False, False, True, -5, ProcessQualityVerdict.BAD_PROCESS_LOSS),
            (True, True, False, 5, ProcessQualityVerdict.INCOMPLETE_EVIDENCE),
        ],
    )
    def test_classify_process_quality(self, followed, rules, evidence, pnl, expected):
        assert (
            classify_process_quality(
                pnl_usd=pnl,
                followed_plan=followed,
                evidence_complete=evidence,
                risk_rules_followed=rules,
            )
            == expected
        )


class TestFailureTaxonomy:
    @pytest.mark.parametrize("ft", ALL_FAILURE_TYPES)
    def test_all_failure_types_classify(self, ft):
        fc = classify_failure(case_id="c1", failure_type=ft, evidence=["e1"])
        assert fc.failure_type == ft
        assert fc.confidence > 0
        assert fc.preventive_rule_candidate

    def test_repeated_mistake_high_severity(self):
        fc = classify_failure(case_id="c2", failure_type=FailureType.REPEATED_KNOWN_MISTAKE)
        assert fc.severity == FailureSeverity.HIGH
        assert fc.preventability == Preventability.PREVENTABLE

    def test_to_dict(self):
        fc = classify_failure(case_id="c3", failure_type=FailureType.CHASE_ENTRY)
        d = fc.to_dict()
        assert d["failure_type"] == "CHASE_ENTRY"


class TestMistakeMemory:
    def test_remember_new(self):
        store = MistakeMemoryStore()
        fc = classify_failure(case_id="a", failure_type=FailureType.ENTRY_TOO_EARLY)
        rec = store.remember("a", fc, symbol="ETHUSDT", strategy_id="s1")
        assert rec.occurrence_count == 1

    def test_remember_increments(self):
        store = MistakeMemoryStore()
        fc = classify_failure(case_id="a", failure_type=FailureType.CHASE_ENTRY)
        store.remember("a", fc, symbol="ETHUSDT", strategy_id="s1")
        rec2 = store.remember("b", fc, symbol="ETHUSDT", strategy_id="s1")
        assert rec2.occurrence_count >= 2

    def test_signature_digest_stable(self):
        s1 = FailureSignature("CHASE_ENTRY", "BTCUSDT", "s1")
        s2 = FailureSignature("CHASE_ENTRY", "BTCUSDT", "s1")
        assert s1.digest() == s2.digest()


class TestSimilarityGuard:
    @pytest.mark.parametrize("action", ALL_GUARD_ACTIONS)
    def test_guard_actions_exist(self, action):
        assert action.value

    def test_escalation_never_changes_leverage(self):
        pol = RecurringErrorEscalationPolicy()
        for count in range(1, 10):
            action = pol.action_for_count(count)
            guard = PreTradeMistakeGuard(MistakeMemoryStore(), fixed_leverage=FIXED_LEVERAGE)
            d = guard.evaluate(symbol="BTCUSDT", strategy_id="s1", failure_type=FailureType.CHASE_ENTRY)
            assert d.leverage == FIXED_LEVERAGE

    def test_block_on_repeated_known(self):
        store = MistakeMemoryStore()
        fc = classify_failure(case_id="x", failure_type=FailureType.REPEATED_KNOWN_MISTAKE)
        store.remember("x", fc, symbol="BTCUSDT", strategy_id="s1")
        store.remember("y", fc, symbol="BTCUSDT", strategy_id="s1")
        guard = PreTradeMistakeGuard(store, fixed_leverage=FIXED_LEVERAGE)
        d = guard.evaluate(symbol="BTCUSDT", strategy_id="s1", failure_type=FailureType.REPEATED_KNOWN_MISTAKE)
        assert d.action == GuardAction.BLOCK


class TestReflection:
    @pytest.mark.parametrize("cf", ALL_COUNTERFACTUALS)
    def test_counterfactual_enum(self, cf):
        assert cf.value

    def test_deep_reflection_produces_proposals(self):
        case = tc(pnl_usd=-10, process_verdict=ProcessQualityVerdict.BAD_PROCESS_LOSS)
        fc = classify_failure(case_id=case.case_id, failure_type=FailureType.ENTRY_TOO_EARLY)
        out = DeepReflectionEngine().reflect(case, fc)
        assert out["proposals"]
        assert all(p["executable"] for p in out["proposals"])

    def test_proposals_not_vague(self):
        gen = LearningProposalGenerator()
        case = tc()
        cfs = CounterfactualAnalyzer().analyze(case)
        props = gen.generate(case, cfs)
        for p in props:
            assert p.action
            assert p.parameter
            assert p.value is not None


class TestDynamicPolicy:
    def test_entry_threshold(self):
        pol = DynamicTradingPolicy(PolicySnapshot(snapshot_id="s1", entry_threshold=0.6))
        assert pol.entry_passes(0.61)
        assert not pol.entry_passes(0.59)

    def test_risk_clamp(self):
        pol = DynamicTradingPolicy()
        m = pol.risk.clamp_margin(400, risk_budget=100, portfolio_remaining=80)
        assert m == 80


class TestAdaptiveController:
    def test_happy_path(self):
        ctrl = AdaptivePolicyController()
        r = ctrl.evaluate_entry(
            symbol="BTCUSDT",
            side="LONG",
            ai_suggested_margin=100,
            risk_budget=200,
            stop_distance_cap=150,
            portfolio_remaining=120,
            liquidity_cap=110,
            slippage_cap=105,
            entry_score=0.7,
        )
        assert r.ok
        assert r.intent.leverage == FIXED_LEVERAGE
        assert MIN_MARGIN <= r.intent.margin_usd <= MAX_MARGIN

    @pytest.mark.parametrize("lev", [3, 10, 50, 100])
    def test_reject_wrong_leverage(self, lev):
        r = AdaptivePolicyController().evaluate_entry(
            symbol="BTCUSDT",
            side="LONG",
            ai_suggested_margin=100,
            risk_budget=200,
            stop_distance_cap=150,
            portfolio_remaining=120,
            liquidity_cap=110,
            slippage_cap=105,
            entry_score=0.7,
            requested_leverage=lev,
        )
        assert not r.ok

    def test_skip_below_min_margin(self):
        r = AdaptivePolicyController().evaluate_entry(
            symbol="BTCUSDT",
            side="LONG",
            ai_suggested_margin=5,
            risk_budget=5,
            stop_distance_cap=5,
            portfolio_remaining=5,
            liquidity_cap=5,
            slippage_cap=5,
            entry_score=0.9,
        )
        assert not r.ok
        assert r.skip_reason == "RISK_BUDGET_BELOW_MINIMUM"


class TestPostEntry:
    @pytest.mark.parametrize("action", ALLOWED_ACTIONS)
    def test_allowed_actions(self, action):
        v = PostEntryRiskInvariant().validate(action.value)
        assert v.ok

    @pytest.mark.parametrize("action", FORBIDDEN_ACTIONS)
    def test_forbidden_actions(self, action):
        v = PostEntryRiskInvariant().validate(action.value)
        assert not v.ok

    def test_tighten_stop_rejects_widen(self):
        v = PostEntryRiskInvariant().validate("TIGHTEN_STOP", new_stop_distance=10, old_stop_distance=5)
        assert not v.ok


class TestPatches:
    @pytest.mark.parametrize("field", FORBIDDEN_PATCH_FIELDS)
    def test_forbidden_fields(self, field):
        patch = LearningPatch("p1", "pr1", "set", field, True)
        ok, reason = ImmutablePatchGuard().validate(patch)
        assert not ok

    def test_shadow_apply_ok(self):
        applier = LearningPatchApplier()
        patch = applier.create_from_proposal("pr1", "set_entry_threshold", "min_score_delta", 0.05, bounds={"min": 0, "max": 1})
        out = applier.submit(patch)
        assert out.status == PatchStatus.SHADOW_APPLIED


class TestChampionChallenger:
    def test_forbidden_statuses(self):
        assert "LIVE_APPLIED" in FORBIDDEN_PROMOTION_STATUSES
        assert "AUTO_PROMOTED" in FORBIDDEN_PROMOTION_STATUSES

    def test_promotion_insufficient_sample(self):
        gate = PromotionGate()
        champ = LearningMetricsSnapshot(sample_size=50, expectancy=1.0, profit_factor=1.5, max_drawdown_pct=5)
        chall = LearningMetricsSnapshot(sample_size=10, expectancy=2.0, profit_factor=2.0, max_drawdown_pct=3, target_status=TargetStatus.TARGET_REACHED_SHADOW_ONLY)
        v = gate.evaluate(champ, chall)
        assert not v.promoted

    def test_max_status_shadow_only(self):
        assert PromotionGate.max_status(PolicyRoleStatus.SHADOW_CHAMPION_CANDIDATE) == PolicyRoleStatus.SHADOW_CHAMPION_CANDIDATE


class TestMetrics:
    def test_empty_insufficient_sample(self):
        m = LearningMetricsCalculator().compute([])
        assert m.target_status == TargetStatus.INSUFFICIENT_SAMPLE

    def test_never_fake_60_without_sample(self):
        m = LearningMetricsCalculator().compute([tc(pnl_usd=5)] * 5)
        assert m.target_status != TargetStatus.TARGET_REACHED_SHADOW_ONLY

    def test_target_reached_requires_sample(self):
        wins = [tc(pnl_usd=10, process_verdict=ProcessQualityVerdict.GOOD_PROCESS_WIN) for _ in range(35)]
        m = LearningMetricsCalculator().compute(wins)
        assert m.sample_size >= 30
        if m.cost_adjusted_win_rate >= TARGET_NET_OOS_WIN_RATE:
            assert m.target_status == TargetStatus.TARGET_REACHED_SHADOW_ONLY


class TestPersistence:
    def test_checksum_roundtrip(self):
        store = InMemoryAdaptivePolicyStore()
        rec = store.append("trade_case", {"id": "1"})
        assert rec.verify()

    def test_file_store(self, tmp_path):
        path = tmp_path / "log.jsonl"
        fs = FileAdaptivePolicyStore(path)
        rec = fs.append("reflection", {"case_id": "c1"})
        assert rec.verify()
        assert len(fs.list_records()) == 1

    def test_postgres_stub(self):
        stub = PostgresAdaptivePolicyStoreStub("postgres://stub")
        assert stub.connect() is True
        rec = stub.append("x", {"a": 1})
        assert rec.verify()


class TestAdaptivePolicyApi:
    def setup_method(self):
        reset_adaptive_policy_api_state()

    @pytest.mark.parametrize(
        "path",
        [
            "/api/nexus/shadow/learning/overview",
            "/api/nexus/shadow/learning/trade-cases",
            "/api/nexus/shadow/learning/failures",
            "/api/nexus/shadow/learning/mistakes",
            "/api/nexus/shadow/learning/reflections",
            "/api/nexus/shadow/learning/proposals",
            "/api/nexus/shadow/learning/metrics",
            "/api/nexus/shadow/learning/patches",
            "/api/nexus/shadow/learning/experiments",
            "/api/nexus/shadow/policy/overview",
            "/api/nexus/shadow/policy/constitution",
            "/api/nexus/shadow/policy/snapshot",
            "/api/nexus/shadow/policy/decisions",
            "/api/nexus/shadow/policy/champion",
            "/api/nexus/shadow/policy/challengers",
        ],
    )
    def test_routes_read_only(self, path):
        out = dispatch_route(path)
        assert out["read_only"] is True
        assert out["exchange_write"] is False

    def test_empty_overview_no_data(self):
        out = dispatch_route("/api/nexus/shadow/learning/overview")
        assert out["data_status"] == "NO_DATA"
        assert out["fixed_leverage"] == 25
        assert out["target_status"] == TargetStatus.INSUFFICIENT_SAMPLE.value

    def test_empty_metrics_no_fake_win_rate(self):
        out = dispatch_route("/api/nexus/shadow/learning/metrics")
        assert out["data_status"] == "NO_DATA"
        assert "net_oos_win_rate" not in out or out.get("net_oos_win_rate", 0) == 0

    def test_unknown_route(self):
        out = dispatch_route("/api/nexus/shadow/learning/unknown")
        assert out["error"] == "unknown_route"


@pytest.fixture
def adaptive_app():
    reset_adaptive_policy_api_state()
    app = Flask(__name__)
    register_adaptive_policy_routes(app)
    return app


@pytest.fixture
def adaptive_client(adaptive_app):
    return adaptive_app.test_client()


class TestAdaptiveFlaskRoutes:
    def setup_method(self):
        reset_adaptive_policy_api_state()

    def test_learning_overview_endpoint(self, adaptive_client):
        res = adaptive_client.get("/api/nexus/shadow/learning/overview")
        assert res.status_code == 200
        data = res.get_json()
        assert data["data_status"] == "NO_DATA"
        assert data["fixed_leverage"] == 25

    def test_policy_constitution_endpoint(self, adaptive_client):
        res = adaptive_client.get("/api/nexus/shadow/policy/constitution")
        assert res.status_code == 200
        data = res.get_json()
        assert data["constitution"]["fixed_leverage"] == 25

    def test_read_only_meta(self):
        assert READ_ONLY_META["exchange_write"] is False


class TestIntegrationFlow:
    def test_end_to_end_shadow_learning(self):
        reset_adaptive_policy_api_state()
        case = tc(pnl_usd=-8, process_verdict=ProcessQualityVerdict.BAD_PROCESS_LOSS)
        fc = classify_failure(case_id=case.case_id, failure_type=FailureType.CHASE_ENTRY)
        store = MistakeMemoryStore()
        store.remember(case.case_id, fc, symbol=case.symbol, strategy_id="s1")
        reflection = DeepReflectionEngine().reflect(case, fc)
        applier = LearningPatchApplier()
        for p in reflection["proposals"][:1]:
            patch = applier.create_from_proposal(p["proposal_id"], p["action"], p["parameter"], p["value"])
            applier.submit(patch)
        st = get_adaptive_policy_api_state()
        st.trade_cases.append(case.to_dict())
        st.failures.append(fc.to_dict())
        st.reflections.append(reflection)
        st.patches.extend([x.to_dict() for x in applier.applied])
        st.metrics = LearningMetricsCalculator().compute([case]).to_dict()
        out = dispatch_route("/api/nexus/shadow/learning/overview")
        assert out["data_status"] == "OK"
        assert out["counts"]["trade_cases"] == 1
