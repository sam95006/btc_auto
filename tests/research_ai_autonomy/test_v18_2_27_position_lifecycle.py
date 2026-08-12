# -*- coding: utf-8 -*-
"""V18.2.27 — persistent position lifecycle + forbidden process exits."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from backend.nexus_research_ai_autonomy.lifecycle_purpose import LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
from backend.nexus_research_ai_autonomy.position_lifecycle_manager import (
    FORBIDDEN_PROCESS_EXIT_REASONS,
    POSITION_STILL_OPEN_MANAGED,
    PersistentPositionLifecycleManager,
    evaluate_horizon_integrity,
)


def test_horizon_integrity_pass_for_trend_family():
    r = evaluate_horizon_integrity(strategy_family="TREND")
    assert r["horizon_integrity_pass"] is True
    assert r["hard_max_hold"] >= r["recommended_hold_window"][0]
    assert r["no_silent_clamp"] is True


def test_forbidden_exit_blocked(tmp_path: Path):
    ck = tmp_path / "pos.json"
    plm = PersistentPositionLifecycleManager(checkpoint_path=ck)
    decision = {
        "symbol": "ETHUSDT",
        "side": "LONG",
        "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "hard_max_hold": 3600,
        "stop_price": 3000.0,
        "target_price": 3500.0,
        "regime": "TREND_UP",
        "strategy_family": "TREND",
    }
    pos = plm.open_from_execution(decision=decision, fill_price=3200.0, qty=0.1)
    res = plm.manage_cycle(
        pos.position_id,
        market={"last_price": 3210.0, "liquidity": 0.9},
        regime="TREND_UP",
        proposed_exit_reason="SESSION_OBSERVER_EXPIRED_CLOSE",
    )
    assert res["action"] == "HOLD"
    assert res["reason"] == POSITION_STILL_OPEN_MANAGED
    assert res["forbidden_exit_blocked"] == "SESSION_OBSERVER_EXPIRED_CLOSE"


def test_observer_stop_saves_checkpoint(tmp_path: Path):
    ck = tmp_path / "pos.json"
    plm = PersistentPositionLifecycleManager(checkpoint_path=ck)
    decision = {
        "symbol": "SOLUSDT",
        "side": "LONG",
        "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "hard_max_hold": 3600,
        "regime": "TREND_UP",
        "strategy_family": "TREND",
    }
    pos = plm.open_from_execution(decision=decision, fill_price=150.0, qty=1.0)
    stop = plm.observer_stop_with_open_position(pos.position_id, mark_price=151.0)
    assert stop["action"] == POSITION_STILL_OPEN_MANAGED
    assert ck.exists()
    data = json.loads(ck.read_text(encoding="utf-8"))
    assert data["checkpoint"]["symbol"] == "SOLUSDT"


def test_recover_from_exchange_no_duplicate(tmp_path: Path):
    ck = tmp_path / "pos.json"
    plm = PersistentPositionLifecycleManager(checkpoint_path=ck)
    client = MagicMock()
    client.list_positions.return_value = [
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "size": "0.01",
            "avgPrice": "64000",
        }
    ]
    pos = plm.recover_from_exchange(client, lifecycle_purpose=LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE)
    assert pos is not None
    assert pos.symbol == "BTCUSDT"
    assert plm.open_count() == 1
    pos2 = plm.recover_from_exchange(client)
    assert plm.open_count() == 1


def test_open_telemetry_separates_unrealized_and_fees():
    plm = PersistentPositionLifecycleManager()
    decision = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "hard_max_hold": 3600,
        "regime": "TREND_UP",
        "strategy_family": "TREND",
    }
    pos = plm.open_from_execution(decision=decision, fill_price=64000.0, qty=0.004)
    tel = plm.compute_open_telemetry(pos, 64100.0)
    assert tel.unrealized_usdt != tel.estimated_net_if_closed_now
    assert tel.estimated_exit_fee_usdt > 0


def test_all_forbidden_exits_enumerated():
    assert "SESSION_OBSERVER_EXPIRED_CLOSE" in FORBIDDEN_PROCESS_EXIT_REASONS
    assert "TEST_RUN_FINISHED_CLOSE" in FORBIDDEN_PROCESS_EXIT_REASONS
    assert "CURSOR_TASK_FINISHED_CLOSE" in FORBIDDEN_PROCESS_EXIT_REASONS
