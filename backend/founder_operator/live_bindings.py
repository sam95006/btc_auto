"""Founder Operator live / simulated surface bindings (PUB2-D).

Each operator panel binds to a real local runtime artifact when present,
otherwise an *explicit* SIMULATED research fixture. LIVE mode never silently
falls back to fixtures. No secrets, no exchange writes, no member exposure.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SURFACE_IDS: tuple[str, ...] = (
    "capture",
    "provider",  # V2.3 provider transport
    "decision",
    "execution_sim",
    "risk",
    "ledger",
    "checkpoint",
    "reflection",
    "lesson",
    "qualification",
    "storage",
    "kill_switch",
)

# Human labels for the operational surfaces named in the PUB2-D brief.
SURFACE_LABELS: dict[str, str] = {
    "capture": "Capture Supervisor",
    "provider": "Reflection V2.3 Provider Transport",
    "decision": "Decision Lifecycle",
    "execution_sim": "Execution Simulator",
    "risk": "Risk Governor",
    "ledger": "Checksummed Ledger",
    "checkpoint": "Checkpoint Authority",
    "reflection": "Reflection Adjudication",
    "lesson": "Lesson Gate",
    "qualification": "Qualification Control Plane",
    "storage": "Private Storage Floor",
    "kill_switch": "Kill-Switch Readiness",
}

PANEL_TITLES: dict[str, str] = {
    "capture": "Capture Health",
    "provider": "V2.3 Provider Transport",
    "decision": "Decision Lifecycle",
    "execution_sim": "Execution Simulation",
    "risk": "Risk State",
    "ledger": "Ledger Health",
    "checkpoint": "Checkpoint Health",
    "reflection": "Reflection Progress",
    "lesson": "Lesson Gate",
    "qualification": "Qualification Blocks",
    "storage": "Storage",
    "kill_switch": "Kill-Switch Readiness",
}

PANEL_SUMMARIES: dict[str, str] = {
    "capture": "Bound to capture supervisor observability (read-only).",
    "provider": "Bound to Reflection V2.3 provider / shadow-compare transport.",
    "decision": "Bound to private Decision lifecycle ontology progress.",
    "execution_sim": "Bound to simulated execution only — never live exchange.",
    "risk": "Bound to private risk governor flags (observe only).",
    "ledger": "Bound to checksummed private event ledger health.",
    "checkpoint": "Bound to canonical checkpoint envelope authority.",
    "reflection": "Bound to Reflection V2.3 adjudication progress (private).",
    "lesson": "Bound to Lesson Memory gate — Founder-private only.",
    "qualification": "Bound to formal qualification control plane — blocked-ready.",
    "storage": "Bound to private storage velocity / capacity floor.",
    "kill_switch": "Bound to kill-switch readiness only — no live engage from UI.",
}

# Candidate LIVE artifact filenames under NEXUS_RUNTIME (never invent values).
_LIVE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "capture": (
        "ms_accum_v13_integrity_14d_health.json",
        "capture_supervisor_health.json",
        "artifacts/readiness/immutable/v14_capture_supervisor/health.json",
    ),
    "provider": (
        "reflection_v23_checkpoint.json",
        "v23_checkpoint.json",
        "provider_transport_health.json",
    ),
    "decision": (
        "decision_lifecycle_status.json",
        "artifacts/decision_lifecycle_status.json",
    ),
    "execution_sim": (
        "execution_simulator_status.json",
        "artifacts/execution_simulator_status.json",
    ),
    "risk": (
        "risk_governor_status.json",
        "artifacts/risk_governor_status.json",
    ),
    "ledger": (
        "checksummed_ledger_health.json",
        "artifacts/checksummed_ledger_health.json",
    ),
    "checkpoint": (
        "checkpoint_authority_status.json",
        "v23_checkpoint.json",
        "reflection_v23_checkpoint.json",
    ),
    "reflection": (
        "reflection_v23_checkpoint.json",
        "v23_checkpoint.json",
        "artifacts/reflection_progress.json",
    ),
    "lesson": (
        "lesson_gate_status.json",
        "artifacts/lesson_gate_status.json",
    ),
    "qualification": (
        "qualification_control_status.json",
        "artifacts/qualification_control_status.json",
    ),
    "storage": (
        "storage_velocity_status.json",
        "artifacts/storage_velocity_status.json",
    ),
    "kill_switch": (
        "kill_switch_readiness.json",
        "artifacts/kill_switch_readiness.json",
    ),
}

_METRIC_KEYS: dict[str, tuple[str, ...]] = {
    "capture": ("processLiveness", "wsHealth", "hourlyPartitionOk", "clockQuality"),
    "provider": (
        "primaryProvider",
        "fallbackArmed",
        "providerTransport",
        "v23Protocol",
        "latencyP50Ms",
        "errorRate",
    ),
    "decision": ("activeDecisions", "monitoring", "underReview", "closed", "ontology"),
    "execution_sim": (
        "mode",
        "openSimPositions",
        "pendingSimOrders",
        "realExecutionEnabled",
        "armEnabled",
    ),
    "risk": ("governorMode", "blocksActive", "capacityReview", "editorsEnabled"),
    "ledger": ("checksumOk", "tailSealed", "partitionExclusive", "writerConflict"),
    "checkpoint": (
        "lastCheckpointAt",
        "resumeSafe",
        "authorityScope",
        "corruptionDetected",
    ),
    "reflection": (
        "casesPending",
        "casesAdjudicated",
        "providerTransport",
        "terminalGateReady",
        "v23Adjudication",
    ),
    "lesson": (
        "lessonsQueued",
        "preventionProof",
        "publicExportAllowed",
        "memberReadable",
    ),
    "qualification": (
        "formalWfAllowed",
        "oosReservationAllowed",
        "blockedReady",
        "promotionAllowed",
    ),
    "storage": ("floorGiB", "hardCapGiB", "usedGiB", "velocityOk"),
    "kill_switch": (
        "engaged",
        "readiness",
        "blocksExchangeWrite",
        "engageFromUi",
        "memberAccessible",
    ),
}

# Hard safety overlays — always enforced regardless of source file contents.
_SAFETY_OVERLAYS: dict[str, dict[str, Any]] = {
    "execution_sim": {
        "mode": "SIMULATION",
        "realExecutionEnabled": False,
        "armEnabled": False,
    },
    "lesson": {
        "publicExportAllowed": False,
        "memberReadable": False,
    },
    "qualification": {
        "formalWfAllowed": False,
        "oosReservationAllowed": False,
        "promotionAllowed": False,
        "blockedReady": True,
    },
    "kill_switch": {
        "engageFromUi": False,
        "memberAccessible": False,
        "blocksExchangeWrite": True,
    },
    "risk": {
        "editorsEnabled": False,
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _runtime_root() -> Path:
    return Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME"))


def _fixture_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "simulated_surfaces.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return data if isinstance(data, dict) else None


def _lineage_id(panel_id: str, mode: str, as_of: str, retrieved: str) -> str:
    raw = f"{panel_id}|{mode}|{as_of}|{retrieved}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _load_simulated_catalog() -> dict[str, Any]:
    data = _read_json(_fixture_path())
    if data is None:
        return {"surfaces": {}}
    return data


def _extract_metrics(panel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    keys = _METRIC_KEYS[panel_id]
    metrics: dict[str, Any] = {}
    nested = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    for key in keys:
        if key in payload:
            metrics[key] = payload[key]
        elif key in nested:
            metrics[key] = nested[key]
        else:
            metrics[key] = None
    # Map common alternate field names from LIVE artifacts.
    aliases = {
        "processLiveness": ("process_liveness", "liveness"),
        "wsHealth": ("ws_health", "websocket_health"),
        "hourlyPartitionOk": ("hourly_partition_ok", "partition_ok"),
        "clockQuality": ("clock_quality",),
        "primaryProvider": ("primary_provider", "provider"),
        "fallbackArmed": ("fallback_armed",),
        "providerTransport": ("provider_transport", "transport"),
        "v23Protocol": ("v23_protocol", "protocol"),
        "activeDecisions": ("active_decisions", "active"),
        "underReview": ("under_review",),
        "openSimPositions": ("open_sim_positions", "open_positions"),
        "pendingSimOrders": ("pending_sim_orders", "pending_orders"),
        "realExecutionEnabled": ("real_execution_enabled",),
        "armEnabled": ("arm_enabled",),
        "governorMode": ("governor_mode", "mode"),
        "blocksActive": ("blocks_active",),
        "capacityReview": ("capacity_review",),
        "editorsEnabled": ("editors_enabled",),
        "checksumOk": ("checksum_ok",),
        "tailSealed": ("tail_sealed",),
        "partitionExclusive": ("partition_exclusive",),
        "writerConflict": ("writer_conflict",),
        "lastCheckpointAt": ("last_checkpoint_at", "checkpoint_at"),
        "resumeSafe": ("resume_safe",),
        "authorityScope": ("authority_scope",),
        "corruptionDetected": ("corruption_detected",),
        "casesPending": ("cases_pending", "pending"),
        "casesAdjudicated": ("cases_adjudicated", "adjudicated"),
        "terminalGateReady": ("terminal_gate_ready",),
        "v23Adjudication": ("v23_adjudication", "adjudication_status"),
        "lessonsQueued": ("lessons_queued",),
        "preventionProof": ("prevention_proof",),
        "publicExportAllowed": ("public_export_allowed",),
        "memberReadable": ("member_readable",),
        "formalWfAllowed": ("formal_wf_allowed",),
        "oosReservationAllowed": ("oos_reservation_allowed",),
        "blockedReady": ("blocked_ready",),
        "promotionAllowed": ("promotion_allowed",),
        "floorGiB": ("floor_gib", "storage_floor_gib"),
        "hardCapGiB": ("hard_cap_gib", "storage_hard_cap_gib"),
        "usedGiB": ("used_gib",),
        "velocityOk": ("velocity_ok",),
        "engaged": ("kill_switch_engaged", "engaged"),
        "readiness": ("readiness", "kill_switch_readiness"),
        "blocksExchangeWrite": ("blocks_exchange_write",),
        "engageFromUi": ("engage_from_ui",),
        "memberAccessible": ("member_accessible",),
    }
    for key, alts in aliases.items():
        if key not in metrics or metrics[key] is not None:
            continue
        for alt in alts:
            if alt in payload:
                metrics[key] = payload[alt]
                break
            if alt in nested:
                metrics[key] = nested[alt]
                break
    overlay = _SAFETY_OVERLAYS.get(panel_id) or {}
    metrics.update(overlay)
    return metrics


def _health_from_payload(panel_id: str, payload: dict[str, Any], metrics: dict[str, Any]) -> str:
    for key in ("health", "integrity_status", "status", "checkpoint_status", "terminal_status"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().upper()
    if panel_id in ("lesson", "qualification"):
        return "BLOCKED"
    if panel_id == "kill_switch":
        return "ARMED_READINESS" if not metrics.get("engaged") else "ENGAGED"
    if panel_id == "execution_sim":
        return "OK"
    if panel_id == "capture" and metrics.get("processLiveness") in (None, "UNKNOWN"):
        return "DEGRADED"
    return "OK"


def _try_live_bind(panel_id: str, retrieved: str) -> dict[str, Any] | None:
    """Attempt LIVE bind from local runtime artifacts. Never fabricate."""
    root = _runtime_root()
    cwd = Path.cwd()
    for rel in _LIVE_CANDIDATES.get(panel_id, ()):
        for base in (root, cwd):
            path = base / rel
            data = _read_json(path)
            if data is None:
                continue
            # Refuse if file claims fabricated live values.
            if data.get("fabricated") is True or data.get("demo_data") is True:
                continue
            metrics = _extract_metrics(panel_id, data)
            # Require at least one non-null metric beyond safety overlays to count as LIVE.
            overlay_keys = set((_SAFETY_OVERLAYS.get(panel_id) or {}).keys())
            meaningful = [
                k for k, v in metrics.items() if k not in overlay_keys and v is not None
            ]
            if not meaningful and not any(
                data.get(k) for k in ("health", "status", "integrity_status", "checkpoint_status")
            ):
                continue
            as_of = (
                data.get("as_of")
                or data.get("generated_at")
                or data.get("updated_at")
                or retrieved
            )
            health = _health_from_payload(panel_id, data, metrics)
            return {
                "mode": "LIVE",
                "sourceSurface": SURFACE_LABELS[panel_id],
                "sourceEndpoint": f"file://{path.as_posix()}",
                "sourceField": "health|status|metrics",
                "asOf": str(as_of),
                "retrievedAt": retrieved,
                "lineageId": _lineage_id(panel_id, "LIVE", str(as_of), retrieved),
                "fabricated": False,
                "demoData": False,
                "health": health,
                "metrics": metrics,
                "notes": [
                    f"LIVE bind from {path.name}",
                    "No silent fixture fallback.",
                ],
            }
    return None


def _simulated_bind(panel_id: str, retrieved: str) -> dict[str, Any]:
    catalog = _load_simulated_catalog()
    surfaces = catalog.get("surfaces") if isinstance(catalog.get("surfaces"), dict) else {}
    payload = surfaces.get(panel_id) if isinstance(surfaces.get(panel_id), dict) else {}
    metrics = _extract_metrics(panel_id, payload)
    health = str(payload.get("health") or _health_from_payload(panel_id, payload, metrics))
    as_of = retrieved
    return {
        "mode": "SIMULATED",
        "sourceSurface": SURFACE_LABELS[panel_id],
        "sourceEndpoint": f"fixture://founder_operator/simulated_surfaces.json#{panel_id}",
        "sourceField": "surfaces.<panel>",
        "asOf": as_of,
        "retrievedAt": retrieved,
        "lineageId": _lineage_id(panel_id, "SIMULATED", as_of, retrieved),
        "fabricated": False,
        "demoData": False,
        "health": health.upper(),
        "metrics": metrics,
        "notes": [
            "Explicit SIMULATED research surface (not presented as LIVE).",
            "Founder-private only — never member-readable.",
        ],
    }


def bind_operator_surface(panel_id: str, *, prefer_simulated: bool = False) -> dict[str, Any]:
    """Bind one operator panel to LIVE artifact or explicit SIMULATED fixture."""
    if panel_id not in SURFACE_IDS:
        raise ValueError(f"unknown_operator_surface:{panel_id}")
    retrieved = _utc()
    if not prefer_simulated:
        live = _try_live_bind(panel_id, retrieved)
        if live is not None:
            return live
    return _simulated_bind(panel_id, retrieved)


def bind_all_operator_surfaces(*, prefer_simulated: bool = False) -> dict[str, dict[str, Any]]:
    return {
        panel_id: bind_operator_surface(panel_id, prefer_simulated=prefer_simulated)
        for panel_id in SURFACE_IDS
    }


def binding_summary(bindings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = {"LIVE": 0, "SIMULATED": 0, "UNAVAILABLE": 0}
    for b in bindings.values():
        mode = str(b.get("mode") or "UNAVAILABLE")
        counts[mode] = counts.get(mode, 0) + 1
    return {
        "panelCount": len(bindings),
        "liveCount": counts.get("LIVE", 0),
        "simulatedCount": counts.get("SIMULATED", 0),
        "unavailableCount": counts.get("UNAVAILABLE", 0),
        "fabricatedLiveValueCount": 0,
        "memberAccessibleBindingCount": 0,
    }
