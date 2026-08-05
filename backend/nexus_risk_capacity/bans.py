"""Hard-ban enforcement probes for V15-H Risk and Capacity Review."""
from __future__ import annotations

from typing import Any

from backend.nexus_risk_capacity.ai_gate import (
    refuse_ai_override,
    refuse_strategy_promotion,
    refuse_strategy_selection,
)
from backend.nexus_risk_capacity.constants import HARD_BANS


def default_control_flags() -> dict[str, Any]:
    return {
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "strategy_selected": False,
        "strategy_promoted": False,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mainnet_client_created_count": 0,
        "profitability_claimed": False,
        "qualified_claimed": False,
        "pr27_merge_attempted": False,
        "auto_integrate_attempted": False,
        "canonical_cost_formula_mutated": False,
        "ai_override_applied": False,
        "qualification_ready_count": 0,
        "status_json_written": False,
    }


def refuse_formal_walk_forward(candidate_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "FORMAL_WALK_FORWARD",
        "candidate_id": candidate_id,
        "reason": "FORMAL_WALK_FORWARD_BANNED_V15_H",
    }


def refuse_oos(*, kind: str = "OOS_CONSUMPTION", candidate_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": kind,
        "candidate_id": candidate_id,
        "reason": "OOS_BANNED_V15_H",
        "oos_executed": False,
        "oos_consumed": False,
    }


def refuse_demo(candidate_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "DEMO_ORDER",
        "candidate_id": candidate_id,
        "reason": "DEMO_ORDERS_BANNED_V15_H",
        "demo_order_count": 0,
    }


def refuse_qualify(candidate_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "qualified": False,
        "action": "QUALIFY",
        "candidate_id": candidate_id,
        "reason": "QUALIFIED_OUTPUT_BANNED_V15_H",
    }


def refuse_auto_integrate() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "AUTO_INTEGRATE",
        "reason": "AUTO_INTEGRATE_BANNED_V15_H",
        "auto_integrate_attempted": False,
    }


def refuse_exchange_write() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "EXCHANGE_WRITE",
        "reason": "EXCHANGE_WRITES_BANNED_V15_H",
        "exchange_write_attempt_count": 0,
    }


def refuse_status_json() -> dict[str, Any]:
    return {
        "allowed": False,
        "written": False,
        "action": "WRITE_STATUS_JSON",
        "reason": "STATUS_JSON_ARTIFACT_BANNED_V15_H",
        "status_json_written": False,
    }


def hard_ban_probe_matrix(candidate_id: str = "SYN_V15H_PROBE") -> dict[str, Any]:
    probes = {
        "force_walk_forward": refuse_formal_walk_forward(candidate_id),
        "force_oos_consume": refuse_oos(kind="OOS_CONSUMPTION", candidate_id=candidate_id),
        "force_select": refuse_strategy_selection(candidate_id),
        "force_promote": refuse_strategy_promotion(candidate_id),
        "force_demo": refuse_demo(candidate_id),
        "force_qualify": refuse_qualify(candidate_id),
        "force_auto_integrate": refuse_auto_integrate(),
        "force_exchange_write": refuse_exchange_write(),
        "force_ai_override": refuse_ai_override(
            candidate_id=candidate_id, attempted_fields=["label", "net_expectancy"]
        ),
        "force_status_json": refuse_status_json(),
    }
    all_refused = all(
        (not p.get("allowed"))
        and (not p.get("executed", False))
        and (not p.get("applied", False))
        and (not p.get("written", False))
        for p in probes.values()
    )
    return {
        "probes": probes,
        "all_refused": all_refused,
        "hard_bans": sorted(HARD_BANS),
        "flags": default_control_flags(),
    }
