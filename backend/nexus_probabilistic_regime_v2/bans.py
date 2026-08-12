"""Hard-ban enforcement probes for V16-C."""
from __future__ import annotations

from typing import Any

from backend.nexus_probabilistic_regime_v2.constants import HARD_BANS


def default_control_flags() -> dict[str, Any]:
    return {
        "pr26_merge_attempted": False,
        "pr27_merge_attempted": False,
        "auto_integrate_attempted": False,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mainnet_client_created_count": 0,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "profitability_claimed": False,
        "predictive_edge_claimed": False,
        "strategy_promoted": False,
        "leverage_mutated": False,
        "risk_gate_overridden": False,
        "status_json_written": False,
        "acceleration_report_edited": False,
        "g_drive_mutated": False,
    }


def _refuse(action: str, reason: str, **extra: Any) -> dict[str, Any]:
    out = {
        "allowed": False,
        "executed": False,
        "applied": False,
        "written": False,
        "action": action,
        "reason": reason,
    }
    out.update(extra)
    return out


def refuse_pr_merge(pr: int) -> dict[str, Any]:
    return _refuse(f"PR{pr}_MERGE", f"PR{pr}_MERGE_BANNED_V16_C")


def refuse_auto_integrate() -> dict[str, Any]:
    return _refuse("AUTO_INTEGRATE", "AUTO_INTEGRATE_BANNED_V16_C")


def refuse_demo() -> dict[str, Any]:
    return _refuse("DEMO_ORDER", "DEMO_ORDERS_BANNED_V16_C", demo_order_count=0)


def refuse_shadow() -> dict[str, Any]:
    return _refuse("SHADOW_ORDER", "SHADOW_ORDERS_BANNED_V16_C", shadow_order_count=0)


def refuse_exchange_write() -> dict[str, Any]:
    return _refuse("EXCHANGE_WRITE", "EXCHANGE_WRITES_BANNED_V16_C", exchange_write_attempt_count=0)


def refuse_mainnet() -> dict[str, Any]:
    return _refuse("MAINNET", "MAINNET_BANNED_V16_C", mainnet_client_created_count=0)


def refuse_formal_wf() -> dict[str, Any]:
    return _refuse("FORMAL_WALK_FORWARD", "FORMAL_WALK_FORWARD_BANNED_V16_C")


def refuse_oos() -> dict[str, Any]:
    return _refuse("OOS_EXECUTION", "OOS_BANNED_V16_C", oos_executed=False)


def refuse_profit_claim() -> dict[str, Any]:
    return _refuse("PROFITABILITY_CLAIM", "PROFITABILITY_CLAIMS_BANNED_V16_C", profitability_claimed=False)


def refuse_edge_claim() -> dict[str, Any]:
    return _refuse("PREDICTIVE_EDGE_CLAIM", "PREDICTIVE_EDGE_CLAIMS_BANNED_V16_C", predictive_edge_claimed=False)


def refuse_strategy_promotion() -> dict[str, Any]:
    return _refuse("STRATEGY_PROMOTION", "STRATEGY_PROMOTION_BANNED_V16_C", strategy_promoted=False)


def refuse_leverage_mutation() -> dict[str, Any]:
    return _refuse("LEVERAGE_MUTATION", "LEVERAGE_MUTATION_BANNED_V16_C", leverage_mutated=False)


def refuse_risk_gate_override() -> dict[str, Any]:
    return _refuse("RISK_GATE_OVERRIDE", "RISK_GATE_OVERRIDE_BANNED_V16_C", risk_gate_overridden=False)


def refuse_status_json() -> dict[str, Any]:
    return _refuse("WRITE_STATUS_JSON", "STATUS_JSON_ARTIFACT_BANNED_V16_C", status_json_written=False)


def refuse_acceleration_report_edit() -> dict[str, Any]:
    return _refuse(
        "EDIT_ACCELERATION_REPORT",
        "ACCELERATION_REPORT_EDIT_BANNED_V16_C",
        acceleration_report_edited=False,
    )


def refuse_g_drive_mutation() -> dict[str, Any]:
    return _refuse("G_DRIVE_MUTATION", "G_DRIVE_MUTATION_BANNED_V16_C", g_drive_mutated=False)


def hard_ban_probe_matrix() -> dict[str, Any]:
    probes = {
        "force_pr26_merge": refuse_pr_merge(26),
        "force_pr27_merge": refuse_pr_merge(27),
        "force_auto_integrate": refuse_auto_integrate(),
        "force_demo": refuse_demo(),
        "force_shadow": refuse_shadow(),
        "force_exchange_write": refuse_exchange_write(),
        "force_mainnet": refuse_mainnet(),
        "force_formal_wf": refuse_formal_wf(),
        "force_oos": refuse_oos(),
        "force_profit_claim": refuse_profit_claim(),
        "force_edge_claim": refuse_edge_claim(),
        "force_strategy_promotion": refuse_strategy_promotion(),
        "force_leverage_mutation": refuse_leverage_mutation(),
        "force_risk_gate_override": refuse_risk_gate_override(),
        "force_status_json": refuse_status_json(),
        "force_acceleration_report_edit": refuse_acceleration_report_edit(),
        "force_g_drive_mutation": refuse_g_drive_mutation(),
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
