"""PUB18-A Live Funnel + Market Pulse first-screen service (read-only)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_pub18_live_funnel.constants import (
    AI_POSTURES,
    BASE_COMMIT,
    BRANCH,
    FIRST_SCREEN_ANSWER_IDS,
    FIRST_SCREEN_QUESTIONS,
    FUNNEL_STAGES,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    PRIVATE_CONTRACT_TIP,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_pub18_live_funnel.fixtures import FIXTURE_AS_OF, catalog
from backend.nexus_pub18_live_funnel.honesty import (
    HonestyViolation,
    assert_not_fake_live,
    build_metric_slot,
    chrome_for_data_class,
    format_stage_display,
    validate_data_class,
    validate_posture,
)
from backend.nexus_pub18_live_funnel.sanitize import (
    assert_no_forbidden_keys,
    count_execution_controls,
    count_forbidden_key_hits,
    scrub_forbidden_keys,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(**payload: Any) -> dict[str, Any]:
    body = {
        "ok": True,
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "package": PACKAGE,
        "base_commit": BASE_COMMIT,
        "private_contract_tip": PRIVATE_CONTRACT_TIP,
        "read_only": True,
        "customer_trading": False,
        "exchange_api_used": False,
        "exchange_write": False,
        "private_core_imported": False,
        "private_core_import_count": 0,
        "private_fields_included": False,
        "private_field_leak_count": 0,
        "execution_control_count": 0,
        "member_execution_control_count": 0,
        "trade_buttons": False,
        "hard_bans": list(HARD_BANS),
        "as_of": _utc(),
        **payload,
    }
    assert_no_forbidden_keys(body)
    leaks = count_forbidden_key_hits(body)
    if leaks:
        raise HonestyViolation(f"private_field_leak:{leaks}")
    exec_count = count_execution_controls(body)
    if exec_count != 0:
        raise HonestyViolation(f"execution_control_count:{exec_count}")
    body["execution_control_count"] = 0
    body["member_execution_control_count"] = 0
    return body


def _answer(answer_id: str, *, answer: str, detail: str, state: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    row = {
        "id": answer_id,
        "question": FIRST_SCREEN_QUESTIONS[answer_id],
        "answer": answer,
        "detail": detail,
        "state": state,
    }
    if extra:
        row.update(extra)
    return row


def build_funnel(case: dict[str, Any]) -> dict[str, Any]:
    data_class = validate_data_class(str(case.get("data_class") or "UNAVAILABLE"))
    raw = case.get("funnel") or {}
    stages: list[dict[str, Any]] = []
    for stage_id, label in FUNNEL_STAGES:
        slot = raw.get(stage_id) or {}
        available = bool(slot.get("available"))
        count = slot.get("count")
        if not available:
            count = None
        display = format_stage_display(count=count, available=available, data_class=data_class)
        if not available and display in {"0", 0}:
            raise HonestyViolation(f"unavailable_as_zero:funnel.{stage_id}")
        stages.append(
            {
                "id": stage_id,
                "label": label,
                "count": count if available else None,
                "available": available,
                "display": display,
            }
        )
    summary = " → ".join(f"{s['label']}: {s['display']}" for s in stages)
    return {
        "stages": stages,
        "stage_ids": [s["id"] for s in stages],
        "summary": summary,
        "data_class": data_class,
        "read_only": True,
    }


def build_first_screen(case: dict[str, Any]) -> dict[str, Any]:
    data_class = validate_data_class(str(case.get("data_class") or "UNAVAILABLE"))
    chrome = chrome_for_data_class(data_class)
    # Allow explicit chrome override only when it matches honesty rules.
    if case.get("chrome_label"):
        chrome = str(case["chrome_label"]).upper()
    assert_not_fake_live(data_class=data_class, chrome_label=chrome)
    posture = validate_posture(str(case.get("ai_posture") or "ABSTAIN"))
    freshness = str(case.get("data_freshness") or data_class).upper()

    if case.get("actually_traded") is True:
        raise HonestyViolation("analysis_presented_as_actual_trading")
    if case.get("trade_buttons") is True:
        raise HonestyViolation("trade_buttons_forbidden")

    gms = case.get("global_market_state") or {}
    deriv = case.get("crypto_derivatives_risk") or {}
    metric_slots = []
    for key, slot in (deriv.get("metrics") or {}).items():
        metric_slots.append(
            build_metric_slot(
                key=str(key),
                value=slot.get("value"),
                available=bool(slot.get("available")),
                provider_required=bool(slot.get("provider_required")),
            )
        )

    top3 = list(case.get("top_3") or [])[:3]
    top3_display = (
        " · ".join(f"{t.get('market')} ({t.get('side_hint')})" for t in top3)
        if top3
        else ("STALE" if data_class == "STALE" else "UNAVAILABLE")
    )

    supporting = list(case.get("supporting_evidence") or [])
    counter = list(case.get("counter_evidence") or [])
    inv = case.get("invalidation") or {}

    supporting_answer = (
        "; ".join(e.get("summary", "") for e in supporting[:3])
        if supporting
        else ("STALE" if data_class == "STALE" else "UNAVAILABLE" if data_class == "UNAVAILABLE" else "none in scope")
    )
    counter_answer = (
        "; ".join(e.get("summary", "") for e in counter[:3])
        if counter
        else ("STALE" if data_class == "STALE" else "none in scope")
    )

    funnel = build_funnel(case)

    answers = [
        _answer(
            "global_market_state",
            answer=str(gms.get("summary") or "UNAVAILABLE"),
            detail=f"regime={gms.get('regime_label') or 'UNAVAILABLE'}",
            state=str(gms.get("availability") or data_class),
            extra={"regime_label": gms.get("regime_label")},
        ),
        _answer(
            "crypto_derivatives_risk",
            answer=str(deriv.get("summary") or "UNAVAILABLE"),
            detail=f"risk_band={deriv.get('risk_band') or 'UNAVAILABLE'}",
            state=str(deriv.get("availability") or data_class),
            extra={"risk_band": deriv.get("risk_band"), "metrics": metric_slots},
        ),
        _answer(
            "top_3_opportunities",
            answer=top3_display,
            detail="Public opportunities only · no Founder position / leverage / entry",
            state=data_class if top3 else ("STALE" if data_class == "STALE" else "UNAVAILABLE"),
            extra={"markets": top3},
        ),
        _answer(
            "ai_posture",
            answer=posture,
            detail="Suggestion / Shadow Decision posture only — not an order",
            state=data_class,
            extra={"allowed_postures": list(AI_POSTURES)},
        ),
        _answer(
            "supporting_evidence",
            answer=supporting_answer,
            detail=f"{len(supporting)} item(s)",
            state=data_class if supporting else ("empty" if data_class == "FIXTURE" else data_class),
            extra={"items": supporting},
        ),
        _answer(
            "counter_evidence",
            answer=counter_answer,
            detail=f"{len(counter)} item(s)",
            state=data_class if counter else ("empty" if data_class in {"FIXTURE", "LIVE_READ_ONLY"} else data_class),
            extra={"items": counter},
        ),
        _answer(
            "invalidation",
            answer=str(inv.get("summary") or "UNAVAILABLE"),
            detail=f"status={inv.get('status') or 'UNAVAILABLE'}",
            state=data_class,
            extra={"status": inv.get("status")},
        ),
        _answer(
            "data_freshness",
            answer=freshness,
            detail="LIVE_READ_ONLY / STALE / UNAVAILABLE / FIXTURE — never fake Live zeros",
            state=freshness,
        ),
        _answer(
            "data_class_label",
            answer=data_class,
            detail="Honest Shadow / Live / Fixture labeling (LIVE_READ_ONLY not bare LIVE)",
            state=data_class,
            extra={"chrome_label": chrome, "shadow_not_fill": True},
        ),
    ]

    ids = [a["id"] for a in answers]
    if ids != list(FIRST_SCREEN_ANSWER_IDS):
        raise HonestyViolation(f"answer_id_mismatch:{ids}")

    screen = {
        "case_id": case["case_id"],
        "surface": "member_live_funnel_market_pulse_first_screen",
        "data_class": data_class,
        "chrome_label": chrome,
        "answers": answers,
        "answer_count": len(answers),
        "ai_posture": posture,
        "data_freshness": freshness,
        "funnel": funnel,
        "top_opportunities": top3,
        "trade_buttons": False,
        "actually_traded": False,
        "private_fields_included": False,
        "founder_private_fields_blocked": True,
        "private_lessons_blocked": True,
        "execution_control_count": 0,
        "member_execution_control_count": 0,
        "private_contract_tip": PRIVATE_CONTRACT_TIP,
        "note": f"{chrome} · READ ONLY · Shadow Decisions only · NOT INVESTMENT ADVICE · no trade buttons",
    }
    assert_no_forbidden_keys(screen)
    if count_execution_controls(screen) != 0:
        raise HonestyViolation("execution_controls_in_screen")
    return scrub_forbidden_keys(screen)


def list_first_screens() -> dict[str, Any]:
    rows = [build_first_screen(c) for c in catalog()]
    return _envelope(
        surface="member_live_funnel_feed",
        count=len(rows),
        first_screens=rows,
        answer_ids=list(FIRST_SCREEN_ANSWER_IDS),
        postures=list(AI_POSTURES),
        funnel_stage_ids=[s[0] for s in FUNNEL_STAGES],
        note="Honest LIVE_READ_ONLY / STALE / UNAVAILABLE / FIXTURE — never bare LIVE fabrication.",
    )


def get_first_screen(case_id: str) -> dict[str, Any]:
    for case in catalog():
        if case["case_id"] == case_id:
            return _envelope(
                surface="member_live_funnel_detail",
                first_screen=build_first_screen(case),
            )
    return {
        "ok": False,
        "error": "first_screen_unavailable",
        "read_only": True,
        "customer_trading": False,
        "availability": "UNAVAILABLE",
        "execution_control_count": 0,
    }


def default_member_home_screen() -> dict[str, Any]:
    """Default home: LIVE_READ_ONLY bounded projection (honest zeros)."""
    live = next(c for c in catalog() if c["case_id"] == "pub18_live_read_only_bounded")
    return _envelope(
        surface="member_home_live_funnel_market_pulse",
        first_screen=build_first_screen(live),
    )


def service_meta() -> dict[str, Any]:
    return _envelope(
        surfaces=[
            "member_home_live_funnel_market_pulse",
            "member_live_funnel_feed",
            "member_live_funnel_detail",
            "three_passes",
        ],
        answer_ids=list(FIRST_SCREEN_ANSWER_IDS),
        postures=list(AI_POSTURES),
        funnel_stage_ids=[s[0] for s in FUNNEL_STAGES],
        methods_allowed=["GET", "HEAD", "OPTIONS"],
        environment="local_staging",
        as_of_fixture=FIXTURE_AS_OF,
        private_contract_tip=PRIVATE_CONTRACT_TIP,
    )
