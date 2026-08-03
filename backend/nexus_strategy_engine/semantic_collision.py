"""V1 result reinterpretation + semantic execution collision audit."""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

from backend.nexus_strategy_engine.strategy_spec import sha_obj

V1_EXECUTION_INTERPRETATION = "GENERIC_FAMILY_EXECUTOR_RESULTS_NOT_COMPONENT_DISTINCT"


def v1_interpretation_record(*, v1_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "v1_execution_interpretation_v1",
        "V1_EXECUTION_INTERPRETATION": V1_EXECUTION_INTERPRETATION,
        "means": (
            "No promising mechanism was found by the current generic family-level "
            "executor over the loaded development datasets."
        ),
        "does_not_mean": [
            "all_16_registered_components_were_independently_tested",
            "all_12_hypotheses_used_distinct_economic_execution_rules",
            "funding_oi_strategies_were_tested_with_actual_funding_oi",
            "all_99_eligible_symbols_were_tested",
            "multi_timeframe_conditions_were_fully_tested",
        ],
        "preserved_v1_package": "artifacts/readiness/immutable/general_multi_strategy_engine_v1",
        "v1_recommendation_preserved": v1_summary.get("recommendation"),
        "overwrite_forbidden": True,
    }


def _trade_keys(hyp: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for e in hyp.get("evidence_sample") or []:
        tid = e.get("trade_id")
        if tid:
            keys.add(str(tid).rsplit("_", 1)[0])  # strip trailing index when present
    # Fallback identity from aggregate metrics
    keys.add(
        sha_obj(
            {
                "completed": hyp.get("completed_trade_count"),
                "net_exp": hyp.get("net_expectancy"),
                "pf": hyp.get("profit_factor"),
                "entries": hyp.get("entry_count"),
                "candidates": hyp.get("candidate_count"),
            }
        )
    )
    return keys


def _metric_identity(hyp: dict[str, Any]) -> str:
    return sha_obj(
        {
            "completed_trade_count": hyp.get("completed_trade_count"),
            "net_expectancy": hyp.get("net_expectancy"),
            "profit_factor": hyp.get("profit_factor"),
            "adverse_profit_factor": hyp.get("adverse_profit_factor"),
            "gross_expectancy": hyp.get("gross_expectancy"),
            "win_rate": hyp.get("win_rate"),
            "candidate_count": hyp.get("candidate_count"),
            "entry_count": hyp.get("entry_count"),
        }
    )


def _exit_identity(hyp: dict[str, Any]) -> str:
    # V1 used universal 1.2 ATR / 2.0 ATR via family executor
    return "UNIVERSAL_ATR_1_2_2_0"


def audit_semantic_collisions(v1_dev: dict[str, Any]) -> dict[str, Any]:
    hyps = list(v1_dev.get("hypotheses") or [])
    pairs = list(combinations(hyps, 2))
    collisions = []
    exact_trade = 0
    exact_metric = 0
    for a, b in pairs:
        ma, mb = _metric_identity(a), _metric_identity(b)
        ta, tb = _trade_keys(a), _trade_keys(b)
        inter = len(ta & tb)
        union = len(ta | tb) or 1
        jaccard = inter / union
        metric_same = ma == mb
        exit_same = _exit_identity(a) == _exit_identity(b)
        fam_bucket = {a.get("strategy_family"), b.get("strategy_family")}
        known_bucket = (
            fam_bucket <= {"TREND", "MOMENTUM", "CROSS_SECTIONAL"}
            or fam_bucket <= {"BREAKOUT", "VOLATILITY", "VOLUME"}
            or fam_bucket <= {"MEAN_REVERSION", "REVERSAL"}
        )
        # V1 family dispatch: same completed/candidate/metrics implies collision
        collided = bool(
            metric_same
            or (jaccard >= 0.9 and exit_same)
            or (known_bucket and metric_same)
            or (
                a.get("completed_trade_count") == b.get("completed_trade_count")
                and a.get("net_expectancy") == b.get("net_expectancy")
                and a.get("profit_factor") == b.get("profit_factor")
                and a.get("completed_trade_count", 0) > 0
            )
        )
        if metric_same and a.get("completed_trade_count", 0) > 0:
            exact_metric += 1
        if jaccard >= 0.99 and a.get("completed_trade_count", 0) > 0:
            exact_trade += 1
        if collided:
            collisions.append(
                {
                    "flag": "SEMANTIC_EXECUTION_COLLISION",
                    "hypothesis_a": a.get("hypothesis_id"),
                    "hypothesis_b": b.get("hypothesis_id"),
                    "family_a": a.get("strategy_family"),
                    "family_b": b.get("strategy_family"),
                    "candidate_set_jaccard": None,  # V1 did not persist candidate sets
                    "completed_trade_set_jaccard": round(jaccard, 6),
                    "metric_identity_equal": metric_same,
                    "exit_rule_identity_equal": exit_same,
                    "known_family_bucket_collision": known_bucket and metric_same,
                }
            )
    return {
        "schema": "semantic_collision_audit_v1",
        "V1_EXECUTION_INTERPRETATION": V1_EXECUTION_INTERPRETATION,
        "hypothesis_count": len(hyps),
        "distinct_strategy_pair_count": len(pairs),
        "semantic_collision_pair_count": len(collisions),
        "exact_trade_set_collision_count": exact_trade,
        "exact_metric_collision_count": exact_metric,
        "collisions": collisions,
        "note": "Collided hypotheses must not be interpreted as independent evidence",
    }


def load_v1_dev_summary(root: Path) -> dict[str, Any]:
    path = (
        root
        / "artifacts"
        / "readiness"
        / "immutable"
        / "general_multi_strategy_engine_v1"
        / "development_research_summary.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))
