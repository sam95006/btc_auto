"""NEXUS Phase 6.5 — Natural PAPER decision funnel observability.

Aggregates scanner → candidate → case → roles → decision → risk → allocation →
order → fill → position → exit without lowering any production gates.
"""
from __future__ import annotations

import time
from collections import Counter
from typing import Any, Optional

# Standard block reason taxonomy (Phase 6.5 Gate B)
BLOCK_REASONS = frozenset({
    "DATA_STALE",
    "DATA_INCOMPLETE",
    "FEATURE_QUALITY_LOW",
    "CANDIDATE_SCORE_LOW",
    "NO_CLEAR_DIRECTION",
    "ROLE_DISAGREEMENT",
    "RISK_CRITIC_REJECT",
    "VOLATILITY_TOO_HIGH",
    "SPREAD_TOO_WIDE",
    "DEPTH_TOO_LOW",
    "FUNDING_TOO_EXTREME",
    "OI_CONFLICT",
    "LIQUIDATION_RISK",
    "STOP_DISTANCE_INVALID",
    "RISK_REWARD_TOO_LOW",
    "POSITION_CAPACITY_FULL",
    "MARGIN_LIMIT",
    "LEVERAGE_LIMIT",
    "DUPLICATE_SETUP",
    "COOLDOWN",
    "PATCH_REQUIRED",
    "REGIME_UNSUPPORTED",
    "NO_ENTRY_TRIGGER",
    "OTHER",
})


def classify_block_reason(raw: str | None) -> str:
    """Map free-text guard/decision detail to standard taxonomy."""
    if not raw:
        return "OTHER"
    u = raw.upper()
    mapping = [
        ("DATA_STALE", ("STALE", "DATA STALE")),
        ("DATA_INCOMPLETE", ("INCOMPLETE", "MISSING DATA", "INSUFFICIENT_HISTORY")),
        ("FEATURE_QUALITY_LOW", ("FEATURE", "QUALITY")),
        ("CANDIDATE_SCORE_LOW", ("SCORE", "BELOW MIN")),
        ("NO_CLEAR_DIRECTION", ("WATCH_ONLY", "NO CLEAR", "NEUTRAL")),
        ("ROLE_DISAGREEMENT", ("DISAGREE", "UNFAVORABLE", "WEAK")),
        ("RISK_CRITIC_REJECT", ("RISK BLOCKED", "RISK_CRITIC", "BLOCKED")),
        ("VOLATILITY_TOO_HIGH", ("VOLATILITY", "ATR")),
        ("SPREAD_TOO_WIDE", ("SPREAD")),
        ("DEPTH_TOO_LOW", ("DEPTH", "LIQUIDITY")),
        ("FUNDING_TOO_EXTREME", ("FUNDING")),
        ("OI_CONFLICT", ("OI ", "OPEN INTEREST")),
        ("LIQUIDATION_RISK", ("LIQUIDATION",)),
        ("STOP_DISTANCE_INVALID", ("STOP",)),
        ("RISK_REWARD_TOO_LOW", ("R:R", "RISK REWARD")),
        ("POSITION_CAPACITY_FULL", ("CAPACITY", "MAX OPEN", "DUPLICATE")),
        ("MARGIN_LIMIT", ("MARGIN",)),
        ("LEVERAGE_LIMIT", ("LEVERAGE",)),
        ("DUPLICATE_SETUP", ("DUPLICATE",)),
        ("COOLDOWN", ("COOLDOWN",)),
        ("PATCH_REQUIRED", ("PATCH",)),
        ("REGIME_UNSUPPORTED", ("REGIME",)),
        ("NO_ENTRY_TRIGGER", ("NO ENTRY", "TRIGGER")),
    ]
    for code, needles in mapping:
        if any(n in u for n in needles):
            return code
    return "OTHER"


def _decision_status(d: dict[str, Any]) -> str:
    return str(d.get("decisionStatus") or d.get("status") or "UNKNOWN")


def _processed_ids(store) -> set[str]:
    ids: set[str] = set()
    try:
        for row in store.query("paper_processed_decisions", limit=500):
            did = row.get("decisionId") or row.get("decision_id")
            if did:
                ids.add(str(did))
    except Exception:  # noqa: BLE001
        pass
    return ids


def build_decision_funnel(*, window_hours: float = 24.0) -> dict[str, Any]:
    """Build aggregate funnel snapshot for natural PAPER pipeline."""
    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - int(window_hours * 3600 * 1000)
    block_counts: Counter[str] = Counter()
    symbol_blocks: Counter[str] = Counter()
    stage_pending: dict[str, int] = {}

    candidate_count = 0
    eligible_count = 0
    case_count = 0
    role_complete_count = 0
    decision_count = 0
    risk_pass_count = 0
    risk_block_count = 0
    allocation_pass_count = 0
    entry_eligible_count = 0
    order_count = 0
    fill_count = 0
    position_count = 0
    exit_count = 0

    data_freshness = "UNKNOWN"
    scanner_transport = None

    try:
        from backend.market.scanner.scanner_service import get_market_scanner

        scanner = get_market_scanner()
        st = scanner.status()
        data_freshness = str(st.get("freshness") or "UNKNOWN")
        scanner_transport = st.get("transport")
        cands = scanner.candidates(limit=200)
        candidate_count = len(cands)
        eligible_count = sum(
            1 for c in cands
            if float(c.get("score") or 0) >= float(st.get("minCandidateScore") or 0)
        )
    except Exception:  # noqa: BLE001
        pass

    store = None
    try:
        from backend.nexus_research.storage import get_research_store

        store = get_research_store()
    except Exception:  # noqa: BLE001
        store = None

    processed = _processed_ids(store) if store else set()

    if store:
        try:
            from backend.nexus_research.review_cases import get_review_case_manager

            cs = get_review_case_manager().status_summary()
            case_count = int(cs.get("active") or 0) + int(cs.get("byStatus", {}).get("COMPLETED", 0) or 0)
            role_complete_count = int(cs.get("byStatus", {}).get("READY", 0) or 0)
        except Exception:  # noqa: BLE001
            pass

        decisions = store.query("research_decisions", limit=300)
        recent = [
            d for d in decisions
            if int(d.get("producedAt") or d.get("createdAtMs") or 0) >= cutoff_ms
            or not d.get("producedAt")
        ]
        decision_count = len(recent)
        for d in recent:
            status = _decision_status(d)
            sym = str(d.get("symbol") or "?")
            if status == "READY_FOR_SIMULATION":
                risk_pass_count += 1
                entry_eligible_count += 1
            elif status == "RISK_BLOCKED":
                risk_block_count += 1
                reason = classify_block_reason(d.get("summary"))
                block_counts[reason] += 1
                symbol_blocks[sym] += 1
            elif status in ("WATCH_ONLY", "REJECTED"):
                reason = classify_block_reason(d.get("summary") or status)
                block_counts[reason] += 1
                symbol_blocks[sym] += 1

        ready_unprocessed = [
            d for d in recent
            if _decision_status(d) == "READY_FOR_SIMULATION"
            and str(d.get("decisionId") or "") not in processed
        ]
        stage_pending["decision_ready_unprocessed"] = len(ready_unprocessed)

        for row in store.query("paper_processed_decisions", limit=300):
            if int(row.get("processedAtMs") or 0) < cutoff_ms:
                continue
            outcome = str(row.get("outcome") or "")
            detail = str(row.get("detail") or "")
            if outcome == "GUARD_BLOCKED":
                reason = classify_block_reason(detail)
                block_counts[reason] += 1
            elif outcome == "SIM_SUBMITTED":
                order_count += 1
                allocation_pass_count += 1

        try:
            from backend.nexus_research.paper_controller import get_paper_controller

            pc = get_paper_controller().status()
            order_count = max(order_count, int(pc.get("totalOrdersSubmitted") or 0))
            exit_count = int(pc.get("totalExits") or 0)
        except Exception:  # noqa: BLE001
            pass

        try:
            from backend.nexus_research.paper_activation import ACCOUNT_PAPER_MAIN_V1
            from backend.nexus_research.simulator import get_simulator

            sim = get_simulator()
            position_count = len(sim.list_open_positions())
            fill_count = len(store.query("sim_attempts", limit=200))
        except Exception:  # noqa: BLE001
            pass

    top_blocked_symbols = [
        {"symbol": s, "count": c}
        for s, c in symbol_blocks.most_common(10)
    ]
    top_block_reasons = [
        {"reason": r, "count": c}
        for r, c in block_counts.most_common(15)
    ]

    return {
        "ok": True,
        "researchOnly": True,
        "privateApi": False,
        "windowHours": window_hours,
        "windowStartMs": cutoff_ms,
        "updatedAt": now_ms,
        "candidateCount": candidate_count,
        "eligibleCount": eligible_count,
        "caseCount": case_count,
        "roleCompleteCount": role_complete_count,
        "decisionCount": decision_count,
        "riskPassCount": risk_pass_count,
        "riskBlockCount": risk_block_count,
        "allocationPassCount": allocation_pass_count,
        "entryEligibleCount": entry_eligible_count,
        "orderCount": order_count,
        "fillCount": fill_count,
        "positionCount": position_count,
        "exitCount": exit_count,
        "blockReasonCounts": dict(block_counts),
        "topBlockedSymbols": top_blocked_symbols,
        "topBlockedSetups": top_block_reasons,
        "oldestPendingStage": stage_pending,
        "dataFreshness": data_freshness,
        "scannerTransport": scanner_transport,
        "zeroOrderDiagnosis": _zero_order_diagnosis(
            candidate_count=candidate_count,
            case_count=case_count,
            role_complete_count=role_complete_count,
            decision_count=decision_count,
            risk_pass_count=risk_pass_count,
            risk_block_count=risk_block_count,
            allocation_pass_count=allocation_pass_count,
            entry_eligible_count=entry_eligible_count,
            order_count=order_count,
            block_counts=block_counts,
            pending=stage_pending,
        ),
        "windows": {
            "1h": {"note": "use ?windowHours=1"},
            "6h": {"note": "use ?windowHours=6"},
            "24h": {"note": "use ?windowHours=24"},
        },
    }


def _zero_order_diagnosis(
    *,
    candidate_count: int,
    case_count: int,
    role_complete_count: int,
    decision_count: int,
    risk_pass_count: int,
    risk_block_count: int,
    allocation_pass_count: int,
    entry_eligible_count: int,
    order_count: int,
    block_counts: Counter[str],
    pending: dict[str, int],
) -> str:
    """Diagnose zero natural orders from real funnel counts (no hardcoded fake)."""
    if order_count > 0:
        return "NATURAL_ORDERS_PRESENT"
    if candidate_count == 0:
        return "NO_SCANNER_CANDIDATES"
    if candidate_count > 0 and case_count == 0:
        return "CASE_INGESTION_BLOCKED"
    if case_count > 0 and role_complete_count == 0 and decision_count == 0:
        return "ROLE_PIPELINE_INCOMPLETE"
    if role_complete_count > 0 and decision_count == 0:
        return "DECISION_ORCHESTRATOR_NOT_PRODUCING"
    if decision_count > 0 and risk_pass_count == 0:
        top = block_counts.most_common(1)
        code = top[0][0] if top else "RISK_CRITIC_REJECT"
        return f"ALL_DECISIONS_RISK_BLOCKED:{code}"
    if risk_pass_count > 0 and allocation_pass_count == 0 and entry_eligible_count == 0:
        return "ALLOCATION_BLOCKED"
    if (allocation_pass_count > 0 or entry_eligible_count > 0) and order_count == 0:
        if pending.get("decision_ready_unprocessed", 0) > 0:
            return "PAPER_ROUTING_OR_ENTRY_TRIGGER_BLOCKED"
        return "PAPER_ROUTING_OR_ENTRY_TRIGGER_BLOCKED"
    if risk_block_count > 0 and risk_pass_count == 0:
        return "ALL_DECISIONS_RISK_BLOCKED"
    return "PIPELINE_ACTIVE_NO_ENTRY_THRESHOLD_MET"


def build_candidate_decision_trace(candidate_id: str) -> dict[str, Any]:
    """Per-candidate trace across funnel stages."""
    sym, _, side = candidate_id.partition(":")
    if not side and ":" not in candidate_id:
        sym = candidate_id
        side = ""

    trace: dict[str, Any] = {
        "ok": True,
        "researchOnly": True,
        "candidateId": candidate_id,
        "symbol": sym.upper() if sym else candidate_id,
        "side": side or None,
        "stages": [],
        "terminalReason": None,
        "updatedAt": int(time.time() * 1000),
    }

    def _stage(name: str, result: str, **extra: Any) -> None:
        trace["stages"].append({
            "stage": name,
            "result": result,
            "atMs": int(time.time() * 1000),
            **extra,
        })

    # Scanner
    candidate_snap: Optional[dict[str, Any]] = None
    try:
        from backend.market.scanner.scanner_service import get_market_scanner

        for c in get_market_scanner().candidates(limit=300):
            if c.get("id") == candidate_id or (
                sym and c.get("symbol", "").upper() == sym.upper()
                and (not side or str(c.get("side", "")).upper() == side.upper())
            ):
                candidate_snap = c
                break
        if candidate_snap:
            _stage(
                "Scanner",
                "CANDIDATE",
                score=candidate_snap.get("score"),
                freshness=candidate_snap.get("freshness"),
            )
        else:
            _stage("Scanner", "NOT_FOUND")
            trace["terminalReason"] = "CANDIDATE_NOT_IN_SCANNER"
            trace["ok"] = False
            return trace
    except Exception as exc:  # noqa: BLE001
        _stage("Scanner", "ERROR", detail=str(exc))
        trace["ok"] = False
        return trace

    # Review case + decision
    store = None
    try:
        from backend.nexus_research.storage import get_research_store

        store = get_research_store()
        cases = store.query("review_cases", limit=500)
        case = next(
            (c for c in cases
             if c.get("candidateId") == candidate_id
             or (c.get("symbol") == candidate_snap.get("symbol")
                 and str(c.get("side", "")).upper() == str(candidate_snap.get("side", "")).upper())),
            None,
        )
        if case:
            _stage("ReviewCase", case.get("status") or "CASE", caseId=case.get("caseId"))
            case_id = case.get("caseId")
            decisions = [
                d for d in store.query("research_decisions", limit=300)
                if d.get("caseId") == case_id
                or d.get("symbol") == candidate_snap.get("symbol")
            ]
            if decisions:
                d0 = decisions[0]
                status = _decision_status(d0)
                _stage(
                    "Decision",
                    status,
                    summary=d0.get("summary"),
                    decisionId=d0.get("decisionId"),
                    supportingFeatureIds=d0.get("supportingFeatureIds") or [],
                    opposingFeatureIds=d0.get("opposingFeatureIds") or [],
                    missingFeatureIds=d0.get("missingFeatureIds") or [],
                    featureQualityScore=d0.get("featureQualityScore"),
                )
                if status != "READY_FOR_SIMULATION":
                    trace["terminalReason"] = classify_block_reason(d0.get("summary") or status)
                # Paper processing
                did = str(d0.get("decisionId") or "")
                processed = [
                    p for p in store.query("paper_processed_decisions", limit=200)
                    if p.get("decisionId") == did
                ]
                if processed:
                    p0 = processed[-1]
                    _stage(
                        "PaperController",
                        p0.get("outcome") or "PROCESSED",
                        detail=p0.get("detail"),
                        blockReason=classify_block_reason(str(p0.get("detail") or "")),
                    )
                    if p0.get("outcome") == "GUARD_BLOCKED":
                        trace["terminalReason"] = classify_block_reason(str(p0.get("detail")))
            else:
                _stage("Decision", "PENDING")
                trace["terminalReason"] = "NO_DECISION_YET"
        else:
            _stage("ReviewCase", "NOT_CREATED")
            trace["terminalReason"] = "CASE_NOT_CREATED"
    except Exception as exc:  # noqa: BLE001
        _stage("Decision", "ERROR", detail=str(exc))

    return trace
