"""Aggregate Stage 4 provider attempt metrics from decisions and system events."""
from __future__ import annotations

from typing import Any, Dict, List

_GROQ_ERRORS_401 = frozenset({"http_unauthorized", "http_forbidden"})
_GROQ_ERRORS_429 = frozenset({"rate_limit", "provider_http_429", "provider_rate_limited"})
_GROQ_ERRORS_EMPTY = frozenset({"content_empty", "empty_llm_response", "provider_quota_exhausted"})
_CEREBRAS_ERRORS_429 = frozenset({"rate_limit", "provider_http_429", "provider_rate_limited"})
_CEREBRAS_ERRORS_404 = frozenset({"http_not_found", "model_not_found"})


def empty_provider_attempt_metrics() -> Dict[str, Any]:
    return {
        "groq_attempt_count": 0,
        "groq_success_count": 0,
        "groq_401_count": 0,
        "groq_429_count": 0,
        "groq_empty_count": 0,
        "cerebras_attempt_count": 0,
        "cerebras_success_count": 0,
        "cerebras_429_count": 0,
        "cerebras_404_count": 0,
        "cerebras_empty_count": 0,
        "cerebras_parse_error_count": 0,
        "fallback_attempt_count": 0,
        "fallback_success_count": 0,
        "provider_chain_failed_count": 0,
        "provider_capacity_ok": False,
    }


def _classify_attempt(provider: str, attempt: Dict[str, Any], metrics: Dict[str, Any]) -> None:
    prov = str(attempt.get("provider") or "").lower()
    result = str(attempt.get("result") or "")
    err = str(attempt.get("error_type") or "")
    http = int(attempt.get("http_status") or 0)

    if prov == "groq":
        metrics["groq_attempt_count"] += 1
        if result == "success":
            metrics["groq_success_count"] += 1
        elif err in _GROQ_ERRORS_401 or http in {401, 403}:
            metrics["groq_401_count"] += 1
        elif err in _GROQ_ERRORS_429 or http == 429:
            metrics["groq_429_count"] += 1
        elif err in _GROQ_ERRORS_EMPTY:
            metrics["groq_empty_count"] += 1
    elif prov == "cerebras":
        metrics["cerebras_attempt_count"] += 1
        if result == "success":
            metrics["cerebras_success_count"] += 1
        elif err in _CEREBRAS_ERRORS_429 or http == 429:
            metrics["cerebras_429_count"] += 1
        elif err in _CEREBRAS_ERRORS_404 or http == 404:
            metrics["cerebras_404_count"] += 1
        elif err in _GROQ_ERRORS_EMPTY:
            metrics["cerebras_empty_count"] += 1
        elif err == "json_decode_error":
            metrics["cerebras_parse_error_count"] += 1


def aggregate_attempt_metrics_from_attempts(
    attempts_list: List[List[Dict[str, Any]]],
    *,
    chain_failed_count: int = 0,
    provider_capacity_ok: bool | None = None,
) -> Dict[str, Any]:
    metrics = empty_provider_attempt_metrics()
    metrics["provider_chain_failed_count"] = chain_failed_count
    saw_cerebras = False
    cerebras_success = False
    for attempts in attempts_list:
        if not attempts:
            continue
        groq_failed_fallback_eligible = False
        for attempt in attempts:
            _classify_attempt(str(attempt.get("provider") or ""), attempt, metrics)
            prov = str(attempt.get("provider") or "").lower()
            if prov == "cerebras":
                saw_cerebras = True
                if attempt.get("result") == "success":
                    cerebras_success = True
            if prov == "groq" and attempt.get("result") == "failed":
                err = str(attempt.get("error_type") or "")
                if err in _GROQ_ERRORS_429 | _GROQ_ERRORS_EMPTY | {"provider_circuit_breaker_open"}:
                    groq_failed_fallback_eligible = True
        if len(attempts) > 1 or (groq_failed_fallback_eligible and saw_cerebras):
            metrics["fallback_attempt_count"] += 1
        if cerebras_success and len(attempts) > 1:
            metrics["fallback_success_count"] += 1
    if provider_capacity_ok is None:
        metrics["provider_capacity_ok"] = bool(
            metrics["groq_success_count"] > 0 or metrics["cerebras_success_count"] > 0
        )
    else:
        metrics["provider_capacity_ok"] = provider_capacity_ok
    return metrics


def aggregate_attempt_metrics(
    *,
    decisions: List[Dict[str, Any]],
    system_events: List[Dict[str, Any]] | None = None,
    chain_failed_count: int = 0,
) -> Dict[str, Any]:
    attempts_list: List[List[Dict[str, Any]]] = []
    for d in decisions:
        attempts = d.get("provider_attempts")
        if attempts:
            attempts_list.append(list(attempts))
    events = system_events or []
    event_chain_failed = 0
    for ev in events:
        attempts = ev.get("provider_attempts")
        if attempts:
            attempts_list.append(list(attempts))
        if ev.get("event_type") == "provider_chain_failed":
            event_chain_failed += 1
    total_chain_failed = max(chain_failed_count, event_chain_failed)
    return aggregate_attempt_metrics_from_attempts(
        attempts_list,
        chain_failed_count=total_chain_failed,
    )
