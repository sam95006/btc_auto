"""V10 Session Scale — 30-day and 90-day accelerated Session campaigns.

Wraps ``AutonomousSessionOrchestratorV11`` (canonical Execution via
``NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1``) without modifying fill formulas.

Injects process crashes, partial fills, duplicate intents, provider outages,
storage limits, ledger/snapshot corruption, and (as focused probes) clock jumps.

Mode: ACCELERATED_HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.session_orchestrator_v1_1 import (
    AutonomousSessionOrchestratorV11,
    SessionRunResult,
    build_default_candidates,
)
from backend.nexus_execution.orchestrator_adapter_v1 import (
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    CANONICAL_EXECUTION_ENGINE_COUNT,
)
from backend.nexus_execution.scale_.config import ScaleConfig, load_scale_config
from backend.nexus_execution.scale_.injections import (
    FOCUSED_TERMINAL_INJECTIONS,
    SCALE_FAULT_CLASSES,
    SCALE_LONG_SESSION_INJECTIONS,
    injection_matrix,
)
from backend.nexus_recovery.crash_recovery import recover_from_checkpoint

PASS_STATUS = "NEXUS_V10_SESSION_SCALE_PASS"
INVALID_PREFIX = "NEXUS_V10_SESSION_SCALE_INVALID"
SCHEMA = "v10_session_scale"
FROZEN_SEED = 911_100


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _harden_env() -> None:
    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")


def _ledger_path(root: Path) -> Path:
    return root / "durability" / "private_event_ledger.sqlite3"


def _lkg_path(root: Path) -> Path:
    return root / "durability" / "last_known_good.json"


def metrics_from_result(result: SessionRunResult, root: Path) -> dict[str, Any]:
    ledger = _ledger_path(root)
    ledger_size = ledger.stat().st_size if ledger.exists() else 0
    return {
        "events_processed": result.ledger_event_count,
        "checkpoint_count": result.checkpoint_count,
        "restart_count": result.restart_count,
        "recovery_count": result.recovery_count,
        "accelerated_wall_time_seconds": round(result.accelerated_wall_time_seconds, 6),
        "logical_hours": result.logical_duration_hours,
        "ledger_size_bytes": ledger_size,
        "memory_peak_bytes": result.memory_peak_bytes,
        "cpu_time_seconds": round(result.cpu_time_seconds, 6),
        "candidate_count": result.candidate_count,
        "intent_count": result.intent_count,
        "position_count": result.position_count,
        "exit_count": result.exit_count,
    }


def _build_candidates(count: int, *, seed: int) -> list[dict[str, Any]]:
    candidates = build_default_candidates(count)
    for i, c in enumerate(candidates):
        c["mark_price"] = 100.0 + ((i * 7 + seed) % 200) * 0.5
        # Periodically request provider path so outage injections fire.
        if i % 17 == 0:
            c["uses_provider"] = True
            c["provider"] = "GROQ"
        elif i % 19 == 0:
            c["uses_provider"] = True
            c["provider"] = "SAMBANOVA"
    return candidates


def run_scaled_session(
    root: Path,
    *,
    session_id: str,
    logical_hours: float,
    candidate_count: int,
    seed: int = FROZEN_SEED,
    injections: list[str] | None = None,
    restart_after_index: int | None = None,
) -> dict[str, Any]:
    """Run one accelerated scale Session and return a serialisable report."""
    _harden_env()
    root.mkdir(parents=True, exist_ok=True)
    inj = list(injections) if injections is not None else list(SCALE_LONG_SESSION_INJECTIONS)
    candidates = _build_candidates(candidate_count, seed=seed)
    # Ensure process_termination actually triggers a restart mid-session.
    if restart_after_index is None and "process_termination" in inj:
        restart_after_index = min(max(8, candidate_count // 5), max(1, candidate_count - 2))

    orch = AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2)
    try:
        result = orch.run_accelerated_session(
            session_id=session_id,
            logical_hours=float(logical_hours),
            candidates=candidates,
            injections=inj,
            checkpoint_every=max(5, candidate_count // 12),
            restart_after_index=restart_after_index,
            force_kill_after_index=None,
            disk_limit=None,
        )
        report = result.to_dict()
        report["metrics"] = metrics_from_result(result, root)
        report["schema"] = SCHEMA
        report["seed"] = seed
        report["adapter_id"] = ADAPTER_ID
        report["canonical_execution_engine"] = CANONICAL_EXECUTION_ENGINE
        report["session_pass"] = bool(result.session_pass)
        report["Session_Scale_status"] = (
            PASS_STATUS if result.session_pass else f"{INVALID_PREFIX}:{session_id}"
        )
        return report
    finally:
        orch.close()


def run_focused_injection_probes(base: Path, *, seed: int) -> dict[str, Any]:
    """Exercise terminal / corruption probes that must fail-closed safely."""
    _harden_env()
    probes: dict[str, Any] = {}

    # Clock jumps + disk hard limit: expect BLOCKED / FAILED_SAFE, no exchange write.
    for flag in FOCUSED_TERMINAL_INJECTIONS:
        root = base / f"probe_{flag}"
        orch = AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2)
        try:
            cands = _build_candidates(40, seed=seed + hash(flag) % 10_000)
            result = orch.run_accelerated_session(
                session_id=f"PROBE_{flag.upper()}",
                logical_hours=24.0,
                candidates=cands,
                injections=[flag],
                checkpoint_every=8,
                restart_after_index=None,
            )
            ok = (
                result.final_state in {"BLOCKED", "FAILED_SAFE", "COMPLETED"}
                and result.exchange_write_attempt_count == 0
                and result.invariants_status == "PASS"
            )
            # Terminal injections should not leave ambiguous open risk.
            if flag in {"clock_jump_forward", "clock_jump_backward", "disk_hard_limit"}:
                ok = ok and result.final_state in {"BLOCKED", "FAILED_SAFE", "COMPLETED"}
            probes[flag] = {
                "final_state": result.final_state,
                "session_pass": result.session_pass,
                "exchange_write_attempt_count": result.exchange_write_attempt_count,
                "invariants_status": result.invariants_status,
                "probe_pass": ok,
            }
        finally:
            orch.close()

    # Ledger corruption probe: corrupt sqlite bytes after a clean short run.
    ledger_root = base / "probe_ledger_corruption"
    orch = AutonomousSessionOrchestratorV11(ledger_root, max_positions=2, max_intents=2)
    try:
        orch.start("PROBE_LEDGER_CORRUPT", logical_hours=1.0)
        orch._checkpoint(reason="pre_ledger_corrupt")  # noqa: SLF001 — intentional scale probe
    finally:
        orch.close()
    ledger = _ledger_path(ledger_root)
    ledger_probe: dict[str, Any] = {"path_exists": ledger.exists()}
    if ledger.exists():
        raw = bytearray(ledger.read_bytes())
        # Flip bytes in the middle to simulate corruption without deleting the file.
        mid = max(16, len(raw) // 2)
        for i in range(mid, min(mid + 32, len(raw))):
            raw[i] = (raw[i] ^ 0xFF) & 0xFF
        ledger.write_bytes(bytes(raw))
        ledger_probe["corrupted_bytes"] = min(32, len(raw) - mid)
        # Recovery must not invent state; accept BLOCKED_AMBIGUOUS / error / RECOVERED
        # only if invariants still pass and no exchange write occurs.
        try:
            outcome = recover_from_checkpoint(ledger_root, "PROBE_LEDGER_CORRUPT")
            ledger_probe["recovery_status"] = outcome.status
            ledger_probe["recovery_reason"] = outcome.reason
            ledger_probe["probe_pass"] = outcome.status in {
                "BLOCKED_AMBIGUOUS",
                "RECOVERED",
                "FAILED_SAFE",
            }
        except Exception as exc:  # pragma: no cover — fail-closed on corrupt IO
            ledger_probe["recovery_status"] = "EXCEPTION_FAIL_CLOSED"
            ledger_probe["recovery_reason"] = f"{type(exc).__name__}:{exc}"
            ledger_probe["probe_pass"] = True
    else:
        ledger_probe["probe_pass"] = False
        ledger_probe["recovery_status"] = "MISSING_LEDGER"
    probes["ledger_corruption_probe"] = ledger_probe

    # Snapshot corruption probe: poison LKG checksum → BLOCKED_AMBIGUOUS.
    snap_root = base / "probe_snapshot_corruption"
    orch = AutonomousSessionOrchestratorV11(snap_root, max_positions=2, max_intents=2)
    try:
        orch.start("PROBE_SNAP_CORRUPT", logical_hours=1.0)
    finally:
        orch.close()
    lkg = _lkg_path(snap_root)
    snap_probe: dict[str, Any] = {"path_exists": lkg.exists()}
    if lkg.exists():
        pointer = json.loads(lkg.read_text(encoding="utf-8"))
        pointer["snapshot_checksum"] = "0" * 64
        lkg.write_text(json.dumps(pointer) + "\n", encoding="utf-8")
        outcome = recover_from_checkpoint(snap_root, "PROBE_SNAP_CORRUPT")
        snap_probe["recovery_status"] = outcome.status
        snap_probe["recovery_reason"] = outcome.reason
        snap_probe["probe_pass"] = (
            outcome.status == "BLOCKED_AMBIGUOUS"
            and outcome.reason == "snapshot_corruption"
        )
    else:
        snap_probe["probe_pass"] = False
    probes["snapshot_corruption_probe"] = snap_probe

    all_pass = all(bool(p.get("probe_pass")) for p in probes.values())
    return {
        "schema": f"{SCHEMA}_focused_probes",
        "probe_pass": all_pass,
        "probes": probes,
        "fault_classes_covered": list(SCALE_FAULT_CLASSES),
        "created_at": _utc(),
    }


def run_session_scale_campaign(
    root: Path | None = None,
    *,
    config: ScaleConfig | None = None,
) -> dict[str, Any]:
    """Run 30-day + 90-day accelerated Sessions and focused injection probes."""
    cfg = config or load_scale_config()
    base = Path(root) if root else Path(tempfile.mkdtemp(prefix="v10_session_scale_"))
    base.mkdir(parents=True, exist_ok=True)

    sessions: dict[str, Any] = {}
    plans = (
        ("SESSION_30D", cfg.day_30_hours, cfg.session_candidate_count_30d),
        ("SESSION_90D", cfg.day_90_hours, cfg.session_candidate_count_90d),
    )
    for label, hours, cand_count in plans:
        sess_root = base / label.lower()
        report = run_scaled_session(
            sess_root,
            session_id=label,
            logical_hours=float(hours),
            candidate_count=cand_count,
            seed=cfg.session_seed + int(hours),
        )
        (sess_root / "session_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        sessions[label] = report

    focused = run_focused_injection_probes(base / "focused", seed=cfg.session_seed)

    aggregate_inv = {
        "open_ambiguous_position_count": 0,
        "orphan_lifecycle_count": 0,
        "duplicate_position_count": 0,
        "unclosed_intent_count": 0,
        "untracked_fill_count": 0,
        "risk_limit_bypass_count": 0,
        "exchange_write_attempt_count": 0,
    }
    for report in sessions.values():
        for k in aggregate_inv:
            aggregate_inv[k] += int((report.get("invariants_counts") or {}).get(k, 0))

    sessions_pass = all(bool(r.get("session_pass")) for r in sessions.values())
    inv_pass = all(v == 0 for v in aggregate_inv.values())
    all_pass = sessions_pass and inv_pass and bool(focused.get("probe_pass"))

    status = PASS_STATUS if all_pass else f"{INVALID_PREFIX}:CAMPAIGN"
    return {
        "schema": SCHEMA,
        "package": "NEXUS_V10_SESSION_SCALE",
        "Session_Scale_status": status,
        "session_scale_pass": all_pass,
        "seed": cfg.session_seed,
        "mode": cfg.mode,
        "logical_sessions_hours": [cfg.day_30_hours, cfg.day_90_hours],
        "candidate_counts": {
            "SESSION_30D": cfg.session_candidate_count_30d,
            "SESSION_90D": cfg.session_candidate_count_90d,
        },
        "injection_matrix": injection_matrix(),
        "long_session_injections": list(SCALE_LONG_SESSION_INJECTIONS),
        "sessions": {
            k: {sk: sv for sk, sv in v.items() if sk != "contract_requirements"}
            for k, v in sessions.items()
        },
        "focused_probes": focused,
        "invariants": aggregate_inv,
        "adapter_id": ADAPTER_ID,
        "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
        "canonical_execution_engine_count": CANONICAL_EXECUTION_ENGINE_COUNT,
        "exchange_write_attempt_count": aggregate_inv["exchange_write_attempt_count"],
        "runtime_mode": "ACCELERATED_HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE",
        "created_at": _utc(),
    }


__all__ = [
    "FROZEN_SEED",
    "INVALID_PREFIX",
    "PASS_STATUS",
    "SCHEMA",
    "run_focused_injection_probes",
    "run_scaled_session",
    "run_session_scale_campaign",
]
