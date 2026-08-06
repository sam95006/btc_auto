"""Private-core → public-safe projection (allow-list only)."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.nexus_private_to_public_projection_v3.allowlist import (
    ForbiddenPayloadKeyError,
    assert_allowlisted_only,
    count_execution_controls,
    serialize_allowlist,
)
from backend.nexus_private_to_public_projection_v3.constants import (
    AI_PUBLIC_SUGGESTIONS,
    CASE_COUNT_BANDS,
    DATA_TRUST_STATUSES,
    OVERLAP_BANDS,
    PERFORMANCE_BANDS,
    QUANTIZATION_STEP,
    RISK_CATEGORIES,
    SCHEMA_VERSION,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _quantize(value: float, step: float = QUANTIZATION_STEP) -> float:
    """Coarse quantization — prevents exact private threshold recovery."""
    if step <= 0:
        return float(value)
    return round(round(float(value) / step) * step, 10)


def _band_performance(raw: Any) -> str:
    if raw is None:
        return "UNAVAILABLE"
    if isinstance(raw, str):
        up = raw.strip().upper()
        return up if up in PERFORMANCE_BANDS else "UNAVAILABLE"
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return "UNAVAILABLE"
    if val < -0.02:
        return "NEGATIVE"
    if val > 0.02:
        return "POSITIVE"
    return "FLAT"


def _band_case_count(raw: Any) -> str:
    if raw is None:
        return "UNAVAILABLE"
    if isinstance(raw, str):
        up = raw.strip().upper()
        return up if up in CASE_COUNT_BANDS else "UNAVAILABLE"
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return "UNAVAILABLE"
    if n <= 0:
        return "NONE"
    if n < 3:
        return "LOW"
    if n < 10:
        return "MEDIUM"
    return "HIGH"


def _normalize_suggestion(raw: Any) -> str:
    if raw is None:
        return "UNAVAILABLE"
    up = str(raw).strip().upper()
    # Map legacy public intelligence labels into PUB17 surface.
    mapping = {
        "RECOMMEND": "LONG",
        "HOLD": "WAIT",
        "LONG": "LONG",
        "SHORT": "SHORT",
        "WAIT": "WAIT",
        "ABSTAIN": "ABSTAIN",
        "UNAVAILABLE": "UNAVAILABLE",
    }
    return mapping.get(up, "UNAVAILABLE" if up not in AI_PUBLIC_SUGGESTIONS else up)


def _normalize_risk(raw: Any) -> str:
    if raw is None:
        return "UNAVAILABLE"
    up = str(raw).strip().upper()
    return up if up in RISK_CATEGORIES else "UNAVAILABLE"


def _normalize_trust(raw: Any) -> str:
    if raw is None:
        return "UNAVAILABLE"
    up = str(raw).strip().upper()
    return up if up in DATA_TRUST_STATUSES else "UNAVAILABLE"


def _public_similarity(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "overlap_band": "UNAVAILABLE",
            "case_count_band": "UNAVAILABLE",
            "status": "AGGREGATED",
            "message": "historical_similarity_aggregate_only",
        }
    overlap = str(raw.get("overlap_band") or raw.get("similar_case_overlap_band") or "UNAVAILABLE")
    overlap = overlap.upper() if overlap.upper() in OVERLAP_BANDS else "UNAVAILABLE"
    count_band = _band_case_count(
        raw.get("case_count_band", raw.get("similar_case_count", raw.get("count")))
    )
    return {
        "overlap_band": overlap,
        "case_count_band": count_band,
        "status": "AGGREGATED",
        "message": "historical_similarity_aggregate_only",
    }


def _public_performance(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        band = _band_performance(raw.get("performance_band", raw.get("value", raw.get("return"))))
        window = str(raw.get("window_label") or "DELAYED_AGGREGATE")
    else:
        band = _band_performance(raw)
        window = "DELAYED_AGGREGATE"
    return {
        "performance_band": band,
        "window_label": window,
        "status": "DELAYED_AGGREGATED",
        "message": "exact_returns_suppressed",
    }


def extract_public_seed(private_core: dict[str, Any]) -> dict[str, Any]:
    """Pull allow-listed public fields from a private core blob.

    Private thresholds / ledger / credentials / lesson text / raw graph nodes
    are never copied — only coarse public summaries.
    """
    pub = private_core.get("public") if isinstance(private_core.get("public"), dict) else {}
    # Prefer nested public section; fall back to top-level allow-listed keys only.
    seed: dict[str, Any] = {}

    def pick(*keys: str) -> Any:
        for k in keys:
            if k in pub and pub[k] is not None:
                return pub[k]
            if k in private_core and private_core[k] is not None:
                return private_core[k]
        return None

    seed["market_state"] = pick("market_state") or "UNAVAILABLE"
    seed["regime_summary"] = pick("regime_summary") or "UNAVAILABLE"
    seed["ai_public_suggestion"] = _normalize_suggestion(
        pick("ai_public_suggestion", "ai_recommendation_state")
    )
    seed["risk_category"] = _normalize_risk(pick("risk_category"))
    seed["evidence_summary"] = pick("evidence_summary") or "UNAVAILABLE"
    seed["counter_evidence_summary"] = pick(
        "counter_evidence_summary", "contradicting_evidence_summary"
    ) or "UNAVAILABLE"
    seed["abstention_reason"] = pick("abstention_reason")
    seed["data_trust"] = _normalize_trust(pick("data_trust", "trust_status"))
    seed["historical_similarity_aggregate"] = _public_similarity(
        pick("historical_similarity_aggregate", "similar_case_summary")
    )
    seed["delayed_aggregated_performance"] = _public_performance(
        pick("delayed_aggregated_performance", "performance_aggregate")
    )
    seed["symbol"] = pick("symbol") or "BTCUSDT"
    return seed


def project_private_to_public(
    private_core: dict[str, Any] | None,
    *,
    environment: str = "STAGING",
    query_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project private core → public DTO via allow-list only.

    ``query_context`` is accepted for multi-query redteam compatibility but
    MUST NOT re-introduce private thresholds into the public surface. Signal
    probes are quantized and never compared against private thresholds here.
    """
    _ = query_context  # intentionally unused for threshold math
    now = utc_now_iso()
    if not isinstance(private_core, dict):
        out = {
            "schema_version": SCHEMA_VERSION,
            "published_at": now,
            "as_of": now,
            "retrieved_at": now,
            "availability": "UNAVAILABLE",
            "environment": environment,
            "lineage_id": str(uuid4()),
            "data_class": "PUBLIC_SAFE",
            "symbol": "UNAVAILABLE",
            "market_state": "UNAVAILABLE",
            "regime_summary": "UNAVAILABLE",
            "ai_public_suggestion": "UNAVAILABLE",
            "risk_category": "UNAVAILABLE",
            "evidence_summary": "UNAVAILABLE",
            "counter_evidence_summary": "UNAVAILABLE",
            "abstention_reason": "private_core_unavailable",
            "data_trust": "UNAVAILABLE",
            "historical_similarity_aggregate": _public_similarity(None),
            "delayed_aggregated_performance": _public_performance(None),
            "member_execution_control_count": 0,
            "private_fields_included": False,
            "raw_memory_graph": False,
            "private_core_import_count": 0,
            "inference_survivors": 0,
        }
        filtered = serialize_allowlist(out)
        assert_allowlisted_only(filtered)
        return filtered

    seed = extract_public_seed(private_core)
    # If query_context provides a public market signal, only emit quantized
    # non-threshold metadata — never binary-search against private thresholds.
    if isinstance(query_context, dict) and "signal" in query_context:
        try:
            _ = _quantize(float(query_context["signal"]))
        except (TypeError, ValueError):
            pass

    out = {
        "schema_version": SCHEMA_VERSION,
        "published_at": now,
        "as_of": private_core.get("as_of") or now,
        "retrieved_at": now,
        "availability": "AVAILABLE",
        "environment": environment,
        "lineage_id": str(private_core.get("lineage_id") or uuid4()),
        "data_class": "PUBLIC_SAFE",
        **seed,
        "member_execution_control_count": 0,
        "private_fields_included": False,
        "raw_memory_graph": False,
        "private_core_import_count": 0,
        "inference_survivors": 0,
    }
    filtered = serialize_allowlist(out)
    assert_allowlisted_only(filtered)
    exec_count = count_execution_controls(filtered)
    if exec_count != 0:
        raise ForbiddenPayloadKeyError(f"member_execution_control_count:{exec_count}")
    filtered["member_execution_control_count"] = 0
    # Second pass: ensure no banned keys survived via nested aliases.
    assert_allowlisted_only(filtered)
    return deepcopy(filtered)


REQUIRED_PUBLIC_KEYS: tuple[str, ...] = (
    "schema_version",
    "market_state",
    "regime_summary",
    "ai_public_suggestion",
    "risk_category",
    "evidence_summary",
    "counter_evidence_summary",
    "abstention_reason",
    "data_trust",
    "historical_similarity_aggregate",
    "delayed_aggregated_performance",
    "member_execution_control_count",
    "private_fields_included",
    "raw_memory_graph",
)
