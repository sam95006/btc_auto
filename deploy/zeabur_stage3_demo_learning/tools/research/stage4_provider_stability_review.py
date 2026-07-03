"""Stage 4 provider stability and fallback-dependency review (read-only metrics)."""
from __future__ import annotations

from typing import Any, Dict, List


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_provider_stability_review(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze Groq/Cerebras yield and fallback dependency from a dry-run summary."""
    provider_success = summary.get("provider_success_distribution") or {}
    groq_success = _safe_int(provider_success.get("groq"))
    cerebras_success = _safe_int(provider_success.get("cerebras"))
    total_success = max(1, groq_success + cerebras_success)
    groq_share = round(groq_success / total_success, 4)
    cerebras_share = round(cerebras_success / total_success, 4)

    fallback_attempt = _safe_int(summary.get("fallback_attempt_count"))
    fallback_success = _safe_int(summary.get("fallback_success_count"))
    groq_cooldown_skip = _safe_int(summary.get("groq_cooldown_skip_count"))
    groq_429 = _safe_int(summary.get("groq_429_count"))
    chain_failed = _safe_int(summary.get("provider_chain_failed_count"))
    parse_errors = _safe_int(summary.get("parse_error_count"))
    cerebras_parse = _safe_int(summary.get("cerebras_parse_error_count"))
    effective = _safe_int(summary.get("effective_decision_count"))
    duration = _safe_float(summary.get("duration_minutes"), 180.0)

    risks: List[str] = []
    if cerebras_share >= 0.65:
        risks.append("high_cerebras_dependency")
    if groq_cooldown_skip >= 50:
        risks.append("groq_tpm_governor_heavy_skip")
    if groq_share < 0.20 and effective >= 30:
        risks.append("groq_primary_yield_low")
    if chain_failed > max(6, int(duration / 30)):
        risks.append("provider_chain_failed_elevated")
    if parse_errors > 0 or cerebras_parse > 0:
        risks.append("parse_errors_present")

    # If Cerebras unavailable: Groq alone yielded groq_success; skipped ticks reduce ceiling.
    skipped = _safe_int(summary.get("skipped_tick_count"))
    groq_only_ceiling_estimate = groq_success + max(0, effective - groq_success - cerebras_success)
    cerebras_failure_impact_pct = round(
        (cerebras_success / max(1, effective)) * 100.0,
        2,
    )

    dependency_risk = "low"
    if cerebras_share >= 0.75 or "high_cerebras_dependency" in risks:
        dependency_risk = "high"
    elif cerebras_share >= 0.55:
        dependency_risk = "medium"

    # Minimum Groq successes per 180m session before 6h is comfortable (observed 34 at 180m).
    provider_success_minimum_by_session = {
        "groq_minimum_recommended": max(20, int(34 * (duration / 180.0) * 0.5)),
        "cerebras_minimum_recommended": max(40, int(80 * (duration / 180.0) * 0.5)),
        "effective_minimum_recommended": max(90, int(120 * (duration / 180.0) * 0.75)),
    }

    needs_budget_guard = cerebras_share >= 0.60 or groq_cooldown_skip >= 40
    readiness_for_longer_run = (
        parse_errors == 0
        and cerebras_parse == 0
        and chain_failed <= max(24, int(24 * (duration / 180.0)))
        and effective >= int(120 * (duration / 180.0) * 0.9)
    )

    return {
        "record_type": "stage4_provider_stability_review",
        "provider_success_distribution": dict(provider_success),
        "groq_success_count": groq_success,
        "cerebras_success_count": cerebras_success,
        "groq_share": groq_share,
        "cerebras_share": cerebras_share,
        "fallback_attempt_count": fallback_attempt,
        "fallback_success_count": fallback_success,
        "groq_cooldown_skip_count": groq_cooldown_skip,
        "groq_429_count": groq_429,
        "provider_chain_failed_count": chain_failed,
        "skipped_tick_count": skipped,
        "cerebras_failure_impact_pct": cerebras_failure_impact_pct,
        "groq_only_ceiling_estimate": groq_only_ceiling_estimate,
        "fallback_dependency_risk": dependency_risk,
        "stability_risks": risks,
        "needs_provider_budget_guard": needs_budget_guard,
        "provider_success_minimum_by_session": provider_success_minimum_by_session,
        "readiness_for_longer_run": readiness_for_longer_run,
        "groq_rate_gate_conservative": groq_cooldown_skip >= 40,
        "cerebras_outage_would_degrade": cerebras_share >= 0.50,
    }


__all__ = ["build_provider_stability_review"]
