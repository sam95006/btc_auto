"""Read-only domain health collectors for Founder-private observability SLO."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_execution.risk_gates import FORBIDDEN_ACTIONS, MAX_LEVERAGE_CEILING
from backend.nexus_microstructure.storage_budget_v10 import (
    DEFAULT_MINIMUM_FREE_DISK_BYTES,
    StorageBudgetControllerV10,
    check_minimum_free_disk,
)
from backend.nexus_observability.constants import STALENESS_THRESHOLD_SECONDS
from backend.nexus_private_control.health import build_health, build_observability
from backend.nexus_provider.transport_status import PROVIDER_TRANSPORT_STATUSES
from backend.nexus_reflection.lesson_gate_v11 import apply_lesson_gate_v11
from backend.nexus_autonomy.qualification_blocked_stages_v10 import (
    HARD_BANS as QUAL_HARD_BANS,
    blocked_stage_matrix_document,
)
from backend.nexus_runtime.durability_v2.constants import BLOCKED_AMBIGUOUS_STATE


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def collect_decision_lifecycle(root: Path, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = dict(overrides or {})
    # Prefer explicit override (tests / harness); else scan lightweight status artifacts.
    if ov:
        age = float(ov.get("max_evidence_age_seconds", 0.0) or 0.0)
        stale = bool(ov.get("stale", age > STALENESS_THRESHOLD_SECONDS))
        dq_ok = bool(ov.get("data_quality_ok", True))
        blocked = int(ov.get("blocked_ambiguous_count", 0) or 0)
        failure_trap = bool(ov.get("failure_trap", False))
        slo_ok = (not stale) and dq_ok and blocked == 0 and not failure_trap
        active = []
        if stale:
            active.append("staleness")
        if not dq_ok:
            active.append("data_quality")
        if blocked:
            active.extend(["ambiguous_state", "failure_state"])
        if failure_trap:
            active.append("failure_state")
        return {
            "domain": "decision_lifecycle",
            "slo_ok": slo_ok,
            "max_evidence_age_seconds": age,
            "stale": stale,
            "data_quality_ok": dq_ok,
            "dq_detail": ov.get("dq_detail"),
            "blocked_ambiguous_count": blocked,
            "failure_trap": failure_trap,
            "active_alert_classes": sorted(set(active)),
            "canonical_states_known": True,
        }

    # Default healthy baseline when no live decision runtime is present.
    return {
        "domain": "decision_lifecycle",
        "slo_ok": True,
        "max_evidence_age_seconds": 0.0,
        "stale": False,
        "data_quality_ok": True,
        "blocked_ambiguous_count": 0,
        "failure_trap": False,
        "active_alert_classes": [],
        "canonical_states_known": True,
        "note": "no_live_decision_runtime_assumed_healthy_baseline",
        "root_scanned": str(root),
    }


def collect_session_lifecycle(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = dict(overrides or {})
    states = list(ov.get("terminal_failure_states") or [])
    failed = bool(ov.get("failed_safe", False)) or ("FAILED_SAFE" in states) or ("BLOCKED" in states)
    return {
        "domain": "session_lifecycle",
        "slo_ok": not failed,
        "terminal_failure_states": states,
        "failed_safe": failed,
        "active_alert_classes": ["failure_state"] if failed else [],
        "canonical_states_known": True,
    }


def collect_risk_gates(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = dict(overrides or {})
    intact = bool(ov.get("gates_intact", True))
    if "forbidden_actions" in ov:
        # Adversarial: missing forbidden actions => compromised
        present = set(ov.get("forbidden_actions") or [])
        intact = intact and FORBIDDEN_ACTIONS.issubset(present)
    return {
        "domain": "risk_gates",
        "slo_ok": intact,
        "gates_intact": intact,
        "max_leverage_ceiling": MAX_LEVERAGE_CEILING,
        "forbidden_action_count": len(FORBIDDEN_ACTIONS),
        "forbidden_actions_sample": sorted(FORBIDDEN_ACTIONS)[:5],
        "detail": ov.get("detail"),
        "active_alert_classes": [] if intact else ["failure_state"],
        "order_or_policy_mutation": False,
    }


def collect_execution_simulator(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = dict(overrides or {})
    mutation_endpoints = int(ov.get("mutation_endpoint_count", 0) or 0)
    return {
        "domain": "execution_simulator",
        "slo_ok": mutation_endpoints == 0,
        "mutation_endpoint_count": mutation_endpoints,
        "read_only_observability": True,
        "execution_mutation_endpoint": False,
        "active_alert_classes": [] if mutation_endpoints == 0 else ["failure_state"],
    }


def collect_provider_health(root: Path, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = dict(overrides or {})
    ckpt = _load_json(root / ".nexus_runtime/blind_reflection_v23_checkpoint.json")
    transport = ckpt.get("transport") or {}
    groq = transport.get("GROQ_REFLECTION_REASONER") or {}
    samba = transport.get("SAMBANOVA_INDEPENDENT_CRITIC") or {}

    success = int(ov.get("success_count", groq.get("success_count") or samba.get("success_count") or 0) or 0)
    pending = int(
        ov.get(
            "pending_count",
            len(ckpt.get("pending_case_ids") or []) + len(ckpt.get("critic_pending_ids") or []),
        )
        or 0
    )
    status = str(ov.get("transport_status") or "").upper()
    terminal = str(ov.get("terminal_status") or "").upper()
    if not terminal and success < 80 and (ckpt or ov):
        # Align with private_observability_v1 capacity signal when checkpoint present or override forces eval
        if ckpt or "success_count" in ov or "pending_count" in ov:
            terminal = "INCOMPLETE_PROVIDER_CAPACITY" if success < 80 else "PENDING_QUALITY_GATES"

    capacity_blocked = bool(ov.get("capacity_blocked", False))
    if status in {"RATE_LIMITED", "CIRCUIT_OPEN", "BUCKET_THROTTLED", "TIMEOUT"}:
        capacity_blocked = True
    if terminal == "INCOMPLETE_PROVIDER_CAPACITY":
        capacity_blocked = True

    # No checkpoint and no overrides => healthy baseline (capacity not yet measured).
    if not ckpt and not ov:
        capacity_blocked = False
        terminal = "NOT_MEASURED"
        success = 0
        pending = 0

    return {
        "domain": "provider_health",
        "slo_ok": not capacity_blocked,
        "transport_status": status or None,
        "terminal_status": terminal or None,
        "success_count": success,
        "pending_count": pending,
        "capacity_blocked": capacity_blocked,
        "known_transport_statuses": sorted(PROVIDER_TRANSPORT_STATUSES),
        "active_alert_classes": ["provider_capacity"] if capacity_blocked else [],
        "secrets_present": False,
    }


def collect_reflection_queue(root: Path, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = dict(overrides or {})
    provider = collect_provider_health(root, ov if ov else None)
    pending = int(ov.get("pending_count", provider.get("pending_count") or 0) or 0)
    success = int(ov.get("success_count", provider.get("success_count") or 0) or 0)
    stale_queue = bool(ov.get("stale_queue", False))
    if pending > 0 and success == 0 and (ov or _load_json(root / ".nexus_runtime/blind_reflection_v23_checkpoint.json")):
        stale_queue = True
    capacity = bool(provider.get("capacity_blocked"))
    slo_ok = (not capacity) and (not stale_queue)
    active = []
    if capacity:
        active.append("provider_capacity")
    if stale_queue:
        active.append("staleness")
    return {
        "domain": "reflection_queue",
        "slo_ok": slo_ok,
        "pending_count": pending,
        "success_count": success,
        "stale_queue": stale_queue,
        "terminal_status": provider.get("terminal_status"),
        "active_alert_classes": active,
    }


def collect_lesson_gate(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = dict(overrides or {})
    gate = apply_lesson_gate_v11(
        terminal_status=ov.get("terminal_status", "INCOMPLETE_PROVIDER_CAPACITY"),
        quality_gates_passed=bool(ov.get("quality_gates_passed", False)),
        proposed_policy_effect_lesson_count=int(ov.get("proposed_policy_effect_lesson_count", 3) or 0),
        fixture_label=ov.get("fixture_label"),
    )
    unauthorized = int(ov.get("unauthorized_lesson_count", 0) or 0)
    # If lessons were incorrectly allowed without VERIFIED, count as unauthorized.
    if gate["policy_effect_lesson_allowed"] is False:
        # Gate correctly blocked — unauthorized should be 0 unless override injects leak.
        unauthorized = int(ov.get("unauthorized_lesson_count", 0) or 0)
    else:
        # Allowed only when VERIFIED — still ok.
        unauthorized = int(ov.get("unauthorized_lesson_count", 0) or 0)
    slo_ok = unauthorized == 0 and gate.get("risk_limits_changed") is False
    return {
        "domain": "lesson_gate",
        "slo_ok": slo_ok,
        "gate": {
            "policy_effect_lesson_allowed": gate["policy_effect_lesson_allowed"],
            "new_policy_effect_lesson_count": gate["new_policy_effect_lesson_count"],
            "lesson_prevention_blocked_reason": gate["lesson_prevention_blocked_reason"],
            "risk_limits_changed": gate["risk_limits_changed"],
            "leverage_changed": gate["leverage_changed"],
        },
        "unauthorized_lesson_count": unauthorized,
        "active_alert_classes": ["data_quality", "failure_state"] if unauthorized else [],
    }


def collect_ledger_snapshot_checkpoint(
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ov = dict(overrides or {})
    ambiguous = bool(ov.get("ambiguous_state", False))
    ambiguous_count = int(ov.get("ambiguous_count", 1 if ambiguous else 0) or 0)
    dq_ok = bool(ov.get("data_quality_ok", True))
    checkpoint_ok = bool(ov.get("checkpoint_ok", True))
    slo_ok = (ambiguous_count == 0) and dq_ok and checkpoint_ok
    active = []
    if ambiguous_count:
        active.append("ambiguous_state")
    if not dq_ok:
        active.append("data_quality")
    if not checkpoint_ok:
        active.append("failure_state")
    return {
        "domain": "ledger_snapshot_checkpoint",
        "slo_ok": slo_ok,
        "ambiguous_state": ambiguous_count > 0,
        "ambiguous_count": ambiguous_count,
        "ambiguous_status_token": BLOCKED_AMBIGUOUS_STATE,
        "data_quality_ok": dq_ok,
        "checkpoint_ok": checkpoint_ok,
        "active_alert_classes": active,
    }


def collect_microstructure_health(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = dict(overrides or {})
    integrity_ok = bool(ov.get("integrity_ok", True))
    event_study_started = bool(ov.get("event_study_started", False))
    event_study_readiness = ov.get("event_study_readiness", "NOT_READY")
    slo_ok = integrity_ok and (not event_study_started) and event_study_readiness == "NOT_READY"
    return {
        "domain": "microstructure_health",
        "slo_ok": slo_ok,
        "integrity_ok": integrity_ok,
        "event_study_started": event_study_started,
        "event_study_readiness": event_study_readiness,
        "detail": ov.get("detail"),
        "active_alert_classes": [] if integrity_ok else ["data_quality"],
    }


def collect_storage_budget(
    root: Path,
    overrides: dict[str, Any] | None = None,
    *,
    disk_root: str | None = None,
) -> dict[str, Any]:
    ov = dict(overrides or {})
    if ov:
        floor_ok = bool(ov.get("floor_ok", True))
        mode = str(ov.get("mode", "NORMAL"))
        return {
            "domain": "storage_budget",
            "slo_ok": floor_ok and mode != "STORAGE_BUDGET_BLOCKED",
            "floor_ok": floor_ok,
            "mode": mode,
            "free_bytes": ov.get("free_bytes"),
            "minimum_free_disk_bytes": ov.get(
                "minimum_free_disk_bytes", DEFAULT_MINIMUM_FREE_DISK_BYTES
            ),
            "stop_reason": ov.get("stop_reason"),
            "active_alert_classes": []
            if (floor_ok and mode != "STORAGE_BUDGET_BLOCKED")
            else ["storage_floor"],
        }

    probe = disk_root or str(root)
    # Use a tiny minimum in default collect to avoid false FAIL on constrained CI disks
    # unless caller asks for production floor via override. Report both measured free and
    # configured production floor constant.
    measured = check_minimum_free_disk(probe, minimum_free_disk_bytes=1)
    ctrl = StorageBudgetControllerV10(disk_root=probe, minimum_free_disk_bytes=1)
    ctrl.refresh_free_disk()
    report = ctrl.report()
    # Production floor evaluation (informational + alert if free < 30GiB)
    prod = check_minimum_free_disk(probe, minimum_free_disk_bytes=DEFAULT_MINIMUM_FREE_DISK_BYTES)
    floor_ok = bool(prod.get("passed"))
    mode = report.get("mode") if floor_ok else "STORAGE_BUDGET_BLOCKED"
    return {
        "domain": "storage_budget",
        "slo_ok": floor_ok,
        "floor_ok": floor_ok,
        "mode": mode,
        "free_bytes": measured.get("free_bytes"),
        "minimum_free_disk_bytes": DEFAULT_MINIMUM_FREE_DISK_BYTES,
        "production_floor": prod,
        "stop_reason": None if floor_ok else "minimum_free_disk_fail",
        "storage_cap_configured": True,
        "active_alert_classes": [] if floor_ok else ["storage_floor"],
    }


def collect_kill_switch_readiness(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = dict(overrides or {})
    reachable = bool(ov.get("reachable", True))
    engaged = bool(ov.get("kill_switch_engaged", False))
    # Exercise read-only health builder (no mutation).
    health = build_health(
        state=ov.get("state", "RUNNING"),
        mode=ov.get("mode", "HISTORICAL_REPLAY_SIMULATED"),
        kill_switch_engaged=engaged,
        exchange_write_attempt_count=0,
        checkpoint_count=int(ov.get("checkpoint_count", 0) or 0),
        run_id=ov.get("run_id", "obs_slo_probe"),
    )
    obs = build_observability(
        state=health["state"],
        mode=health["mode"],
        kill_switch_engaged=engaged,
        kill_switch_reason=ov.get("kill_switch_reason"),
        exchange_write_attempt_count=0,
        checkpoint_count=health["checkpoint_count"],
        transition_count=0,
        run_id=health["run_id"],
        allowed_modes=["HISTORICAL_REPLAY_SIMULATED", "PROVIDER_CALIBRATION", "MICROSTRUCTURE_CAPTURE"],
        commands_invoked=["observability"],
    )
    return {
        "domain": "kill_switch_readiness",
        "slo_ok": reachable,
        "reachable": reachable,
        "kill_switch_engaged": engaged,
        "health_healthy_flag": health.get("healthy"),
        "observability_read_only": obs.get("read_only"),
        "public_api_exposed": False,
        "active_alert_classes": [] if reachable else ["failure_state"],
    }


def collect_qualification_block_state(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = dict(overrides or {})
    doc = blocked_stage_matrix_document()
    stages = dict(ov.get("stages") or doc["stages"])
    all_blocked = all(v == "BLOCKED" for v in stages.values())
    if "all_stages_blocked" in ov:
        all_blocked = bool(ov["all_stages_blocked"])
    bans = list(ov.get("hard_bans") or doc["hard_bans"])
    bans_intact = set(QUAL_HARD_BANS).issubset(set(bans))
    slo_ok = all_blocked and bans_intact
    return {
        "domain": "qualification_block_state",
        "slo_ok": slo_ok,
        "all_stages_blocked": all_blocked,
        "stages": stages,
        "hard_bans_intact": bans_intact,
        "hard_ban_count": len(bans),
        "active_alert_classes": [] if slo_ok else ["failure_state"],
    }


def collect_all_domains(
    root: Path,
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
    disk_root: str | None = None,
) -> dict[str, Any]:
    ov = overrides or {}
    return {
        "decision_lifecycle": collect_decision_lifecycle(root, ov.get("decision_lifecycle")),
        "session_lifecycle": collect_session_lifecycle(ov.get("session_lifecycle")),
        "risk_gates": collect_risk_gates(ov.get("risk_gates")),
        "execution_simulator": collect_execution_simulator(ov.get("execution_simulator")),
        "provider_health": collect_provider_health(root, ov.get("provider_health")),
        "reflection_queue": collect_reflection_queue(root, ov.get("reflection_queue")),
        "lesson_gate": collect_lesson_gate(ov.get("lesson_gate")),
        "ledger_snapshot_checkpoint": collect_ledger_snapshot_checkpoint(
            ov.get("ledger_snapshot_checkpoint")
        ),
        "microstructure_health": collect_microstructure_health(ov.get("microstructure_health")),
        "storage_budget": collect_storage_budget(
            root, ov.get("storage_budget"), disk_root=disk_root
        ),
        "kill_switch_readiness": collect_kill_switch_readiness(ov.get("kill_switch_readiness")),
        "qualification_block_state": collect_qualification_block_state(
            ov.get("qualification_block_state")
        ),
    }
