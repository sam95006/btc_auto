"""Stage 4 parse-error classification and summary metrics."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CANONICAL_PARSE_ERROR_TYPES = frozenset(
    {
        "provider_response_truncated",
        "provider_invalid_json",
        "provider_empty_response",
        "provider_schema_mismatch",
    }
)

_EMPTY_TYPES = frozenset(
    {
        "content_empty",
        "empty_llm_response",
        "provider_empty_response",
    }
)

_TRUNCATED_TYPES = frozenset(
    {
        "provider_response_truncated",
    }
)

_INVALID_JSON_TYPES = frozenset(
    {
        "json_decode_error",
        "json_not_object",
        "json_parse_failed",
        "llm_parse_failed",
        "invalid_json",
        "provider_invalid_json",
    }
)

_SCHEMA_MISMATCH_PREFIXES = (
    "missing_fields",
    "invalid_final_action",
    "invalid_candidate_side",
    "confidence_out_of_range",
    "provider_schema_mismatch",
)


def normalize_parse_error_type(
    raw: Optional[str],
    *,
    raw_content_empty: bool = False,
    finish_reason: Optional[str] = None,
) -> str:
    """Map provider/parser errors to canonical Stage 4 parse error classes."""
    if raw_content_empty:
        return "provider_empty_response"
    err = str(raw or "").strip().lower()
    if not err:
        if str(finish_reason or "").lower() == "length":
            return "provider_response_truncated"
        return "provider_invalid_json"
    if err in _EMPTY_TYPES:
        return "provider_empty_response"
    if err in _TRUNCATED_TYPES or str(finish_reason or "").lower() == "length":
        return "provider_response_truncated"
    if err in _INVALID_JSON_TYPES:
        return "provider_invalid_json"
    if err == "provider_schema_mismatch":
        return "provider_schema_mismatch"
    if any(err.startswith(prefix) for prefix in _SCHEMA_MISMATCH_PREFIXES):
        return "provider_schema_mismatch"
    if err in CANONICAL_PARSE_ERROR_TYPES:
        return err
    return "provider_invalid_json"


def _decision_provider(decision: Dict[str, Any]) -> str:
    provider = str(decision.get("provider") or "").strip().lower()
    if provider:
        return provider
    attempts = decision.get("provider_attempts") or []
    for attempt in reversed(attempts):
        if str(attempt.get("result") or "") == "ok":
            return str(attempt.get("provider") or "unknown").lower()
    if attempts:
        return str(attempts[-1].get("provider") or "unknown").lower()
    return "unknown"


def build_parse_error_summary(decisions: List[Dict[str, Any]], *, sample_limit: int = 5) -> Dict[str, Any]:
    """Aggregate parse-error metrics for dry-run summary and validator."""
    by_symbol: Dict[str, int] = {}
    by_provider: Dict[str, int] = {}
    samples: List[Dict[str, Any]] = []

    for index, decision in enumerate(decisions):
        if not decision.get("parse_error"):
            continue
        sym = str(decision.get("symbol") or "unknown").upper()
        provider = _decision_provider(decision)
        by_symbol[sym] = int(by_symbol.get(sym) or 0) + 1
        by_provider[provider] = int(by_provider.get(provider) or 0) + 1
        if len(samples) < sample_limit:
            samples.append(
                {
                    "decision_index": index,
                    "decision_id": decision.get("decision_id"),
                    "symbol": sym,
                    "provider": provider,
                    "parse_error_type": decision.get("parse_error_type"),
                    "parse_error_type_normalized": normalize_parse_error_type(
                        decision.get("parse_error_type"),
                        raw_content_empty=bool(decision.get("raw_content_empty")),
                    ),
                }
            )

    return {
        "parse_error_count": sum(by_symbol.values()),
        "parse_error_count_by_symbol": by_symbol,
        "parse_error_count_by_provider": by_provider,
        "parse_error_sample_refs": samples,
    }


__all__ = [
    "CANONICAL_PARSE_ERROR_TYPES",
    "build_parse_error_summary",
    "normalize_parse_error_type",
]
