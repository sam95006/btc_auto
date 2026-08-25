from __future__ import annotations

import inspect
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flask import Flask

from backend.nexus_bounded_runtime.bounded_start_auth import (
    SHORT_FOUNDER_PHRASE,
    sign_bounded_start_request,
    verify_bounded_start_request,
)
from backend.nexus_bounded_runtime.certified_session import CertifiedBounded6HSession
from backend.nexus_bounded_runtime.certified_short_session import (
    SHORT_ENTRY_CUTOFF_BUFFER_SEC,
    SHORT_EXPIRY_BLOCK_REASON,
    SHORT_MAX_DURATION_SEC,
    SHORT_SESSION_ID_PREFIX,
    CertifiedShortBoundedSession,
)
from backend.nexus_bounded_runtime.runtime_lease import RuntimeLease, validate_runtime_lease
from backend.nexus_demo_execution.session_policy import policy_12h_v3, policy_6h_v2, policy_short_v1
from backend.security.validation_public_guard import CONTROL_TOKEN_ENV, GUARD_ENV, install_validation_public_guard
from tools.ci.demo_bounded_session_lease import FOUNDER_PHRASE, create_lease

ROOT = Path(__file__).resolve().parents[1]
TEST_SHA = "d287463f929795c2a3db2ee8fa4e0091a3cb4287"
TEST_SECRET = "short-bounded-test-secret-not-production"
CONTROL_TOKEN = "short-control-token-not-production"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _short_lease(*, seconds: int = SHORT_MAX_DURATION_SEC, **overrides) -> dict[str, object]:
    start = overrides.pop("authorized_at_dt", _now())
    payload: dict[str, object] = {
        "session_id": f"NEXUS-DEMO-SHORT-V1-{start.strftime('%Y%m%dT%H%M%SZ')}-abc12345",
        "authorized_at": _fmt(start),
        "expires_at": _fmt(start + timedelta(seconds=seconds)),
        "exchange": "BYBIT_DEMO",
        "mainnet": False,
        "real_money": False,
        "expected_runtime_sha": TEST_SHA,
        "service_name": "nexus-bybit-demo-learning-validation",
    }
    payload.update(overrides)
    return payload


def _session(tmp_path: Path) -> CertifiedShortBoundedSession:
    return CertifiedShortBoundedSession(
        gate=MagicMock(),
        reader=MagicMock(),
        persistence=MagicMock(),
        epoch_tracker=MagicMock(),
        kill_switch=MagicMock(engaged=False),
        writer=MagicMock(),
        approval=MagicMock(),
        export_dir=tmp_path,
        data_root=tmp_path,
    )


def _disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(key, "false")
    monkeypatch.setenv("GITHUB_SHA", TEST_SHA)


def test_short_policy_contract_and_6h_12h_regression_values() -> None:
    short = policy_short_v1()
    six = policy_6h_v2()
    twelve = policy_12h_v3()
    assert short.session_duration_sec == 3600
    assert short.max_total_entry_orders == 1
    assert short.max_completed_trades == 1
    assert short.max_hold_sec == 1800
    assert SHORT_ENTRY_CUTOFF_BUFFER_SEC == 300
    assert short.session_id_prefix == "NEXUS-DEMO-SHORT-V1"
    assert short.session_gate_name == "DEMO_CERTIFIED_SHORT_BOUNDED_V1"
    assert short.founder_approval_env == "FOUNDER_SHORT_BOUNDED_APPROVED"
    assert short.margin_per_trade == six.margin_per_trade == 20.0
    assert short.leverage == six.leverage == 25
    assert short.margin_mode == six.margin_mode == "ISOLATED"
    assert short.max_single_trade_net_loss == six.max_single_trade_net_loss == 3.0
    assert short.max_session_net_loss == six.max_session_net_loss == 10.0
    assert six.session_duration_sec == 6 * 3600
    assert six.max_total_entry_orders == 6
    assert twelve.session_duration_sec == 12 * 3600


def test_short_signed_phrase_valid_and_cross_phrase_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv("NEXUS_BOUNDED_SESSION_CONTROL_SECRET", TEST_SECRET)
    body = sign_bounded_start_request(
        lease=_short_lease(),
        founder_phrase=SHORT_FOUNDER_PHRASE,
        secret=TEST_SECRET,
    )
    assert verify_bounded_start_request(body, expected_founder_phrase=SHORT_FOUNDER_PHRASE)["ok"] is True
    assert verify_bounded_start_request(body)["reason"] == "founder_phrase_invalid"

    six = create_lease(founder_phrase=FOUNDER_PHRASE, expected_runtime_sha=TEST_SHA)
    six_body = sign_bounded_start_request(
        lease=six.to_runtime_payload(),
        founder_phrase=FOUNDER_PHRASE,
        secret=TEST_SECRET,
    )
    assert verify_bounded_start_request(six_body)["ok"] is True
    assert verify_bounded_start_request(six_body, expected_founder_phrase=SHORT_FOUNDER_PHRASE)["reason"] == "founder_phrase_invalid"


def test_short_auth_rejects_wrong_signature_and_expired_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv("NEXUS_BOUNDED_SESSION_CONTROL_SECRET", TEST_SECRET)
    body = sign_bounded_start_request(
        lease=_short_lease(),
        founder_phrase=SHORT_FOUNDER_PHRASE,
        secret=TEST_SECRET,
    )
    wrong = dict(body)
    wrong["signature"] = "0" * 64
    assert verify_bounded_start_request(wrong, expected_founder_phrase=SHORT_FOUNDER_PHRASE)["reason"] == "signature_mismatch"

    old = sign_bounded_start_request(
        lease=_short_lease(),
        founder_phrase=SHORT_FOUNDER_PHRASE,
        signed_at=_fmt(_now() - timedelta(minutes=10)),
        secret=TEST_SECRET,
    )
    assert verify_bounded_start_request(old, expected_founder_phrase=SHORT_FOUNDER_PHRASE)["reason"] == "signed_at_skew_exceeded"


def test_short_lease_scope_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    valid = RuntimeLease.from_dict(_short_lease())
    assert validate_runtime_lease(valid, session_id_prefix=SHORT_SESSION_ID_PREFIX, max_duration_sec=3600)["ok"] is True
    bad_sha = RuntimeLease.from_dict(_short_lease(expected_runtime_sha="0" * 40))
    assert validate_runtime_lease(bad_sha, session_id_prefix=SHORT_SESSION_ID_PREFIX, max_duration_sec=3600)["reason"] == "runtime_sha_mismatch"
    mainnet = RuntimeLease.from_dict(_short_lease(mainnet=True))
    assert validate_runtime_lease(mainnet, session_id_prefix=SHORT_SESSION_ID_PREFIX, max_duration_sec=3600)["reason"] == "runtime_lease_mainnet_or_real_money"
    real_money = RuntimeLease.from_dict(_short_lease(real_money=True))
    assert validate_runtime_lease(real_money, session_id_prefix=SHORT_SESSION_ID_PREFIX, max_duration_sec=3600)["reason"] == "runtime_lease_mainnet_or_real_money"
    wrong_exchange = RuntimeLease.from_dict(_short_lease(exchange="BYBIT_MAINNET"))
    assert validate_runtime_lease(wrong_exchange, session_id_prefix=SHORT_SESSION_ID_PREFIX, max_duration_sec=3600)["reason"] == "runtime_lease_exchange_mismatch"
    too_long = RuntimeLease.from_dict(_short_lease(seconds=3601))
    assert validate_runtime_lease(too_long, session_id_prefix=SHORT_SESSION_ID_PREFIX, max_duration_sec=3600)["reason"] == "runtime_lease_duration_exceeds_scope"


def test_entry_cutoff_blocks_before_durable_intent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _disarm(monkeypatch)
    s = _session(tmp_path)
    s._runtime_lease = RuntimeLease.from_dict(_short_lease(seconds=(30 * 60)))
    s._state["entries_total"] = 0
    s.session_write_enabled = True
    assert s._before_durable_entry_intent() is False
    assert s._state["short_entry_window_closed"] is True
    assert s._state["NEW_ENTRY_BLOCKED_BY_SHORT_EXPIRY"] is True
    assert s._state["short_new_entry_block_reason"] == SHORT_EXPIRY_BLOCK_REASON


def test_first_entry_and_first_completed_trade_make_second_entry_impossible(tmp_path: Path) -> None:
    s = _session(tmp_path)
    s._runtime_lease = RuntimeLease.from_dict(_short_lease(seconds=3600))
    s._state["entries_total"] = 1
    assert s._before_durable_entry_intent() is False
    assert s._state["short_entry_limit_reached"] is True
    s._state["entries_total"] = 0
    s._state["trades_completed"] = 1
    assert s._before_durable_entry_intent() is False


def test_lesson_readback_success_auto_stops_short(tmp_path: Path) -> None:
    s = _session(tmp_path)
    s.session_write_enabled = True
    lesson = {"ok": True, "lesson_id": "LC_abc", "source_evidence_hash": "hash-abc"}
    s._certified_lesson_store = MagicMock()
    s._certified_lesson_store.get_by_evidence_hash.return_value = {
        "lesson_id": "LC_abc",
        "source_evidence_hash": "hash-abc",
    }
    out = s._after_durable_lesson_written(lesson=lesson, active={}, account_epoch="epoch", exit_reason="TP")
    assert out["ok"] is True
    assert s._state["short_learning_closure_complete"] is True
    assert s._state["short_entry_limit_reached"] is True
    assert s.session_write_enabled is False
    assert s._stop.is_set() is True


def test_lesson_readback_fail_is_failed_learning_closure(tmp_path: Path) -> None:
    s = _session(tmp_path)
    s._state["entries_total"] = 1
    s._certified_lesson_store = MagicMock()
    s._certified_lesson_store.get_by_evidence_hash.return_value = {}
    out = s._after_durable_lesson_written(
        lesson={"ok": True, "lesson_id": "LC_abc", "source_evidence_hash": "hash-abc"},
        active={},
        account_epoch="epoch",
        exit_reason="TP",
    )
    assert out["ok"] is False
    assert s._state["durable_learning_closure_hold"] is True
    assert s._state["short_entry_limit_reached"] is True
    assert s.session_write_enabled is False


def test_manual_stop_race_cannot_create_second_entry_after_one_entry(tmp_path: Path) -> None:
    s = _session(tmp_path)
    s._runtime_lease = RuntimeLease.from_dict(_short_lease(seconds=3600))
    s._state["entries_total"] = 1
    s.stop("OPERATOR_STOP")
    assert s._before_durable_entry_intent() is False
    assert s._state["short_entry_limit_reached"] is True


def test_active_position_expiry_uses_certified_safe_close_path() -> None:
    source = inspect.getsource(CertifiedBounded6HSession._force_flat)
    assert "_execute_durable_close" in source
    assert "super()._force_flat" in source


def test_short_6h_12h_mutual_exclusion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path / "data"))
    from backend.nexus_demo_execution.api_routes import DemoExecutionApiState

    st = DemoExecutionApiState()
    st._bounded_6h = MagicMock()
    st._bounded_6h.status.return_value = {"thread_alive": True, "status": "RUNNING"}
    assert st.start_bounded_short({})["active_controller"] == "6H_V2"
    st._bounded_6h = None
    st._bounded_12h = MagicMock()
    st._bounded_12h.status.return_value = {"thread_alive": True, "status": "RUNNING"}
    assert st.start_bounded_short({})["active_controller"] == "12H_V3"
    st._bounded_12h = None
    st._bounded_short = MagicMock()
    st._bounded_short.status.return_value = {"thread_alive": True, "status": "RUNNING"}
    assert st.start_bounded_6h()["active_controller"] == "SHORT_V1"
    assert st.start_bounded_12h({})["active_controller"] == "SHORT_V1"


def test_anonymous_short_post_guarded_and_control_token_does_not_bypass_signed_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _disarm(monkeypatch)
    monkeypatch.setenv(GUARD_ENV, "true")
    monkeypatch.setenv(CONTROL_TOKEN_ENV, CONTROL_TOKEN)
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FOUNDER_GATE", "DEMO_CERTIFIED_SHORT_BOUNDED_V1")
    monkeypatch.setenv("FOUNDER_SHORT_BOUNDED_APPROVED", "true")
    import backend.nexus_bounded_runtime.bootstrap as bootstrap

    bootstrap.CERTIFIED_BOUNDED_RUNTIME_ACTIVE = True
    app = Flask(__name__)
    install_validation_public_guard(app)
    from backend.nexus_demo_execution.api_routes import register_demo_execution_routes

    register_demo_execution_routes(app)
    client = app.test_client()
    assert client.post("/api/nexus/demo-execution/bounded-short/start").status_code == 403
    resp = client.post(
        "/api/nexus/demo-execution/bounded-short/start",
        headers={"Authorization": f"Bearer {CONTROL_TOKEN}"},
        json={},
    )
    assert resp.status_code == 200
    start = resp.get_json()["bounded_short_start"]
    assert start["ok"] is False
    assert start["reason"] == "lease_missing"


def test_risk_cost_fee_semantics_and_p1_p2_statement_preserved() -> None:
    source = inspect.getsource(CertifiedShortBoundedSession)
    assert "evaluate_certified_entry_risk" not in source
    assert "evaluate_cost_gate" not in source
    assert "fetch_fee_rate_quote" not in source
    statement = (ROOT / "docs" / "validation" / "P1_P2_REGRESSION_PRESERVATION.md").read_text(encoding="utf-8")
    assert "P1_HISTORICAL_EVIDENCE_PRESERVED" in statement
    assert "P2_HISTORICAL_EVIDENCE_PRESERVED" in statement
    assert "FULL_P1_RERUN_REQUIRED" in statement
    assert "FULL_P2_RERUN_REQUIRED" in statement


def test_no_demo_network_order_sent_in_short_tests() -> None:
    assert os.environ.get("TEST_DEMO_ORDER_SENT", "0") == "0"
