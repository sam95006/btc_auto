"""Read-only Stage 3 Bybit demo learning status aggregator for UI."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]

DEPLOY_VERSION_CANDIDATES = (
    Path("/app/STAGE3_DEPLOY_VERSION.json"),
    ROOT / "deploy" / "zeabur_stage3_demo_learning" / "STAGE3_DEPLOY_VERSION.json",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_jsonl(path: Path, *, limit: int | None = None) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    if limit is not None and limit > 0:
        return rows[-limit:]
    return rows


def resolve_output_dir() -> Path:
    custom = os.environ.get("STAGE3_OUTPUT_DIR", "").strip()
    if custom:
        return Path(custom)
    nexus = os.environ.get("NEXUS_DATA_DIR", "").strip()
    if nexus:
        return Path(nexus) / "stage3_demo_learning"
    return ROOT / "data" / "external_alpha" / "stage3_demo_learning"


def read_deploy_version() -> Dict[str, Any]:
    for candidate in DEPLOY_VERSION_CANDIDATES:
        if candidate.is_file():
            payload = _read_json(candidate)
            if payload:
                payload = dict(payload)
                payload["path"] = str(candidate)
                return payload
    return {
        "branch": "stage3-demo-learning",
        "commit": "unknown",
        "contains_24h_runner": False,
        "path": None,
    }


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def build_safety_gates() -> Dict[str, Any]:
    return {
        "bybit_mainnet_allowed": _env_bool("BYBIT_MAINNET_ALLOWED", False),
        "real_money": _env_bool("REAL_MONEY", False),
        "live_trading": _env_bool("LIVE_TRADING", False),
        "production_promotion_allowed": _env_bool("PRODUCTION_PROMOTION_ALLOWED", False),
        "arm_allowed": _env_bool("ARM_ALLOWED", False),
        "max_margin_usd": _env_float("MAX_MARGIN_USD", 20.0),
        "max_leverage": _env_int("MAX_LEVERAGE", 3),
        "max_open_positions": _env_int("MAX_OPEN_POSITIONS", 1),
    }


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _elapsed_minutes(started_at: Any) -> Optional[float]:
    start = _parse_iso(started_at)
    if not start:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - start.astimezone(timezone.utc)
    return round(max(0.0, delta.total_seconds() / 60.0), 1)


def derive_runner_phase(
    *,
    status: Dict[str, Any],
    summary: Dict[str, Any],
    stop: Dict[str, Any],
    safety: Dict[str, Any],
    startup_mode: str,
) -> str:
    if safety.get("bybit_mainnet_allowed") or safety.get("real_money") or safety.get("live_trading"):
        return "STOPPED"
    alerts = summary.get("mainnet_detected") or summary.get("real_money_detected") or summary.get("production_detected")
    if alerts:
        return "STOPPED"
    triggered = list(stop.get("triggered") or summary.get("stop_conditions_triggered") or [])
    if triggered:
        return "STOPPED"
    raw_status = str(status.get("status") or status.get("current_status") or "").lower()
    if raw_status in {"stopped", "failed", "validator_failed", "error"}:
        return "STOPPED"
    if summary.get("validator_passed") is False or status.get("validator_failed"):
        return "STOPPED"
    if status.get("run_completed") or summary.get("run_completed"):
        return "COMPLETED"
    if status.get("run_started") or status.get("runner_started_24h") or summary.get("run_started"):
        return "RUNNING"
    return "IDLE"


def _latest_account(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not snapshots:
        return {}
    snap = snapshots[-1]
    return {
        "account_total_equity": snap.get("total_equity"),
        "account_available_balance": snap.get("available_balance"),
        "account_wallet_balance": snap.get("wallet_balance"),
        "used_margin": snap.get("used_margin"),
        "unrealized_pnl": snap.get("unrealized_pnl"),
        "coin": snap.get("coin"),
        "balance_read_ok": snap.get("balance_read_ok"),
        "snapshot_at_utc": snap.get("snapshot_at_utc") or snap.get("created_at_utc"),
    }


def _learning_counts(
    trades: List[Dict[str, Any]],
    reflections: List[Dict[str, Any]],
    patches: List[Dict[str, Any]],
) -> Dict[str, Any]:
    loss_trades = [t for t in trades if float(t.get("close_pnl") or 0) < 0]
    loss_without_reflection = [t for t in loss_trades if not t.get("reflection_created")]
    repeated_detected = [t for t in trades if t.get("repeated_mistake_detected")]
    repeated_blocked = [t for t in trades if t.get("repeated_mistake_blocked")]
    latest_trade = trades[-1] if trades else {}
    latest_reflection = reflections[-1] if reflections else {}
    latest_patch = patches[-1] if patches else {}
    return {
        "trade_results_count": len(trades),
        "reflection_records_count": len(reflections),
        "applied_learning_patches_count": len(patches),
        "loss_trade_count": len(loss_trades),
        "loss_without_reflection_count": len(loss_without_reflection),
        "repeated_mistake_detected_count": len(repeated_detected),
        "repeated_mistake_blocked_count": len(repeated_blocked),
        "latest_close_pnl": latest_trade.get("close_pnl"),
        "latest_reflection_created": latest_reflection.get("created_at_utc") or latest_reflection.get("reflection_id"),
        "latest_patch_created": latest_patch.get("created_at_utc") or latest_patch.get("patch_id"),
    }


def _runner_block(
    *,
    status: Dict[str, Any],
    summary: Dict[str, Any],
    audit: Dict[str, Any],
    session: Dict[str, Any],
    orders: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    learning: Dict[str, Any],
) -> Dict[str, Any]:
    latest_order = orders[-1] if orders else {}
    started_at = (
        status.get("started_at_utc")
        or audit.get("started_at_utc")
        or status.get("run_started_at_utc")
    )
    return {
        "started_at_utc": started_at,
        "duration_minutes_target": status.get("duration_minutes_target")
        or summary.get("duration_minutes_target")
        or audit.get("duration_minutes")
        or 1440,
        "elapsed_minutes": status.get("elapsed_minutes") or _elapsed_minutes(started_at),
        "max_orders_per_day": status.get("max_orders_per_day")
        or audit.get("max_orders_per_day")
        or 6,
        "orders_sent": int(
            audit.get("orders_sent")
            or status.get("orders_sent")
            or summary.get("orders_sent")
            or len(orders)
            or 0
        ),
        "orders_closed": int(summary.get("orders_closed") or sum(1 for t in trades if t.get("position_closed")) or len(trades)),
        "open_positions_after": session.get("open_positions_after", audit.get("open_positions_after")),
        "open_positions_current": session.get("open_positions_current", session.get("open_positions_after", 0)),
        "latest_order_id": latest_order.get("order_id") or (trades[-1].get("order_id") if trades else None),
        "latest_close_pnl": learning.get("latest_close_pnl"),
        "latest_reflection_created": learning.get("latest_reflection_created"),
        "latest_patch_created": learning.get("latest_patch_created"),
    }


def _stop_block(stop: Dict[str, Any], summary: Dict[str, Any], session: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "stop_conditions_triggered": list(stop.get("triggered") or summary.get("stop_conditions_triggered") or []),
        "validator_passed": summary.get("validator_passed") if "validator_passed" in summary else stop.get("validator_passed"),
        "reconciliation_status": session.get("reconciliation_status") or summary.get("reconciliation_status"),
        "requires_manual_review": session.get("requires_manual_review") if "requires_manual_review" in session else summary.get("requires_manual_review"),
    }


def _read_log_tail(path: Path, lines: int = 80) -> List[str]:
    if not path.is_file() or lines <= 0:
        return []
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:]


def _data_available(out: Path) -> bool:
    markers = (
        "stage3_24h_status.json",
        "stage3_24h_summary.json",
        "runner_audit.json",
        "decisions.jsonl",
    )
    return any((out / name).is_file() for name in markers)


def build_stage3_context() -> Dict[str, Any]:
    out = resolve_output_dir()
    deploy = read_deploy_version()
    startup_mode = os.environ.get("STAGE3_STARTUP_MODE", "idle").strip().lower() or "idle"
    safety = build_safety_gates()

    status = _read_json(out / "stage3_24h_status.json")
    summary = _read_json(out / "stage3_24h_summary.json")
    audit = _read_json(out / "runner_audit.json")
    session = _read_json(out / "demo_order_session_report.json")
    stop = _read_json(out / "stop_conditions.json")

    snapshots = _read_jsonl(out / "account_snapshots.jsonl")
    trades = _read_jsonl(out / "trade_results.jsonl")
    reflections = _read_jsonl(out / "reflection_records.jsonl")
    patches = _read_jsonl(out / "applied_learning_patches.jsonl")
    orders = _read_jsonl(out / "orders.jsonl")
    decisions = _read_jsonl(out / "decisions.jsonl", limit=20)

    learning = _learning_counts(trades, reflections, patches)
    runner = _runner_block(
        status=status,
        summary=summary,
        audit=audit,
        session=session,
        orders=orders,
        trades=trades,
        learning=learning,
    )
    stop_block = _stop_block(stop, summary, session)
    runner_phase = derive_runner_phase(
        status=status,
        summary=summary,
        stop=stop,
        safety=safety,
        startup_mode=startup_mode,
    )

    return {
        "read_only": True,
        "data_available": _data_available(out),
        "output_dir": str(out),
        "generated_at_utc": utc_now_iso(),
        "deploy": {
            "github_branch": deploy.get("branch", "stage3-demo-learning"),
            "deploy_commit": deploy.get("commit", "unknown"),
            "contains_24h_runner": bool(deploy.get("contains_24h_runner")),
            "startup_mode": startup_mode,
            "path": deploy.get("path"),
        },
        "startup_mode": startup_mode,
        "runner_started_24h": bool(
            status.get("runner_started_24h")
            or audit.get("zeabur_runner_started_24h")
            or status.get("run_started")
        ),
        "run_completed": bool(status.get("run_completed") or summary.get("run_completed")),
        "current_status": status.get("status") or status.get("current_status") or runner_phase,
        "runner_phase": runner_phase,
        "account": _latest_account(snapshots),
        "runner": runner,
        "learning": learning,
        "safety": safety,
        "stop": stop_block,
        "alerts": {
            "mainnet_detected": bool(summary.get("mainnet_detected")),
            "real_money_detected": bool(summary.get("real_money_detected")),
            "production_detected": bool(summary.get("production_detected")),
        },
        "log_tail": _read_log_tail(out / "stage3_24h_runner.log", 40),
        "events": [
            {
                "type": "decision",
                "at": row.get("created_at_utc"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "decision_id": row.get("decision_id"),
            }
            for row in decisions[-12:]
        ],
    }


def build_stage3_summary() -> Dict[str, Any]:
    ctx = build_stage3_context()
    return {
        "read_only": True,
        "output_dir": ctx["output_dir"],
        "generated_at_utc": ctx["generated_at_utc"],
        "deploy": ctx["deploy"],
        "runner_phase": ctx["runner_phase"],
        "startup_mode": ctx["startup_mode"],
        "runner_started_24h": ctx["runner_started_24h"],
        "run_completed": ctx["run_completed"],
        "current_status": ctx["current_status"],
        "runner": ctx["runner"],
        "learning": ctx["learning"],
        "stop": ctx["stop"],
    }


def build_stage3_account() -> Dict[str, Any]:
    out = resolve_output_dir()
    snapshots = _read_jsonl(out / "account_snapshots.jsonl")
    return {
        "read_only": True,
        "output_dir": str(out),
        "generated_at_utc": utc_now_iso(),
        "account": _latest_account(snapshots),
        "snapshots_count": len(snapshots),
        "latest_snapshots": snapshots[-5:],
    }


def build_stage3_trades(*, limit: int = 50) -> Dict[str, Any]:
    out = resolve_output_dir()
    trades = _read_jsonl(out / "trade_results.jsonl", limit=limit)
    orders = _read_jsonl(out / "orders.jsonl", limit=limit)
    return {
        "read_only": True,
        "output_dir": str(out),
        "generated_at_utc": utc_now_iso(),
        "trade_results": trades,
        "orders": orders,
        "trade_results_count": len(_read_jsonl(out / "trade_results.jsonl")),
        "orders_count": len(_read_jsonl(out / "orders.jsonl")),
    }


def build_stage3_learning(*, limit: int = 50) -> Dict[str, Any]:
    out = resolve_output_dir()
    trades = _read_jsonl(out / "trade_results.jsonl")
    reflections = _read_jsonl(out / "reflection_records.jsonl", limit=limit)
    patches = _read_jsonl(out / "applied_learning_patches.jsonl", limit=limit)
    learning = _learning_counts(trades, _read_jsonl(out / "reflection_records.jsonl"), _read_jsonl(out / "applied_learning_patches.jsonl"))
    return {
        "read_only": True,
        "output_dir": str(out),
        "generated_at_utc": utc_now_iso(),
        "learning": learning,
        "reflection_records": reflections,
        "applied_learning_patches": patches,
    }


def build_stage3_log_tail(*, lines: int = 80) -> Dict[str, Any]:
    out = resolve_output_dir()
    tail = _read_log_tail(out / "stage3_24h_runner.log", lines)
    return {
        "read_only": True,
        "output_dir": str(out),
        "generated_at_utc": utc_now_iso(),
        "log_path": str(out / "stage3_24h_runner.log"),
        "lines": lines,
        "log_tail": tail,
    }
