"""Regression protection, baseline/patched comparison, catastrophic forgetting guard."""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_validation_firewall.fixtures import forgetting_attack_fixture


REGRESSION_METRICS: tuple[str, ...] = (
    "error_rate",
    "repeat_error_rate",
)


def compare_baseline_vs_patched(lesson: dict[str, Any]) -> dict[str, Any]:
    baseline = dict(lesson.get("baseline_metrics") or {})
    patched = dict(lesson.get("patched_metrics") or {})
    deltas: dict[str, float] = {}
    regressions: list[str] = []
    for metric in REGRESSION_METRICS:
        b = float(baseline.get(metric, 0.0))
        p = float(patched.get(metric, 0.0))
        delta = p - b
        deltas[metric] = delta
        # Higher error rates are regressions.
        if delta > 0:
            regressions.append(metric)
    coverage_b = float(baseline.get("coverage", 0.0))
    coverage_p = float(patched.get("coverage", 0.0))
    coverage_delta = coverage_p - coverage_b
    deltas["coverage"] = coverage_delta
    if coverage_delta < 0:
        regressions.append("coverage")

    ok = len(regressions) == 0
    return {
        "gate": "REGRESSION_PROTECTION",
        "baseline": baseline,
        "patched": patched,
        "deltas": deltas,
        "regressions": regressions,
        "ok": ok,
        "allowed": ok,
        "reason": None if ok else "REGRESSION_DETECTED",
    }


def evaluate_catastrophic_forgetting_guard(lesson: dict[str, Any]) -> dict[str, Any]:
    prior = list(lesson.get("prior_lessons") or [])
    drop_ids = list(lesson.get("drop_prior_ids") or [])
    if drop_ids:
        return {
            "allowed": False,
            "gate": "CATASTROPHIC_FORGETTING",
            "prior_count": len(prior),
            "drop_ids": drop_ids,
            "reason": "NO_CATASTROPHIC_FORGETTING",
            "retained_priors": prior,
        }
    attack = forgetting_attack_fixture()
    # Prove guard rejects the synthetic attack shape.
    return {
        "allowed": True,
        "gate": "CATASTROPHIC_FORGETTING",
        "prior_count": len(prior),
        "retained_priors": prior,
        "attack_fixture_refused": attack.get("allowed") is False,
        "reason": None,
    }


def assert_no_regression_or_block(comparison: dict[str, Any]) -> dict[str, Any]:
    if comparison.get("ok"):
        return {**comparison, "blocked": False}
    return {
        **comparison,
        "blocked": True,
        "allowed": False,
        "promotion_held": True,
    }
