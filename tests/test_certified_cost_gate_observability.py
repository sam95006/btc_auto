from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.nexus_bounded_runtime.certified_session import CertifiedBounded6HSession
from backend.nexus_bounded_runtime.runtime_lease import RuntimeLease
from backend.nexus_demo_execution.bounded_universe import BoundedCandidate
from backend.nexus_demo_execution.cost_entry_gate import CostGateResult, evaluate_cost_gate
from backend.nexus_demo_execution.persistence import DemoExecutionPersistence
from backend.nexus_demo_execution.session_policy import policy_6h_v2

TEST_SHA = "1aee84000cc24b67d2d123baeac800ce7dc91c25"


class CostGateFailingPersistence:
    def __init__(self, inner: DemoExecutionPersistence) -> None:
        self.inner = inner

    def append(self, stream: str, record: dict, *, account_epoch: str | None = None) -> str:
        if stream == "cost_gates":
            raise RuntimeError("unit_test_cost_gate_persistence_failure")
        return self.inner.append(stream, record, account_epoch=account_epoch)

    def count(self, stream: str, *, account_epoch: str | None = None) -> int:
        return self.inner.count(stream, account_epoch=account_epoch)

    def read_all(self, stream: str, *, account_epoch: str | None = None) -> list[dict]:
        return self.inner.read_all(stream, account_epoch=account_epoch)


def _lease_payload() -> dict[str, object]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "session_id": f"NEXUS-DEMO-6H-V2-{now.strftime('%Y%m%dT%H%M%SZ')}-costobs",
        "authorized_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exchange": "BYBIT_DEMO",
        "mainnet": False,
        "real_money": False,
        "expected_runtime_sha": TEST_SHA,
        "service_name": "nexus-bybit-demo-learning-validation",
    }


def _candidate(symbol: str = "BTCUSDT", direction: str = "Buy", score: float = 0.91) -> BoundedCandidate:
    return BoundedCandidate(
        candidate_id=f"cand-{symbol.lower()}-{direction.lower()}",
        symbol=symbol,
        direction=direction,
        regime="TREND_UP",
        strategy="COST_GATE_OBSERVABILITY_TEST",
        candidate_score=score,
        last_price=50_000.0,
        spread_bps=1.0,
        turnover24h=100_000_000.0,
        market_quality={"pass": True},
        funding_rate=0.0001,
        funding_status="KNOWN",
        atr=100.0,
        recent_swing_high=50_500.0,
        recent_swing_low=49_500.0,
        support=49_500.0,
        resistance=50_500.0,
        tick_size=0.1,
        qty_step=0.001,
        geometry_status="GEOMETRY_INPUTS_COMPLETE",
    )


def _blocked_cost(reason: str = "BLOCK_COST_DOMINATED_ENTRY") -> CostGateResult:
    return CostGateResult(
        allowed=False,
        reason=reason,
        fee_rate_status="FEE_RATE_CONFIGURED_CONSERVATIVE",
        funding_status="KNOWN",
        estimated_net_reward=0.12,
        estimated_net_risk=0.20,
        estimated_total_cost=0.04,
        net_reward_risk_ratio=0.60,
        cost_to_gross_reward_ratio=0.25,
        labels=[reason, "net_reward_risk_ratio_low"],
        breakdown={"estimated_round_trip_fee": 0.02},
        fee_meta={"status": "FEE_RATE_CONFIGURED_CONSERVATIVE"},
    )


def _allowed_cost() -> CostGateResult:
    return CostGateResult(
        allowed=True,
        reason="COST_GATE_PASS",
        fee_rate_status="FEE_RATE_CONFIGURED_CONSERVATIVE",
        funding_status="KNOWN",
        estimated_net_reward=1.80,
        estimated_net_risk=1.00,
        estimated_total_cost=0.10,
        net_reward_risk_ratio=1.80,
        cost_to_gross_reward_ratio=0.05,
        labels=[],
        breakdown={"estimated_round_trip_fee": 0.05},
        fee_meta={"status": "FEE_RATE_CONFIGURED_CONSERVATIVE"},
    )


def _session(tmp_path: Path, persistence: object | None = None) -> CertifiedBounded6HSession:
    session = CertifiedBounded6HSession(
        gate=MagicMock(),
        reader=MagicMock(),
        persistence=persistence or DemoExecutionPersistence(tmp_path / "demo_execution.sqlite3"),
        epoch_tracker=MagicMock(),
        kill_switch=MagicMock(engaged=False),
        writer=MagicMock(),
        approval=MagicMock(),
        export_dir=tmp_path / "export",
        data_root=tmp_path,
        policy=policy_6h_v2(),
    )
    session.session_id = "NEXUS-DEMO-6H-V2-cost-gate-observability"
    session.session_write_enabled = True
    session._founder_auth_consumed = True
    session._runtime_lease = RuntimeLease.from_dict(_lease_payload())
    session._ensure_certified_stores = MagicMock()
    session._certified_ledger = MagicMock()
    session._certified_ledger.unfinished.return_value = []
    session._certified_lesson_store = MagicMock()
    session._certified_reconciler = MagicMock()
    session.gate.can_write_orders.return_value = True
    session.reader.read_with_constitution.return_value = SimpleNamespace(
        wallet_balance=100.0,
        equity=100.0,
        open_positions=[],
        open_orders=[],
    )
    session.memory = MagicMock()
    session.memory.apply.return_value = {"blocked": False, "source": "unit_test"}
    session.writer.list_positions.return_value = []
    session.writer.list_open_orders.return_value = []
    session.writer.fetch_instrument.return_value = {"symbol": "BTCUSDT"}
    session.writer.compute_qty.return_value = "0.001"
    session.writer.tick_size.return_value = "0.1"
    session.writer.format_price.side_effect = lambda price, tick: f"{float(price):.1f}"
    session.writer.fetch_fee_rate_quote.return_value = SimpleNamespace(
        usable_taker=0.00055,
        to_dict=lambda: {"status": "FEE_RATE_CONFIGURED_CONSERVATIVE"},
    )
    return session


def _wire_pre_cost_path(monkeypatch: pytest.MonkeyPatch, candidates: list[BoundedCandidate]) -> None:
    import backend.nexus_bounded_runtime.certified_session as certified_module

    monkeypatch.setenv("GITHUB_SHA", TEST_SHA)
    monkeypatch.setattr(
        certified_module,
        "scan_dynamic_candidates",
        lambda limit=8: (candidates, {"source": "unit_test", "limit": limit}),
    )
    monkeypatch.setattr(
        certified_module,
        "evaluate_certified_guard",
        lambda **kwargs: {"blocked": False, "policy_authority": "DURABLE_POSTGRES_LESSON"},
    )
    monkeypatch.setattr(
        certified_module,
        "evaluate_certified_entry_risk",
        lambda **kwargs: {"allowed": True, "authority": "CERTIFIED_V2_KILL_SWITCH_AND_SESSION_LIMITS"},
    )


def test_blocked_cost_gate_persists_once_and_updates_counters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import backend.nexus_bounded_runtime.certified_session as certified_module

    _wire_pre_cost_path(monkeypatch, [_candidate()])
    evaluate = MagicMock(return_value=_blocked_cost())
    monkeypatch.setattr(certified_module, "evaluate_cost_gate", evaluate)
    persist_intent = MagicMock()
    submit = MagicMock()
    monkeypatch.setattr(certified_module, "persist_durable_intent", persist_intent)
    monkeypatch.setattr(certified_module, "submit_after_persist", submit)
    session = _session(tmp_path)

    result = session._try_entry(MagicMock(), tmp_path / "export", "epoch")

    rows = session.persistence.read_all("cost_gates", account_epoch="epoch")
    assert result is None
    assert evaluate.call_count == 1
    assert len(rows) == 1
    assert rows[0]["session_id"] == session.session_id
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["entry_price"] == 50_000.0
    assert rows[0]["stop_loss"] == 49_600.0
    assert rows[0]["take_profit"] == 50_400.0
    assert rows[0]["qty"] == 0.001
    assert rows[0]["cost_reason"] == "BLOCK_COST_DOMINATED_ENTRY"
    assert rows[0]["cost_allowed"] is False
    assert session._state["cost_gate_evaluated_total"] == 1
    assert session._state["cost_gate_pass_total"] == 0
    assert session._state["cost_gate_blocks"] == 1
    assert session._state["cost_gate_block_total"] == 1
    assert session._state["cost_gate_block_reason_distribution"] == {"BLOCK_COST_DOMINATED_ENTRY": 1}
    assert session._state["order_intent_total"] == 0
    assert session._state["exchange_write_attempt_total"] == 0
    persist_intent.assert_not_called()
    submit.assert_not_called()
    session.writer.create_market_order.assert_not_called()


def test_allowed_cost_gate_persists_once_and_continues_to_durable_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import backend.nexus_bounded_runtime.certified_session as certified_module

    _wire_pre_cost_path(monkeypatch, [_candidate()])
    monkeypatch.setattr(certified_module, "evaluate_cost_gate", MagicMock(return_value=_allowed_cost()))
    persist_intent = MagicMock(side_effect=RuntimeError("stop_at_mocked_durable_boundary"))
    submit = MagicMock()
    monkeypatch.setattr(certified_module, "persist_durable_intent", persist_intent)
    monkeypatch.setattr(certified_module, "submit_after_persist", submit)
    session = _session(tmp_path)

    result = session._try_entry(MagicMock(), tmp_path / "export", "epoch")

    assert result is None
    assert session.persistence.count("cost_gates", account_epoch="epoch") == 1
    assert session._state["cost_gate_evaluated_total"] == 1
    assert session._state["cost_gate_pass_total"] == 1
    assert session._state["cost_gate_blocks"] == 0
    assert session._state["cost_gate_block_total"] == 0
    persist_intent.assert_called_once()
    submit.assert_not_called()
    session.writer.create_market_order.assert_not_called()


def test_cost_gate_observability_has_no_double_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import backend.nexus_bounded_runtime.certified_session as certified_module

    candidates = [
        _candidate("BTCUSDT", "Buy", 0.91),
        _candidate("ETHUSDT", "Sell", 0.89),
        _candidate("SOLUSDT", "Buy", 0.87),
    ]
    _wire_pre_cost_path(monkeypatch, candidates)
    evaluate = MagicMock(side_effect=[_blocked_cost("R1"), _blocked_cost("R2"), _allowed_cost()])
    monkeypatch.setattr(certified_module, "evaluate_cost_gate", evaluate)
    monkeypatch.setattr(
        certified_module,
        "persist_durable_intent",
        MagicMock(side_effect=RuntimeError("stop_at_mocked_durable_boundary")),
    )
    session = _session(tmp_path)

    result = session._try_entry(MagicMock(), tmp_path / "export", "epoch")

    assert result is None
    assert evaluate.call_count == 3
    assert session.persistence.count("cost_gates", account_epoch="epoch") == 3
    assert session._state["cost_gate_evaluated_total"] == 3
    assert session._state["cost_gate_pass_total"] + session._state["cost_gate_block_total"] == 3
    assert session._state["cost_gate_block_total"] == 2
    assert sum(session._state["cost_gate_block_reason_distribution"].values()) == 2


def test_cost_gate_persistence_failure_fails_closed_before_intent_or_exchange(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import backend.nexus_bounded_runtime.certified_session as certified_module

    _wire_pre_cost_path(monkeypatch, [_candidate()])
    evaluate = MagicMock(return_value=_allowed_cost())
    monkeypatch.setattr(certified_module, "evaluate_cost_gate", evaluate)
    persist_intent = MagicMock()
    submit = MagicMock()
    monkeypatch.setattr(certified_module, "persist_durable_intent", persist_intent)
    monkeypatch.setattr(certified_module, "submit_after_persist", submit)
    persistence = CostGateFailingPersistence(DemoExecutionPersistence(tmp_path / "demo_execution.sqlite3"))
    session = _session(tmp_path, persistence=persistence)

    result = session._try_entry(MagicMock(), tmp_path / "export", "epoch")

    assert result is None
    assert evaluate.call_count == 1
    assert persistence.count("cost_gates", account_epoch="epoch") == 0
    assert session._state["OBSERVABILITY_PERSISTENCE_FAIL_CLOSED"] is True
    assert session._state["last_entry_block_reason"] == "OBSERVABILITY_PERSISTENCE_FAIL_CLOSED"
    assert session._state["stop_reason"] == "OBSERVABILITY_PERSISTENCE_FAIL_CLOSED"
    assert session.session_write_enabled is False
    assert session._stop.is_set() is True
    session.gate.close_smoke_write_window.assert_called_once()
    persist_intent.assert_not_called()
    submit.assert_not_called()
    session.writer.create_market_order.assert_not_called()
    assert session._state["order_intent_total"] == 0
    assert session._state["exchange_write_attempt_total"] == 0

    second = session._try_entry(MagicMock(), tmp_path / "export", "epoch")

    assert second is None
    assert evaluate.call_count == 1
    persist_intent.assert_not_called()
    submit.assert_not_called()
    session.writer.create_market_order.assert_not_called()
    assert session._state["order_intent_total"] == 0
    assert session._state["exchange_write_attempt_total"] == 0


def test_cost_gate_decision_semantics_preserved_in_observation_record(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import backend.nexus_bounded_runtime.certified_session as certified_module

    _wire_pre_cost_path(monkeypatch, [_candidate()])
    consumed: list[CostGateResult] = []

    def _evaluate_once(**kwargs) -> CostGateResult:
        result = evaluate_cost_gate(**kwargs)
        consumed.append(result)
        return result

    monkeypatch.setattr(certified_module, "evaluate_cost_gate", MagicMock(side_effect=_evaluate_once))
    session = _session(tmp_path)

    result = session._try_entry(MagicMock(), tmp_path / "export", "epoch")

    rows = session.persistence.read_all("cost_gates", account_epoch="epoch")
    assert result is None
    assert len(consumed) == 1
    assert len(rows) == 1
    direct = consumed[0]
    assert rows[0]["cost_allowed"] == direct.allowed
    assert rows[0]["cost_reason"] == direct.reason
    assert rows[0]["cost_labels"] == direct.labels
    assert rows[0]["estimated_total_cost"] == direct.estimated_total_cost
    assert rows[0]["estimated_net_reward"] == direct.estimated_net_reward
    assert rows[0]["estimated_net_risk"] == direct.estimated_net_risk
    assert rows[0]["net_reward_risk_ratio"] == direct.net_reward_risk_ratio
    assert rows[0]["cost_to_gross_reward_ratio"] == direct.cost_to_gross_reward_ratio
    assert session._state["order_intent_total"] == 0
    session.writer.create_market_order.assert_not_called()


def test_certified_fixed_geometry_remains_unchanged() -> None:
    source = inspect.getsource(CertifiedBounded6HSession._try_entry)
    assert "sl_f, tp_f = price * 0.992, price * 1.008" in source
    assert "sl_f, tp_f = price * 1.008, price * 0.992" in source
    assert "compute_structure_geometry" not in source
