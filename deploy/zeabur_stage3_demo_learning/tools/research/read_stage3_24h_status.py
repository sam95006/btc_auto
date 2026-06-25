#!/usr/bin/env python3
"""Read / write Stage 3 24h demo learning runner status and summary."""
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

STATUS_NAME = "stage3_24h_status.json"
SUMMARY_NAME = "stage3_24h_summary.json"
LOG_NAME = "stage3_24h_runner.log"
PID_NAME = "stage3_24h_runner.pid"


def _output_dir() -> Path:
    custom = os.environ.get("STAGE3_OUTPUT_DIR", "").strip()
    if custom:
        return Path(custom)
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
            "record_type": "stage3_24h_status",
            "output_dir": str(out),
            "updated_at_utc": utc_now_iso(),
        }
    )
    current.update(fields)
    write_json(path, current)
    return current


def build_summary(*, validator_passed: bool = False) -> Dict[str, Any]:
    out = _output_dir()
    status = _read_json(out / STATUS_NAME)
    audit = _read_json(out / "runner_audit.json")
    session = _read_json(out / "demo_order_session_report.json")
    stop = _read_json(out / "stop_conditions.json")
    trades = _read_jsonl(out / "trade_results.jsonl")
    reflections = _read_jsonl(out / "reflection_records.jsonl")
    patches = _read_jsonl(out / "applied_learning_patches.jsonl")
    snapshots = _read_jsonl(out / "account_snapshots.jsonl")

    loss_trades = [t for t in trades if float(t.get("close_pnl") or 0) < 0]
    loss_without_reflection = [t for t in loss_trades if not t.get("reflection_created")]
    repeated_detected = [t for t in trades if t.get("repeated_mistake_detected")]
    repeated_blocked = [t for t in trades if t.get("repeated_mistake_blocked")]

    balance_before = session.get("account_balance_before")
    balance_after = session.get("account_balance_after")
    if snapshots and balance_before is None:
        balance_before = snapshots[0].get("available_balance")
    if snapshots and balance_after is None:
        balance_after = snapshots[-1].get("available_balance")

    try:
        b_before = float(balance_before or 0)
        b_after = float(balance_after or 0)
        balance_delta = round(b_after - b_before, 6)
    except (TypeError, ValueError):
        balance_delta = 0.0

    total_close_pnl = round(sum(float(t.get("close_pnl") or 0) for t in trades), 6)
    orders_closed = sum(1 for t in trades if t.get("position_closed"))

    summary = {
        "record_type": "stage3_24h_summary",
        "phase": "D",
        "generated_at_utc": utc_now_iso(),
        "output_dir": str(out),
        "run_started": bool(status.get("run_started") or audit.get("runner_started")),
        "run_completed": bool(status.get("run_completed")),
        "duration_minutes_target": status.get("duration_minutes_target")
        or audit.get("duration_minutes")
        or 1440,
        "orders_sent": int(audit.get("orders_sent") or status.get("orders_sent") or len(trades)),
        "orders_closed": orders_closed,
        "open_positions_after": session.get("open_positions_after", audit.get("open_positions_after")),
        "total_close_pnl": total_close_pnl,
        "account_balance_before": balance_before,
        "account_balance_after": balance_after,
        "account_balance_delta": balance_delta,
        "reflection_records_count": len(reflections),
        "applied_learning_patches_count": len(patches),
        "loss_trade_count": len(loss_trades),
        "loss_without_reflection_count": len(loss_without_reflection),
        "repeated_mistake_detected_count": len(repeated_detected),
        "repeated_mistake_blocked_count": len(repeated_blocked),
        "stop_conditions_triggered": list(stop.get("triggered") or audit.get("stop_triggered") or []),
        "validator_passed": validator_passed,
        "mainnet_detected": False,
        "real_money_detected": False,
        "production_detected": False,
        "account_snapshots_count": len(snapshots),
        "trade_results_count": len(trades),
        "reconciliation_status": session.get("reconciliation_status"),
        "requires_manual_review": session.get("requires_manual_review"),
        "status_snapshot": status,
    }
    write_json(out / SUMMARY_NAME, summary)
    write_status(summary_written=True, summary_path=str(out / SUMMARY_NAME))
    return summary


def read_status(*, tail_log: int = 80) -> Dict[str, Any]:
    out = _output_dir()
    status = _read_json(out / STATUS_NAME)
    summary = _read_json(out / SUMMARY_NAME)
    pid = None
    pid_path = out / PID_NAME
    if pid_path.is_file():
        pid = pid_path.read_text(encoding="utf-8").strip() or None
    log_tail: List[str] = []
    log_path = out / LOG_NAME
    if tail_log > 0 and log_path.is_file():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        log_tail = lines[-tail_log:]
    return {
        "record_type": "stage3_24h_status_read",
        "generated_at_utc": utc_now_iso(),
        "output_dir": str(out),
        "pid": status.get("pid") or pid,
        "status": status.get("status"),
        "run_started": status.get("run_started"),
        "run_completed": status.get("run_completed"),
        "status_json": status,
        "summary_json": summary,
        "log_tail": log_tail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3 24h runner status")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--finalize-summary", action="store_true")
    parser.add_argument("--tail-log", type=int, default=80)
    parser.add_argument("kv", nargs="*", help="key=value for --write")
    args = parser.parse_args()

    if args.finalize_summary:
        fields = {}
        for item in args.kv:
            if "=" in item:
                k, v = item.split("=", 1)
                fields[k.strip()] = _coerce_value(v)
        summary = build_summary(validator_passed=bool(fields.get("validator_passed")))
        write_status(**fields)
        print(json.dumps({"summary_written": True, "orders_sent": summary.get("orders_sent")}, indent=2))
        return 0

    if args.write:
        fields: Dict[str, Any] = {}
        for item in args.kv:
            if "=" not in item:
                continue
            key, val = item.split("=", 1)
            fields[key.strip()] = _coerce_value(val)
        status = write_status(**fields)
        print(json.dumps({"written": True, "status": status.get("status")}, indent=2))
        return 0

    result = read_status(tail_log=args.tail_log)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
