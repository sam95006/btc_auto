"""Composition root for Structural Geometry qualification + event-driven sim.

Depends on structural_geometry_qualify and geometry_event_sim (one-way).
Keeps those two modules free of a mutual import cycle.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.geometry_contracts import CandidateEvidence
from backend.nexus_demo_execution.geometry_event_sim import run_event_driven_folds
from backend.nexus_demo_execution.risk_review_packet import build_risk_review_packet
from backend.nexus_demo_execution.session_limits import (
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
)
from backend.nexus_demo_execution.structural_geometry_qualify import (
    compare_ab,
    stage_metrics,
    synthesize_structure_candidates,
)


def run_qualification_pipeline(candidates: list[CandidateEvidence] | None = None) -> dict[str, Any]:
    """Chronological non-overlapping splits + event-driven sim. Never auto-arms live policy."""
    cands = candidates if candidates is not None else synthesize_structure_candidates(2407)
    ordered = sorted(cands, key=lambda c: float(c.ts or 0.0))
    n = len(ordered)
    i1 = int(n * 0.50)
    i2 = int(n * 0.75)
    replay_set = ordered[:i1]
    wf_set = ordered[i1:i2]
    oos_set = ordered[i2:]

    ab_all = compare_ab(ordered)
    ab_summary = {k: v for k, v in ab_all.items() if k != "rows"}

    replay_rows = compare_ab(replay_set)["rows"]
    wf_rows = compare_ab(wf_set)["rows"]
    oos_rows = compare_ab(oos_set)["rows"]

    event = run_event_driven_folds(ordered)
    wf_sim = event["walk_forward"]
    oos_sim = event["oos"]

    wf_stage = stage_metrics("WALK_FORWARD_VALIDATED", wf_rows, time_range="t50%..t75%")
    wf_stage.update(
        {
            "trade_simulation_count": wf_sim.get("simulated_trade_count"),
            "entry_triggered_count": wf_sim.get("entry_triggered_count"),
            "gross_pnl": wf_sim.get("gross_pnl"),
            "fees": wf_sim.get("fees"),
            "slippage": wf_sim.get("slippage_cost"),
            "funding": wf_sim.get("funding"),
            "net_pnl": wf_sim.get("net_pnl"),
            "profit_factor": wf_sim.get("profit_factor"),
            "maximum_drawdown": wf_sim.get("maximum_drawdown"),
            "win_rate": wf_sim.get("win_rate"),
            "expectancy": wf_sim.get("expectancy"),
            "intrabar_resolution_method": wf_sim.get("intrabar_resolution_method"),
            "look_ahead_contamination": wf_sim.get("look_ahead_contamination"),
            "status": wf_sim.get("walk_forward_status") or wf_stage["status"],
            "process_labels": {
                k: wf_sim.get(k)
                for k in (
                    "GOOD_PROCESS_WIN",
                    "GOOD_PROCESS_LOSS",
                    "BAD_PROCESS_WIN",
                    "BAD_PROCESS_LOSS",
                )
            },
        }
    )
    if (wf_stage.get("trade_simulation_count") or 0) > 0:
        wf_stage["calibration"] = "EVENT_DRIVEN_SYNTHETIC_PATH"

    oos_stage = stage_metrics("OOS_VALIDATED", oos_rows, time_range="t75%..t100%")
    oos_status = event.get("oos_status") or "OOS_FRAMEWORK_VALIDATED"
    # Never allow legacy OOS_VALIDATED; synthetic paths cannot become PERFORMANCE_VALIDATED.
    if (oos_sim.get("simulated_trade_count") or 0) == 0 or oos_sim.get("net_pnl") is None:
        oos_status = "OOS_FRAMEWORK_VALIDATED"
    if oos_sim.get("path_source") == "SYNTHETIC_FORCED" and oos_status == "OOS_PERFORMANCE_VALIDATED":
        oos_status = "OOS_FRAMEWORK_VALIDATED"
    oos_stage.update(
        {
            "trade_simulation_count": oos_sim.get("simulated_trade_count"),
            "entry_triggered_count": oos_sim.get("entry_triggered_count"),
            "gross_pnl": oos_sim.get("gross_pnl"),
            "fees": oos_sim.get("fees"),
            "total_fees": oos_sim.get("fees"),
            "slippage": oos_sim.get("slippage_cost"),
            "funding": oos_sim.get("funding"),
            "net_pnl": oos_sim.get("net_pnl"),
            "profit_factor": oos_sim.get("profit_factor"),
            "maximum_drawdown": oos_sim.get("maximum_drawdown"),
            "win_rate": oos_sim.get("win_rate"),
            "expectancy": oos_sim.get("expectancy"),
            "intrabar_resolution_method": oos_sim.get("intrabar_resolution_method"),
            "look_ahead_contamination": oos_sim.get("look_ahead_contamination"),
            "oos_status": oos_status,
            "status": oos_status,
            "process_labels": {
                k: oos_sim.get(k)
                for k in (
                    "GOOD_PROCESS_WIN",
                    "GOOD_PROCESS_LOSS",
                    "BAD_PROCESS_WIN",
                    "BAD_PROCESS_LOSS",
                )
            },
        }
    )
    if (oos_stage.get("trade_simulation_count") or 0) > 0:
        oos_stage["calibration"] = "EVENT_DRIVEN_SYNTHETIC_PATH"

    risk_packet = build_risk_review_packet(
        walk_forward=wf_sim,
        oos={**oos_sim, "oos_status": oos_status},
        diagnostic_ab=ab_summary,
    )

    stages = {
        "REPLAY_VALIDATED": stage_metrics("REPLAY_VALIDATED", replay_rows, time_range="t0..t50%"),
        "WALK_FORWARD_VALIDATED": wf_stage,
        "OOS_VALIDATED": oos_stage,
        "RISK_REVIEWED": {
            "stage": "RISK_REVIEWED",
            "status": "RISK_REVIEW_PENDING_FOUNDER",
            "floors_unchanged": True,
            "min_net_rr": MIN_NET_REWARD_RISK_RATIO,
            "min_reward_to_cost": MIN_NET_REWARD_TO_COST,
            "no_threshold_tuning_between_folds": True,
            "look_ahead_contamination": bool(oos_sim.get("look_ahead_contamination")),
            "packet_ready": risk_packet.get("packet_ready"),
        },
        "SHADOW_APPLIED": {
            "stage": "SHADOW_APPLIED",
            "status": "NOT_APPLIED",
            "note": "Shadow must not be classified as live; requires Founder arm after risk review.",
            "shadow_equals_live": False,
        },
    }

    qualification_complete = False  # requires Founder RISK_REVIEWED + SHADOW_APPLIED

    if (
        risk_packet.get("packet_ready")
        and oos_status == "OOS_PERFORMANCE_VALIDATED"
        and not oos_sim.get("look_ahead_contamination")
    ):
        recommendation = "NEXUS_RISK_REVIEW_READY"
    else:
        recommendation = "NEXUS_GEOMETRY_QUALIFICATION_IN_PROGRESS"

    return {
        "fixed_geometry_retired_from_qualification": True,
        "active_execution_policy_unchanged": True,
        "diagnostic_ab": ab_summary,
        "event_driven": {
            "oos_status": oos_status,
            "walk_forward_status": event.get("walk_forward_status"),
            "intrabar_resolution_method": event.get("intrabar_resolution_method"),
            "folds": {
                "oos_fold2": event.get("oos_fold2"),
                "oos_fold3": event.get("oos_fold3"),
            },
        },
        "stages": stages,
        "risk_review_packet": risk_packet,
        "qualification_complete": qualification_complete,
        "recommendation": recommendation,
    }
