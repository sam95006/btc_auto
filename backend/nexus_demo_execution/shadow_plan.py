"""Read-only Shadow execution plan — never applied by this module."""
from __future__ import annotations

from typing import Any


def build_shadow_plan() -> dict[str, Any]:
    return {
        "shadow_plan_ready": True,
        "shadow_status": "NOT_APPLIED",
        "shadow_equals_live": False,
        "shadow_equals_demo_execution": False,
        "constraints": {
            "read_only": True,
            "bybit_order": False,
            "demo_position": False,
            "write_window": False,
            "exchange_write": False,
        },
        "pipeline": [
            "Universe",
            "Regime",
            "Strategy",
            "Geometry",
            "Cost Gate",
            "Risk Critic",
            "Intent",
            "Protection",
            "Exit",
            "Outcome",
        ],
        "labeling": {
            "forbidden_labels": ["Live", "Demo Execution", "Live Execution"],
            "required_label": "SHADOW_SIMULATION_ONLY",
        },
        "activation_requires": [
            "Founder RISK_REVIEWED sign-off",
            "oos_status=OOS_PERFORMANCE_VALIDATED",
            "synthetic_forced_trade_count=0",
            "look_ahead_contamination=false",
        ],
        "note": "Plan only — do not apply Shadow in this qualification wave.",
    }
