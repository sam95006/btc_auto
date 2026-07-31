#!/usr/bin/env python3
"""Offline / CI dry-run for 6H V2 decision chain — exchange_write_call_count must stay 0."""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("DEMO_6H_V2_DRY_RUN_ONLY", "true")
os.environ["EXCHANGE_WRITE"] = "false"
os.environ["DEMO_AUTONOMOUS_ENABLED"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_demo_execution.v2_session_controller import SessionControllerV2
from backend.nexus_demo_execution.v2_six_role import stub_complete_roles
from backend.nexus_demo_execution.v2_decision_delta import build_learning_delta
from backend.nexus_demo_execution.v2_policy import POLICY_VERSION


def _good_long() -> dict:
    return {
        "candidate_id": "c-long-1",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_reference": 100.0,
        "atr": 2.0,
        "atr_period": 14,
        "recent_swing_high": 108.0,
        "recent_swing_low": 96.0,
        "support_levels": [95.0],
        "resistance_levels": [110.0],
        "liquidity_above": [109.0],
        "liquidity_below": [94.0],
        "spread_bps": 1.0,
        "slippage_bps": 1.0,
        "funding_rate": 0.0001,
        "tick_size": 0.1,
    }


def _good_short() -> dict:
    c = _good_long()
    c.update(
        {
            "candidate_id": "c-short-1",
            "side": "Sell",
            "recent_swing_high": 104.0,
            "recent_swing_low": 90.0,
            "support_levels": [88.0],
            "resistance_levels": [105.0],
            "liquidity_above": [106.0],
            "liquidity_below": [87.0],
        }
    )
    return c


def main() -> int:
    ctl = SessionControllerV2(dry_run_only=True)
    roles = stub_complete_roles()
    results = {}

    results["valid_long"] = ctl.evaluate_candidate(_good_long(), roles=roles)
    results["valid_short"] = ctl.evaluate_candidate(_good_short(), roles=roles)

    missing = dict(_good_long())
    missing["candidate_id"] = "c-missing"
    missing["atr"] = None
    results["geometry_missing"] = ctl.evaluate_candidate(missing, roles=roles)

    results["fee_expired"] = ctl.evaluate_candidate(_good_long(), roles=roles, fee_expired=True)

    low_rr = dict(_good_long())
    low_rr["candidate_id"] = "c-lowrr"
    low_rr["resistance_levels"] = [100.4]
    low_rr["recent_swing_high"] = 100.4
    low_rr["liquidity_above"] = [100.3]
    results["low_net_rr_or_cost"] = ctl.evaluate_candidate(low_rr, roles=roles)

    veto_roles = stub_complete_roles(risk_verdict="VETO")
    results["risk_critic_veto"] = ctl.evaluate_candidate(_good_long(), roles=veto_roles)

    results["mistake_guard"] = ctl.evaluate_candidate(
        _good_long(), roles=roles, mistake_guard_block=True
    )
    results["duplicate_intent"] = ctl.evaluate_candidate(
        _good_long(), roles=roles, duplicate_intent=True
    )
    results["stale_account"] = ctl.evaluate_candidate(
        _good_long(), roles=roles, account={"snapshot_age_sec": 90, "position_count": 0, "open_order_count": 0, "available_balance": 100, "reconciliation": "MATCH", "execution_owner_count": 1}
    )

    incomplete_roles = {"market_context": {"verdict": "ALLOW"}}
    results["role_incomplete"] = ctl.evaluate_candidate(_good_long(), roles=incomplete_roles)

    # Learning delta only with full fields
    ok_delta = build_learning_delta(
        source_trade_case_id="tc-1",
        reflection_id="ref-1",
        similar_candidate_id="c-2",
        similarity_score=0.91,
        before_verdict="ALLOW",
        after_verdict="BLOCK",
        before_score=0.8,
        after_score=0.4,
        guard_action="EXACT_SETUP_COOLDOWN",
        policy_version=POLICY_VERSION,
    )
    assert ctl.record_learning_delta(ok_delta) is True
    assert ctl.record_learning_delta({"reason": "BLOCK_COST_DOMINATED_ENTRY"}) is False

    summary = ctl.summary()
    assert summary["exchange_write_call_count"] == 0
    assert summary["dry_run_only"] is True
    assert summary["mainnet"] is False
    assert summary["real_money"] is False

    out = {"results": {k: {"allowed": v.get("allowed"), "reason": v.get("reason"), "decision_delta": v.get("decision_delta")} for k, v in results.items()}, "summary": summary}
    print(json.dumps(out, ensure_ascii=True, indent=2))

    # Expect blocks for failure cases
    assert results["geometry_missing"]["allowed"] is False
    assert results["fee_expired"]["allowed"] is False
    assert results["risk_critic_veto"]["allowed"] is False
    assert results["mistake_guard"]["allowed"] is False
    assert results["duplicate_intent"]["allowed"] is False
    assert results["stale_account"]["allowed"] is False
    assert results["role_incomplete"]["allowed"] is False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
