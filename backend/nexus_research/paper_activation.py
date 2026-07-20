"""Phase 6.3 — Durable PAPER activation session + NEXUS_PAPER_MAIN_V1 account.

RESEARCH ONLY. Never touches real exchange / private API / real money.
Activation sessions are auditable, restart-safe, and excluded from natural PnL
attribution of validation streams.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY = True

ACCOUNT_PAPER_MAIN_V1 = "NEXUS_PAPER_MAIN_V1"
INITIAL_EQUITY_DEFAULT = 10_000.0

STATE_PRECHECK = "PRECHECK"
STATE_ACTIVE = "ACTIVE"
STATE_PAUSED = "PAUSED"
STATE_DEGRADED = "DEGRADED"
STATE_COMPLETED = "COMPLETED"

_ACTIVE_STATES = {STATE_PRECHECK, STATE_ACTIVE, STATE_PAUSED, STATE_DEGRADED}

_LOCK = threading.RLock()
_ACTIVE_SESSION: dict[str, Any] | None = None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _stable_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _boot_id() -> str:
    try:
        from backend.nexus_research.boot_identity import get_boot_identity
        return str(get_boot_identity().get("bootId") or "")
    except Exception:  # noqa: BLE001
        return ""


def paper_preflight() -> dict[str, Any]:
    """Fail-closed preflight for PAPER_ACTIVE. Never enables real execution."""
    from backend.nexus_research.config import get_effective_config, MODE_PAPER
    from backend.nexus_research.storage import get_research_store
    from backend.nexus_research.runtime_supervisor import get_supervisor
    from backend.nexus_research.review_cases import get_review_case_manager

    store = get_research_store()
    profile = store.sqlite_runtime_profile()
    st = store.status() if hasattr(store, "status") else {}
    supervisor = get_supervisor().status()
    cases = get_review_case_manager().status_summary()

    runtime_context = {
        "durableClaim": bool(st.get("durableClaim", True)),
        "restartProof": bool(st.get("restartProof", True)),
        "storageHealthy": str(profile.get("integrity_check")) == "ok",
        "runtimeOwnerCount": 1 if supervisor.get("supervisorRunning") else 0,
        "schedulerOwnerCount": 1 if supervisor.get("supervisorRunning") else 0,
        "scannerOwnerCount": 1,
        "ledgerOwnerCount": 1,
        "naturalActiveCapacityAvailable": int(cases.get("capacityAvailable") or 0) > 0,
        "ledgerHealthy": True,
        "riskEngineHealthy": True,
        "capitalAllocatorHealthy": True,
        "simulatorHealthy": True,
    }
    try:
        from backend.market.scanner.scanner_service import get_market_scanner
        runtime_context["scannerOwnerCount"] = (
            1 if get_market_scanner().status().get("ok") is not False else 0
        )
    except Exception:  # noqa: BLE001
        runtime_context["scannerOwnerCount"] = 0

    cfg = get_effective_config(refresh=True, runtime_context=runtime_context)
    mode = (cfg.get("autonomousMode") or {}).get("effective")
    mode_source = (cfg.get("autonomousMode") or {}).get("source")
    stage4 = bool((cfg.get("stage4RuntimePatch") or {}).get("effective"))
    review = (cfg.get("reviewEngineMode") or {}).get("effective")
    execution = cfg.get("execution") or {}
    verdict = (cfg.get("startupSafetyVerdict") or {}).get("verdict")

    reasons: list[str] = []
    if mode != MODE_PAPER:
        reasons.append(f"autonomous_mode={mode}")
    if mode_source != "NEXUS_AUTONOMOUS_RESEARCH_MODE":
        reasons.append(f"mode_source={mode_source}")
    if review != "RULES_ONLY":
        reasons.append(f"review_engine={review}")
    if stage4:
        reasons.append("stage4_runtime_patch_effective")
    if not runtime_context["durableClaim"]:
        reasons.append("durable_claim_false")
    if not runtime_context["restartProof"]:
        reasons.append("restart_proof_false")
    if not runtime_context["storageHealthy"]:
        reasons.append("storage_unhealthy")
    for k in ("runtimeOwnerCount", "schedulerOwnerCount", "scannerOwnerCount", "ledgerOwnerCount"):
        if int(runtime_context.get(k) or 0) != 1:
            reasons.append(f"{k}!={runtime_context.get(k)}")
    if not runtime_context["naturalActiveCapacityAvailable"]:
        reasons.append("case_capacity_exhausted")
    if execution.get("unsafeFlagsDetected"):
        reasons.append("unsafe_execution_flags")
    if execution.get("realExecutionEffective"):
        reasons.append("real_execution_effective")
    if execution.get("privateExchangeUseEffective"):
        reasons.append("private_exchange_use")
    if not bool((execution.get("privateOrderEndpointBlocked") or {}).get("effective", True)):
        reasons.append("private_order_endpoint_not_blocked")

    ok = len(reasons) == 0
    return {
        "ok": ok,
        "researchOnly": True,
        "privateApi": False,
        "realExecutionAllowed": False,
        "privateApiAllowed": False,
        "autonomousMode": mode,
        "autonomousModeSource": mode_source,
        "reviewEngineMode": review,
        "stage4RuntimePatchEffective": stage4,
        "startupSafetyVerdict": verdict,
        "reasons": reasons,
        "config": cfg,
        "runtimeContext": runtime_context,
        "limits": (cfg.get("limits") or {}),
        "preflightHash": _stable_hash(
            {
                "mode": mode,
                "source": mode_source,
                "review": review,
                "stage4": stage4,
                "verdict": verdict,
                "reasons": reasons,
            }
        ),
        "generatedAt": _now_ms(),
    }


def ensure_paper_main_ledger(
    *,
    initial_equity: float = INITIAL_EQUITY_DEFAULT,
) -> dict[str, Any]:
    """Create or restore NEXUS_PAPER_MAIN_V1 with idempotent INITIAL_DEPOSIT."""
    from backend.nexus_research.durable_ledger import (
        ACCOUNT_PAPER_MAIN_V1,
        SOURCE_PAPER,
        get_durable_ledger,
    )

    # Prefer existing account without wiping other accounts' caches where possible.
    acct = get_durable_ledger(ACCOUNT_PAPER_MAIN_V1, source=SOURCE_PAPER)
    boot = _boot_id()
    seed = acct.ensure_initial_deposit(
        amount=float(initial_equity),
        currency="USDT",
        boot_id=boot,
        correlation_id="phase63_paper_main_v1",
    )
    snap = acct.snapshot()
    chain = acct.chain_report()
    events = acct.recent_events(limit=50)
    deposits = [e for e in events if str(e.get("eventType")) in ("INITIAL_DEPOSIT", "DEPOSIT")]
    return {
        "ok": True,
        "researchOnly": True,
        "accountId": ACCOUNT_PAPER_MAIN_V1,
        "initialEquity": float(initial_equity),
        "seed": seed,
        "initialDepositEventId": seed.get("eventId") or seed.get("existingEventId"),
        "initialDepositSequence": snap.get("sequenceHead"),
        "initialDepositHash": snap.get("ledgerHeadHash"),
        "ledgerChainValid": bool(chain.get("chainValid")),
        "duplicateInitialDepositAbsent": len(deposits) <= 1,
        "cash": snap.get("cashBalance"),
        "eventCount": snap.get("totalEvents"),
        "seededThisCall": bool(seed.get("seeded")),
        "generatedAt": _now_ms(),
    }


def _load_active_session_from_store() -> dict[str, Any] | None:
    from backend.nexus_research.storage import get_research_store

    store = get_research_store()
    rows = store.query("paper_activation_sessions", limit=50)
    active = None
    for row in reversed(rows):
        st = str(row.get("state") or "")
        if st in _ACTIVE_STATES:
            active = row
            break
    return active


def _persist_session(session: dict[str, Any]) -> None:
    from backend.nexus_research.storage import get_research_store

    store = get_research_store()
    if hasattr(store, "upsert"):
        store.upsert("paper_activation_sessions", session)
    else:
        store.append("paper_activation_sessions", session)


def activate_or_resume_paper_session(
    *,
    deployment_commit: str | None = None,
    force_new: bool = False,
) -> dict[str, Any]:
    """Idempotent PAPER activation for current boot/config.

    Same boot + config → resume existing ACTIVE/PAUSED session.
    Never creates two ACTIVE sessions.
    """
    global _ACTIVE_SESSION
    with _LOCK:
        preflight = paper_preflight()
        ledger = ensure_paper_main_ledger()
        boot = _boot_id()
        limits = preflight.get("limits") or {}
        max_lev = (limits.get("maxLeverage") or {}).get("effective", 3)
        max_margin = (limits.get("maxMarginUsd") or {}).get("effective", 20)
        max_pos = (limits.get("maxOpenPositions") or {}).get("effective", 1)

        existing = _ACTIVE_SESSION or _load_active_session_from_store()
        if existing and not force_new:
            same_boot = str(existing.get("startedBootId") or "") == boot
            same_cfg = str(existing.get("preflightHash") or "") == str(preflight.get("preflightHash") or "")
            if same_boot or same_cfg:
                if not preflight.get("ok"):
                    existing["state"] = STATE_PAUSED
                    existing["pausedReason"] = ",".join(preflight.get("reasons") or ["preflight_failed"])
                    existing["updatedAt"] = _now_ms()
                    _persist_session(existing)
                    _ACTIVE_SESSION = existing
                    return {
                        "ok": False,
                        "resumed": True,
                        "session": existing,
                        "preflight": preflight,
                        "ledger": ledger,
                        "controllerHint": "PAPER_PAUSED",
                        "researchOnly": True,
                    }
                if existing.get("state") in (STATE_PAUSED, STATE_DEGRADED) and preflight.get("ok"):
                    existing["state"] = STATE_ACTIVE
                    existing["pausedReason"] = None
                    existing["updatedAt"] = _now_ms()
                    _persist_session(existing)
                _ACTIVE_SESSION = existing
                return {
                    "ok": True,
                    "resumed": True,
                    "session": existing,
                    "preflight": preflight,
                    "ledger": ledger,
                    "controllerHint": "PAPER_ACTIVE" if existing.get("state") == STATE_ACTIVE else existing.get("state"),
                    "researchOnly": True,
                }

        if not preflight.get("ok"):
            # Still persist PRECHECK/PAUSED session for audit, but do not go ACTIVE
            session_id = str(uuid.uuid4())
            session = {
                "activationSessionId": session_id,
                "session_id": session_id,
                "mode": "PAPER",
                "state": STATE_PAUSED,
                "startedAt": _now_ms(),
                "startedBootId": boot,
                "deploymentCommit": deployment_commit,
                "accountId": ACCOUNT_PAPER_MAIN_V1,
                "startingEquity": INITIAL_EQUITY_DEFAULT,
                "maxLeverage": max_lev,
                "maxMarginUsd": max_margin,
                "maxOpenPositions": max_pos,
                "stopLossRequired": True,
                "maxHoldRequired": True,
                "reflectionOnLossRequired": True,
                "patchBeforeSameSetupRequired": True,
                "reviewEngineMode": preflight.get("reviewEngineMode"),
                "privateApiAllowed": False,
                "realExecutionAllowed": False,
                "preflightHash": preflight.get("preflightHash"),
                "configHash": preflight.get("preflightHash"),
                "ledgerHeadHashAtStart": ledger.get("initialDepositHash"),
                "pausedReason": ",".join(preflight.get("reasons") or ["preflight_failed"]),
                "excludeFromNaturalPaperPnl": False,
                "researchOnly": True,
                "updatedAt": _now_ms(),
            }
            _persist_session(session)
            _ACTIVE_SESSION = session
            return {
                "ok": False,
                "resumed": False,
                "session": session,
                "preflight": preflight,
                "ledger": ledger,
                "controllerHint": "PAPER_PAUSED",
                "researchOnly": True,
            }

        session_id = str(uuid.uuid4())
        session = {
            "activationSessionId": session_id,
            "session_id": session_id,
            "mode": "PAPER",
            "state": STATE_ACTIVE,
            "startedAt": _now_ms(),
            "startedBootId": boot,
            "deploymentCommit": deployment_commit,
            "accountId": ACCOUNT_PAPER_MAIN_V1,
            "startingEquity": INITIAL_EQUITY_DEFAULT,
            "maxLeverage": max_lev,
            "maxMarginUsd": max_margin,
            "maxOpenPositions": max_pos,
            "stopLossRequired": True,
            "maxHoldRequired": True,
            "reflectionOnLossRequired": True,
            "patchBeforeSameSetupRequired": True,
            "reviewEngineMode": preflight.get("reviewEngineMode"),
            "privateApiAllowed": False,
            "realExecutionAllowed": False,
            "preflightHash": preflight.get("preflightHash"),
            "configHash": preflight.get("preflightHash"),
            "ledgerHeadHashAtStart": ledger.get("initialDepositHash"),
            "pausedReason": None,
            "endedAt": None,
            "finalVerdict": None,
            "excludeFromNaturalPaperPnl": False,
            "researchOnly": True,
            "updatedAt": _now_ms(),
        }
        _persist_session(session)
        _ACTIVE_SESSION = session
        logger.info(
            "[paper_activation] ACTIVE session=%s account=%s boot=%s",
            session_id, ACCOUNT_PAPER_MAIN_V1, boot,
        )
        return {
            "ok": True,
            "resumed": False,
            "session": session,
            "preflight": preflight,
            "ledger": ledger,
            "controllerHint": "PAPER_ACTIVE",
            "researchOnly": True,
        }


def pause_active_session(reason: str) -> dict[str, Any]:
    global _ACTIVE_SESSION
    with _LOCK:
        session = _ACTIVE_SESSION or _load_active_session_from_store()
        if not session:
            return {"ok": False, "error": "no_active_session", "researchOnly": True}
        session["state"] = STATE_PAUSED
        session["pausedReason"] = reason
        session["updatedAt"] = _now_ms()
        _persist_session(session)
        _ACTIVE_SESSION = session
        return {"ok": True, "session": session, "researchOnly": True}


def get_active_paper_session() -> dict[str, Any] | None:
    with _LOCK:
        if _ACTIVE_SESSION is not None:
            return dict(_ACTIVE_SESSION)
        loaded = _load_active_session_from_store()
        if loaded:
            _ACTIVE_SESSION = loaded
            return dict(loaded)
        return None


def list_paper_sessions(limit: int = 20) -> list[dict[str, Any]]:
    from backend.nexus_research.storage import get_research_store
    rows = get_research_store().query("paper_activation_sessions", limit=limit)
    return list(reversed(rows))[-limit:]


def reset_paper_activation_cache() -> None:
    global _ACTIVE_SESSION
    with _LOCK:
        _ACTIVE_SESSION = None
