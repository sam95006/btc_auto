"""Member Web Intelligence Experience service (UX-B).

Builds public-safe experience payloads with UX-A-compatible nested intelligence.
Read-only. Never places orders. Never imports private_core.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_public_member_intel.constants import (
    BASE_COMMIT,
    BRANCH,
    FUNNEL_STAGES,
    HARD_BANS,
    LANE,
    LANE_NAME,
    LIFECYCLE_STATES,
    MEMBER_POSTURES,
    PACKAGE,
    SCHEMA_VERSION,
)
from backend.nexus_public_member_intel.dto import intelligence_block_from_experience
from backend.nexus_public_member_intel.fixtures import FIXTURE_AS_OF, catalog
from backend.nexus_public_member_intel.honesty import (
    HonestyViolation,
    assert_no_fake_guarantee,
    assert_suggestion_not_filled,
    build_funnel_stage,
    honesty_attestations,
    validate_lifecycle,
    validate_posture,
)
from backend.nexus_public_member_intel.sanitize import (
    assert_no_forbidden_keys,
    scrub_forbidden_keys,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(**payload: Any) -> dict[str, Any]:
    body = {
        "ok": True,
        "schema": SCHEMA_VERSION,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "package": PACKAGE,
        "base_commit": BASE_COMMIT,
        "read_only": True,
        "customer_trading": False,
        "exchange_api_used": False,
        "private_core_imported": False,
        "private_core_import_count": 0,
        "hard_bans": list(HARD_BANS),
        "as_of": _utc(),
        **payload,
    }
    assert_no_forbidden_keys(body)
    assert_no_fake_guarantee(body)
    return body


def build_experience(case: dict[str, Any]) -> dict[str, Any]:
    """Materialize one member intelligence experience card from a fixture case."""
    lifecycle = validate_lifecycle(str(case["lifecycle_state"]))
    posture = validate_posture(str(case["posture"]))
    mode = str(case.get("mode") or "DEMO_DATA")
    actually_ordered = case.get("actually_ordered")
    order_fill_claimed = bool(case.get("order_fill_claimed", False))

    assert_suggestion_not_filled(
        lifecycle_state=lifecycle,
        actually_ordered=actually_ordered if isinstance(actually_ordered, bool) else None,
        order_fill_claimed=order_fill_claimed,
    )

    funnel_raw = case.get("funnel") or {}
    stages = []
    for key, label in FUNNEL_STAGES:
        stage_info = funnel_raw.get(key) or {"count": None, "available": False}
        stages.append(
            build_funnel_stage(
                key=key,
                label=label,
                count=stage_info.get("count"),
                available=bool(stage_info.get("available")),
            )
        )

    attest = honesty_attestations(
        mode=mode,
        lifecycle_state=lifecycle,
        actually_ordered=actually_ordered if isinstance(actually_ordered, bool) else None,
        order_fill_claimed=order_fill_claimed,
    )

    similar = case["similar"]
    similar_stats = similar.to_public_dict()

    intelligence = intelligence_block_from_experience(
        schema_version="public.intelligence.v2",
        symbol=str(case["symbol"]),
        decision_id=str(case["decision_id"]),
        regime=case["regime"],
        regime_label=str(case.get("regime_label") or "UNAVAILABLE"),
        posture=posture,
        why_suggested=list(case.get("why_suggested") or []),
        supporting=list(case.get("supporting") or []),
        contradicting=list(case.get("contradicting") or []),
        uncertainty_band=str(case.get("uncertainty_band") or "UNAVAILABLE"),
        abstention_reason=case.get("abstention_reason"),
        strategy_expert_label=str(case.get("strategy_expert_label") or "UNAVAILABLE"),
        lesson_applied_label=str(case.get("lesson_applied_label") or "UNAVAILABLE"),
        similar=similar,
        data_freshness=str(case.get("data_freshness") or "UNAVAILABLE"),
        uxa_lifecycle=str(case.get("uxa_lifecycle") or "UNAVAILABLE"),
        as_of=FIXTURE_AS_OF,
        retrieved_at=_utc(),
    )

    ordered_display = (
        "UNAVAILABLE"
        if actually_ordered is None
        else ("YES" if actually_ordered else "NO")
    )

    experience = {
        "case_id": case["case_id"],
        "symbol": case["symbol"],
        "decision_id": case["decision_id"],
        "lifecycle_state": lifecycle,
        "posture": posture,
        "mode": mode,
        "chrome_label": attest["chrome_label"],
        "data_freshness": case.get("data_freshness"),
        "regime_label": case.get("regime_label"),
        "funnel": {
            "stages": stages,
            "summary": " → ".join(f"{s['label']}: {s['display']}" for s in stages),
            "source_mode": mode,
        },
        "why_suggested": list(case.get("why_suggested") or []),
        "contradicting_evidence": [
            e.to_public_dict() for e in (case.get("contradicting") or [])
        ],
        "supporting_evidence": [
            e.to_public_dict() for e in (case.get("supporting") or [])
        ],
        "similar_case_stats": similar_stats,
        "actually_ordered": actually_ordered,
        "actually_ordered_display": ordered_display,
        "order_fill_claimed": False,
        "suggestion_only": attest["suggestion_only"],
        "honesty": attest,
        "intelligence": intelligence,  # UX-A compatible nested shape
    }
    assert_no_fake_guarantee(experience)
    assert_no_forbidden_keys(experience)
    return scrub_forbidden_keys(experience)


def list_experiences() -> dict[str, Any]:
    rows = [build_experience(c) for c in catalog()]
    return _envelope(
        surface="member_intelligence_feed",
        count=len(rows),
        experiences=rows,
        lifecycle_states=list(LIFECYCLE_STATES),
        postures=list(MEMBER_POSTURES),
        funnel_stage_ids=[k for k, _ in FUNNEL_STAGES],
        note="DEMO_DATA / replay fixtures only — never Live chrome for fixtures.",
    )


def get_experience(case_id: str) -> dict[str, Any]:
    for case in catalog():
        if case["case_id"] == case_id:
            return _envelope(
                surface="member_intelligence_detail",
                experience=build_experience(case),
            )
    return {
        "ok": False,
        "error": "experience_unavailable",
        "read_only": True,
        "customer_trading": False,
        "lifecycle_state": "UNAVAILABLE",
    }


def state_matrix() -> dict[str, Any]:
    """Return the required distinct presentation states with honesty notes."""
    notes = {
        "OBSERVING": "Watching markets — no suggestion yet",
        "AI_ANALYZING": "Model running — not an order",
        "AI_SUGGESTION": "Suggestion only — never a filled order",
        "RISK_REVIEW": "Risk gate review",
        "READY": "Ready for human disposition — not entered",
        "ENTERED": "Human-confirmed entry state (advisory display)",
        "MANAGING": "Open thesis management",
        "EXITED": "Closed / exited",
        "BLOCKED": "Gate blocked",
        "ABSTAINED": "Explicit abstention",
        "SIMULATION": "Simulation — not live",
        "HISTORICAL_REPLAY": "Replay — not live",
        "DEMO_DATA": "Fixture / demo catalog",
        "UNAVAILABLE": "No value — never render as 0",
        "STALE": "As-of lag — not live",
    }
    return _envelope(
        surface="lifecycle_state_matrix",
        states=[
            {"state": s, "note": notes[s], "distinct": True}
            for s in LIFECYCLE_STATES
        ],
    )


def service_meta() -> dict[str, Any]:
    return _envelope(
        surfaces=[
            "member_intelligence_feed",
            "member_intelligence_detail",
            "lifecycle_state_matrix",
            "three_passes",
        ],
        lifecycle_states=list(LIFECYCLE_STATES),
        postures=list(MEMBER_POSTURES),
        funnel_stage_ids=[k for k, _ in FUNNEL_STAGES],
        uxa_compatible=True,
        methods_allowed=["GET", "HEAD", "OPTIONS"],
        environment="local_staging",
    )


def refuse_fixture_as_live() -> None:
    raise HonestyViolation("HARD BAN: fixture/DEMO_DATA must not be labeled LIVE")


def refuse_unavailable_as_zero() -> None:
    raise HonestyViolation("HARD BAN: unavailable must not render as 0")


def refuse_ai_suggestion_as_fill() -> None:
    raise HonestyViolation("HARD BAN: AI_SUGGESTION must not be presented as filled order")


def refuse_backtest_as_live() -> None:
    raise HonestyViolation("HARD BAN: backtest/HISTORICAL_REPLAY must not be labeled LIVE")


def refuse_fake_60_guarantee() -> None:
    raise HonestyViolation("HARD BAN: fake 60% guarantee refused")
