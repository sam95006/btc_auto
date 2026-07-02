"""Stage 4 parse-error classification and summary metrics."""
from __future__ import annotations

from typing import Any, Dict, List

STANDARD_PARSE_ERROR_TYPES = frozenset(
    {
        "provider_response_truncated",
        "provider_invalid_json",
        "provider_empty_response",
        "provider_schema_mismatch",
    }
)


def normalize_parse_error_type(
    raw: str | None,
    *,
    finish_reason: str | None = None,
) -> str:
    err = str(raw or "").strip().lower()
    finish = str(finish_reason or "").strip().lower()
    if finish == "length" or err == "provider_response_truncated":
        return "provider_response_truncated"
    if err in {"content_empty", "empty_llm_response", "provider_empty_response"}:
        return "provider_empty_response"
    if err in {"json_decode_error", "json_not_object", "json_parse_failed", "llm_parse_failed"}:
        return "provider_invalid_json"
    if err in {"parse_error", "schema_mismatch", "provider_schema_mismatch"}:
        return "provider_schema_mismatch"
    if err in STANDARD_PARSE_ERROR_TYPES:
        return err
    return err or "provider_invalid_json"


def build_parse_error_summary(
    decisions: List[Dict[str, Any]],
    *,
    max_samples: int = 8,
) -> Dict[str, Any]:
    by_symbol: Dict[str, int] = {}
    by_provider: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    samples: List[Dict[str, Any]] = []
    total = 0

    for index, decision in enumerate(decisions):
        if not decision.get("parse_error"):
            continue
        total += 1
        sym = str(decision.get("symbol") or "?").upper()
        prov = str(decision.get("provider") or "unknown").lower()
        err = normalize_parse_error_type(
            str(decision.get("parse_error_type") or ""),
            finish_reason=str(decision.get("finish_reason") or ""),
        )
        by_symbol[sym] = int(by_symbol.get(sym) or 0) + 1
        by_provider[prov] = int(by_provider.get(prov) or 0) + 1
        by_type[err] = int(by_type.get(err) or 0) + 1
        if len(samples) < max_samples:
            samples.append(
                {
                    "line_index": index + 1,
                    "decision_id": decision.get("decision_id"),
                    "symbol": sym,
                    "provider": prov,
                    "parse_error_type": err,
                }
            )

    return {
        "parse_error_count": total,
        "parse_error_count_by_symbol": by_symbol,
        "parse_error_count_by_provider": by_provider,
        "parse_error_count_by_type": by_type,
        "parse_error_sample_refs": samples,
    }


def effective_decision(decision: Dict[str, Any]) -> bool:
    """True when decision counts toward effective yield (no parse/mock/context skip)."""
    if decision.get("market_context_unavailable"):
        return False
    if decision.get("parse_error"):
        return False
    if decision.get("is_mock_ai"):
        return False
    return bool(decision.get("real_llm_used"))


__all__ = [
    "STANDARD_PARSE_ERROR_TYPES",
    "build_parse_error_summary",
    "effective_decision",
    "normalize_parse_error_type",
]
