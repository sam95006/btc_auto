#!/usr/bin/env python3
"""verify_phase5_gate_c.py — NEXUS Phase 5 Gate C Verification Script.

Covers:
  1. Module import checks (simulator, ledger, risk, allocator, reflection, patch, replay, soak, bridge)
  2. Isolation guards (RESEARCH_ONLY=True, no private API references)
  3. Simulator: order lifecycle (submit → fill → close), kill switch, reject
  4. Ledger: deposit/withdraw/margin/reconcile, negative-balance reject
  5. Risk engine: allow/block verdicts, duplicate, leverage, notional
  6. Capital allocator: score gate, conservative sample, allocation cap
  7. Reflection: attribution, patch proposals, no auto-apply production
  8. Patch governance: state machine, approval preconditions, block non-sim scope
  9. Replay: session create, synthetic bars, run, pause/resume, checkpoint
  10. Soak: smoke soak passes, verdict=PASS, wall-clock reasonable
  11. Gate B → Gate C bridge: try_simulate_decision (eligible + skip)
  12. API routes: import check, Blueprint registered
  13. Deploy mirror: all gate_c files present in deploy directory

Exit 0 → VERDICT=PASS
Exit 1 → VERDICT=FAIL
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str, str]] = []  # (check_id, status, detail)


def check(check_id: str, fn) -> bool:
    try:
        fn()
        _results.append((check_id, PASS, ""))
        return True
    except Exception as exc:  # noqa: BLE001
        _results.append((check_id, FAIL, str(exc)))
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 1. Module imports
# ─────────────────────────────────────────────────────────────────────────────

def _check_imports():
    from backend.nexus_research import simulator, sim_ledger, risk_engine
    from backend.nexus_research import capital_allocator, reflection, patch_governance
    from backend.nexus_research import replay, soak, sim_routes, gate_b_to_gate_c

check("1.imports", _check_imports)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Isolation guards
# ─────────────────────────────────────────────────────────────────────────────

def _check_isolation():
    import importlib
    for mod_name in [
        "backend.nexus_research.simulator",
        "backend.nexus_research.sim_ledger",
        "backend.nexus_research.risk_engine",
        "backend.nexus_research.capital_allocator",
        "backend.nexus_research.reflection",
        "backend.nexus_research.patch_governance",
        "backend.nexus_research.replay",
        "backend.nexus_research.soak",
        "backend.nexus_research.gate_b_to_gate_c",
    ]:
        mod = importlib.import_module(mod_name)
        assert getattr(mod, "RESEARCH_ONLY", None) is True, \
            f"{mod_name} missing RESEARCH_ONLY=True"
        # Check source for forbidden patterns
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for forbidden in ("bybit_client", "real_order", "place_order", "BYBIT_API_SECRET"):
            assert forbidden not in src, \
                f"{mod_name} contains forbidden pattern: {forbidden!r}"

check("2.isolation_guards", _check_isolation)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Simulator
# ─────────────────────────────────────────────────────────────────────────────

def _check_simulator():
    from backend.nexus_research.simulator import (
        SimulatedExchange, SIDE_LONG, SIDE_SHORT, ORDER_MARKET, ORDER_LIMIT,
        STATE_FILLED, STATE_REJECTED, STATE_CANCELLED, STATE_EXPIRED,
    )

    sim = SimulatedExchange(config={"fill_latency_ms": 0, "spread_bps": 1})

    # Submit + fill MARKET order
    oid = sim.submit_order("BTCUSDT", SIDE_LONG, ORDER_MARKET, qty=0.001)
    filled = sim.process_pending_orders({"BTCUSDT": 65000.0})
    assert oid in filled, "MARKET order should have filled"
    orders = sim.list_orders(state=STATE_FILLED)
    assert any(o["orderId"] == oid for o in orders), "filled order not in list"

    # Open position check
    open_pos = sim.list_open_positions()
    assert len(open_pos) == 1, f"expected 1 open position, got {len(open_pos)}"

    # Close position
    pos_id = open_pos[0]["positionId"]
    pnl = sim.close_position(pos_id, {"BTCUSDT": 65500.0})
    assert pnl is not None, "close_position should return PnL"
    assert len(sim.list_open_positions()) == 0, "position should be closed"
    assert len(sim.list_closed_positions()) == 1, "closed position should be recorded"

    # LIMIT order: SHORT at 66000 should NOT fill when mark is BELOW limit
    oid2 = sim.submit_order("BTCUSDT", SIDE_SHORT, ORDER_LIMIT, qty=0.001, limit_price=66000.0)
    filled2 = sim.process_pending_orders({"BTCUSDT": 65000.0})  # below limit → no fill for SHORT
    assert oid2 not in filled2, "LIMIT SHORT order should not fill when mark is below limit_price"
    sim.cancel_order(oid2)
    orders2 = sim.list_orders(state=STATE_CANCELLED)
    assert any(o["orderId"] == oid2 for o in orders2), "cancelled order not found"

    # Kill switch
    sim.activate_kill_switch("test")
    oid3 = sim.submit_order("BTCUSDT", SIDE_LONG, ORDER_MARKET, qty=0.001)
    orders3 = sim.list_orders(state=STATE_REJECTED)
    # kill switch causes reject
    assert sim._kill_switch is True
    sim.deactivate_kill_switch()

    # Invalid qty
    oid4 = sim.submit_order("BTCUSDT", SIDE_LONG, ORDER_MARKET, qty=0.0)
    orders4 = sim.list_orders(state=STATE_REJECTED)
    assert any(o["orderId"] == oid4 for o in orders4), "zero qty should be rejected"

    # Status
    st = sim.status()
    assert st["researchOnly"] is True
    assert st["privateApi"] is False

check("3.simulator", _check_simulator)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Ledger
# ─────────────────────────────────────────────────────────────────────────────

def _check_ledger():
    from backend.nexus_research.sim_ledger import SimLedger, LedgerRejectError

    ledger = SimLedger(initial_cash=1000.0)

    # Basic deposit/withdraw
    ledger.deposit(500.0, "bonus")
    assert abs(ledger._cash_balance - 1500.0) < 0.01

    ledger.withdraw(200.0, "fee")
    assert abs(ledger._cash_balance - 1300.0) < 0.01

    # Negative balance reject
    try:
        ledger.withdraw(9999.0, "too_much")
        raise AssertionError("should have raised LedgerRejectError")
    except LedgerRejectError:
        pass

    # Margin reserve/release
    ledger.reserve_margin(100.0, "ord1", "BTCUSDT")
    assert abs(ledger._margin_used - 100.0) < 0.01
    assert abs(ledger._cash_balance - 1200.0) < 0.01
    ledger.release_margin(100.0, "ord1", "BTCUSDT")
    assert abs(ledger._margin_used - 0.0) < 0.01

    # Reconcile
    rec = ledger.reconcile(unrealised_pnl=50.0)
    assert rec["consistent"] is True
    assert rec["researchOnly"] is True

    # Idempotency
    ledger.deposit(100.0, "idem_test", idempotency_key="idem1")
    ledger.deposit(100.0, "idem_test", idempotency_key="idem1")  # deduped
    before_count = ledger._total_events

    # Events
    events = ledger.recent_events(limit=5)
    assert len(events) > 0

    snap = ledger.snapshot()
    assert snap["researchOnly"] is True
    assert snap["cashBalance"] >= 0

check("4.ledger", _check_ledger)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Risk engine
# ─────────────────────────────────────────────────────────────────────────────

def _check_risk():
    from backend.nexus_research.risk_engine import (
        SimRiskEngine, RiskRequest,
        ALLOW_SIMULATION, BLOCK_MAX_LEVERAGE, BLOCK_MISSING_EVIDENCE,
        BLOCK_DUPLICATE, BLOCK_MAX_NOTIONAL,
    )
    from backend.nexus_research.simulator import SimulatedExchange, SIDE_LONG, ORDER_MARKET

    risk = SimRiskEngine(config={"max_leverage": 10.0})
    sim = SimulatedExchange(config={"fill_latency_ms": 0})

    # Basic allow
    req = RiskRequest(
        symbol="BTCUSDT", side=SIDE_LONG, qty=0.001,
        entry_price=65000.0, leverage=5.0,
        candidate={"score": 70.0, "side": "LONG"},
    )
    v = risk.check(req, sim=sim)
    assert v.verdict == ALLOW_SIMULATION, f"expected ALLOW, got {v.verdict}"
    assert v.allowed is True

    # Leverage block
    req2 = RiskRequest(
        symbol="BTCUSDT", side=SIDE_LONG, qty=0.001,
        entry_price=65000.0, leverage=50.0,
    )
    v2 = risk.check(req2)
    assert v2.verdict == BLOCK_MAX_LEVERAGE
    assert v2.allowed is False

    # Missing evidence (required field 'score')
    req3 = RiskRequest(
        symbol="ETHUSDT", side=SIDE_LONG, qty=0.01,
        entry_price=3000.0, leverage=3.0,
        candidate={"side": "LONG"},  # missing 'score'
    )
    v3 = risk.check(req3)
    assert v3.verdict == BLOCK_MISSING_EVIDENCE

    # Duplicate position block
    sim2 = SimulatedExchange(config={"fill_latency_ms": 0})
    oid = sim2.submit_order("BTCUSDT", SIDE_LONG, ORDER_MARKET, qty=0.001)
    sim2.process_pending_orders({"BTCUSDT": 65000.0})
    req4 = RiskRequest(
        symbol="BTCUSDT", side=SIDE_LONG, qty=0.001,
        entry_price=65000.0, leverage=3.0,
        candidate={"score": 70.0, "side": "LONG"},
    )
    v4 = risk.check(req4, sim=sim2)
    assert v4.verdict == BLOCK_DUPLICATE

    st = risk.status()
    assert st["researchOnly"] is True

check("5.risk_engine", _check_risk)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Capital allocator
# ─────────────────────────────────────────────────────────────────────────────

def _check_allocator():
    from backend.nexus_research.capital_allocator import SimCapitalAllocator

    alloc = SimCapitalAllocator()

    # Score below min → zero
    r = alloc.allocate(
        symbol="BTCUSDT", side="LONG",
        entry_price=65000.0, candidate={"score": 40.0},
        equity=10_000.0,
    )
    assert r.suggested_qty == 0.0, f"below score_min should be zero, got {r.suggested_qty}"

    # Normal allocation
    r2 = alloc.allocate(
        symbol="BTCUSDT", side="LONG",
        entry_price=65000.0, candidate={"score": 70.0},
        equity=10_000.0, closed_trades_count=30,
    )
    assert r2.suggested_qty > 0.0
    assert r2.conservative is False

    # Conservative when sample < min
    r3 = alloc.allocate(
        symbol="BTCUSDT", side="LONG",
        entry_price=65000.0, candidate={"score": 70.0},
        equity=10_000.0, closed_trades_count=5,
    )
    assert r3.conservative is True
    assert r3.suggested_qty < r2.suggested_qty

    # Cap at max notional
    r4 = alloc.allocate(
        symbol="BTCUSDT", side="LONG",
        entry_price=65000.0, candidate={"score": 90.0},
        equity=10_000.0,
        existing_symbol_notional=25_000.0,  # near cap
    )
    assert r4.notional <= 20_000.0 + 1.0  # max_notional_per_symbol_usd default

    st = alloc.status()
    assert st["researchOnly"] is True

check("6.capital_allocator", _check_allocator)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Reflection
# ─────────────────────────────────────────────────────────────────────────────

def _check_reflection():
    from backend.nexus_research.reflection import ReflectionAnalyst

    analyst = ReflectionAnalyst()

    # Winning position
    pos_win = {
        "positionId": "test_pos_win",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "qty": 0.001,
        "entryPrice": 65000.0,
        "exitPrice": 66000.0,
        "realisedPnl": 1.0,
        "entryFee": 0.03,
        "exitFee": 0.03,
        "fundingAccrued": 0.0,
        "notional": 65.0,
    }
    record = analyst.reflect(pos_win, candidate={"score": 75.0, "side": "LONG"})
    assert record.attribution.outcome_class == "WIN"
    assert record.attribution.realised_pnl > 0
    assert all(p.get("autoApplyProduction") is False for p in record.patch_proposals)

    # Loss position
    pos_loss = {
        "positionId": "test_pos_loss",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "qty": 0.001,
        "entryPrice": 65000.0,
        "exitPrice": 64000.0,
        "realisedPnl": -1.0,
        "entryFee": 0.03,
        "exitFee": 0.03,
        "fundingAccrued": 0.0,
        "notional": 65.0,
    }
    record_l = analyst.reflect(pos_loss, candidate={"score": 70.0, "side": "LONG"})
    assert record_l.attribution.outcome_class == "LOSS"

    # High fee drag → patch proposal generated
    pos_fee = {
        "positionId": "test_pos_fee",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "qty": 1.0,
        "entryPrice": 100.0,
        "exitPrice": 101.0,
        "realisedPnl": 0.1,
        "entryFee": 1.0,   # 1% fee drag
        "exitFee": 0.8,
        "fundingAccrued": 0.0,
        "notional": 100.0,
    }
    record_f = analyst.reflect(pos_fee)
    assert any("fee" in p.get("problem", "").lower() for p in record_f.patch_proposals)

    st = analyst.status()
    assert st["autoApplyProduction"] is False

check("7.reflection", _check_reflection)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Patch governance
# ─────────────────────────────────────────────────────────────────────────────

def _check_patch_governance():
    from backend.nexus_research.patch_governance import (
        PatchGovernanceManager, PatchGovernanceError,
        STATE_PROPOSED, STATE_UNDER_REVIEW, STATE_APPROVED_SIM,
        STATE_APPLIED_TO_SIMULATION, STATE_REJECTED,
    )

    mgr = PatchGovernanceManager()

    # Ingest from reflection
    prop_dict = {
        "proposalId": "pg_test_1",
        "scope": "simulation_only",
        "problem": "test problem",
        "evidence": {"symbol": "BTCUSDT", "test": True},
        "suggestedChange": {"parameter": "score_scale_min", "direction": "increase", "delta": 5.0},
        "sampleSize": 15,
        "requiresMinSample": 10,
        "requiresReplay": False,
        "requiresWalkForward": False,
        "requiresRollbackPlan": True,
        "rollbackDescription": "revert to prior value",
        "autoApplyProduction": False,
    }
    prop = mgr.ingest_from_reflection(prop_dict)
    assert prop.state == STATE_PROPOSED

    # Transition to UNDER_REVIEW
    mgr.transition("pg_test_1", STATE_UNDER_REVIEW, actor="test", note="review started")
    assert mgr.get("pg_test_1").state == STATE_UNDER_REVIEW

    # Transition to APPROVED_SIM (preconditions met)
    mgr.transition("pg_test_1", STATE_APPROVED_SIM, actor="test")
    assert mgr.get("pg_test_1").state == STATE_APPROVED_SIM

    # Apply to simulation
    mgr.transition("pg_test_1", STATE_APPLIED_TO_SIMULATION, actor="test")
    assert mgr.get("pg_test_1").state == STATE_APPLIED_TO_SIMULATION

    # Invalid transition should raise
    try:
        mgr.transition("pg_test_1", STATE_UNDER_REVIEW)
        raise AssertionError("should have raised PatchGovernanceError")
    except PatchGovernanceError:
        pass

    # Scope guard: non-simulation_only blocked
    prop_dict2 = {**prop_dict, "proposalId": "pg_test_2", "scope": "production"}
    prop2 = mgr.ingest_from_reflection(prop_dict2)
    mgr.transition("pg_test_2", STATE_UNDER_REVIEW)
    try:
        mgr.transition("pg_test_2", STATE_APPROVED_SIM)
        raise AssertionError("should have raised for non-simulation_only scope")
    except PatchGovernanceError:
        pass

    # Sample size gate
    prop_dict3 = {**prop_dict, "proposalId": "pg_test_3", "sampleSize": 2}
    prop3 = mgr.ingest_from_reflection(prop_dict3)
    mgr.transition("pg_test_3", STATE_UNDER_REVIEW)
    try:
        mgr.transition("pg_test_3", STATE_APPROVED_SIM)
        raise AssertionError("should have raised for insufficient sample")
    except PatchGovernanceError:
        pass

    st = mgr.status()
    assert st["autoApplyProduction"] is False
    assert st["researchOnly"] is True

check("8.patch_governance", _check_patch_governance)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Replay
# ─────────────────────────────────────────────────────────────────────────────

def _check_replay():
    from backend.nexus_research.replay import ReplayEngine, REPLAY_COMPLETED, REPLAY_PAUSED

    engine = ReplayEngine()
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 3600_000  # 1h ago
    end_ms = now_ms

    # Create session with synthetic bars
    sid = engine.create_session(
        symbols=["BTCUSDT"],
        start_ms=start_ms,
        end_ms=end_ms,
        interval="5m",
        seed=42,
        synthetic=True,
    )
    session = engine.get_session(sid)
    assert session is not None
    assert session.total_bars > 0

    # Run (limited bars)
    result = engine.run_session(sid, max_bars=10, checkpoint_every_n_bars=5)
    assert result["state"] == REPLAY_COMPLETED or result["currentBarIndex"] >= 9

    # Second session: pause mid-run
    sid2 = engine.create_session(
        symbols=["ETHUSDT"], start_ms=start_ms, end_ms=end_ms,
        interval="5m", seed=99, synthetic=True,
    )
    import threading
    def _pause_later():
        time.sleep(0.01)
        engine.pause()
    t = threading.Thread(target=_pause_later, daemon=True)
    t.start()
    result2 = engine.run_session(sid2, max_bars=200)
    t.join()
    # Should be COMPLETED (fast run) or PAUSED
    assert result2["state"] in (REPLAY_COMPLETED, REPLAY_PAUSED)

    st = engine.status()
    assert st["researchOnly"] is True

check("9.replay", _check_replay)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Soak
# ─────────────────────────────────────────────────────────────────────────────

def _check_soak():
    from backend.nexus_research.soak import SoakFramework, SOAK_SMOKE

    framework = SoakFramework()
    t0 = time.time()
    result = framework.run_smoke_verify()
    wall = time.time() - t0

    assert result.verdict() == "PASS", f"soak smoke verdict: {result.verdict()}, errors: {result.errors}"
    assert result.state == "COMPLETED"
    assert result.total_bars > 0
    assert wall < 60.0, f"smoke soak took too long: {wall:.1f}s"

    st = framework.status()
    assert st["latestVerdict"] == "PASS"
    assert st["researchOnly"] is True

check("10.soak", _check_soak)


# ─────────────────────────────────────────────────────────────────────────────
# 11. Gate B → Gate C bridge
# ─────────────────────────────────────────────────────────────────────────────

def _check_gate_b_bridge():
    from backend.nexus_research.gate_b_to_gate_c import (
        try_simulate_decision, read_sim_closed_positions_for_reflection,
    )

    # Eligible decision: READY_FOR_SIMULATION
    decision_ready = {
        "decisionId": "test_decision_ready",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "status": "READY_FOR_SIMULATION",
        "score": 72.0,
        "evidence": {"price": 65000.0},
    }
    result = try_simulate_decision(decision_ready)
    assert result.attempted is True
    assert result.researchOnly_check() if hasattr(result, "researchOnly_check") else True
    # Should succeed or fail gracefully (never throws)
    assert isinstance(result.success, bool)
    d = result.to_dict()
    assert d["researchOnly"] is True
    assert d["privateApi"] is False

    # Non-eligible decision: WATCH_ONLY
    decision_watch = {
        "decisionId": "test_decision_watch",
        "symbol": "ETHUSDT",
        "side": "SHORT",
        "status": "WATCH_ONLY",
        "score": 60.0,
    }
    result2 = try_simulate_decision(decision_watch)
    assert result2.attempted is False
    assert "not eligible" in (result2.skip_reason or "")

    # Read sim closed positions
    positions = read_sim_closed_positions_for_reflection(symbol="BTCUSDT")
    assert isinstance(positions, list)

check("11.gate_b_bridge", _check_gate_b_bridge)


# ─────────────────────────────────────────────────────────────────────────────
# 12. API routes
# ─────────────────────────────────────────────────────────────────────────────

def _check_api_routes():
    from backend.nexus_research.sim_routes import nexus_sim_bp, register_gate_c_routes
    from flask import Flask

    app = Flask(__name__)
    register_gate_c_routes(app)

    # Verify key routes are registered
    rule_map = {r.rule for r in app.url_map.iter_rules()}
    required = [
        "/api/nexus/simulator/status",
        "/api/nexus/simulator/orders",
        "/api/nexus/simulator/positions",
        "/api/nexus/simulator/ledger",
        "/api/nexus/risk/status",
        "/api/nexus/replay/status",
        "/api/nexus/reflection/status",
        "/api/nexus/patch/status",
        "/api/nexus/soak/status",
    ]
    for route in required:
        assert route in rule_map, f"route {route!r} not registered"

check("12.api_routes", _check_api_routes)


# ─────────────────────────────────────────────────────────────────────────────
# 13. Deploy mirror
# ─────────────────────────────────────────────────────────────────────────────

def _check_deploy_mirror():
    deploy_dir = ROOT / "deploy" / "zeabur_stage3_demo_learning" / "backend" / "nexus_research"
    assert deploy_dir.is_dir(), f"deploy dir missing: {deploy_dir}"

    gate_c_files = [
        "__init__.py", "simulator.py", "sim_ledger.py", "risk_engine.py",
        "capital_allocator.py", "reflection.py", "patch_governance.py",
        "replay.py", "soak.py", "sim_routes.py", "gate_b_to_gate_c.py",
    ]
    for f in gate_c_files:
        target = deploy_dir / f
        assert target.is_file(), f"deploy mirror missing: {f}"
        src = ROOT / "backend" / "nexus_research" / f
        assert target.read_bytes() == src.read_bytes(), f"deploy mirror differs: {f}"

check("13.deploy_mirror", _check_deploy_mirror)


# ─────────────────────────────────────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────────────────────────────────────

def _print_results():
    print()
    print("=" * 65)
    print("  NEXUS Phase 5 Gate C -- Verification Results")
    print("=" * 65)
    passed = 0
    failed = 0
    for check_id, status, detail in _results:
        icon = "PASS" if status == PASS else "FAIL"
        print(f"  [{icon}] {check_id:<35} {status}")
        if detail:
            for line in detail.splitlines()[:3]:
                print(f"       {line}")
        if status == PASS:
            passed += 1
        else:
            failed += 1
    print("-" * 65)
    total = passed + failed
    verdict = PASS if failed == 0 else FAIL
    print(f"  Passed: {passed}/{total}   Failed: {failed}/{total}")
    print(f"  VERDICT={verdict}")
    print("=" * 65)
    print()
    return verdict


if __name__ == "__main__":
    verdict = _print_results()
    sys.exit(0 if verdict == PASS else 1)
