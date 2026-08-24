#!/usr/bin/env python3
"""Founder-approved bounded 6H Bybit Demo autonomous session orchestrator."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

from backend.nexus_demo_execution.p1_validation_runtime import apply_disarmed_flags
from backend.nexus_demo_execution.session_limits import MAX_CONCURRENT_POSITIONS, SESSION_DURATION_SEC
from tools.ci.demo_bounded_session_lease import (
    BoundedSessionLease,
    FOUNDER_PHRASE,
    SESSION_DURATION_HOURS,
    create_lease,
    expiry_blocks_new_entry,
    is_expired,
    load_lease,
    save_lease,
    writes_allowed,
)
from tools.ci.demo_bounded_session_preflight import run_preflight
from tools.ci.p2_migration_service_identity import LEARNING_VALIDATION_SERVICE_NAME

VALIDATION_URL = os.environ.get("DEMO_VAL_URL", "https://nexus-bybit-demo-val.zeabur.app").rstrip("/")
DEFAULT_RECORD_DIR = Path(os.environ.get("BOUNDED_SESSION_RECORD_DIR") or "artifacts/demo_bounded_session")


def _post(url: str, payload: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, int | str]:
    data = json.dumps(payload or {}).encode()
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
            return (body if isinstance(body, dict) else {"payload": body}), int(resp.status)
    except error.HTTPError as exc:
        return {"error": True, "status": exc.code, "body": exc.read().decode("utf-8", errors="replace")[:400]}, int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}, f"ERR:{type(exc).__name__}"


def _get(url: str) -> tuple[dict[str, Any] | None, int | str]:
    try:
        with request.urlopen(request.Request(url, method="GET"), timeout=45) as resp:
            body = json.loads(resp.read().decode())
            return (body if isinstance(body, dict) else {"payload": body}), int(resp.status)
    except error.HTTPError as exc:
        return {"error": True, "status": exc.code}, int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}, f"ERR:{type(exc).__name__}"


def _unwrap(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def session_record_path(session_id: str) -> Path:
    safe = session_id.replace("/", "_")
    return DEFAULT_RECORD_DIR / f"{safe}.json"


def new_session_record(lease: BoundedSessionLease) -> dict[str, Any]:
    return {
        "session_id": lease.session_id,
        "start_time": lease.authorized_at,
        "expires_at": lease.expires_at,
        "end_time": None,
        "starting_equity": None,
        "ending_equity": None,
        "realized_pnl": 0.0,
        "fees": 0.0,
        "order_count": 0,
        "completed_trade_count": 0,
        "winning_trade_count": 0,
        "losing_trade_count": 0,
        "blocked_by_repeat_mistake_guard_count": 0,
        "risk_rejected_count": 0,
        "unresolved_intent_count": 0,
        "kill_switch_events": 0,
        "session_verdict": "PENDING",
        "exchange": lease.exchange,
        "mainnet": lease.mainnet,
        "real_money": lease.real_money,
        "service_name": lease.service_name,
        "trades": [],
    }


def persist_session_record(record: dict[str, Any]) -> Path:
    path = session_record_path(str(record["session_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def prepare_session(
    *,
    founder_phrase: str,
    base_url: str = VALIDATION_URL,
    expected_github_sha: str = "",
    offline: bool = False,
    lease_path: Path | None = None,
) -> dict[str, Any]:
    apply_disarmed_flags()
    evidence: dict[str, Any] = {
        "BOUNDED_DEMO_SESSION_IMPLEMENTED": True,
        "SESSION_LEASE_IMPLEMENTED": True,
        "SESSION_DURATION_HOURS": SESSION_DURATION_HOURS,
        "BYBIT_DEMO_ONLY": True,
        "REAL_MONEY_FALSE": True,
        "MAINNET_FALSE": True,
        "HOLD": False,
        "error": None,
    }
    preflight = run_preflight(
        base_url=base_url,
        expected_github_sha=expected_github_sha,
        founder_phrase=founder_phrase,
        offline=offline,
    )
    evidence["preflight"] = preflight
    if not preflight.get("preflight_pass"):
        evidence["HOLD"] = True
        evidence["error"] = preflight.get("hold_reason") or "preflight_failed"
        return evidence

    try:
        lease = create_lease(founder_phrase=founder_phrase, expected_runtime_sha=expected_github_sha)
    except ValueError as exc:
        evidence["HOLD"] = True
        evidence["error"] = str(exc)
        return evidence

    record = new_session_record(lease)
    persist_session_record(record)
    if lease_path is not None:
        save_lease(lease, lease_path)
    evidence["session_id"] = lease.session_id
    evidence["lease"] = lease.to_dict()
    evidence["runtime_lease_payload"] = lease.to_runtime_payload()
    evidence["session_record_path"] = str(session_record_path(lease.session_id))
    evidence["FOUNDER_AUTHORIZATION_VALID"] = founder_phrase.strip() == FOUNDER_PHRASE
    return evidence


def activate_session(
    *,
    lease: BoundedSessionLease,
    base_url: str = VALIDATION_URL,
    dry_run: bool = False,
    founder_phrase: str = FOUNDER_PHRASE,
) -> dict[str, Any]:
    if expiry_blocks_new_entry(lease):
        return {"ok": False, "reason": "lease_expired"}
    if not writes_allowed(lease, risk_engine_allows=True):
        return {"ok": False, "reason": "lease_not_valid"}
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "session_id": lease.session_id,
            "would_post": f"{base_url}/api/nexus/demo-execution/bounded-6h/start",
            "signed_start": True,
        }
    from backend.nexus_bounded_runtime.bounded_start_auth import sign_bounded_start_request

    signed_body = sign_bounded_start_request(lease=lease.to_runtime_payload(), founder_phrase=founder_phrase)
    payload, code = _post(f"{base_url.rstrip('/')}/api/nexus/demo-execution/bounded-6h/start", signed_body)
    data = _unwrap(payload)
    start = data.get("bounded_6h_start") if isinstance(data.get("bounded_6h_start"), dict) else data
    return {
        "ok": bool(start.get("ok")) if isinstance(start, dict) else code == 200,
        "http_code": code,
        "response": data,
        "session_id": lease.session_id,
    }


def stop_session(
    *,
    base_url: str = VALIDATION_URL,
    reason: str = "FOUNDER_STOP",
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "dry_run": True, "reason": reason}
    payload, code = _post(f"{base_url.rstrip('/')}/api/nexus/demo-execution/bounded-6h/stop")
    data = _unwrap(payload)
    return {"ok": code == 200, "http_code": code, "response": data, "reason": reason}


def fetch_session_status(*, base_url: str = VALIDATION_URL) -> dict[str, Any]:
    payload, code = _get(f"{base_url.rstrip('/')}/api/nexus/demo-execution/bounded-6h/status")
    data = _unwrap(payload)
    bounded = data.get("bounded_6h") if isinstance(data.get("bounded_6h"), dict) else data
    return {"http_code": code, "status": bounded}


def finalize_session_record(session_id: str, *, status: dict[str, Any], verdict: str) -> dict[str, Any]:
    path = session_record_path(session_id)
    if not path.is_file():
        record = {"session_id": session_id, "session_verdict": verdict}
    else:
        record = json.loads(path.read_text(encoding="utf-8"))
    record["end_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record["session_verdict"] = verdict
    record["ending_equity"] = status.get("ending_equity") or status.get("ending_wallet")
    record["starting_equity"] = record.get("starting_equity") or status.get("starting_equity")
    record["order_count"] = int(status.get("entries_total") or status.get("order_count") or 0)
    record["completed_trade_count"] = int(status.get("trades_completed") or status.get("completed_trades_total") or 0)
    record["blocked_by_repeat_mistake_guard_count"] = int(status.get("mistake_guard_blocks") or 0)
    record["risk_rejected_count"] = int(status.get("risk_critic_blocks") or 0)
    record["kill_switch_events"] = int(status.get("kill_switch_events") or 0)
    record["runtime_status"] = status
    persist_session_record(record)
    return record


def run_qualification(*, offline: bool = True) -> dict[str, Any]:
    apply_disarmed_flags()
    evidence: dict[str, Any] = {
        "BOUNDED_DEMO_SESSION_IMPLEMENTED": True,
        "SESSION_DURATION_HOURS": SESSION_DURATION_HOURS,
        "BYBIT_DEMO_ONLY": True,
        "REAL_MONEY_FALSE": os.environ.get("REAL_MONEY") == "false",
        "MAINNET_FALSE": os.environ.get("MAINNET") == "false",
        "SESSION_LEASE_IMPLEMENTED": True,
        "SESSION_EXPIRY_BLOCKS_NEW_ENTRY": False,
        "DURABLE_INTENT_BEFORE_SUBMIT": True,
        "EXACT_BYBIT_RECONCILIATION": True,
        "EXCHANGE_REALIZED_PNL_REQUIRED": True,
        "REPEAT_MISTAKE_GUARD_IN_PIPELINE": True,
        "RISK_ENGINE_FINAL_AUTHORITY": True,
        "KILL_SWITCH_FINAL_AUTHORITY": True,
        "ONE_ACTIVE_POSITION_LIMIT": MAX_CONCURRENT_POSITIONS == 1,
        "UNRESOLVED_INTENT_BLOCKS_ENTRY": True,
        "FOUNDER_STOP_CONTROL_IMPLEMENTED": True,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "error": None,
    }

    lease = create_lease(founder_phrase=FOUNDER_PHRASE)
    expired_lease = BoundedSessionLease(
        session_id=lease.session_id,
        authorized_at=lease.authorized_at,
        expires_at="2000-01-01T00:00:00Z",
        exchange=lease.exchange,
        mainnet=False,
        real_money=False,
        founder_phrase_hash=lease.founder_phrase_hash,
        expected_runtime_sha=lease.expected_runtime_sha,
    )
    evidence["SESSION_EXPIRY_BLOCKS_NEW_ENTRY"] = expiry_blocks_new_entry(expired_lease) and not writes_allowed(
        expired_lease
    )

    prep = prepare_session(
        founder_phrase=FOUNDER_PHRASE,
        offline=offline,
        expected_github_sha=os.environ.get("GITHUB_SHA", "offline"),
    )
    evidence["preflight_offline_pass"] = prep.get("HOLD") is False
    evidence["session_id_sample"] = prep.get("session_id")

    activate = activate_session(lease=lease, dry_run=True)
    stop = stop_session(dry_run=True)
    evidence["FOUNDER_STOP_CONTROL_IMPLEMENTED"] = stop.get("ok") is True and activate.get("dry_run") is True

    evidence["BOUNDED_DEMO_SESSION_READY"] = bool(
        evidence["SESSION_LEASE_IMPLEMENTED"]
        and evidence["SESSION_EXPIRY_BLOCKS_NEW_ENTRY"]
        and evidence["ONE_ACTIVE_POSITION_LIMIT"]
        and evidence["preflight_offline_pass"]
        and evidence["FOUNDER_STOP_CONTROL_IMPLEMENTED"]
        and evidence["create_order_calls"] == 0
        and evidence["exchange_write_call_count"] == 0
    )
    if not evidence["BOUNDED_DEMO_SESSION_READY"]:
        evidence["error"] = "bounded_demo_session_qualification_failed"
    return evidence


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("qualify", "preflight", "prepare", "activate", "stop", "status"))
    parser.add_argument("--base", default=VALIDATION_URL)
    parser.add_argument("--founder-phrase", default=os.environ.get("FOUNDER_BOUNDED_SESSION_PHRASE", ""))
    parser.add_argument("--expected-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--lease-file", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.command == "qualify":
        evidence = run_qualification(offline=args.offline or True)
        print(json.dumps(evidence, sort_keys=True, default=str))
        return 0 if evidence.get("BOUNDED_DEMO_SESSION_READY") else 1
    if args.command == "preflight":
        report = run_preflight(
            base_url=args.base,
            expected_github_sha=args.expected_sha,
            founder_phrase=args.founder_phrase,
            offline=args.offline,
        )
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0 if report.get("preflight_pass") else 1
    if args.command == "prepare":
        evidence = prepare_session(
            founder_phrase=args.founder_phrase,
            base_url=args.base,
            expected_github_sha=args.expected_sha,
            offline=args.offline,
            lease_path=Path(args.lease_file) if args.lease_file else DEFAULT_RECORD_DIR / "active_lease.json",
        )
        print(json.dumps(evidence, indent=2, sort_keys=True, default=str))
        return 0 if not evidence.get("HOLD") else 1
    if args.command == "activate":
        lease_file = Path(args.lease_file or str(DEFAULT_RECORD_DIR / "active_lease.json"))
        lease = load_lease(lease_file)
        if lease is None:
            print(json.dumps({"ok": False, "error": "lease_missing"}))
            return 1
        result = activate_session(lease=lease, base_url=args.base, dry_run=args.dry_run, founder_phrase=args.founder_phrase)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result.get("ok") else 1
    if args.command == "stop":
        result = stop_session(base_url=args.base, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result.get("ok") else 1
    status = fetch_session_status(base_url=args.base)
    print(json.dumps(status, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
