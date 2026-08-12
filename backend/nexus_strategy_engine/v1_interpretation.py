"""V1 execution reinterpretation — do not treat as component-distinct failures."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

V1_EXECUTION_INTERPRETATION = "GENERIC_FAMILY_EXECUTOR_RESULTS_NOT_COMPONENT_DISTINCT"


def build_v1_interpretation(*, v1_summary_path: Path) -> dict[str, Any]:
    summary = {}
    if v1_summary_path.is_file():
        summary = json.loads(v1_summary_path.read_text(encoding="utf-8"))
    return {
        "schema": "v1_execution_interpretation_v1",
        "V1_execution_interpretation": V1_EXECUTION_INTERPRETATION,
        "means": (
            "No promising mechanism was found by the current generic family-level "
            "executor over the loaded development datasets."
        ),
        "does_not_mean": [
            "all 16 registered components were independently tested",
            "all 12 hypotheses used distinct economic execution rules",
            "Funding/OI strategies were tested with actual Funding/OI",
            "all 99 eligible symbols were tested",
            "multi-timeframe conditions were fully tested",
        ],
        "preserved_v1_package": "artifacts/readiness/immutable/general_multi_strategy_engine_v1",
        "v1_recommendation_preserved": summary.get("recommendation"),
        "v1_executed_hypothesis_count": (summary.get("development") or {}).get("executed_hypothesis_count"),
        "overwrite_forbidden": True,
    }
