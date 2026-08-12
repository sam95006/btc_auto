"""Focused tests for Founder-private control plane V10.

Covers: allowed modes, lifecycle controls, kill switch, recover/checkpoint,
fail-closed exchange writes, and secret-free observability.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.nexus_private_control import (
    ALLOWED_MODES,
    ControlPlaneError,
    ModeRejectedError,
    PrivateControlPlaneV10,
    validate_mode,
)
from backend.nexus_private_control.checkpoint import sanitize_checkpoint_payload
from backend.nexus_private_control.state_machine import InvalidTransitionError
from backend.nexus_private_control.write_guard import ExchangeWriteForbidden


OWNED_PATHS = [
    "backend/nexus_private_control",
    "tools/research/run_private_control_plane_v10.py",
    "tests/test_private_control_plane_v10.py",
    "artifacts/readiness/immutable/v10_private_control_plane",
]

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]


@pytest.fixture()
def plane(tmp_path: Path) -> PrivateControlPlaneV10:
    return PrivateControlPlaneV10(tmp_path)


def test_allowed_modes_contract() -> None:
    assert ALLOWED_MODES == frozenset(
        {
            "HISTORICAL_REPLAY_SIMULATED",
            "PROVIDER_CALIBRATION",
            "MICROSTRUCTURE_CAPTURE",
        }
    )
    for mode in ALLOWED_MODES:
        assert validate_mode(mode) == mode


@pytest.mark.parametrize(
    "banned",
    ["DEMO", "SHADOW", "MAINNET", "LIVE_TRADING", "OOS_EXECUTION", "WALK_FORWARD"],
)
def test_banned_modes_fail_closed(banned: str) -> None:
    with pytest.raises(ModeRejectedError):
        validate_mode(banned)


def test_start_status_pause_resume_stop(plane: PrivateControlPlaneV10) -> None:
    st = plane.start("HISTORICAL_REPLAY_SIMULATED", run_id="t1")
    assert st["state"] == "RUNNING"
    assert st["mode"] == "HISTORICAL_REPLAY_SIMULATED"
    assert plane.status()["state"] == "RUNNING"
    assert plane.pause(reason="unit")["state"] == "PAUSED"
    assert plane.resume(reason="unit")["state"] == "RUNNING"
    assert plane.stop(reason="unit")["state"] == "STOPPED"
    assert plane.guard.exchange_write_attempt_count == 0


def test_start_rejects_disallowed_mode(plane: PrivateControlPlaneV10) -> None:
    with pytest.raises(ControlPlaneError):
        plane.start("DEMO_ORDERS")
    assert plane.state_machine.state == "IDLE"


def test_checkpoint_and_recover(plane: PrivateControlPlaneV10) -> None:
    plane.start("PROVIDER_CALIBRATION", run_id="t_ckpt")
    ck = plane.checkpoint()
    assert ck["checkpoint"]["seq"] >= 1
    plane.pause()
    out = plane.recover(reason="unit_recover")
    assert out["recovery_status"] == "RECOVERED"
    assert out["state"] == "RUNNING"


def test_kill_switch_blocks_resume(plane: PrivateControlPlaneV10) -> None:
    plane.start("MICROSTRUCTURE_CAPTURE", run_id="t_kill")
    killed = plane.kill_switch(reason="unit_kill")
    assert killed["kill_switch_status"] == "TRIGGERED"
    assert plane.state_machine.state == "KILLED"
    with pytest.raises(ControlPlaneError):
        plane.resume()
    # Read-only surfaces remain available.
    assert plane.status()["kill_switch_engaged"] is True
    assert plane.health()["kill_switch_engaged"] is True
    obs = plane.observability()
    assert obs["read_only"] is True
    assert obs["secrets_present"] is False


def test_exchange_write_fail_closed(plane: PrivateControlPlaneV10) -> None:
    plane.start("HISTORICAL_REPLAY_SIMULATED", run_id="t_write")
    with pytest.raises(ExchangeWriteForbidden):
        plane.attempt_exchange_write("/v5/order/create")
    assert plane.guard.exchange_write_attempt_count == 1
    assert plane.state_machine.state == "FAILED_SAFE"


def test_invalid_transition_fail_closed(plane: PrivateControlPlaneV10) -> None:
    with pytest.raises(ControlPlaneError):
        plane.pause()
    with pytest.raises(ControlPlaneError):
        plane.stop()


def test_observability_has_no_secrets(plane: PrivateControlPlaneV10) -> None:
    plane.start("HISTORICAL_REPLAY_SIMULATED", run_id="t_obs")
    obs = plane.observability()
    blob = json.dumps(obs)
    assert "api_key" not in blob.lower() or obs.get("secrets_present") is False
    assert obs["formal_trading_state"]["demo_order_count"] == 0
    assert obs["formal_trading_state"]["mainnet"] is False
    assert obs["profitability_claim"] is None
    assert obs["public_product_exposure"] is False


def test_checkpoint_sanitizes_secrets(tmp_path: Path) -> None:
    cleaned = sanitize_checkpoint_payload({"api_key": "SHOULD_NOT_PERSIST", "mode": "X"})
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["mode"] == "X"


def test_controls_surface_complete(plane: PrivateControlPlaneV10) -> None:
    required = {
        "start",
        "status",
        "pause",
        "resume",
        "stop",
        "recover",
        "kill_switch",
        "checkpoint",
        "health",
        "observability",
    }
    assert set(plane.CONTROLS) == required
    for name in required:
        assert callable(getattr(plane, name))


def test_secret_scan_owned_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    hits: list[str] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if not target.exists():
            continue
        files = (
            [p for p in target.rglob("*") if p.is_file()]
            if target.is_dir()
            else [target]
        )
        for path in files:
            if path.suffix.lower() not in {".py", ".json", ".md", ".yml", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(str(path.relative_to(root)))
                    break
    assert hits == [], f"secret_leak_count={len(hits)} hits={hits}"


def test_state_machine_rejects_unknown_target(plane: PrivateControlPlaneV10) -> None:
    plane.start("HISTORICAL_REPLAY_SIMULATED", run_id="t_sm")
    with pytest.raises(InvalidTransitionError):
        plane.state_machine.transition("NOT_A_STATE", command="bogus")
