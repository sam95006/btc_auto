#!/usr/bin/env python3
"""Read / write Stage 3 Zeabur background demo-order session status."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage3_learning_loop import resolve_output_dir  # noqa: E402

STATUS_NAME = "background_session_status.json"
REPORT_NAME = "background_session_report.json"
PID_NAME = "background_session.pid"
LOG_NAME = "background_session.log"


def _output_dir() -> Path:
    return resolve_output_dir()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _coerce_value(raw: str) -> Any:
    low = raw.strip().lower()
    if low in {"true", "false"}:
        return low == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def write_status(**fields: Any) -> Dict[str, Any]:
    out = _output_dir()
    path = out / STATUS_NAME
    current = _read_json(path)
    current.update(
        {
            "record_type": "stage3_background_session_status",
            "output_dir": str(out),
            "updated_at_utc": utc_now_iso(),
        }
    )
    current.update(fields)
    write_json(path, current)
    return current


def finalize_report() -> Dict[str, Any]:
    out = _output_dir()
    status = _read_json(out / STATUS_NAME)
    session = _read_json(out / "demo_order_session_report.json")
    audit = _read_json(out / "runner_audit.json")
    validation_path = ROOT / "data/external_alpha/reports/stage3_demo_learning_runner_readiness.json"
    validation = _read_json(validation_path)
    val_result = validation.get("validation") or {}

    reflections = _read_jsonl(out / "reflection_records.jsonl")
    patches = _read_jsonl(out / "applied_learning_patches.jsonl")
    trades = _read_jsonl(out / "trade_results.jsonl")
    stop = _read_json(out / "stop_conditions.json")

    trade = trades[-1] if trades else {}
    recon = {k: session.get(k, trade.get(k)) for k in (
        "reconciliation_status",
        "close_pnl",
        "execution_fee",
        "funding_fee",
        "account_balance_delta",
        "pnl_balance_delta_gap",
        "fee_or_slippage_estimate",
        "possible_orphan_close_impact",
        "requires_manual_review",
    )}

    report = {
        "record_type": "stage3_background_session_report",
        "phase": "C+3",
        "generated_at_utc": utc_now_iso(),
        "output_dir": str(out),
        "pid_file": str(out / PID_NAME),
        "log_file": str(out / LOG_NAME),
        "status_file": str(out / STATUS_NAME),
        "background_session_started": status.get("background_session_started", False),
        "background_pid": status.get("pid") or _read_pid(out),
        "background_status": status.get("status"),
        "session_completed": status.get("session_completed", False),
        "validator_passed": bool(val_result.get("passed") or status.get("validator_passed")),
        "demo_order_sent": bool(session.get("demo_order_sent") or audit.get("demo_order_sent")),
        "order_id": session.get("order_id") or (trade.get("order_id") if trade else None),
        "position_opened": session.get("position_opened"),
        "position_closed": session.get("position_closed"),
        "close_pnl": recon.get("close_pnl"),
        "execution_fee": recon.get("execution_fee"),
        "account_balance_delta": recon.get("account_balance_delta"),
        "pnl_balance_delta_gap": recon.get("pnl_balance_delta_gap"),
        "reconciliation_status": recon.get("reconciliation_status"),
        "requires_manual_review": recon.get("requires_manual_review"),
        "open_positions_after": session.get("open_positions_after"),
        "reflection_records_count": len(reflections),
        "applied_learning_patches_count": len(patches),
        "loss_without_reflection_count": val_result.get("loss_without_reflection_count", 0),
        "stop_conditions_triggered": list(stop.get("triggered") or []),
        "bybit_base_url": audit.get("bybit_base_url", "https://api-demo.bybit.com"),
        "bybit_mainnet_allowed": False,
        "real_money": False,
        "live_trading": False,
        "production_promotion_allowed": False,
        "arm_allowed": False,
        "zeabur_entrypoint_modified": False,
        "zeabur_runner_started_24h": False,
        "production_service_touched": False,
        "validation": val_result,
        "session_report": session,
        "status_snapshot": status,
    }
    write_json(out / REPORT_NAME, report)
    write_status(background_report_written=True, final_report_path=str(out / REPORT_NAME))
    return report


def _read_pid(out: Path) -> str | None:
    pid_path = out / PID_NAME
    if pid_path.is_file():
        return pid_path.read_text(encoding="utf-8").strip() or None
    return None


def read_status(*, tail_log: int = 0) -> Dict[str, Any]:
    out = _output_dir()
    status = _read_json(out / STATUS_NAME)
    report = _read_json(out / REPORT_NAME)
    session = _read_json(out / "demo_order_session_report.json")
    pid = _read_pid(out)
    log_tail: List[str] = []
    log_path = out / LOG_NAME
    if tail_log > 0 and log_path.is_file():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        log_tail = lines[-tail_log:]

    return {
        "record_type": "stage3_background_status_read",
        "generated_at_utc": utc_now_iso(),
        "output_dir": str(out),
        "background_pid": status.get("pid") or pid,
        "background_status": status.get("status"),
        "operator_go_present": status.get("operator_go_present"),
        "background_session_started": status.get("background_session_started", False),
        "session_completed": status.get("session_completed", False),
        "validator_passed": status.get("validator_passed"),
        "status": status,
        "final_report": report,
        "session_report": session,
        "log_tail": log_tail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3 background session status reader/writer")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--finalize-report", action="store_true")
    parser.add_argument("--tail-log", type=int, default=80)
    parser.add_argument("kv", nargs="*", help="key=value fields for --write")
    args = parser.parse_args()

    if args.finalize_report:
        report = finalize_report()
        print(json.dumps({"final_report_written": True, "background_status": report.get("background_status")}, indent=2))
        return 0

    if args.write:
        fields: Dict[str, Any] = {}
        for item in args.kv:
            if "=" not in item:
                continue
            key, val = item.split("=", 1)
            fields[key.strip()] = _coerce_value(val)
        if os.environ.get("OPERATOR_GO_STAGE3_C1_DEMO_ORDER", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "enabled",
        }:
            fields.setdefault("operator_go_present", True)
        status = write_status(**fields)
        print(json.dumps({"written": True, "status": status.get("status")}, indent=2))
        return 0

    result = read_status(tail_log=args.tail_log)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
