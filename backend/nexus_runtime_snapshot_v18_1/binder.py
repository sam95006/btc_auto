"""Map Runtime Snapshot → pub18 Live Funnel first-screen + mobile surface DTOs."""
from __future__ import annotations

from typing import Any

from backend.nexus_runtime_snapshot_v18_1.constants import HARD_BANS, PACKAGE, SCHEMA
from backend.nexus_runtime_snapshot_v18_1.loader import load_runtime_snapshot


def snapshot_to_live_funnel_screen(snap: dict[str, Any]) -> dict[str, Any]:
    """Build a pub18-compatible first_screen from a runtime snapshot (extend, don't rewrite)."""
    display = str(snap.get("display_label") or snap.get("chrome_label") or "UNAVAILABLE")
    data_class = str(snap.get("data_class") or display)
    freshness = str(snap.get("data_freshness") or display)
    is_live = bool(snap.get("is_live_view"))
    funnel = snap.get("universe_funnel") or {}
    decisions = snap.get("decision_counts") or {}
    top = list(snap.get("top_opportunities") or [])
    shadow = snap.get("shadow_status") or {}
    ai = snap.get("AI_gateway_status") or {}
    source = snap.get("source_health") or {}
    reasons = list(snap.get("degraded_reasons") or [])

    last_decision = str(shadow.get("last_decision") or "ABSTAIN").upper()
    if last_decision not in {"LONG", "SHORT", "WAIT", "ABSTAIN", "BLOCK"}:
        last_decision = "ABSTAIN"
    # Member pulse posture excludes BLOCK → map to ABSTAIN for ai_posture slot.
    ai_posture = "ABSTAIN" if last_decision == "BLOCK" else last_decision
    if ai_posture not in {"LONG", "SHORT", "WAIT", "ABSTAIN"}:
        ai_posture = "ABSTAIN"

    def _stage(stage_id: str, label: str, count: int | None) -> dict[str, Any]:
        available = funnel.get("available") is True and count is not None
        if not available:
            return {
                "id": stage_id,
                "label": label,
                "count": None,
                "available": False,
                "display": display if display in {"STALE", "RUNTIME_STOPPED", "UNAVAILABLE", "PAUSED"} else "UNAVAILABLE",
            }
        return {
            "id": stage_id,
            "label": label,
            "count": count,
            "available": True,
            "display": str(count),
        }

    scanned = funnel.get("contracts_scanned")
    eligible = funnel.get("eligible")
    observe = funnel.get("observe_only")
    blocked = funnel.get("blocked")
    candidates = funnel.get("candidates")
    shadow_n = shadow.get("shadow_opened_count")
    if shadow_n is None:
        shadow_n = 0 if funnel.get("available") else None

    stages = [
        _stage("scanned", "Scanned", scanned if isinstance(scanned, int) else None),
        _stage("data_available", "Data available", eligible if isinstance(eligible, int) else None),
        _stage("liquidity", "Liquidity", observe if isinstance(observe, int) else None),
        _stage(
            "data_trust",
            "Data Trust",
            eligible if isinstance(eligible, int) else None,
        ),
        _stage("candidate", "Candidate", candidates if isinstance(candidates, int) else None),
        _stage(
            "ai_review",
            "AI Review",
            int(ai.get("AI_requests") or 0) if funnel.get("available") else None,
        ),
        _stage("cost_blocked", "Cost Blocked", 0 if funnel.get("available") else None),
        _stage("risk_blocked", "Risk Blocked", blocked if isinstance(blocked, int) else None),
        _stage(
            "shadow_decisions",
            "Shadow Decisions",
            int(shadow_n) if funnel.get("available") else None,
        ),
    ]
    summary = " → ".join(f"{s['label']}: {s['display']}" for s in stages)

    state = data_class
    answers = [
        {
            "id": "global_market_state",
            "question": "Global Market State",
            "answer": (
                f"Runtime {snap.get('runtime_state')} · source {source.get('status')}"
                if is_live
                else f"{display} — not Live"
            ),
            "detail": f"runtime_state={snap.get('runtime_state')}",
            "state": state,
        },
        {
            "id": "crypto_derivatives_risk",
            "question": "Crypto Derivatives Risk",
            "answer": (
                "Data Trust / eligibility fail-closed"
                if "eligible_zero_fail_closed" in reasons
                else ("Provider / source watch" if source.get("status") == "DEGRADED" else display)
            ),
            "detail": f"source_health={source.get('status')}",
            "state": state,
            "metrics": [
                {
                    "key": "source_health",
                    "display": str(source.get("status") or "UNAVAILABLE"),
                    "available": source.get("status") not in {None, "UNAVAILABLE"},
                },
                {
                    "key": "AI_gateway",
                    "display": str(ai.get("health") or "UNAVAILABLE"),
                    "available": ai.get("health") not in {None, "UNAVAILABLE"},
                },
            ],
        },
        {
            "id": "top_3_opportunities",
            "question": "Top 3 Opportunities",
            "answer": (
                " · ".join(f"{t.get('market')} ({t.get('side_hint')})" for t in top)
                if top
                else display
            ),
            "detail": "Public opportunities only · no Founder position / leverage / entry",
            "state": state,
            "markets": top,
        },
        {
            "id": "ai_posture",
            "question": "AI posture",
            "answer": ai_posture,
            "detail": f"Last shadow decision={last_decision} · not an order",
            "state": state,
        },
        {
            "id": "supporting_evidence",
            "question": "Supporting Evidence",
            "answer": (
                f"Projection rows={snap.get('projection_count')} · lineage={snap.get('lineage_id')}"
                if snap.get("projection_count")
                else display
            ),
            "detail": "runtime projection evidence",
            "state": state,
            "items": (
                [
                    {
                        "summary": f"lineage {snap.get('lineage_id')}",
                        "polarity": "SUPPORTING",
                    }
                ]
                if snap.get("lineage_id")
                else []
            ),
        },
        {
            "id": "counter_evidence",
            "question": "Counter Evidence",
            "answer": "; ".join(reasons) if reasons else "none in scope",
            "detail": f"{len(reasons)} reason(s)",
            "state": state,
            "items": [{"summary": r, "polarity": "CONTRADICTING"} for r in reasons[:5]],
        },
        {
            "id": "invalidation",
            "question": "Invalidation",
            "answer": (
                "Live view invalidated — runtime not RUNNING"
                if not is_live
                else "Invalidate when Data Trust / eligibility gates fail"
            ),
            "detail": f"status={'INVALIDATED' if not is_live else 'INTACT'}",
            "state": state,
        },
        {
            "id": "data_freshness",
            "question": "Data Freshness",
            "answer": freshness,
            "detail": "RUNTIME_STOPPED / STALE / UNAVAILABLE when not live — never fake Live",
            "state": freshness,
        },
        {
            "id": "data_class_label",
            "question": "Shadow / Live / Fixture label",
            "answer": data_class,
            "detail": f"chrome={display} · actual_ordered=false · actual_filled=false",
            "state": data_class,
            "actually_traded": False,
        },
    ]

    return {
        "case_id": f"v18_1_runtime_{str(snap.get('lineage_id') or 'na')}",
        "surface": "member_live_funnel_market_pulse_runtime_bound",
        "data_class": data_class,
        "chrome_label": display,
        "answers": answers,
        "answer_count": len(answers),
        "ai_posture": ai_posture,
        "data_freshness": freshness,
        "funnel": {
            "stages": stages,
            "stage_ids": [s["id"] for s in stages],
            "summary": summary,
            "data_class": data_class,
            "read_only": True,
        },
        "top_opportunities": top,
        "runtime_state": snap.get("runtime_state"),
        "source_health": source,
        "decision_counts": decisions,
        "shadow_status": shadow,
        "AI_gateway_status": ai,
        "degraded_reasons": reasons,
        "actual_ordered": False,
        "actual_filled": False,
        "trade_buttons": False,
        "actually_traded": False,
        "is_live_view": is_live,
        "last_updated": snap.get("last_updated"),
        "lineage_id": snap.get("lineage_id"),
        "private_fields_included": False,
        "founder_private_fields_blocked": True,
        "private_lessons_blocked": True,
        "execution_control_count": 0,
        "member_execution_control_count": 0,
        "fixture_as_live_count": 0,
        "note": snap.get("note"),
    }


def snapshot_to_mobile_surface(snap: dict[str, Any]) -> dict[str, Any]:
    """Mobile-safe surface payload — status, pulse, opportunities, evidence, risk, alerts slots."""
    screen = snapshot_to_live_funnel_screen(snap)
    return {
        "schema": "mobile_v18_1_runtime_snapshot_surface_v1",
        "schema_version": "1",
        "ok": bool(snap.get("ok", True)),
        "runtime_status": snap.get("runtime_state"),
        "display_label": snap.get("display_label"),
        "chrome_label": snap.get("chrome_label"),
        "data_class": snap.get("data_class"),
        "data_freshness": snap.get("data_freshness"),
        "is_live_view": bool(snap.get("is_live_view")),
        "last_updated": snap.get("last_updated"),
        "market_pulse": {
            "global_market_state": next(
                (a["answer"] for a in screen["answers"] if a["id"] == "global_market_state"),
                snap.get("display_label"),
            ),
            "ai_posture": screen.get("ai_posture"),
            "data_freshness": snap.get("data_freshness"),
        },
        "opportunity_list": screen.get("top_opportunities") or [],
        "decision_detail": {
            "last_decision": (snap.get("shadow_status") or {}).get("last_decision"),
            "last_symbol": (snap.get("shadow_status") or {}).get("last_symbol"),
            "lineage_id": snap.get("lineage_id"),
            "actual_ordered": False,
            "actual_filled": False,
        },
        "evidence": next(
            (a.get("items") or [] for a in screen["answers"] if a["id"] == "supporting_evidence"),
            [],
        ),
        "counter_evidence": next(
            (a.get("items") or [] for a in screen["answers"] if a["id"] == "counter_evidence"),
            [],
        ),
        "risk": {
            "degraded_reasons": list(snap.get("degraded_reasons") or []),
            "source_health": (snap.get("source_health") or {}).get("status"),
            "AI_gateway_health": (snap.get("AI_gateway_status") or {}).get("health"),
        },
        "freshness": snap.get("data_freshness"),
        "shadow_status": snap.get("shadow_status"),
        "provider_degraded_state": (snap.get("source_health") or {}).get("status"),
        "universe_funnel": snap.get("universe_funnel"),
        "decision_counts": snap.get("decision_counts"),
        "alerts": list(snap.get("alerts") or []),
        "trade_buttons": False,
        "member_execution_control_count": 0,
        "execution_control_count": 0,
        "read_only": True,
        "note": "Mobile read-only binding · no trade controls",
    }


def build_bound_home(*, runtime_root: Any = None) -> dict[str, Any]:
    snap = load_runtime_snapshot(runtime_root)
    from backend.nexus_runtime_snapshot_v18_1.alerts import build_runtime_alerts

    alerts = build_runtime_alerts(snap)
    snap = {**snap, "alerts": alerts}
    screen = snapshot_to_live_funnel_screen(snap)
    mobile = snapshot_to_mobile_surface({**snap, "alerts": alerts})
    return {
        "ok": True,
        "schema": SCHEMA,
        "package": PACKAGE,
        "read_only": True,
        "customer_trading": False,
        "exchange_write": False,
        "trade_buttons": False,
        "actual_ordered": False,
        "actual_filled": False,
        "fixture_as_live_count": 0,
        "private_field_leak_count": 0,
        "member_execution_control_count": 0,
        "hard_bans": list(HARD_BANS),
        "runtime_snapshot": snap,
        "first_screen": screen,
        "mobile_surface": mobile,
        "alerts": alerts,
        "surface": "v18_1_phase_b_runtime_live_binding",
    }
