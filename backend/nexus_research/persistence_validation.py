"""Phase 6.1 — Persistence validation dataset + probes (research-only).

Creates a tagged PERSISTENCE_VALIDATION pack for controlled restart proof.
Never uses private API / real orders. Never counts toward natural Paper PnL.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

VALIDATION_LABEL = "PERSISTENCE_VALIDATION"
CONTRACT = "NEXUS_PHASE61_PERSISTENCE_VALIDATION_V1"


def _ts() -> int:
    return int(time.time() * 1000)


def _redact_path(path: str | None) -> str | None:
    if not path:
        return None
    # Keep only /data/... shape; strip host-specific prefixes.
    p = path.replace("\\", "/")
    idx = p.find("/data/")
    if idx >= 0:
        return p[idx:]
    if p.endswith("nexus_research.db"):
        return "/data/nexus-research/nexus_research.db"
    return "/data/nexus-research/<redacted>"


def create_persistence_probe(*, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create and persist a PersistenceProbe record."""
    from backend.nexus_research.boot_identity import get_boot_identity
    from backend.nexus_research.storage import get_research_store

    boot = get_boot_identity()
    store = get_research_store()
    probe_id = str(uuid.uuid4())
    created_at = _ts()
    body = {
        "nonce": str(uuid.uuid4()),
        "createdAt": created_at,
        "note": "phase61_restart_proof",
        **(payload or {}),
    }
    payload_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    probe = {
        "probeId": probe_id,
        "probe_id": probe_id,
        "createdAt": created_at,
        "createdBootId": boot.get("bootId"),
        "created_boot_id": boot.get("bootId"),
        "createdDeploymentIdPresent": bool(boot.get("deploymentIdPresent")),
        "databaseSchemaVersion": store.schema_version,
        "storageMode": store.backend_type,
        "payloadHash": payload_hash,
        "payload_hash": payload_hash,
        "payload": body,
        "validationLabel": VALIDATION_LABEL,
        "validation_label": VALIDATION_LABEL,
        "validationType": VALIDATION_LABEL,
        "researchOnly": True,
        "idempotencyKey": f"probe:{probe_id}",
    }
    store.append("persistence_probes", probe)
    store.persist_validation_marker(
        marker_id=f"probe-marker:{probe_id}",
        tag=VALIDATION_LABEL,
        payload={"probeId": probe_id, "payloadHash": payload_hash},
    )
    # Also write a file-level probe under volume_probe/ when possible.
    try:
        from backend.nexus_research.boot_identity import research_data_dir

        root = research_data_dir()
        if root is not None:
            probe_dir = root / "volume_probe"
            probe_dir.mkdir(parents=True, exist_ok=True)
            (probe_dir / f"{probe_id}.json").write_text(
                json.dumps(probe, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[persistence_validation] file probe write failed: %s", exc)
    return probe


def run_persistence_validation_pack() -> dict[str, Any]:
    """Build full PERSISTENCE_VALIDATION dataset using live public candidate if available."""
    from backend.nexus_research.boot_identity import get_boot_identity
    from backend.nexus_research.roles import DecisionOrchestrator
    from backend.nexus_research.ai_review_cycle import get_ai_review_scheduler
    from backend.nexus_research.patch_governance import get_patch_governance
    from backend.nexus_research.sim_ledger import get_sim_ledger
    from backend.nexus_research.storage import get_research_store
    from backend.nexus_research.domain_events import publish_event

    boot = get_boot_identity()
    store = get_research_store()
    correlation_id = str(uuid.uuid4())
    pack_id = str(uuid.uuid4())

    # Real public candidate snapshot (best-effort).
    candidate: dict[str, Any] = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "stage": "WATCHING",
        "score": 1.0,
        "opportunityScore": 1.0,
        "confirmationScore": 1.0,
        "riskScore": 10.0,
        "collecting": False,
        "validationType": VALIDATION_LABEL,
        "researchOnly": True,
    }
    try:
        from backend.market.scanner.scanner_service import get_market_scanner

        snap = get_market_scanner().candidates(side="LONG", limit=5)
        items = snap.get("candidates") or []
        if items:
            live = dict(items[0])
            live["validationType"] = VALIDATION_LABEL
            live["researchOnly"] = True
            candidate = live
    except Exception as exc:  # noqa: BLE001
        logger.warning("[persistence_validation] live candidate unavailable: %s", exc)

    symbol = str(candidate.get("symbol") or "BTCUSDT")
    side = str(candidate.get("side") or "LONG")
    case_id = str(uuid.uuid4())

    case = {
        "caseId": case_id,
        "case_id": case_id,
        "symbol": symbol,
        "direction": side,
        "side": side,
        "trigger": "MANUAL_RESEARCH",
        "status": "COMPLETED",
        "validationType": VALIDATION_LABEL,
        "validationLabel": VALIDATION_LABEL,
        "correlationId": correlation_id,
        "researchOnly": True,
        "createdAt": _ts(),
        "updatedAt": _ts(),
        "candidateSnapshot": candidate,
        "idempotencyKey": f"pval-case:{pack_id}",
    }
    store.append("review_cases", case)

    decision = DecisionOrchestrator().run(
        case_id,
        candidate,
        {
            "activeCases": 0,
            "triggerType": "PERSISTENCE_VALIDATION",
            "validationType": VALIDATION_LABEL,
            "correlationId": correlation_id,
        },
    )
    decision_id = str(uuid.uuid4())
    decision_row = {
        **decision,
        "decisionId": decision_id,
        "decision_id": decision_id,
        "decision_type": decision.get("decisionStatus"),
        "validationType": VALIDATION_LABEL,
        "validationLabel": VALIDATION_LABEL,
        "correlationId": correlation_id,
        "idempotencyKey": f"pval-decision:{pack_id}",
        "excludeFromNaturalPaperPnl": True,
    }
    store.append("research_decisions", decision_row)

    assessments = decision.get("assessments") or []
    assessment_ids: list[str] = []
    for a in assessments:
        aid = str(uuid.uuid4())
        assessment_ids.append(aid)
        row = {
            **a,
            "assessmentId": aid,
            "assessment_id": aid,
            "caseId": case_id,
            "case_id": case_id,
            "validationType": VALIDATION_LABEL,
            "validationLabel": VALIDATION_LABEL,
            "correlationId": correlation_id,
            "idempotencyKey": f"pval-assess:{pack_id}:{a.get('role')}",
        }
        store.append("role_assessments", row)

    session_id = get_ai_review_scheduler().trigger_manual()
    # Tag the session as persistence validation (best-effort update via append note).
    store.append(
        "review_sessions",
        {
            "sessionId": session_id,
            "session_id": session_id,
            "status": "COMPLETED",
            "slotKey": f"PERSISTENCE_VALIDATION_{pack_id}",
            "validationType": VALIDATION_LABEL,
            "validationLabel": VALIDATION_LABEL,
            "correlationId": correlation_id,
            "excludeFromNaturalScheduledReview": True,
            "idempotencyKey": f"pval-session:{pack_id}",
            "createdAt": _ts(),
        },
    )

    # Zero-notional ledger checkpoint (no market exposure).
    ledger = get_sim_ledger()
    before = ledger.snapshot() if hasattr(ledger, "snapshot") else {}
    checkpoint_id = str(uuid.uuid4())
    ledger_checkpoint = {
        "entryId": checkpoint_id,
        "entry_id": checkpoint_id,
        "entry_type": "PERSISTENCE_CHECKPOINT",
        "validationType": VALIDATION_LABEL,
        "validationLabel": VALIDATION_LABEL,
        "correlationId": correlation_id,
        "simulatedCash": float(before.get("cashBalance") or 0.0),
        "reservedMargin": float(before.get("marginUsed") or 0.0),
        "openPositionCount": 0,
        "eventCount": int(before.get("totalEvents") or before.get("eventLogSize") or 0),
        "zeroNotional": True,
        "excludeFromNaturalPaperPnl": True,
        "idempotencyKey": f"pval-ledger:{pack_id}",
        "createdAt": _ts(),
    }
    store.append("sim_ledger", ledger_checkpoint)

    # Reflection + patch NEEDS_DATA (no production apply).
    reflection_id = str(uuid.uuid4())
    reflection = {
        "reflectionId": reflection_id,
        "reflection_id": reflection_id,
        "session_id": session_id,
        "caseId": case_id,
        "summary": "PERSISTENCE_VALIDATION reflection — restart recovery probe only",
        "validationType": VALIDATION_LABEL,
        "validationLabel": VALIDATION_LABEL,
        "correlationId": correlation_id,
        "excludeFromNaturalPaperPnl": True,
        "autoApplyProduction": False,
        "idempotencyKey": f"pval-reflection:{pack_id}",
        "createdAt": _ts(),
    }
    store.append("reflections", reflection)

    proposal_id = str(uuid.uuid4())
    patch = {
        "proposalId": proposal_id,
        "proposal_id": proposal_id,
        "status": "NEEDS_DATA",
        "problemStatement": "Persistence validation only — insufficient natural sample",
        "sampleSize": 0,
        "validationType": VALIDATION_LABEL,
        "validationLabel": VALIDATION_LABEL,
        "correlationId": correlation_id,
        "autoApplyProduction": False,
        "excludeFromNaturalPaperPnl": True,
        "idempotencyKey": f"pval-patch:{pack_id}",
        "createdAt": _ts(),
    }
    store.append("patch_proposals", patch)
    try:
        get_patch_governance()  # ensure module importable; do not auto-approve
    except Exception:  # noqa: BLE001
        pass

    probe = create_persistence_probe(
        payload={
            "packId": pack_id,
            "correlationId": correlation_id,
            "caseId": case_id,
            "decisionId": decision_id,
            "sessionId": session_id,
            "reflectionId": reflection_id,
            "proposalId": proposal_id,
            "ledgerCheckpointId": checkpoint_id,
        }
    )

    # WAL checkpoint after writes.
    wal = store.wal_checkpoint()

    try:
        publish_event(
            "PERSISTENCE_VALIDATION_PACK_CREATED",
            {
                "packId": pack_id,
                "probeId": probe["probeId"],
                "validationLabel": VALIDATION_LABEL,
                "researchOnly": True,
            },
            idempotency_key=f"pval-pack:{pack_id}",
        )
    except Exception:  # noqa: BLE001
        pass

    snap = build_pre_restart_snapshot(
        pack_id=pack_id,
        probe=probe,
        case_id=case_id,
        assessment_ids=assessment_ids,
        decision_id=decision_id,
        session_id=session_id,
        ledger_checkpoint_id=checkpoint_id,
        reflection_id=reflection_id,
        proposal_id=proposal_id,
        correlation_id=correlation_id,
        wal=wal,
    )
    store.append(
        "persistence_validation_markers",
        {
            "marker_id": f"pre-restart-snapshot:{pack_id}",
            "markerId": f"pre-restart-snapshot:{pack_id}",
            "tag": VALIDATION_LABEL,
            "payload": snap,
            "idempotencyKey": f"pval-snapshot:{pack_id}",
        },
    )
    return snap


def build_pre_restart_snapshot(**kwargs: Any) -> dict[str, Any]:
    from backend.nexus_research.boot_identity import get_boot_identity, research_data_dir
    from backend.nexus_research.storage import get_research_store
    from backend.nexus_research.runtime_supervisor import get_supervisor
    from backend.nexus_research.sim_ledger import get_sim_ledger

    boot = get_boot_identity()
    store = get_research_store()
    supervisor = get_supervisor().status()
    ledger = get_sim_ledger()
    ledger_status = ledger.snapshot() if hasattr(ledger, "snapshot") else {}
    ledger_events = []
    try:
        ledger_events = ledger.recent_events(limit=500)
    except Exception:  # noqa: BLE001
        ledger_events = []

    # Stable hash over event ids / amounts.
    hash_src = json.dumps(
        [
            {
                "id": e.get("eventId") or e.get("entryId") or e.get("id"),
                "type": e.get("eventType") or e.get("type") or e.get("entry_type"),
                "cashAfter": e.get("cashAfter"),
            }
            for e in ledger_events
        ],
        sort_keys=True,
        default=str,
    )
    ledger_hash = hashlib.sha256(hash_src.encode("utf-8")).hexdigest()

    scanner_owner_count = 1
    try:
        from backend.market.scanner.scanner_service import get_market_scanner

        st = get_market_scanner().status()
        scanner_owner_count = 1 if st.get("ok") is not False else 0
    except Exception:  # noqa: BLE001
        scanner_owner_count = 0

    root = research_data_dir()
    probe = kwargs.get("probe") or {}

    event_count = 0
    dead_letter_count = 0
    last_event_id = None
    try:
        event_count = store.count("domain_events")
        dead_letter_count = store.count("dead_letters")
        events = store.query("domain_events", limit=1)
        if events:
            last_event_id = events[-1].get("eventId") or events[-1].get("event_id")
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "researchOnly": True,
        "privateApi": False,
        "validationType": VALIDATION_LABEL,
        "contract": CONTRACT,
        "packId": kwargs.get("pack_id"),
        "correlationId": kwargs.get("correlation_id"),
        "boot_id": boot.get("bootId"),
        "bootId": boot.get("bootId"),
        "startedAt": boot.get("startedAt"),
        "runtime_owner_count": 1 if supervisor.get("supervisorRunning") else 0,
        "scheduler_owner_count": 1 if "ai_review_cycle_6h" in (supervisor.get("jobs") or {}) else 0,
        "scanner_owner_count": scanner_owner_count,
        "supervisorRunning": bool(supervisor.get("supervisorRunning")),
        "jobCount": supervisor.get("jobCount"),
        "storage_mode": store.backend_type,
        "storageMode": store.backend_type,
        "durable_claim": False,
        "durableClaim": False,
        "production_persistence_available": False,
        "researchDatabasePathRedacted": _redact_path(store.db_path),
        "researchDataDirRedacted": "/data/nexus-research" if root else None,
        "schemaVersion": store.schema_version,
        "sqliteRuntimeProfile": store.sqlite_runtime_profile(),
        "probe_id": probe.get("probeId"),
        "probeId": probe.get("probeId"),
        "probe_hash": probe.get("payloadHash"),
        "probeCreatedBootId": probe.get("createdBootId"),
        "review_case_id": kwargs.get("case_id"),
        "role_assessment_count": len(kwargs.get("assessment_ids") or []),
        "role_assessment_ids": kwargs.get("assessment_ids") or [],
        "research_decision_id": kwargs.get("decision_id"),
        "review_session_id": kwargs.get("session_id"),
        "ledger_checkpoint_id": kwargs.get("ledger_checkpoint_id"),
        "reflection_id": kwargs.get("reflection_id"),
        "patch_proposal_id": kwargs.get("proposal_id"),
        "ledger_event_count": int(
            ledger_status.get("totalEvents")
            or ledger_status.get("eventLogSize")
            or len(ledger_events)
        ),
        "ledger_hash": ledger_hash,
        "simulated_cash": float(ledger_status.get("cashBalance") or 0.0),
        "reserved_margin": float(ledger_status.get("marginUsed") or 0.0),
        "open_position_count": 0,
        "event_count": event_count,
        "dead_letter_count": dead_letter_count,
        "last_event_id": last_event_id,
        "wal": kwargs.get("wal") or {},
        "paperModeEnabled": False,
        "readyForControlledRestart": True,
        "generatedAt": _ts(),
    }


def list_probes(limit: int = 20) -> list[dict[str, Any]]:
    from backend.nexus_research.storage import get_research_store

    rows = get_research_store().query("persistence_probes", limit=limit)
    # newest first
    rows = list(reversed(rows))
    return rows
