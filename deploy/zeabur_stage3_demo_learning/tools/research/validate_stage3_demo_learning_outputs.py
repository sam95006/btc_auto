#!/usr/bin/env python3
"""Validate Stage 3 demo learning runner outputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import TRADE_RECORD_FIELDS, utc_now_iso, write_json
from tools.research.stage3_learning_loop import OUTPUT_FILES, RECONCILIATION_FIELDS, resolve_output_dir

READINESS_REPORT = ROOT / "data/external_alpha/reports/stage3_demo_learning_runner_readiness.json"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def validate(
    output_dir: Path | None = None,
    *,
    require_balance: bool | None = None,
    require_demo_order: bool = False,
) -> Dict[str, Any]:
    out = output_dir or resolve_output_dir()
    audit = json.loads((out / "runner_audit.json").read_text(encoding="utf-8")) if (out / "runner_audit.json").is_file() else {}
    mode = audit.get("mode", "")
    if require_balance is None:
        require_balance = mode in {"dry-run", "demo-order"}

    errors: List[str] = []
    for name in OUTPUT_FILES:
        if not (out / name).is_file():
            errors.append(f"missing_file:{name}")

    decisions = _read_jsonl(out / "decisions.jsonl")
    orders = _read_jsonl(out / "orders.jsonl")
    trades = _read_jsonl(out / "trade_results.jsonl")
    reflections = _read_jsonl(out / "reflection_records.jsonl")
    patches = _read_jsonl(out / "applied_learning_patches.jsonl")
    snapshots = _read_jsonl(out / "account_snapshots.jsonl")
    stop = json.loads((out / "stop_conditions.json").read_text(encoding="utf-8")) if (out / "stop_conditions.json").is_file() else {}

    latest_snapshot = snapshots[-1] if snapshots else {}
    balance_read_ok = bool(latest_snapshot.get("balance_read_ok"))
    decision_balance_linked = all(
        d.get("balance_snapshot_id") and "account_total_equity" in d and "account_available_balance" in d
        for d in decisions
    ) if decisions else False

    if require_balance:
        if not snapshots:
            errors.append("account_snapshots_missing")
        if not balance_read_ok:
            errors.append("latest_balance_read_ok_false")
        if latest_snapshot.get("coin") != "USDT":
            errors.append("latest_coin_not_usdt")
        for fld in ("total_equity", "available_balance", "wallet_balance"):
            if fld not in latest_snapshot:
                errors.append(f"snapshot_missing_field:{fld}")
        if decisions and not decision_balance_linked:
            errors.append("decisions_missing_balance_fields")
        for d in decisions:
            for fld in ("account_total_equity", "account_available_balance", "balance_snapshot_id"):
                if fld not in d:
                    errors.append(f"decision_missing_field:{fld}")

    loss_trades = [t for t in trades if float(t.get("close_pnl") or 0) < 0]
    loss_without_reflection = [t for t in loss_trades if not t.get("reflection_created")]
    repeated_detected = [t for t in trades if t.get("repeated_mistake_detected")]
    repeated_blocked = [t for t in trades if t.get("repeated_mistake_blocked")]

    confidence_reduction_verified = False
    size_reduction_verified = False
    for t in loss_trades:
        cb = float(t.get("confidence_before") or 0)
        ca = float(t.get("confidence_after") or 0)
        sb = float(t.get("position_size_before") or 0)
        sa = float(t.get("position_size_after") or 0)
        if ca < cb:
            confidence_reduction_verified = True
        if sa < sb:
            size_reduction_verified = True
        if not t.get("reflection_created"):
            errors.append(f"loss_without_reflection:{t.get('decision_id')}")
        if not t.get("patch_created"):
            errors.append(f"loss_without_patch:{t.get('decision_id')}")

    for t in trades:
        for fld in TRADE_RECORD_FIELDS:
            if fld not in t:
                errors.append(f"missing_trade_field:{fld}")

    if mode == "mock":
        if not loss_trades:
            errors.append("no_loss_trade_for_learning_loop_test")
        if not repeated_blocked:
            errors.append("no_repeated_mistake_blocked_record")
        if not reflections:
            errors.append("no_reflection_records")
        if not patches:
            errors.append("no_applied_patches")

    session_report = {}
    if (out / "demo_order_session_report.json").is_file():
        session_report = json.loads((out / "demo_order_session_report.json").read_text(encoding="utf-8"))

    demo_order_sent = bool(audit.get("demo_order_sent") or session_report.get("demo_order_sent"))
    real_orders = [o for o in orders if o.get("demo_order_sent") and not str(o.get("order_id", "")).startswith("mock")]
    open_positions_after = session_report.get("open_positions_after")
    position_closed = session_report.get("position_closed")

    if require_demo_order:
        if not demo_order_sent:
            errors.append("demo_order_sent_false")
        if len(real_orders) != 1:
            errors.append(f"orders_count_expected_1_got_{len(real_orders)}")
        if not real_orders[0].get("order_id") if real_orders else True:
            errors.append("real_order_id_missing")
        if len(trades) < 1:
            errors.append("trade_results_missing")
        if position_closed is not True and open_positions_after != 0:
            errors.append("position_not_closed")
        if loss_trades and len(reflections) < 1:
            errors.append("reflection_required_on_loss")
        if loss_trades and len(patches) < 1:
            errors.append("patch_required_on_loss")
        for fld in RECONCILIATION_FIELDS:
            if fld not in session_report:
                errors.append(f"session_report_missing_reconciliation:{fld}")
        if trades:
            latest_trade = trades[-1]
            for fld in RECONCILIATION_FIELDS:
                if fld not in latest_trade:
                    errors.append(f"trade_missing_reconciliation:{fld}")
            if session_report.get("reconciliation_status") not in {
                "matched",
                "gap_detected",
                "orphan_impact_suspected",
                "unknown",
            }:
                errors.append("reconciliation_status_invalid")
        if not audit.get("mainnet", False) is False:
            pass
        for o in real_orders:
            if not o.get("stop_loss_attached"):
                errors.append("stop_loss_not_attached")
            if o.get("mainnet"):
                errors.append("order_mainnet_true")
            if o.get("real_money"):
                errors.append("order_real_money_true")

    stop_triggered = list(stop.get("triggered") or [])
    balance_read_failed_count = sum(1 for s in snapshots if not s.get("balance_read_ok"))

    passed = not errors
    result = {
        "record_type": "stage3_demo_learning_output_validation",
        "generated_at_utc": utc_now_iso(),
        "output_dir": str(out),
        "mode": mode,
        "require_balance": require_balance,
        "require_demo_order": require_demo_order,
        "demo_order_sent": demo_order_sent,
        "position_closed": position_closed,
        "open_positions_after": open_positions_after,
        "passed": passed,
        "errors": errors,
        "decisions_count": len(decisions),
        "orders_count": len(orders),
        "trade_results_count": len(trades),
        "reflection_records_count": len(reflections),
        "applied_learning_patches_count": len(patches),
        "account_snapshots_count": len(snapshots),
        "balance_read_ok": balance_read_ok,
        "account_coin": latest_snapshot.get("coin"),
        "account_total_equity": latest_snapshot.get("total_equity"),
        "account_wallet_balance": latest_snapshot.get("wallet_balance"),
        "account_available_balance": latest_snapshot.get("available_balance"),
        "used_margin": latest_snapshot.get("used_margin"),
        "unrealized_pnl": latest_snapshot.get("unrealized_pnl"),
        "balance_snapshot_written": bool(snapshots),
        "decision_balance_linked": decision_balance_linked,
        "balance_read_failed_count": balance_read_failed_count,
        "wallet_coin_missing": bool(latest_snapshot.get("wallet_coin_missing")),
        "loss_trade_count": len(loss_trades),
        "loss_without_reflection_count": len(loss_without_reflection),
        "repeated_mistake_detected_count": len(repeated_detected),
        "repeated_mistake_blocked_count": len(repeated_blocked),
        "confidence_reduction_verified": confidence_reduction_verified,
        "position_size_reduction_verified": size_reduction_verified,
        "stop_conditions_triggered": stop_triggered,
    }
    if session_report:
        for fld in RECONCILIATION_FIELDS:
            result[fld] = session_report.get(fld)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--require-balance", action="store_true")
    parser.add_argument("--require-demo-order", action="store_true")
    parser.add_argument("--no-require-balance", action="store_true")
    args = parser.parse_args()
    out = Path(args.output_dir) if args.output_dir else None
    require_balance = True if args.require_balance else False if args.no_require_balance else None
    result = validate(out, require_balance=require_balance, require_demo_order=args.require_demo_order)
    write_json(
        READINESS_REPORT,
        {
            "record_type": "stage3_demo_learning_runner_readiness",
            "generated_at_utc": utc_now_iso(),
            "phase": "C+2" if args.require_demo_order else "B",
            "validation": result,
            "mock_or_dry_run_passed": result["passed"],
        },
    )
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
