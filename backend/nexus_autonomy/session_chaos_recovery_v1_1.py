"""Session Chaos V1.1 campaign helpers — package 24h/72h/168h accelerated runs.

Wraps ``AutonomousSessionOrchestratorV11`` without modifying the Execution
Simulator fill formulas. Founder-only / no exchange writes.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.session_orchestrator_v1_1 import (
    INJECTION_CATALOG,
    AutonomousSessionOrchestratorV11,
    SessionRunResult,
    build_default_candidates,
)

PASS_STATUS = "NEXUS_AUTONOMOUS_SESSION_ORCHESTRATOR_V1_1_PASS"
INVALID_PREFIX = "NEXUS_SESSION_CHAOS_INVALID"
FROZEN_SEED = 911_001
LOGICAL_SESSION_HOURS: tuple[float, ...] = (24.0, 72.0, 168.0)
SCHEMA = "autonomous_session_orchestrator_v1_1"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def candidate_count_for_hours(logical_hours: float) -> int:
    """Dense enough for modulo-scheduled injection catalog coverage."""
    return max(60, int(logical_hours) + len(INJECTION_CATALOG) * 2)


def _ledger_size_bytes(root: Path) -> int:
    path = root / "durability" / "private_event_ledger.sqlite3"
    try:
        return path.stat().st_size if path.exists() else 0
    except OSError:
        return 0


def _snapshot_size_bytes(root: Path) -> int:
    backup = root / "durability" / "backups"
    total = 0
    if not backup.exists():
        return 0
    for p in backup.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def metrics_from_result(result: SessionRunResult, root: Path) -> dict[str, Any]:
    return {
        "events_processed": result.ledger_event_count,
        "checkpoint_count": result.checkpoint_count,
        "restart_count": result.restart_count,
        "recovery_duration_ms": round(result.accelerated_wall_time_seconds * 1000.0, 3),
        "memory_growth_bytes": max(0, result.memory_peak_bytes - result.memory_start_bytes),
        "cpu_time_ms": round(result.cpu_time_seconds * 1000.0, 3),
        "ledger_size_bytes": _ledger_size_bytes(root),
        "snapshot_size_bytes": _snapshot_size_bytes(root),
        "accelerated_wall_time_seconds": round(result.accelerated_wall_time_seconds, 6),
        "logical_hours": result.logical_duration_hours,
    }


def run_one_chaos_session(
    root: Path,
    *,
    session_id: str,
    logical_hours: float,
    seed: int = FROZEN_SEED,
) -> dict[str, Any]:
    """Run a single accelerated chaos session and return a serialisable report."""
    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")

    count = candidate_count_for_hours(logical_hours)
    # Deterministic shuffle of candidate marks via seed offset in prices.
    candidates = build_default_candidates(count)
    for i, c in enumerate(candidates):
        c["mark_price"] = 100.0 + ((i * 7 + seed) % 200) * 0.5

    injections = list(INJECTION_CATALOG)
    orch = AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2)
    try:
        result = orch.run_accelerated_session(
            session_id=session_id,
            logical_hours=float(logical_hours),
            candidates=candidates,
            injections=injections,
            checkpoint_every=max(5, count // 10),
            restart_after_index=min(12, count // 5),
            force_kill_after_index=None,
            disk_limit=None,  # derived from catalog flags inside orchestrator
        )
        report = result.to_dict()
        report["metrics"] = metrics_from_result(result, root)
        report["schema"] = SCHEMA
        report["seed"] = seed
        report["session_pass"] = bool(result.session_pass)
        report["Session_Chaos_status"] = (
            PASS_STATUS if result.session_pass else f"{INVALID_PREFIX}:{session_id}"
        )
        return report
    finally:
        orch.close()


def run_session_chaos_campaign(
    root: Path | None = None,
    *,
    seed: int = FROZEN_SEED,
    logical_hours: tuple[float, ...] = LOGICAL_SESSION_HOURS,
) -> dict[str, Any]:
    """Run 24h / 72h / 168h accelerated chaos sessions and aggregate status."""
    base = Path(root) if root else Path(tempfile.mkdtemp(prefix="session_chaos_v11_"))
    base.mkdir(parents=True, exist_ok=True)

    sessions: dict[str, Any] = {}
    aggregate_metrics = {
        "events_processed": 0,
        "checkpoint_count": 0,
        "restart_count": 0,
        "recovery_duration_ms": 0.0,
        "memory_growth_bytes": 0,
        "cpu_time_ms": 0.0,
        "ledger_size_bytes": 0,
        "snapshot_size_bytes": 0,
    }
    aggregate_inv = {
        "open_ambiguous_position_count": 0,
        "orphan_lifecycle_count": 0,
        "duplicate_position_count": 0,
        "unclosed_intent_count": 0,
        "untracked_fill_count": 0,
        "risk_limit_bypass_count": 0,
        "exchange_write_attempt_count": 0,
    }
    all_pass = True
    invalid_reasons: list[str] = []

    for hours in logical_hours:
        label = f"SESSION_{int(hours)}H"
        sess_root = base / label.lower()
        report = run_one_chaos_session(
            sess_root,
            session_id=label,
            logical_hours=float(hours),
            seed=seed + int(hours),
        )
        (sess_root / "session_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        sessions[label] = report

        for k in aggregate_metrics:
            aggregate_metrics[k] = aggregate_metrics[k] + float(report["metrics"].get(k, 0))
        for k in aggregate_inv:
            aggregate_inv[k] = aggregate_inv[k] + int((report.get("invariants_counts") or {}).get(k, 0))
        if not report.get("session_pass"):
            all_pass = False
            invalid_reasons.append(report.get("Session_Chaos_status") or f"{INVALID_PREFIX}:{label}")

    if any(v != 0 for v in aggregate_inv.values()):
        all_pass = False
        bad = {k: v for k, v in aggregate_inv.items() if v != 0}
        invalid_reasons.append(f"{INVALID_PREFIX}:AGG_INVARIANTS:{bad}")

    status = PASS_STATUS if all_pass else (invalid_reasons[0] if invalid_reasons else f"{INVALID_PREFIX}:UNKNOWN")
    return {
        "schema": SCHEMA,
        "package": "NEXUS_AUTONOMOUS_SESSION_ORCHESTRATOR_V1_1",
        "Session_Chaos_status": status,
        "seed": seed,
        "logical_sessions_hours": list(logical_hours),
        "chaos_catalog": list(INJECTION_CATALOG),
        "sessions": {
            k: {sk: sv for sk, sv in v.items() if sk != "contract_requirements"}
            for k, v in sessions.items()
        },
        "metrics_summary": aggregate_metrics,
        "invariants": aggregate_inv,
        "exchange_write_attempt_count": aggregate_inv["exchange_write_attempt_count"],
        "mode": "ACCELERATED_HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE",
        "created_at": _utc(),
    }
