"""Stdlib-only Run #8 recovery bootstrap.

Heavy recovery is imported only after the evidence path is known.
An uncaught exception still writes sanitized HOLD evidence.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DISARMED = {
    "MAINNET": "false",
    "REAL_MONEY": "false",
    "DEMO_AUTONOMOUS_ENABLED": "false",
    "AUTONOMOUS_SEND": "false",
    "EXCHANGE_WRITE": "false",
}


def _evidence_path() -> Path:
    return Path(os.environ.get("P1_EVIDENCE_PATH") or "/tmp/nexus_demo_validation/p1_run8_accounting_recovery.json")


def _bootstrap_path() -> Path:
    explicit = os.environ.get("P1_BOOTSTRAP_FAILURE_PATH")
    if explicit:
        return Path(explicit)
    evidence = _evidence_path()
    return evidence.with_name("p1_run8_bootstrap_failure.json")


def _hold_payload(*, stage: str, exception_type: str | None = None) -> dict:
    return {
        "recovery_stage": stage,
        "exception_type": exception_type,
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": "HOLD",
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": "HOLD",
        "candidate_count": 0,
        "read_only_exchange": True,
        "runner_json_detected": True,
    }


def _write(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, indent=2, default=str)
        path.write_text(text, encoding="utf-8")
    except OSError:
        return


def _prepare_sys_path() -> None:
    os.environ.setdefault("PYTHONPATH", "/app")
    for root in ("/app", os.getcwd()):
        if root and root not in sys.path:
            sys.path.insert(0, root)


def main() -> int:
    for key, value in DISARMED.items():
        os.environ[key] = value
    stage = "MODULE_IMPORT"
    try:
        _prepare_sys_path()
        from backend.nexus_demo_execution.p1_run8_accounting_recovery import run_recovery_with_probes

        payload = run_recovery_with_probes()
        if not isinstance(payload, dict):
            payload = _hold_payload(stage="MODULE_IMPORT", exception_type="TypeError")
            _write(_bootstrap_path(), payload)
            try:
                _evidence_path().unlink(missing_ok=True)
            except OSError:
                pass
            print(json.dumps(payload, default=str))
            return 1
        payload.setdefault("runner_json_detected", True)
        payload.setdefault("create_order_calls", 0)
        payload.setdefault("exchange_write_call_count", 0)
        _write(_evidence_path(), payload)
        print(json.dumps(payload, default=str))
        return 0 if payload.get("BYBIT_DEMO_SINGLE_TRADE_E2E_PASS") == "PASS" else 1
    except Exception as exc:  # noqa: BLE001
        payload = _hold_payload(stage=stage, exception_type=type(exc).__name__)
        _write(_bootstrap_path(), payload)
        try:
            _evidence_path().unlink(missing_ok=True)
        except OSError:
            pass
        print(json.dumps(payload, default=str))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
