"""365-day deterministic synthetic system lifecycle campaign.

SYSTEM CORRECTNESS ONLY — no profitability, strategy selection, formal
Walk-forward, OOS consumption, or edge claims.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.session_orchestrator_v1_1 import (
    AutonomousSessionOrchestratorV11,
    SessionRunResult,
)
from backend.nexus_execution.orchestrator_adapter_v1 import (
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    CANONICAL_EXECUTION_ENGINE_COUNT,
)
from backend.nexus_system.lifecycle_365d.config import (
    Lifecycle365Config,
    load_lifecycle_365_config,
)
from backend.nexus_system.lifecycle_365d.injections import (
    LIFECYCLE_FAULT_CLASSES,
    LIFECYCLE_LONG_SESSION_INJECTIONS,
    injection_matrix,
)
from backend.nexus_system.lifecycle_365d.invariants import (
    HARD_BANS,
    REQUIRED_ZERO_INVARIANTS,
    empty_invariant_counts,
    invariants_pass,
    merge_invariant_counts,
    violations,
)
from backend.nexus_system.lifecycle_365d.probes import run_focused_lifecycle_probes
from backend.nexus_system.lifecycle_365d.universe import (
    build_lifecycle_candidates,
    universe_summary,
)

PASS_STATUS = "NEXUS_V11_1_SYSTEM_LIFECYCLE_365D_PASS"
INVALID_PREFIX = "NEXUS_V11_1_SYSTEM_LIFECYCLE_365D_INVALID"
SCHEMA = "v11_1_system_365d"
FROZEN_SEED = 911_365
PACKAGE = "NEXUS_V11_1_SYSTEM_LIFECYCLE_365D"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _harden_env() -> None:
    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")
    os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)


def campaign_digest(payload: dict[str, Any]) -> str:
    """Stable digest over deterministic campaign fields (excludes timestamps)."""
    material = {
        "schema": payload.get("schema"),
        "seed": payload.get("seed"),
        "logical_days": payload.get("logical_days"),
        "logical_hours": payload.get("logical_hours"),
        "candidate_count": payload.get("candidate_count"),
        "universe": payload.get("universe"),
        "injection_matrix": payload.get("injection_matrix"),
        "invariants": payload.get("invariants"),
        "session": {
            k: payload.get("session", {}).get(k)
            for k in (
                "session_pass",
                "final_state",
                "logical_duration_hours",
                "candidate_count",
                "restart_count",
                "recovery_count",
                "checkpoint_count",
                "injection_flags",
                "invariants_counts",
                "exchange_write_attempt_count",
                "kill_switch_status",
            )
        },
        "focused_probes_pass": (payload.get("focused_probes") or {}).get("probe_pass"),
        "hard_bans": payload.get("hard_bans"),
        "system_correctness_only": payload.get("system_correctness_only"),
        "edge_claim": payload.get("edge_claim"),
        "profitability_measured": payload.get("profitability_measured"),
        "formal_walk_forward_executed": payload.get("formal_walk_forward_executed"),
        "oos_consumed": payload.get("oos_consumed"),
        "strategy_selected": payload.get("strategy_selected"),
    }
    blob = json.dumps(material, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _sim_extra_invariants(orch: AutonomousSessionOrchestratorV11) -> dict[str, int]:
    """Pull cost-bridge / evidence / checkpoint extras beyond session recovery set."""
    inv = empty_invariant_counts()
    report = orch.sim.report()
    counters = report.get("counters") or {}
    inv["cost_bridge_failure_count"] = int(counters.get("cost_bridge_failure_count", 0) or 0)
    inv["exchange_write_attempt_count"] = int(
        report.get("exchange_write_attempt_count", 0) or orch.guard.exchange_write_attempt_count
    )

    # Evidence binding: every completed reflection/lesson entry must carry intent_key.
    evidence_failures = 0
    for item in orch.reflection_queue:
        if not item.get("intent_key"):
            evidence_failures += 1
    for item in orch.lesson_queue:
        if not item.get("intent_key"):
            evidence_failures += 1
    # Completed trades must have a verifiable cost bridge when present.
    # Binding: position_id + entry/exit order ids (CompletedTrade has no intent_key).
    inner = getattr(orch.sim, "_sim", None)
    trades = getattr(inner, "completed_trades", None) if inner is not None else None
    if trades:
        for t in trades:
            bridge = getattr(t, "cost_bridge", None)
            if bridge is not None and hasattr(bridge, "verify") and not bridge.verify():
                inv["cost_bridge_failure_count"] += 1
            if not getattr(t, "position_id", None) or not getattr(t, "entry_order_id", None):
                evidence_failures += 1
            # Exit must be bound for a completed round-trip.
            if not getattr(t, "exit_order_id", None):
                evidence_failures += 1
    inv["evidence_binding_failure_count"] = evidence_failures

    # Checkpoint loss: if checkpoints were taken, LKG / checkpoint file must exist.
    ckpt = orch.root / f"{orch.session_id}.checkpoint.json"
    lkg = orch.root / "durability" / "last_known_good.json"
    loss = 0
    if orch.checkpoint_count > 0 and not ckpt.exists() and not lkg.exists():
        loss = 1
    inv["checkpoint_loss_count"] = loss
    return inv


def _metrics_from_result(result: SessionRunResult, root: Path) -> dict[str, Any]:
    ledger = root / "durability" / "private_event_ledger.sqlite3"
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
        "provider_failure_count": result.provider_failure_count,
        "reflection_queue_len": result.reflection_queue_len,
        "lesson_queue_len": result.lesson_queue_len,
    }


def run_lifecycle_session(
    root: Path,
    *,
    config: Lifecycle365Config,
) -> dict[str, Any]:
    """Run one accelerated 365-logical-day system session."""
    _harden_env()
    root.mkdir(parents=True, exist_ok=True)
    candidates = build_lifecycle_candidates(
        config.candidate_count,
        seed=config.seed,
        logical_days=config.logical_days,
    )
    uni = universe_summary(candidates)
    inj = list(LIFECYCLE_LONG_SESSION_INJECTIONS)
    restart_after = min(max(8, config.candidate_count // 5), max(1, config.candidate_count - 2))

    orch = AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2)
    try:
        result = orch.run_accelerated_session(
            session_id="SESSION_365D",
            logical_hours=float(config.logical_hours),
            candidates=candidates,
            injections=inj,
            checkpoint_every=max(5, config.candidate_count // 12),
            restart_after_index=restart_after,
            force_kill_after_index=None,
            disk_limit=None,
        )
        base_inv = dict(result.invariants_counts or {})
        extra = _sim_extra_invariants(orch)
        # Session recovery set uses a subset; merge into required zero set.
        merged = empty_invariant_counts()
        for k in REQUIRED_ZERO_INVARIANTS:
            merged[k] = int(base_inv.get(k, 0) or 0) + int(extra.get(k, 0) or 0)
        # Prefer explicit exchange write from guard / extra.
        merged["exchange_write_attempt_count"] = max(
            int(result.exchange_write_attempt_count or 0),
            int(extra.get("exchange_write_attempt_count", 0) or 0),
        )

        report = result.to_dict()
        report["metrics"] = _metrics_from_result(result, root)
        report["schema"] = SCHEMA
        report["seed"] = config.seed
        report["logical_days"] = config.logical_days
        report["universe"] = uni
        report["adapter_id"] = ADAPTER_ID
        report["canonical_execution_engine"] = CANONICAL_EXECUTION_ENGINE
        report["invariants_counts"] = merged
        report["invariants_status"] = "PASS" if invariants_pass(merged) else "FAIL"
        report["session_pass"] = bool(result.session_pass) and invariants_pass(merged)
        report["System_Lifecycle_365d_status"] = (
            PASS_STATUS if report["session_pass"] else f"{INVALID_PREFIX}:SESSION"
        )
        return report
    finally:
        orch.close()


def run_system_lifecycle_365d_campaign(
    root: Path | None = None,
    *,
    config: Lifecycle365Config | None = None,
) -> dict[str, Any]:
    """Run 365d session + focused probes; return immutable-ready package."""
    _harden_env()
    cfg = config or load_lifecycle_365_config()
    base = Path(root) if root else Path(tempfile.mkdtemp(prefix="v11_1_system_365d_"))
    base.mkdir(parents=True, exist_ok=True)

    session = run_lifecycle_session(base / "session_365d", config=cfg)
    focused = run_focused_lifecycle_probes(base / "focused", seed=cfg.seed)

    aggregate = merge_invariant_counts(
        session.get("invariants_counts") or {},
        focused.get("invariants") or {},
    )

    sessions_pass = bool(session.get("session_pass"))
    probes_pass = bool(focused.get("probe_pass"))
    inv_ok = invariants_pass(aggregate)
    all_pass = sessions_pass and probes_pass and inv_ok

    # Hard-ban attestations (system correctness only).
    hard_ban_attest = {
        "strategy_profitability_measured": False,
        "strategy_selected": False,
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
        "edge_claimed": False,
        "exchange_write_attempted": aggregate["exchange_write_attempt_count"] != 0,
    }
    hard_ban_ok = not any(hard_ban_attest.values())

    status = PASS_STATUS if (all_pass and hard_ban_ok) else f"{INVALID_PREFIX}:CAMPAIGN"
    package: dict[str, Any] = {
        "schema": SCHEMA,
        "package": PACKAGE,
        "System_Lifecycle_365d_status": status,
        "system_lifecycle_365d_pass": all_pass and hard_ban_ok,
        "seed": cfg.seed,
        "mode": cfg.mode,
        "logical_days": cfg.logical_days,
        "logical_hours": cfg.logical_hours,
        "candidate_count": cfg.candidate_count,
        "universe": session.get("universe"),
        "fault_classes": list(LIFECYCLE_FAULT_CLASSES),
        "injection_matrix": injection_matrix(),
        "long_session_injections": list(LIFECYCLE_LONG_SESSION_INJECTIONS),
        "session": {
            k: v
            for k, v in session.items()
            if k not in {"contract_requirements"}
        },
        "focused_probes": focused,
        "invariants": aggregate,
        "invariant_violations": violations(aggregate),
        "required_zero_invariants": list(REQUIRED_ZERO_INVARIANTS),
        "hard_bans": list(HARD_BANS),
        "hard_ban_attestations": hard_ban_attest,
        "system_correctness_only": True,
        "edge_claim": False,
        "profitability_measured": False,
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
        "strategy_selected": False,
        "adapter_id": ADAPTER_ID,
        "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
        "canonical_execution_engine_count": CANONICAL_EXECUTION_ENGINE_COUNT,
        "exchange_write_attempt_count": aggregate["exchange_write_attempt_count"],
        "runtime_mode": "ACCELERATED_HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE",
        "created_at": _utc(),
    }
    package["campaign_digest"] = campaign_digest(package)
    return package


__all__ = [
    "FROZEN_SEED",
    "INVALID_PREFIX",
    "PACKAGE",
    "PASS_STATUS",
    "SCHEMA",
    "campaign_digest",
    "run_lifecycle_session",
    "run_system_lifecycle_365d_campaign",
]
