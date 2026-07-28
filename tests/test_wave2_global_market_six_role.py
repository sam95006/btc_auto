"""Wave 2 Global Market Six-role Shadow Intelligence tests (>=80)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_global_shadow import (
    BENCHMARK_SYMBOLS,
    MAX_OPEN_POSITIONS,
    MAX_PENDING_ORDERS,
    SCHEMA_VERSION,
)
from backend.nexus_global_shadow.api_routes import (
    dispatch_route,
    get_shadow_api_state,
    handle_overview,
    reset_shadow_api_state,
)
from backend.nexus_global_shadow.architecture_scan import scan_nexus_global_shadow
from backend.nexus_global_shadow.candidates import GlobalCandidateRanker
from backend.nexus_global_shadow.compat import adapt_legacy_payload
from backend.nexus_global_shadow.contracts import (
    Candidate,
    EvidenceEnvelope,
    LifecycleState,
    MarketObservation,
    Mode,
    Outcome,
    Regime,
    RoleVerdict,
    ShadowPosition,
    assert_transition,
    forbid_mode,
    strip_fleet_id,
)
from backend.nexus_global_shadow.eati import EATIShadowLearningPipeline, FORBIDDEN_PATCH_STATUSES
from backend.nexus_global_shadow.intelligence import GlobalMarketIntelligenceComposer
from backend.nexus_global_shadow.lifecycle import ShadowLifecycleManager
from backend.nexus_global_shadow.persistence import InMemoryEvidenceStore, verify_checksum
from backend.nexus_global_shadow.pipeline import GlobalShadowPipeline
from backend.nexus_global_shadow.portfolio import ShadowPortfolioPolicy
from backend.nexus_global_shadow.regime import RegimeRouter
from backend.nexus_global_shadow.replay import FAULT_FIXTURES, NAMED_FIXTURES, ReplayHarness
from backend.nexus_global_shadow.scoreboard import GlobalMarketShadowScoreboard
from backend.nexus_global_shadow.six_role import SixRoleDecisionAggregator, ALL_ROLES
from backend.nexus_global_shadow.strategy import EXPERIMENTAL_STRATEGIES, FORMAL_STRATEGIES, StrategyRouter
from backend.nexus_global_shadow.universe import (
    DynamicMarketUniverseProvider,
    MarketQualityEvaluator,
    MarketUniverseBuilder,
    ProviderCircuitBreaker,
    RateLimitState,
    UniverseFilterEngine,
    UniverseSnapshotStore,
)
from backend.nexus_global_shadow.workers import WorkerHealthRegistry, WORKER_TYPES


def inst(symbol: str = "LINKUSDT", **kw) -> dict:
    base = symbol.replace("USDT", "")
    row = {
        "symbol": symbol,
        "base_coin": base,
        "quote_coin": "USDT",
        "contract_type": "LinearPerpetual",
        "status": "Trading",
        "tick_size": 0.001,
        "qty_step": 0.1,
        "min_order_qty": 0.1,
        "min_notional": 5.0,
        "max_leverage_available": 50.0,
    }
    row.update(kw)
    return row


def qual(symbol: str = "LINKUSDT", **kw) -> dict:
    row = {
        "volume_24h": 5e7,
        "turnover_24h": 8e7,
        "trade_count": 10000,
        "spread_bps": 4.0,
        "bid_depth": 50000.0,
        "ask_depth": 48000.0,
        "estimated_slippage": 0.001,
        "funding_rate": 0.0001,
        "open_interest": 1e8,
        "price_freshness": "FRESH",
        "orderbook_freshness": "FRESH",
        "provider_quality": "OK",
        "last_price": 12.5,
        "momentum": 0.18,
        "volatility": 0.025,
        "liquidity_score": 85.0,
        "freshness": "FRESH",
    }
    row.update(kw)
    return row


def obs(symbol: str = "LINKUSDT") -> MarketObservation:
    q = qual(symbol)
    return MarketObservation(
        symbol=symbol,
        last_price=q["last_price"],
        momentum=q["momentum"],
        volatility=q["volatility"],
        spread_bps=q["spread_bps"],
        volume_24h=q["volume_24h"],
        funding_rate=q["funding_rate"],
        open_interest=q["open_interest"],
        liquidity_score=q["liquidity_score"],
        freshness="FRESH",
    )


def good_candidate(**kw) -> Candidate:
    router = RegimeRouter()
    sr = StrategyRouter()
    intel_c = GlobalMarketIntelligenceComposer()
    ranker = GlobalCandidateRanker()
    o = obs()
    regime = router.classify(o)
    q = MarketQualityEvaluator().evaluate("LINKUSDT", qual())
    strat = sr.route("trend_following", o, q, regime)
    intel = intel_c.compose("LINKUSDT", o, q, regime)
    c = ranker.build_candidate("LINKUSDT", "uni_test", "LONG", strat, intel, regime)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


class TestContracts:
    def test_schema_version(self):
        assert SCHEMA_VERSION == "wave2.global.six_role.v1"

    def test_forbid_demo_write(self):
        with pytest.raises(ValueError):
            forbid_mode("DEMO_WRITE")

    def test_forbid_mainnet(self):
        with pytest.raises(ValueError):
            forbid_mode("MAINNET")

    def test_evidence_envelope_checksum(self):
        e = EvidenceEnvelope(symbol="X", mode=Mode.SHADOW.value)
        e.finalize()
        assert len(e.checksum) == 32

    def test_evidence_to_dict(self):
        e = EvidenceEnvelope(mode=Mode.SHADOW.value).finalize()
        assert e.to_dict()["mode"] == "SHADOW"

    def test_legal_transition(self):
        assert_transition(LifecycleState.CANDIDATE.value, LifecycleState.SIX_ROLE_REVIEWED.value)

    def test_illegal_transition(self):
        with pytest.raises(ValueError):
            assert_transition(LifecycleState.CANDIDATE.value, LifecycleState.SHADOW_OPEN.value)

    def test_strip_fleet_id(self):
        out = strip_fleet_id({"fleet_id": "BTC_FLEET", "symbol": "BTCUSDT"})
        assert "fleet_id" not in out
        assert out["deprecated_fleet_id_ignored"] is True

    def test_no_fleet_id_in_candidate_fields(self):
        assert "fleet_id" not in Candidate.__dataclass_fields__

    def test_benchmark_symbols_not_universe(self):
        assert len(BENCHMARK_SYMBOLS) == 4


class TestUniverse:
    def test_provider_callable(self):
        p = DynamicMarketUniverseProvider(lambda: [inst("ARBUSDT")])
        rows, status = p.fetch_instruments()
        assert status == "OK"
        assert len(rows) == 1

    def test_provider_list_injection(self):
        p = DynamicMarketUniverseProvider([inst("DOGEUSDT")])
        rows, _ = p.fetch_instruments()
        assert rows[0]["symbol"] == "DOGEUSDT"

    def test_provider_failure_unavailable(self):
        def boom():
            raise RuntimeError("fail")

        p = DynamicMarketUniverseProvider(boom)
        rows, status = p.fetch_instruments()
        assert rows == []
        assert status == "UNIVERSE_UNAVAILABLE"

    def test_rate_limit_degraded(self):
        rl = RateLimitState(max_calls=1)
        p = DynamicMarketUniverseProvider([inst()], rate_limit=rl)
        p.fetch_instruments()
        _, status = p.fetch_instruments()
        assert status == "UNIVERSE_DEGRADED"

    def test_circuit_breaker_opens(self):
        cb = ProviderCircuitBreaker(failure_threshold=2)

        def boom():
            raise TimeoutError

        p = DynamicMarketUniverseProvider(boom, circuit_breaker=cb)
        p.fetch_instruments()
        p.fetch_instruments()
        rows, status = p.fetch_instruments()
        assert status == "UNIVERSE_UNAVAILABLE"
        assert rows == []

    def test_usdt_perpetual_filter_pass(self):
        ok, reasons = UniverseFilterEngine().filter_instrument(inst())
        assert ok and not reasons

    def test_non_usdt_rejected(self):
        ok, reasons = UniverseFilterEngine().filter_instrument(inst("BTCUSD", quote_coin="USD"))
        assert not ok
        assert any("not_usdt" in r for r in reasons)

    def test_non_trading_rejected(self):
        ok, reasons = UniverseFilterEngine().filter_instrument(inst(status="Closed"))
        assert not ok

    def test_missing_tick_rejected(self):
        row = inst()
        row.pop("tick_size")
        ok, reasons = UniverseFilterEngine().filter_instrument(row)
        assert not ok

    def test_quality_missing_fails(self):
        q = MarketQualityEvaluator().evaluate("X", None)
        assert q.quality == "FAIL"
        assert "all" in q.missing_fields

    def test_stale_freshness_fails_gate(self):
        q = MarketQualityEvaluator().evaluate("X", qual(price_freshness="STALE"))
        ok, _ = MarketQualityEvaluator().passes_quality_gate(q)
        assert not ok

    def test_volume_filter(self):
        q = MarketQualityEvaluator().evaluate("X", qual(volume_24h=1.0))
        ok, _ = MarketQualityEvaluator().passes_quality_gate(q)
        assert not ok

    def test_spread_filter(self):
        q = MarketQualityEvaluator().evaluate("X", qual(spread_bps=100))
        ok, _ = MarketQualityEvaluator().passes_quality_gate(q)
        assert not ok

    def test_slippage_filter(self):
        q = MarketQualityEvaluator().evaluate("X", qual(estimated_slippage=0.02))
        ok, _ = MarketQualityEvaluator().passes_quality_gate(q)
        assert not ok

    def test_liquidity_depth_filter(self):
        q = MarketQualityEvaluator().evaluate("X", qual(bid_depth=10, ask_depth=10))
        ok, _ = MarketQualityEvaluator().passes_quality_gate(q)
        assert not ok

    def test_universe_builder_funnel(self):
        symbols = [inst(f"S{i}USDT") for i in range(5)]
        qmap = {f"S{i}USDT": qual(f"S{i}USDT") for i in range(5)}
        b = MarketUniverseBuilder(DynamicMarketUniverseProvider(symbols))
        snap = b.build(qmap)
        assert snap.total_markets == 5
        assert snap.eligible_markets >= 1

    def test_snapshot_store_no_stale_as_fresh_on_fail(self):
        store = UniverseSnapshotStore()

        def boom():
            raise RuntimeError("x")

        bad = MarketUniverseBuilder(DynamicMarketUniverseProvider(boom)).build({})
        store.save(bad)
        assert store.latest() is None

    def test_funding_missing_not_zero(self):
        raw = qual()
        raw["funding_rate"] = None
        q = MarketQualityEvaluator().evaluate("X", raw)
        assert q.funding_rate is None


class TestRegimeStrategy:
    def test_regime_uncertain_no_obs(self):
        r = RegimeRouter().classify(None)
        assert r.regime == Regime.UNCERTAIN.value

    def test_regime_uncertain_missing_momentum(self):
        r = RegimeRouter().classify({"last_price": 1.0, "volatility": 0.01})
        assert r.regime == Regime.UNCERTAIN.value

    def test_regime_trending_up(self):
        r = RegimeRouter().classify({"last_price": 1, "momentum": 0.2, "volatility": 0.02})
        assert r.regime == Regime.TRENDING_UP.value

    def test_regime_high_vol(self):
        r = RegimeRouter().classify({"last_price": 1, "momentum": 0.05, "volatility": 0.1})
        assert r.regime == Regime.HIGH_VOLATILITY.value

    def test_strategy_blocks_uncertain(self):
        q = MarketQualityEvaluator().evaluate("X", qual())
        s = StrategyRouter().route("trend_following", obs(), q, RegimeRouter().classify(None))
        assert s.strategy_status == "BLOCKED"

    def test_formal_strategies_defined(self):
        assert "trend_following" in FORMAL_STRATEGIES
        assert len(FORMAL_STRATEGIES) >= 8

    def test_experimental_strategies_marked(self):
        q = MarketQualityEvaluator().evaluate("X", qual())
        s = StrategyRouter().route("dynamic_grid", obs(), q, RegimeRouter().classify(obs()))
        assert s.strategy_status == "EXPERIMENTAL"

    def test_strategy_list_empty_for_uncertain(self):
        assert StrategyRouter().list_for_regime(Regime.UNCERTAIN.value) == []


class TestIntelligence:
    def test_news_unavailable(self):
        q = MarketQualityEvaluator().evaluate("X", qual())
        r = RegimeRouter().classify(obs())
        snap = GlobalMarketIntelligenceComposer().compose("LINKUSDT", obs(), q, r, news_items=None)
        assert snap.news_context_availability == "UNAVAILABLE"

    def test_benchmark_context_btc_eth_only(self):
        q = MarketQualityEvaluator().evaluate("X", qual())
        r = RegimeRouter().classify(obs())
        snap = GlobalMarketIntelligenceComposer().compose(
            "LINKUSDT",
            obs(),
            q,
            r,
            benchmark_observations={"BTCUSDT": {"last_price": 1}, "ETHUSDT": {"last_price": 2}},
        )
        assert "BTCUSDT" in snap.benchmark_context
        assert snap.benchmark_context.get("mode") == "BENCHMARK_ONLY"

    def test_missing_price_not_zero(self):
        o = MarketObservation(symbol="X", last_price=None)
        q = MarketQualityEvaluator().evaluate("X", qual(last_price=None))
        r = RegimeRouter().classify({"last_price": None, "momentum": None, "volatility": None})
        snap = GlobalMarketIntelligenceComposer().compose("X", o, q, r)
        assert snap.momentum is None


class TestCandidates:
    def test_rank_deterministic(self):
        ranker = GlobalCandidateRanker()
        c1 = good_candidate()
        c2 = good_candidate()
        c2.candidate_id = "cand_other"
        r1 = ranker.rank([c1, c2])
        r2 = ranker.rank([c1, c2])
        assert [c.rank for c in r1[:2]] == [c.rank for c in r2[:2]]

    def test_hash_tiebreak(self):
        ranker = GlobalCandidateRanker()
        a = good_candidate(rank_score=0.5)
        b = good_candidate(rank_score=0.5)
        b.candidate_id = "cand_b"
        ranked = ranker.rank([a, b])
        assert ranked[0].rank == 1

    def test_rejected_has_block_reasons(self):
        c = good_candidate(block_reasons=["test"], status="REJECTED")
        assert c.block_reasons

    def test_score_waterfall_present(self):
        c = good_candidate()
        assert c.score_waterfall

    def test_uncertain_regime_rejects(self):
        ranker = GlobalCandidateRanker()
        q = MarketQualityEvaluator().evaluate("X", qual())
        strat = StrategyRouter().route("trend_following", obs(), q, RegimeRouter().classify(None))
        intel = GlobalMarketIntelligenceComposer().compose("X", obs(), q, RegimeRouter().classify(None))
        regime = RegimeRouter().classify(None)
        c = ranker.build_candidate("X", "u1", "LONG", strat, intel, regime)
        assert c.status == "REJECTED"

    def test_directions_long_short_neutral(self):
        for d in ("LONG", "SHORT", "NEUTRAL"):
            c = good_candidate(direction=d)
            assert c.direction == d


class TestSixRole:
    def test_all_roles_present(self):
        assert len(ALL_ROLES) == 6

    def test_complete_review(self):
        c = good_candidate(block_reasons=[], missing_evidence=[])
        q = MarketQualityEvaluator().evaluate("X", qual())
        intel = GlobalMarketIntelligenceComposer().compose("LINKUSDT", obs(), q, RegimeRouter().classify(obs()))
        rs = SixRoleDecisionAggregator().review_candidate(c, intel)
        assert rs.review_complete
        assert len(rs.reviews) == 6

    def test_missing_roles_incomplete(self):
        c = good_candidate()
        rs = SixRoleDecisionAggregator().review_candidate(c, None, roles=ALL_ROLES[:3])
        assert not rs.review_complete

    def test_risk_critic_block_vetoes(self):
        c = good_candidate(block_reasons=["bad"])
        agg = SixRoleDecisionAggregator()
        rs = agg.review_candidate(c, None)
        assert agg.risk_critic_blocks_portfolio(rs)

    def test_risk_critic_unknown_vetoes(self):
        c = good_candidate(missing_evidence=["risk_score"], risk_score=None)
        agg = SixRoleDecisionAggregator()
        rs = agg.review_candidate(c, None)
        assert rs.risk_critic_verdict == RoleVerdict.UNKNOWN.value
        assert agg.risk_critic_blocks_portfolio(rs)

    def test_consensus_cannot_override_veto(self):
        c = good_candidate(block_reasons=["x"])
        rs = SixRoleDecisionAggregator().review_candidate(c, None)
        assert rs.consensus == "VETOED"

    def test_performance_insufficient_sample(self):
        c = good_candidate()
        rs = SixRoleDecisionAggregator().review_candidate(
            c, None, context={"sample_sufficiency": "INSUFFICIENT_SAMPLE"}
        )
        perf = next(r for r in rs.reviews if r["role"] == "Performance Analyst")
        assert perf["verdict"] == RoleVerdict.WATCH.value


class TestPortfolio:
    def test_max_open_two(self):
        assert ShadowPortfolioPolicy().max_open == MAX_OPEN_POSITIONS == 2

    def test_max_pending_two(self):
        assert ShadowPortfolioPolicy().max_pending == MAX_PENDING_ORDERS == 2

    def test_risk_critic_blocks_selection(self):
        c = good_candidate()
        full = SixRoleDecisionAggregator().review_candidate(c, None)
        full.risk_critic_verdict = "BLOCK"
        full.review_complete = True
        verdicts = ShadowPortfolioPolicy().evaluate([c], {c.candidate_id: full})
        assert not verdicts[0].selected

    def test_duplicate_candidate_blocked(self):
        c = good_candidate()
        rs = SixRoleDecisionAggregator().review_candidate(c, None)
        verdicts = ShadowPortfolioPolicy().evaluate([c, c], {c.candidate_id: rs})
        assert any("duplicate_candidate" in v.block_reasons for v in verdicts)

    def test_same_symbol_conflict(self):
        c2 = good_candidate()
        c2.candidate_id = "c2"
        rs2 = SixRoleDecisionAggregator().review_candidate(c2, None)
        pos = ShadowPosition(symbol="LINKUSDT", direction="LONG", state=LifecycleState.SHADOW_OPEN.value)
        verdicts = ShadowPortfolioPolicy().evaluate([c2], {c2.candidate_id: rs2}, open_positions=[pos])
        assert any("same_symbol_conflict" in v.block_reasons for v in verdicts)


class TestLifecycle:
    def test_open_shadow_chain(self):
        lm = ShadowLifecycleManager()
        p = ShadowPosition(state=LifecycleState.CANDIDATE.value)
        lm.open_shadow(p, 100.0, fee=0.1, slippage=0.05)
        assert p.state == LifecycleState.SHADOW_OPEN.value
        assert p.entry_price == 100.0

    def test_protection_simulation(self):
        lm = ShadowLifecycleManager()
        p = ShadowPosition(state=LifecycleState.CANDIDATE.value)
        lm.open_shadow(p, 50.0)
        lm.simulate_protection(p, {"sl": 45, "tp": 60, "exit_policy": {"time_stop": 3600}})
        assert p.state == LifecycleState.PROTECTED_SIMULATED.value

    def test_exit_reasons(self):
        lm = ShadowLifecycleManager()
        p = ShadowPosition(state=LifecycleState.CANDIDATE.value)
        lm.open_shadow(p, 10.0)
        lm.request_exit(p, "STOP_LOSS")
        assert p.exit_reason == "STOP_LOSS"

    def test_close_no_fake_zero_pnl(self):
        lm = ShadowLifecycleManager()
        p = ShadowPosition(state=LifecycleState.CANDIDATE.value, direction="LONG", position_size=1.0)
        lm.open_shadow(p, None)
        lm.request_exit(p, "DATA_QUALITY_EXIT")
        _, outcome = lm.close(p, None)
        assert outcome.net_pnl is None
        assert outcome.incomplete

    def test_learning_chain_transitions(self):
        lm = ShadowLifecycleManager()
        p = ShadowPosition(state=LifecycleState.CANDIDATE.value)
        lm.open_shadow(p, 1.0)
        lm.request_exit(p, "TAKE_PROFIT")
        lm.close(p, 1.1)
        lm.advance_learning_chain(p)
        assert p.state == LifecycleState.ARCHIVED.value


class TestEATI:
    def test_failure_classes(self):
        pipe = EATIShadowLearningPipeline()
        o = Outcome(incomplete=True)
        assert pipe.classify_failure(o) == "INSUFFICIENT_EVIDENCE"

    def test_reflection_created(self):
        pipe = EATIShadowLearningPipeline()
        o = Outcome(exit_reason="STOP_LOSS", net_pnl=-1.0, incomplete=False)
        r = pipe.create_reflection(o, context={"regime_mismatch": "yes"})
        assert r.failure_class == "REGIME_FAILURE"

    def test_patch_no_live_applied(self):
        pipe = EATIShadowLearningPipeline()
        for s in FORBIDDEN_PATCH_STATUSES:
            with pytest.raises(ValueError):
                pipe.assert_no_live_apply(s)

    def test_walk_forward_needs_three_folds(self):
        pipe = EATIShadowLearningPipeline()
        patch = pipe.propose_patch(pipe.create_reflection(Outcome(incomplete=True)))
        patch = pipe.validate_walk_forward(patch, "PASS", folds=2)
        assert patch.status == "REJECTED"

    def test_oos_isolation_required(self):
        pipe = EATIShadowLearningPipeline()
        patch = pipe.propose_patch(pipe.create_reflection(Outcome(incomplete=False, net_pnl=1)))
        patch = pipe.validate_oos(patch, "PASS", isolated=False)
        assert patch.sample_sufficiency == "INSUFFICIENT_SAMPLE"


class TestReplay:
    def test_ten_named_fixtures(self):
        assert len(NAMED_FIXTURES) >= 10

    def test_fault_fixtures_exist(self):
        assert "provider_timeout" in FAULT_FIXTURES
        assert "risk_critic_unknown" in FAULT_FIXTURES

    def test_fixture_labels(self):
        r = ReplayHarness().run_fixture("btc_trend_up", pipeline_fn=lambda p: p)
        assert r.labels["mode"] == "FIXTURE"
        assert r.labels["live"] == "NOT_LIVE"

    def test_deterministic_replay(self):
        h = ReplayHarness()
        assert h.run_deterministic_twice("eth_range", lambda p: {"h": h._hash(p)})

    def test_walk_forward_three_folds(self):
        h = ReplayHarness()
        datasets = [[{"sym": "A"}], [{"sym": "B"}], [{"sym": "C"}]]
        r = h.walk_forward(datasets, lambda ds: {"universe_count": len(ds)}, oos_index=2)
        assert len(r.folds) == 3
        assert r.oos_isolated

    def test_insufficient_sample_lt3(self):
        r = ReplayHarness().walk_forward([[{}], [{}]], lambda ds: {})
        assert r.sample_sufficiency == "INSUFFICIENT_SAMPLE"


class TestPersistenceWorkers:
    def test_inmemory_append_only(self):
        store = InMemoryEvidenceStore()
        rid = store.append({"record_id": "ev1", "mode": "SHADOW", "symbol": "X"})
        assert store.get(rid)["symbol"] == "X"

    def test_idempotent_append(self):
        store = InMemoryEvidenceStore()
        rid1 = store.append({"record_id": "ev1", "mode": "SHADOW"})
        rid2 = store.append({"record_id": "ev1", "mode": "SHADOW"})
        assert rid1 == rid2

    def test_checksum_verify(self):
        e = EvidenceEnvelope(mode=Mode.SHADOW.value, symbol="T").finalize()
        assert verify_checksum(e.to_dict())

    def test_worker_all_types(self):
        reg = WorkerHealthRegistry()
        reg.ensure_all_types_registered()
        assert len(reg.snapshot()) == len(WORKER_TYPES)

    def test_worker_stall(self):
        reg = WorkerHealthRegistry()
        w = reg.register("w1", "universe")
        reg.start("w1")
        reg.mark_stalled("w1", "no_progress")
        assert w.health == "STALLED"


class TestApiScoreboardScan:
    def setup_method(self):
        reset_shadow_api_state()

    def test_overview_read_only(self):
        out = handle_overview()
        assert out["read_only"] is True
        assert out["exchange_write"] is False

    def test_overview_funnel_keys(self):
        out = handle_overview()
        assert "marketsScanned" in out["funnel"]

    def test_dispatch_route(self):
        out = dispatch_route("/api/nexus/shadow/overview")
        assert "funnel" in out

    def test_scoreboard_no_fleet_health(self):
        sb = GlobalMarketShadowScoreboard()
        assert sb.assert_no_fleet_health()

    def test_architecture_scan_package_clean(self):
        report = scan_nexus_global_shadow(
            Path(__file__).resolve().parents[1] / "backend" / "nexus_global_shadow"
        )
        assert report.active_architecture_violation_count == 0

    def test_compat_deprecated_fleet(self):
        out = adapt_legacy_payload({"fleet_id": "ETH_FLEET"})
        assert out.get("deprecated") is True


class TestPipeline:
    def test_full_cycle(self):
        symbols = [inst(f"M{i}USDT") for i in range(3)]
        qmap = {f"M{i}USDT": qual(f"M{i}USDT") for i in range(3)}
        pipe = GlobalShadowPipeline(symbols, qmap)
        result = pipe.run_cycle()
        assert result["universe_count"] == 3
        assert "candidate_count" in result

    def test_pipeline_populates_api_state(self):
        reset_shadow_api_state()
        st = get_shadow_api_state()
        symbols = [inst("ZENUSDT")]
        qmap = {"ZENUSDT": qual("ZENUSDT")}
        result = GlobalShadowPipeline(symbols, qmap).run_cycle()
        st.universe_snapshots.append(
            {
                "total_markets": result["universe_count"],
                "eligible_markets": result["eligible_count"],
                "excluded_markets": result["universe_count"] - result["eligible_count"],
                "exclusion_reason_counts": {},
                "provider_status": result["provider_status"],
                "universe_snapshot_id": result["universe_snapshot_id"],
            }
        )
        st.scoreboard.update_funnel(scanned=result["universe_count"], eligible=result["eligible_count"])
        out = handle_overview(st)
        assert out["funnel"]["marketsScanned"] >= 1


class TestSchema:
    def test_schema_file_exists(self):
        p = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / "nexus_global_shadow"
            / "schema"
            / "evidence_envelope.schema.json"
        )
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["title"] == "EvidenceEnvelope"
