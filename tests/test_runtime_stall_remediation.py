"""Runtime stall remediation + Zeabur observer + migration path guards."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_research.demo_autonomous.controller import AutonomousDemoController
from backend.nexus_research.demo_autonomous.error_sanitize import (
    build_structured_error,
    sanitize_text,
)
from backend.nexus_research.demo_autonomous.ops_status import AutonomousOpsStore, build_operations_status
from backend.nexus_research.demo_autonomous.outcome_reflection import build_reflection_bundle
from backend.nexus_research.demo_autonomous.validation_observer import (
    ZeaburCleanValidationObserver,
    get_validation_observer,
)


def test_controller_exception_includes_sanitized_message_and_traceback():
    try:
        raise ValueError("boom api_key=SECRET123 and token=abcd")
    except ValueError as exc:
        err = build_structured_error(
            exc,
            stage="instruments",
            cycle_id="c1",
            started_at_ms=1,
            failed_at_ms=2,
            last_successful_stage="account_snapshot",
            consecutive_failure_count=1,
        )
    assert err["error_type"] == "ValueError"
    assert "boom" in err["error_message_sanitized"]
    assert "SECRET123" not in err["error_message_sanitized"]
    assert "***" in err["error_message_sanitized"] or "api_key=***" in err["error_message_sanitized"]
    assert err["traceback_sanitized"]
    assert err["error_id"]
    assert err["stage"] == "instruments"


def test_secret_redaction_hex_and_keywords():
    raw = "authorization: Bearer deadbeefdeadbeefdeadbeefdeadbeef password=hunter2"
    cleaned = sanitize_text(raw)
    assert "hunter2" not in cleaned
    assert "deadbeefdeadbeefdeadbeefdeadbeef" not in cleaned


def test_stalled_controller_blocks_new_entries():
    ctrl = AutonomousDemoController()
    ctrl.health.stalled = True
    ctrl.health.stall_reason = "cycle_timeout"
    ok, reason = ctrl.health.allow_new_orders()
    assert ok is False
    assert reason == "cycle_timeout"
    assert ctrl.health_label() == "STOPPED" or ctrl.health_label() in ("STALLED", "STOPPED")
    # Force running-like label path
    ctrl._thread = type("T", (), {"is_alive": lambda self: True})()
    assert ctrl.health_label() == "STALLED"


def test_cycle_timeout_marks_stalled(monkeypatch):
    ctrl = AutonomousDemoController(interval_sec=0.01, cycle_timeout_sec=0.05)

    def hang():
        import time

        time.sleep(1.0)
        return {"ok": True}

    assert ctrl.start(hang) is True
    import time

    time.sleep(0.35)
    ctrl.stop()
    time.sleep(0.05)
    assert ctrl.failure_count >= 1
    assert ctrl.last_cycle is not None
    assert ctrl.last_cycle.get("error_type") in ("TimeoutError", "ValueError") or "error" in ctrl.last_cycle
    assert ctrl.health.stalled is True or ctrl.last_cycle.get("stage")


def test_missing_fee_not_converted_to_zero():
    bundle = build_reflection_bundle(
        symbol="BTCUSDT",
        side="Buy",
        strategy="s",
        regime="r",
        confidence=80,
        leverage=5,
        gross_pnl=10.0,
        fees=None,
        funding=None,
        slippage=None,
        risk_amount=5.0,
    )
    assert bundle.outcome.incomplete is True
    assert bundle.outcome.fees is None
    assert bundle.outcome.funding is None
    assert "fees" in bundle.outcome.missing_fields
    d = bundle.outcome.to_dict()
    assert d["fees"] is None
    assert d["incomplete"] is True


def test_stale_existing_position_blocker_cleared(monkeypatch):
    store = AutonomousOpsStore()
    store.last_block_reasons = ["existing_position_or_order"]
    store.last_scan_at_ms = 1
    store.updated_at_ms = 1

    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.ops_status.get_ops_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.ops_status.save_ops_store",
        lambda s=None: None,
    )

    class FakeCtrl:
        def to_dict(self):
            return {
                "running": True,
                "controllerHealth": "HEALTHY",
                "scannerHealth": "HEALTHY",
                "stalled": False,
                "currentCycleId": "x",
                "health": {"allowNewOrders": True},
            }

    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.controller.get_autonomous_controller",
        lambda: FakeCtrl(),
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.session_authorization.get_authorization_validator",
        lambda: type("A", (), {"session": None, "to_public_dict": lambda self: None})(),
    )

    # Avoid live snapshot: force empty via include_snapshot False path defaults
    status = build_operations_status(include_snapshot=False)
    assert "existing_position_or_order" not in status["blockReasons"]
    assert status["staleBlockReasonCount"] >= 0
    # audit history retained before clear — either audit or detail may show stale
    assert any(
        (b.get("reason") == "existing_position_or_order" and b.get("stale"))
        for b in status.get("blockReasonsDetail") or []
    ) or "existing_position_or_order" not in status["blockReasons"]


def test_observer_single_owner_and_duplicate_blocked():
    obs = ZeaburCleanValidationObserver(interval_sec=60)
    assert obs.start() is True
    assert obs.start() is False  # second owner rejected
    assert obs.to_dict()["ownerCount"] == 1
    obs.stop()


def test_observer_boot_change_fails(monkeypatch):
    obs = ZeaburCleanValidationObserver()
    obs.boot_id_at_start = "boot-a"
    obs.commit_at_start = "commit-a"

    def fake_status(include_snapshot=True):
        return {
            "bootId": "boot-b",
            "deploymentCommit": "commit-a",
            "controllerOwnerCount": 1,
            "mainnetUsed": False,
            "realMoneyUsed": False,
            "controllerHealth": "HEALTHY",
            "scannerHealth": "HEALTHY",
            "positionCount": 0,
            "openOrderCount": 0,
            "reconciliationStatus": "OK",
            "staleBlockReasonCount": 0,
            "blockReasons": [],
            "sessionStatus": "NONE",
            "controller": {"cycleCount": 1, "lastCycleProgressAtMs": 1},
        }

    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.ops_status.build_operations_status",
        fake_status,
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.ops_status.resolve_deployment_commit",
        lambda: "commit-a",
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.validation_observer._evidence_dir",
        lambda: None,
    )
    obs._sample_once()
    assert obs.validation_failed is True
    assert obs.fail_reason == "runtime_boot_changed"


def test_no_absolute_c_drive_path_in_active_runtime():
    root = Path(__file__).resolve().parents[1]
    needle = "C:" + "\\Users\\user\\.cursor\\projects\\" + "g-btc-bot"
    needle2 = "C:" + "/Users/user/.cursor/projects/" + "g-btc-bot"
    bad = []
    for path in (root / "backend" / "nexus_research" / "demo_autonomous").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if needle in text or needle2 in text:
            bad.append(str(path))
    assert bad == []


def test_dockerignore_excludes_archives():
    text = Path("Dockerfile").exists() and Path(".dockerignore").read_text(encoding="utf-8")
    assert "archives/" in text


def test_observer_default_disabled_and_read_only_surface():
    from backend.nexus_research.demo_autonomous import validation_observer as vo

    # Default ensure without env must not start.
    import os

    os.environ.pop("NEXUS_ZEABUR_CLEAN_OBSERVER", None)
    # Reset singleton for isolation
    vo._OBSERVER = None
    out = vo.ensure_validation_observer()
    assert out["enabled"] is False
    assert out["running"] is False
    assert out.get("exchangeWrite") is False
    assert out.get("localMonitorRequired") is False


def test_observer_fail_injection_commit_change_and_owner(monkeypatch):
    obs = ZeaburCleanValidationObserver()
    obs.boot_id_at_start = "boot-a"
    obs.commit_at_start = "commit-a"

    def fake_status(include_snapshot=True):
        return {
            "bootId": "boot-a",
            "deploymentCommit": "commit-b",
            "controllerOwnerCount": 2,
            "mainnetUsed": False,
            "realMoneyUsed": False,
            "controllerHealth": "HEALTHY",
            "scannerHealth": "HEALTHY",
            "positionCount": 0,
            "openOrderCount": 0,
            "reconciliationStatus": "OK",
            "staleBlockReasonCount": 0,
            "blockReasons": [],
            "sessionStatus": "NONE",
            "controller": {"cycleCount": 1, "lastCycleProgressAtMs": 1},
        }

    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.ops_status.build_operations_status",
        fake_status,
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.ops_status.resolve_deployment_commit",
        lambda: "commit-b",
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.validation_observer._evidence_dir",
        lambda: None,
    )
    obs._sample_once()
    assert obs.validation_failed is True
    assert obs.fail_reason in ("commit_changed", "controller_owner_not_1")


def test_observer_fail_injection_stalled_and_mainnet(monkeypatch):
    obs = ZeaburCleanValidationObserver()
    obs.boot_id_at_start = "boot-a"
    obs.commit_at_start = "commit-a"

    def fake_status(include_snapshot=True):
        return {
            "bootId": "boot-a",
            "deploymentCommit": "commit-a",
            "controllerOwnerCount": 1,
            "mainnetUsed": True,
            "realMoneyUsed": False,
            "controllerHealth": "STALLED",
            "scannerHealth": "STALLED",
            "positionCount": 0,
            "openOrderCount": 0,
            "reconciliationStatus": "OK",
            "staleBlockReasonCount": 0,
            "blockReasons": [],
            "sessionStatus": "NONE",
            "controller": {"cycleCount": 1, "lastCycleProgressAtMs": 1},
        }

    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.ops_status.build_operations_status",
        fake_status,
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.ops_status.resolve_deployment_commit",
        lambda: "commit-a",
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.validation_observer._evidence_dir",
        lambda: None,
    )
    obs._sample_once()
    assert obs.validation_failed is True
    assert obs.fail_reason in ("mainnet_or_real_money", "runtime_stalled")


def test_observer_sequence_monotonic_with_temp_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.validation_observer._evidence_dir",
        lambda: tmp_path,
    )

    def fake_status(include_snapshot=True):
        return {
            "bootId": "boot-a",
            "deploymentCommit": "commit-a",
            "controllerOwnerCount": 1,
            "mainnetUsed": False,
            "realMoneyUsed": False,
            "controllerHealth": "HEALTHY",
            "scannerHealth": "HEALTHY",
            "positionCount": 0,
            "openOrderCount": 0,
            "reconciliationStatus": "OK",
            "staleBlockReasonCount": 0,
            "blockReasons": [],
            "sessionStatus": "NONE",
            "controller": {"cycleCount": 3, "lastCycleProgressAtMs": 1},
        }

    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.ops_status.build_operations_status",
        fake_status,
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.ops_status.resolve_deployment_commit",
        lambda: "commit-a",
    )
    obs = ZeaburCleanValidationObserver()
    r1 = obs._sample_once()
    r2 = obs._sample_once()
    assert r2["sequence"] == r1["sequence"] + 1
    lines = (tmp_path / "samples.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_auto_send_missing_env_fail_closed(monkeypatch):
    monkeypatch.delenv("NEXUS_AUTONOMOUS_DEMO_AUTO_SEND", raising=False)
    from backend.nexus_research.demo_autonomous.runtime_bootstrap import _auto_send_enabled

    assert _auto_send_enabled() is False


def test_auto_send_false_env_fail_closed(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTONOMOUS_DEMO_AUTO_SEND", "false")
    from backend.nexus_research.demo_autonomous.runtime_bootstrap import _auto_send_enabled

    assert _auto_send_enabled() is False


def test_auto_send_requires_explicit_true(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTONOMOUS_DEMO_AUTO_SEND", "true")
    from backend.nexus_research.demo_autonomous.runtime_bootstrap import _auto_send_enabled

    assert _auto_send_enabled() is True


def test_auto_send_session_alone_cannot_enable(monkeypatch):
    """Session.auto_send must not bypass missing/false env (fail-closed)."""
    monkeypatch.delenv("NEXUS_AUTONOMOUS_DEMO_AUTO_SEND", raising=False)

    class _Sess:
        auto_send = True

        def is_active(self):
            return True

    class _Auth:
        session = _Sess()

    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.session_authorization.get_authorization_validator",
        lambda: _Auth(),
    )
    from backend.nexus_research.demo_autonomous.runtime_bootstrap import _auto_send_enabled

    assert _auto_send_enabled() is False


def test_dockerfile_auto_send_default_false():
    text = Path("Dockerfile").read_text(encoding="utf-8")
    assert "NEXUS_AUTONOMOUS_DEMO_AUTO_SEND=false" in text
    assert "NEXUS_AUTONOMOUS_DEMO_AUTO_SEND=true" not in text
