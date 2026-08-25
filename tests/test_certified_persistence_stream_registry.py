from __future__ import annotations

import ast
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.nexus_bounded_runtime.certified_short_session import (
    SHORT_MAX_DURATION_SEC,
    CertifiedShortBoundedSession,
)
from backend.nexus_bounded_runtime.runtime_lease import RuntimeLease
from backend.nexus_demo_execution.bounded_universe import BoundedCandidate
from backend.nexus_demo_execution.cost_entry_gate import CostGateResult
from backend.nexus_demo_execution.p2_durable_learning_store import DurableLessonStore
from backend.nexus_demo_execution.persistence import DemoExecutionPersistence, STREAMS
from backend.nexus_demo_execution.session_policy import policy_short_v1
from backend.nexus_demo_execution.v2_session_recovery import SessionRecoverySnapshot, SessionRecoveryStore

ROOT = Path(__file__).resolve().parents[1]
NEW_CERTIFIED_STREAMS = frozenset(
    {
        "session_mistake_telemetry",
        "certified_risk",
        "durable_lessons",
    }
)
TEST_SHA = "19dee3e000524d1aa9d75119b8c6c42d33d53688"


def _append_receiver_name(node: ast.Call) -> str:
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "append":
        return ""
    try:
        return ast.unparse(node.func.value)
    except Exception:
        return ""


def _literal_persistence_streams() -> tuple[set[str], list[str]]:
    produced: set[str] = set()
    dynamic: list[str] = []
    for base in (ROOT / "backend" / "nexus_bounded_runtime", ROOT / "backend" / "nexus_demo_execution"):
        for path in sorted(base.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                receiver = _append_receiver_name(node)
                if receiver not in {"self.persistence", "persistence"} and not receiver.endswith(".persistence"):
                    continue
                if not node.args:
                    continue
                rel = path.relative_to(ROOT).as_posix()
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    produced.add(first.value)
                else:
                    dynamic.append(f"{rel}:{node.lineno}:{ast.unparse(first)}")
    return produced, dynamic


def _lease_payload(*, seconds: int = SHORT_MAX_DURATION_SEC) -> dict[str, object]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "session_id": f"NEXUS-DEMO-SHORT-V1-{now.strftime('%Y%m%dT%H%M%SZ')}-registry",
        "authorized_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exchange": "BYBIT_DEMO",
        "mainnet": False,
        "real_money": False,
        "expected_runtime_sha": TEST_SHA,
        "service_name": "nexus-bybit-demo-learning-validation",
    }


def _session(tmp_path: Path) -> CertifiedShortBoundedSession:
    session = CertifiedShortBoundedSession(
        gate=MagicMock(),
        reader=MagicMock(),
        persistence=DemoExecutionPersistence(tmp_path / "demo_execution.sqlite3"),
        epoch_tracker=MagicMock(),
        kill_switch=MagicMock(engaged=False),
        writer=MagicMock(),
        approval=MagicMock(),
        export_dir=tmp_path / "export",
        data_root=tmp_path,
        policy=policy_short_v1(),
    )
    session.gate.can_write_orders.return_value = True
    session.reader.read_with_constitution.return_value = SimpleNamespace(
        wallet_balance=100.0,
        equity=100.0,
        open_positions=[],
        open_orders=[],
    )
    session.session_write_enabled = True
    session._founder_auth_consumed = True
    session._runtime_lease = RuntimeLease.from_dict(_lease_payload())
    session._ensure_certified_stores = MagicMock()
    session._certified_ledger = MagicMock()
    session._certified_ledger.unfinished.return_value = []
    session._certified_lesson_store = MagicMock()
    session._certified_reconciler = MagicMock()
    return session


def test_certified_runtime_persistence_stream_registry_complete() -> None:
    produced, dynamic = _literal_persistence_streams()
    assert dynamic == []
    assert produced <= set(STREAMS)
    assert NEW_CERTIFIED_STREAMS <= set(STREAMS)


def test_certified_stream_append_readback_and_unknown_fail_closed(tmp_path: Path) -> None:
    persistence = DemoExecutionPersistence(tmp_path / "streams.sqlite3")
    for stream in sorted(NEW_CERTIFIED_STREAMS):
        checksum = persistence.append(stream, {"stream": stream, "ok": True}, account_epoch="epoch")
        rows = persistence.read_all(stream, account_epoch="epoch")
        assert rows == [
            {
                "_record_id": rows[0]["_record_id"],
                "account_epoch": "epoch",
                "checksum": checksum,
                "ok": True,
                "stream": stream,
            }
        ]
    with pytest.raises(ValueError, match="unknown_stream:arbitrary_unknown_stream"):
        persistence.append("arbitrary_unknown_stream", {"ok": False})


def test_short_pre_entry_uses_canonical_persistence_for_certified_streams(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import backend.nexus_bounded_runtime.certified_session as certified_module

    monkeypatch.setenv("GITHUB_SHA", TEST_SHA)
    candidate = BoundedCandidate(
        candidate_id="cand-registry",
        symbol="BTCUSDT",
        direction="Buy",
        regime="TREND_UP",
        strategy="REGISTRY_REGRESSION",
        candidate_score=0.91,
        last_price=50_000.0,
        spread_bps=1.0,
        turnover24h=100_000_000.0,
        market_quality={"ok": True},
        funding_rate=0.0001,
        funding_status="KNOWN",
        atr=100.0,
        recent_swing_high=50_500.0,
        recent_swing_low=49_500.0,
        support=49_500.0,
        resistance=50_500.0,
        tick_size=0.1,
        qty_step=0.001,
        geometry_status="COMPLETE",
    )
    monkeypatch.setattr(
        certified_module,
        "scan_dynamic_candidates",
        lambda limit=8: ([candidate], {"source": "unit_test", "limit": limit}),
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
    monkeypatch.setattr(
        certified_module,
        "evaluate_cost_gate",
        lambda **kwargs: CostGateResult(
            allowed=False,
            reason="BLOCK_COST_DOMINATED_ENTRY",
            fee_rate_status="FEE_RATE_CONFIGURED_CONSERVATIVE",
            funding_status="KNOWN",
            labels=["unit_test_blocks_before_order"],
        ),
    )
    session = _session(tmp_path)
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

    result = session._try_entry(MagicMock(), tmp_path / "export", "epoch")

    assert result is None
    assert session.persistence.count("session_mistake_telemetry", account_epoch="epoch") == 1
    assert session.persistence.count("certified_risk", account_epoch="epoch") == 1
    assert session._state["order_intent_total"] == 0
    assert session._state["exchange_write_attempt_total"] == 0
    session.writer.create_market_order.assert_not_called()


def test_short_exit_learning_uses_canonical_persistence_without_replacing_lesson_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import backend.nexus_bounded_runtime.certified_session as certified_module
    import backend.nexus_demo_execution.pnl_reconcile as pnl_module

    evidence_hash = "hash-registry-learning"
    lesson_store = DurableLessonStore(sqlite_path=tmp_path / "lessons.sqlite3")
    lesson_store.upsert_lesson(
        {
            "lesson_id": "LC_registry_learning",
            "source_trade_id": "trade-registry",
            "source_decision_id": "decision-registry",
            "source_evidence_hash": evidence_hash,
            "campaign_id": "bybit-demo-bounded-6h",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "mistake_labels": ["unit_test"],
            "primary_mistake": "unit_test",
            "lesson_rule": "unit_test_rule",
            "support_count": 1,
            "policy_truth": False,
            "revalidation_required": True,
        }
    )
    monkeypatch.setattr(
        certified_module,
        "reconcile_close_pnl_for_order",
        lambda **kwargs: {"ok": True, "net_pnl": "0.12", "exit_price": "50010"},
    )
    monkeypatch.setattr(
        certified_module,
        "write_durable_lesson_from_trade",
        lambda **kwargs: {"ok": True, "lesson_id": "LC_registry_learning", "source_evidence_hash": evidence_hash},
    )
    monkeypatch.setattr(
        pnl_module,
        "reconcile_via_writer",
        lambda writer, symbol: {
            "net_pnl_status": "AVAILABLE",
            "net_pnl": "0.12",
            "gross_pnl": "0.20",
            "entry_fee": "0.04",
            "exit_fee": "0.04",
            "total_fees": "0.08",
            "funding": "0.0",
            "fee_source": "unit_test",
            "actual_fees_status": "AVAILABLE",
        },
    )
    session = _session(tmp_path)
    session._certified_lesson_store = lesson_store
    session._state["entries_total"] = 1
    active = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "qty": "0.001",
        "trade_case_id": "case-registry",
        "trade_id": "trade-registry",
        "decision_id": "decision-registry",
        "order_intent_id": "intent-registry",
        "entry_order_id": "entry-registry",
        "close_order_id": "close-registry",
        "candidate": {"symbol": "BTCUSDT", "direction": "Buy"},
        "cost_labels": [],
    }

    session._record_exit(active, "TP", tmp_path / "export", "epoch")

    rows = session.persistence.read_all("durable_lessons", account_epoch="epoch")
    assert rows[0]["ok"] is True
    assert rows[0]["source_evidence_hash"] == evidence_hash
    assert lesson_store.get_by_evidence_hash(evidence_hash)["lesson_id"] == "LC_registry_learning"
    assert session._state["short_lesson_readback_pass"] is True
    assert session.writer.create_market_order.call_count == 0
    lesson_store.close()


def test_unknown_stream_failure_does_not_create_orders_or_uncontrolled_intent(tmp_path: Path) -> None:
    session = _session(tmp_path)
    with pytest.raises(ValueError, match="unknown_stream:arbitrary_unknown_stream"):
        session.persistence.append("arbitrary_unknown_stream", {"ok": False})
    assert session._state["order_intent_total"] == 0
    assert session._state["exchange_write_attempt_total"] == 0
    session.writer.create_market_order.assert_not_called()


def test_stale_running_recovery_snapshot_does_not_permanently_block_new_session(tmp_path: Path) -> None:
    recovery = SessionRecoveryStore(tmp_path / "recovery")
    failed_session_id = "NEXUS-DEMO-SHORT-V1-20260825T130951Z-47ff294b"
    recovery.save(
        SessionRecoverySnapshot(
            session_id=failed_session_id,
            policy_version="DEMO_SHORT_V1",
            state="RUNNING",
            deadline_ts=time.time() - 60,
            entries_total=0,
            completed_trades=0,
            consecutive_losses=0,
            bad_process_outcomes=0,
            session_net_pnl=0.0,
            write_window_open=False,
            leader_token="old-leader",
        )
    )
    recovery.acquire("old-leader", session_id=failed_session_id)
    assert recovery.recover_or_block(leader_token="new-leader", expected_session_id="different-session")["detail"] == "session_id_mismatch"
    lock = json.loads(recovery.lock_path.read_text(encoding="utf-8"))
    lock["updated_at"] = 0
    recovery.lock_path.write_text(json.dumps(lock), encoding="utf-8")
    recovery.acquire("fresh-new-leader", session_id="different-session")
