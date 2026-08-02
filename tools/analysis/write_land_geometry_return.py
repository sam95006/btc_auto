#!/usr/bin/env python3
"""Write Founder §16 return for post-12H land + geometry qualification wave."""
from __future__ import annotations

import json
from pathlib import Path

from backend.nexus_demo_execution.structural_geometry_qualify import (
    run_qualification_pipeline,
    synthesize_structure_candidates,
)

OUT = Path("docs/04_readiness")
OUT.mkdir(parents=True, exist_ok=True)
geom = run_qualification_pipeline(synthesize_structure_candidates(2407))
ab = geom.get("diagnostic_ab") or {}
stages = geom.get("stages") or {}

ret = {
    "post_forensic_commit": "4bc0bb8aebeb5f71a607bbfb7bec3bf5fcf5ce17",
    "pr_head": "4bc0bb8aebeb5f71a607bbfb7bec3bf5fcf5ce17",
    "push_status": "SUCCESS",
    "force_push": False,
    "ci_run": "https://github.com/sam95006/btc_auto/actions/runs/30738866697",
    "ci_status": "PASS",
    "failed_tests": 0,
    "secret_leak_count": 0,
    "deploy_run": "https://github.com/sam95006/btc_auto/actions/runs/30738943964",
    "deployment_commit": "824817d5bd86d0abd6ae9b34cd9369788bbc5947",
    "health_t0": 200,
    "health_t60": "NOT_REMEASURED_AFTER_ROUTE_LIVE",
    "health_t180": "NOT_REMEASURED_AFTER_ROUTE_LIVE",
    "forensic_routes_live": True,
    "account_state": "ACCOUNT_CONFIRMED_FLAT",
    "reconciliation": "MATCH",
    "wallet_delta_classification": "UNKNOWN",
    "wallet_delta_attributed": 0.0,
    "wallet_delta_unattributed": -0.97052039,
    "wallet_delta_note": "Pre-session Same-Router Probe closedPnl/fees visible with NEXUS-PROBE-* ids before 12H start; no in-window ledger rows explain the intra-session -0.97052039. available≠wallet semantic gap observed. Do not attribute to 12H.",
    "fixed_geometry_replay": {
        "pass_rate": ab.get("fixed_geometry_pass_rate"),
        "pass_count": ab.get("fixed_pass_count"),
    },
    "structural_geometry_replay": {
        "pass_rate": ab.get("structural_geometry_pass_rate"),
        "pass_count": ab.get("structural_pass_count"),
        "complete": ab.get("structural_geometry_complete"),
        "missing": ab.get("structural_geometry_missing"),
        "invalid": ab.get("structural_geometry_invalid"),
        "diagnostic_only": True,
        "oos_claim_forbidden": True,
    },
    "walk_forward_result": stages.get("WALK_FORWARD_VALIDATED"),
    "oos_result": stages.get("OOS_VALIDATED"),
    "risk_review_result": stages.get("RISK_REVIEWED"),
    "shadow_result": stages.get("SHADOW_APPLIED"),
    "instrument_qty_patch_verified": True,
    "qualification_complete": False,
    "recommendation": "NEXUS_GEOMETRY_QUALIFICATION_IN_PROGRESS",
    "safety_freeze": {
        "no_new_6h": True,
        "no_new_12h": True,
        "no_24h": True,
        "no_mainnet": True,
        "no_real_money": True,
        "no_autonomous_canary": True,
        "session_write_window_open": False,
        "effective_demo_write_authorized": False,
        "global_exchange_write_enabled": False,
        "24H_GATE_APPROVED": False,
    },
}

(OUT / "NEXUS_POST_12H_LAND_AND_GEOMETRY_RETURN.json").write_text(json.dumps(ret, indent=2) + "\n", encoding="utf-8")
md = [
    "# NEXUS Post-12H Land + Geometry Qualification Return",
    "",
    f"- recommendation: `{ret['recommendation']}`",
    f"- post_forensic_commit / pr_head: `{ret['pr_head']}`",
    f"- ci_status: `{ret['ci_status']}` · {ret['ci_run']}",
    f"- deployment_commit (live): `{ret['deployment_commit']}`",
    f"- forensic_routes_live: `{ret['forensic_routes_live']}`",
    f"- account_state: `{ret['account_state']}` · reconciliation: `{ret['reconciliation']}`",
    f"- wallet_delta_unattributed: `{ret['wallet_delta_unattributed']}` ({ret['wallet_delta_classification']})",
    f"- fixed_geometry_pass_rate: `{ab.get('fixed_geometry_pass_rate')}`",
    f"- structural_geometry_pass_rate: `{ab.get('structural_geometry_pass_rate')}` (diagnostic only)",
    f"- RISK/SHADOW: pending Founder sign-off — qualification_complete=false",
    "",
    "Do not start another autonomous session.",
    "",
]
(OUT / "NEXUS_POST_12H_LAND_AND_GEOMETRY_RETURN.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print(json.dumps(ret, indent=2))
