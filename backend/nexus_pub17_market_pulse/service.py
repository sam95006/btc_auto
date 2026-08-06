"""PUB17-B Market Pulse first-screen service (read-only, public-safe)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_pub17_market_pulse.constants import (
    AI_POSTURES,
    BASE_COMMIT,
    BRANCH,
    DISPLAY_ANALYSIS_ONLY,
    FIRST_SCREEN_ANSWER_IDS,
    FIRST_SCREEN_QUESTIONS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_pub17_market_pulse.fixtures import FIXTURE_AS_OF, catalog
from backend.nexus_pub17_market_pulse.honesty import (
    HonestyViolation,
    assert_not_fake_live,
    build_metric_slot,
    validate_availability,
    validate_freshness,
    validate_posture,
    validate_trading_flag,
)
from backend.nexus_pub17_market_pulse.sanitize import (
    assert_no_forbidden_keys,
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
        "read_only": True,
        "customer_trading": False,
        "exchange_api_used": False,
        "private_core_imported": False,
        "private_core_import_count": 0,
        "private_fields_included": False,
        "private_field_leak_count": 0,
        "hard_bans": list(HARD_BANS),
        "as_of": _utc(),
        **payload,
    }
    assert_no_forbidden_keys(body)
    leaks = count_forbidden_key_hits(body)
    if leaks:
        raise HonestyViolation(f"private_field_leak:{leaks}")
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


def build_first_screen(case: dict[str, Any]) -> dict[str, Any]:
    """Materialize the nine member-first-screen answers from a fixture case."""
    mode = str(case.get("mode") or "DEMO_DATA")
    chrome = str(case.get("chrome_label") or mode)
    freshness = validate_freshness(str(case.get("data_freshness") or "UNAVAILABLE"))
    posture = validate_posture(str(case.get("ai_posture") or "ABSTAIN"))
    trading_flag = validate_trading_flag(str(case.get("analysis_vs_actual_trading") or "ANALYSIS_ONLY"))
    assert_not_fake_live(mode=mode, freshness=freshness, chrome_label=chrome)

    gms = case.get("global_market_state") or {}
    validate_availability(str(gms.get("availability") or "UNAVAILABLE"))
    deriv = case.get("crypto_derivatives_risk") or {}
    validate_availability(str(deriv.get("availability") or "UNAVAILABLE"))

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

    top3 = list(case.get("top_3") or [])
    if len(top3) > 3:
        top3 = top3[:3]
    top3_display = (
        " · ".join(f"{t.get('market')} ({t.get('side_hint')})" for t in top3)
        if top3
        else ("PROVIDER_REQUIRED" if mode == "PROVIDER_REQUIRED" else "UNAVAILABLE")
    )

    supporting = list(case.get("supporting_evidence") or [])
    counter = list(case.get("counter_evidence") or [])
    inv = case.get("invalidation") or {}

    gms_answer = str(gms.get("summary") or "UNAVAILABLE")
    deriv_answer = str(deriv.get("summary") or "UNAVAILABLE")
    if gms.get("provider_required"):
        gms_answer = "PROVIDER_REQUIRED"
    if str(deriv.get("availability")) == "PROVIDER_REQUIRED":
        deriv_answer = "PROVIDER_REQUIRED"

    supporting_answer = (
        "; ".join(e.get("summary", "") for e in supporting[:3])
        if supporting
        else ("PROVIDER_REQUIRED" if mode == "PROVIDER_REQUIRED" else "UNAVAILABLE")
    )
    counter_answer = (
        "; ".join(e.get("summary", "") for e in counter[:3])
        if counter
        else ("PROVIDER_REQUIRED" if mode == "PROVIDER_REQUIRED" else "none in scope")
    )
    inv_answer = str(inv.get("summary") or "UNAVAILABLE")
    if str(inv.get("availability")) == "PROVIDER_REQUIRED":
        inv_answer = "PROVIDER_REQUIRED"

    trading_answer = (
        DISPLAY_ANALYSIS_ONLY
        if trading_flag in {"ANALYSIS_ONLY", "NOT_ACTUAL_TRADING"}
        else trading_flag
    )
    if case.get("actually_traded") is True:
        raise HonestyViolation("analysis_presented_as_actual_trading")

    answers = [
        _answer(
            "global_market_state",
            answer=gms_answer,
            detail=f"regime={gms.get('regime_label') or 'UNAVAILABLE'}",
            state=str(gms.get("availability") or freshness),
            extra={"regime_label": gms.get("regime_label")},
        ),
        _answer(
            "crypto_derivatives_risk",
            answer=deriv_answer,
            detail=f"risk_band={deriv.get('risk_band') or 'UNAVAILABLE'}",
            state=str(deriv.get("availability") or freshness),
            extra={"risk_band": deriv.get("risk_band"), "metrics": metric_slots},
        ),
        _answer(
            "top_3_markets_contracts",
            answer=top3_display,
            detail="Public markets/contracts only · no position size / leverage / entry",
            state="DEMO_DATA" if top3 else ("PROVIDER_REQUIRED" if mode == "PROVIDER_REQUIRED" else "UNAVAILABLE"),
            extra={"markets": top3},
        ),
        _answer(
            "ai_posture",
            answer=posture,
            detail="Suggestion / research posture only — not an order",
            state=freshness if mode != "PROVIDER_REQUIRED" else "PROVIDER_REQUIRED",
            extra={"allowed_postures": list(AI_POSTURES)},
        ),
        _answer(
            "supporting_evidence",
            answer=supporting_answer,
            detail=f"{len(supporting)} item(s)",
            state=freshness if supporting else ("PROVIDER_REQUIRED" if mode == "PROVIDER_REQUIRED" else "empty"),
            extra={"items": supporting},
        ),
        _answer(
            "counter_evidence",
            answer=counter_answer,
            detail=f"{len(counter)} item(s)",
            state=freshness if counter else ("PROVIDER_REQUIRED" if mode == "PROVIDER_REQUIRED" else "empty"),
            extra={"items": counter},
        ),
        _answer(
            "invalidation",
            answer=inv_answer,
            detail=f"status={inv.get('status') or 'UNAVAILABLE'}",
            state=str(inv.get("availability") or freshness),
            extra={"status": inv.get("status")},
        ),
        _answer(
            "data_freshness",
            answer=freshness,
            detail="Never treat DEMO_DATA / PROVIDER_REQUIRED as LIVE",
            state=freshness,
        ),
        _answer(
            "analysis_vs_actual_trading",
            answer=trading_answer,
            detail="Member surface is analysis-only · exchange write disabled",
            state=trading_flag,
            extra={
                "flag": trading_flag,
                "actually_traded": False,
                "customer_trading": False,
                "exchange_write": False,
            },
        ),
    ]

    ids = [a["id"] for a in answers]
    if ids != list(FIRST_SCREEN_ANSWER_IDS):
        raise HonestyViolation(f"answer_id_mismatch:{ids}")

    screen = {
        "case_id": case["case_id"],
        "surface": "member_market_pulse_first_screen",
        "mode": mode,
        "chrome_label": chrome,
        "answers": answers,
        "answer_count": len(answers),
        "ai_posture": posture,
        "data_freshness": freshness,
        "analysis_vs_actual_trading": trading_flag,
        "top_opportunities": top3,
        "note": "DEMO/PROVIDER_REQUIRED · READ ONLY · NOT INVESTMENT ADVICE · no exchange orders",
        "private_fields_included": False,
        "founder_private_fields_blocked": True,
    }
    assert_no_forbidden_keys(screen)
    return scrub_forbidden_keys(screen)


def list_first_screens() -> dict[str, Any]:
    rows = [build_first_screen(c) for c in catalog()]
    return _envelope(
        surface="member_market_pulse_feed",
        count=len(rows),
        first_screens=rows,
        answer_ids=list(FIRST_SCREEN_ANSWER_IDS),
        postures=list(AI_POSTURES),
        note="Fixtures / PROVIDER_REQUIRED only — never Live chrome for unbound providers.",
    )


def get_first_screen(case_id: str) -> dict[str, Any]:
    for case in catalog():
        if case["case_id"] == case_id:
            return _envelope(
                surface="member_market_pulse_detail",
                first_screen=build_first_screen(case),
            )
    return {
        "ok": False,
        "error": "first_screen_unavailable",
        "read_only": True,
        "customer_trading": False,
        "availability": "UNAVAILABLE",
    }


def default_member_home_screen() -> dict[str, Any]:
    """Default home binding: DEMO wait case (never LIVE)."""
    case = catalog()[0]
    return _envelope(
        surface="member_home_market_pulse",
        first_screen=build_first_screen(case),
    )


def service_meta() -> dict[str, Any]:
    return _envelope(
        surfaces=[
            "member_home_market_pulse",
            "member_market_pulse_feed",
            "member_market_pulse_detail",
            "three_passes",
        ],
        answer_ids=list(FIRST_SCREEN_ANSWER_IDS),
        postures=list(AI_POSTURES),
        methods_allowed=["GET", "HEAD", "OPTIONS"],
        environment="local_staging",
        as_of_fixture=FIXTURE_AS_OF,
    )
