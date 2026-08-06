"""PUB18-B Decision Detail transparency service (read-only, public-safe)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_pub18_decision_detail.constants import (
    AI_POSTURES,
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    MEMBER_VISIBLE_FIELD_IDS,
    MEMBER_VISIBLE_FIELD_LABELS,
    PACKAGE,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_pub18_decision_detail.fixtures import FIXTURE_AS_OF, catalog
from backend.nexus_pub18_decision_detail.honesty import (
    HonestyViolation,
    assert_not_fake_live,
    validate_availability,
    validate_chrome,
    validate_freshness,
    validate_posture,
)
from backend.nexus_pub18_decision_detail.sanitize import (
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


def _field(
    field_id: str,
    *,
    answer: str,
    detail: str,
    state: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "id": field_id,
        "label": MEMBER_VISIBLE_FIELD_LABELS[field_id],
        "answer": answer,
        "detail": detail,
        "state": state,
    }
    if extra:
        row.update(extra)
    return row


def _evidence_answer(items: list[dict[str, Any]], *, mode: str, empty_label: str) -> str:
    if items:
        return "; ".join(str(e.get("summary") or "") for e in items[:3] if e.get("summary"))
    if mode == "PROVIDER_REQUIRED":
        return "PROVIDER_REQUIRED"
    if mode == "UNAVAILABLE":
        return "UNAVAILABLE"
    return empty_label


def build_decision_detail(case: dict[str, Any]) -> dict[str, Any]:
    """Materialize the twelve member-visible transparency fields from a fixture case."""
    mode = str(case.get("mode") or "DEMO_DATA")
    chrome = validate_chrome(str(case.get("chrome_label") or mode))
    freshness = validate_freshness(str(case.get("data_freshness") or "UNAVAILABLE"))
    posture = validate_posture(str(case.get("ai_posture") or "ABSTAIN"))
    assert_not_fake_live(mode=mode, freshness=freshness, chrome_label=chrome)

    timeline = case.get("decision_timeline") or {}
    regime = case.get("market_regime") or {}
    trust = case.get("data_trust") or {}
    expert = case.get("strategy_expert_label") or {}
    evidence = list(case.get("evidence") or [])
    counter = list(case.get("counter_evidence") or [])
    risk = case.get("risk_reason") or {}
    why = case.get("why_wait_abstain") or {}
    hist = case.get("historical_similarity_aggregate") or {}
    shadow = case.get("shadow_outcome") or {}
    process = case.get("process_classification_aggregate") or {}
    delayed = case.get("delayed_learning_summary") or {}

    for block in (timeline, regime, trust, expert, risk, why, hist, shadow, process, delayed):
        if isinstance(block, dict) and block.get("availability"):
            validate_availability(str(block["availability"]))

    fields = [
        _field(
            "decision_timeline",
            answer=str(timeline.get("summary") or "UNAVAILABLE"),
            detail=f"stages={len(timeline.get('stages') or [])}",
            state=str(timeline.get("availability") or freshness),
            extra={"stages": list(timeline.get("stages") or [])},
        ),
        _field(
            "market_regime",
            answer=str(regime.get("label") or regime.get("summary") or "UNAVAILABLE"),
            detail=str(regime.get("summary") or ""),
            state=str(regime.get("availability") or freshness),
            extra={"regime_label": regime.get("label")},
        ),
        _field(
            "data_trust",
            answer=str(trust.get("band") or trust.get("summary") or "UNAVAILABLE"),
            detail=str(trust.get("summary") or ""),
            state=str(trust.get("availability") or freshness),
            extra={"trust_band": trust.get("band")},
        ),
        _field(
            "strategy_expert_label",
            answer=str(expert.get("label") or "UNAVAILABLE"),
            detail=str(expert.get("summary") or "Public expert label only — no private weights"),
            state=str(expert.get("availability") or freshness),
            extra={"expert_label": expert.get("label")},
        ),
        _field(
            "evidence",
            answer=_evidence_answer(evidence, mode=mode, empty_label="none in scope"),
            detail=f"{len(evidence)} item(s)",
            state=freshness if evidence else ("PROVIDER_REQUIRED" if mode == "PROVIDER_REQUIRED" else "empty"),
            extra={"items": evidence},
        ),
        _field(
            "counter_evidence",
            answer=_evidence_answer(counter, mode=mode, empty_label="none in scope"),
            detail=f"{len(counter)} item(s)",
            state=freshness if counter else ("PROVIDER_REQUIRED" if mode == "PROVIDER_REQUIRED" else "empty"),
            extra={"items": counter},
        ),
        _field(
            "risk_reason",
            answer=str(risk.get("summary") or "UNAVAILABLE"),
            detail="Advisory risk reason only — no override controls",
            state=str(risk.get("availability") or freshness),
        ),
        _field(
            "why_wait_abstain",
            answer=str(why.get("summary") or "UNAVAILABLE"),
            detail=f"posture={why.get('posture') or posture}",
            state=str(why.get("availability") or freshness),
            extra={"posture": why.get("posture") or posture},
        ),
        _field(
            "historical_similarity_aggregate",
            answer=str(hist.get("summary") or "UNAVAILABLE"),
            detail="Aggregate counts only — never exact proprietary thresholds",
            state=str(hist.get("availability") or freshness),
            extra={
                "sample_count": hist.get("sample_count"),
                "aggregate_only": True,
            },
        ),
        _field(
            "shadow_outcome",
            answer=str(shadow.get("status") or shadow.get("summary") or "UNAVAILABLE"),
            detail=str(shadow.get("summary") or ""),
            state=str(shadow.get("availability") or freshness),
            extra={"shadow_status": shadow.get("status")},
        ),
        _field(
            "process_classification_aggregate",
            answer=str(process.get("summary") or "UNAVAILABLE"),
            detail="Public process aggregate — no private raw graph",
            state=str(process.get("availability") or freshness),
        ),
        _field(
            "delayed_learning_summary",
            answer=str(delayed.get("summary") or "UNAVAILABLE"),
            detail=f"status={delayed.get('status') or 'UNAVAILABLE'} · no private lesson memory",
            state=str(delayed.get("availability") or freshness),
            extra={
                "learning_status": delayed.get("status"),
                "private_lesson_memory": False,
            },
        ),
    ]

    ids = [f["id"] for f in fields]
    if ids != list(MEMBER_VISIBLE_FIELD_IDS):
        raise HonestyViolation(f"field_id_mismatch:{ids}")

    detail = {
        "case_id": case["case_id"],
        "decision_id": case.get("decision_id"),
        "surface": "member_decision_detail_transparency",
        "mode": mode,
        "chrome_label": chrome,
        "fields": fields,
        "field_count": len(fields),
        "ai_posture": posture,
        "data_freshness": freshness,
        "note": (
            f"{chrome} · READ ONLY · learning transparency aggregates only · "
            "no private graph / thresholds / weights / prompts / CoT / account data"
        ),
        "private_fields_included": False,
        "founder_private_fields_blocked": True,
        "actually_traded": False,
        "customer_trading": False,
        "exchange_write": False,
    }
    assert_no_forbidden_keys(detail)
    return scrub_forbidden_keys(detail)


def list_decision_details() -> dict[str, Any]:
    rows = [build_decision_detail(c) for c in catalog()]
    return _envelope(
        surface="member_decision_detail_feed",
        count=len(rows),
        decision_details=rows,
        field_ids=list(MEMBER_VISIBLE_FIELD_IDS),
        postures=list(AI_POSTURES),
        note="Fixtures / PROVIDER_REQUIRED / STALE / UNAVAILABLE only — never fake LIVE.",
    )


def get_decision_detail(case_id: str) -> dict[str, Any]:
    for case in catalog():
        if case["case_id"] == case_id or str(case.get("decision_id")) == case_id:
            return _envelope(
                surface="member_decision_detail",
                decision_detail=build_decision_detail(case),
            )
    return {
        "ok": False,
        "error": "decision_detail_unavailable",
        "read_only": True,
        "customer_trading": False,
        "availability": "UNAVAILABLE",
    }


def default_member_decision_detail() -> dict[str, Any]:
    """Default detail binding: DEMO wait case (never LIVE)."""
    case = catalog()[0]
    return _envelope(
        surface="member_decision_detail_default",
        decision_detail=build_decision_detail(case),
    )


def service_meta() -> dict[str, Any]:
    return _envelope(
        surfaces=[
            "member_decision_detail_default",
            "member_decision_detail_feed",
            "member_decision_detail",
            "three_passes",
        ],
        field_ids=list(MEMBER_VISIBLE_FIELD_IDS),
        postures=list(AI_POSTURES),
        methods_allowed=["GET", "HEAD", "OPTIONS"],
        environment="local_staging",
        as_of_fixture=FIXTURE_AS_OF,
        member_may_see=list(MEMBER_VISIBLE_FIELD_IDS),
        member_must_not_see=[
            "private_raw_graph",
            "exact_proprietary_thresholds",
            "full_private_strategy_weights",
            "founder_entry_exit",
            "internal_prompts",
            "raw_cot",
            "account_data",
        ],
    )
