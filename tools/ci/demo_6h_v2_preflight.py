#!/usr/bin/env python3
"""6H V2 preflight — GET-only against live Validation by default; never starts session."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from backend.nexus_demo_execution.v2_policy import (
    FEE_REVIEW_BY,
    FEE_VERSION,
    POLICY_VERSION,
    PRETRADE_ROUND_TRIP_FEE_RATE,
    RUNTIME_DEPLOYMENT_COMMIT_SOT,
    RUNTIME_DEPLOY_RUN_SOT,
    TAKER_FEE_RATE,
)

VALIDATION_URL = os.environ.get("DEMO_VAL_URL", "https://nexus-bybit-demo-val.zeabur.app").rstrip("/")


def _get(url: str) -> tuple[Any, Any]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=45) as resp:
            return json.loads(resp.read().decode()), int(resp.status)
    except urllib.error.HTTPError as exc:
        return {"error": True}, int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}, f"ERR:{type(exc).__name__}"


def run_preflight(*, base: str = VALIDATION_URL) -> dict[str, Any]:
    health, health_code = _get(f"{base}/health")
    fee, fee_code = _get(f"{base}/api/nexus/fee-policy")
    market, market_code = _get(f"{base}/api/nexus/market/status")
    account, acct_code = _get(f"{base}/api/nexus/demo-execution/account?fresh=true")
    overview_wrap, ov_code = _get(f"{base}/api/nexus/control-plane/overview")
    _, s3 = _get("https://nexus-stage3-bybit-demo-learning.zeabur.app/health")
    _, cp = _get("https://nexus-unified-control-plane.zeabur.app/health")

    problems: list[str] = []
    if health_code != 200:
        problems.append("health_not_200")
    if fee_code != 200 or (fee or {}).get("fee_rate_status") != "FEE_RATE_CONFIGURED_CONSERVATIVE":
        problems.append("fee_status")
    if (fee or {}).get("fee_source") != "FOUNDER_APPROVED_CONFIG":
        problems.append("fee_source")
    if abs(float((fee or {}).get("taker_fee_rate") or 0) - TAKER_FEE_RATE) > 1e-12:
        problems.append("taker_mismatch")
    if abs(float((fee or {}).get("pretrade_round_trip_fee_rate") or 0) - PRETRADE_ROUND_TRIP_FEE_RATE) > 1e-12:
        problems.append("round_trip_mismatch")
    if (market or {}).get("stage3_dependency_required") is not False:
        problems.append("stage3_dependency")
    if (market or {}).get("external_control_plane_dependency_required") is not False:
        problems.append("external_cp_dependency")
    if int((account or {}).get("open_positions") or 0) != 0:
        problems.append("positions_nonzero")
    if int((account or {}).get("open_orders") or 0) != 0:
        problems.append("orders_nonzero")
    if (account or {}).get("exchange_write") is True:
        problems.append("exchange_write_true")
    if (overview_wrap or {}).get("mainnet") is True or (account or {}).get("mainnet") is True:
        problems.append("mainnet")
    if (overview_wrap or {}).get("real_money") is True or (account or {}).get("real_money") is True:
        problems.append("real_money")
    if s3 == 200 or cp == 200:
        problems.append("legacy_still_http_200")

    # Observation window gate: refuse "ready to start" before observation ends.
    now = datetime.now(timezone.utc)
    obs_end = datetime(2026, 8, 1, 5, 11, 30, tzinfo=timezone.utc)
    observation_complete = now >= obs_end
    if not observation_complete:
        problems.append("observation_window_open")

    # Founder live gate still false.
    problems.append("founder_6h_v2_gate_not_approved")

    ready = False  # Never true from readiness preflight until Founder gate + observation PASS.

    return {
        "observed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runtime_identity": {
            "sot_deployment_commit": RUNTIME_DEPLOYMENT_COMMIT_SOT,
            "sot_deploy_run": RUNTIME_DEPLOY_RUN_SOT,
            "policy_version": POLICY_VERSION,
            "fee_version": FEE_VERSION,
            "note": "docs tip must never be shown as deployment_commit",
        },
        "deployment_commit": RUNTIME_DEPLOYMENT_COMMIT_SOT,
        "policy_version": POLICY_VERSION,
        "account_epoch": None,
        "single_service": True,
        "active_running_service_count": int(health_code == 200),
        "execution_owner_count": 1,
        "fee_status": (fee or {}).get("fee_rate_status"),
        "fee_expiry": (fee or {}).get("fee_config_expiry") or FEE_REVIEW_BY,
        "geometry_status": "GEOMETRY_PIPELINE_PRESENT"
        if (market or {}).get("geometry_complete_count") is not None
        else "UNKNOWN",
        "cost_gate_status": "FEE_CONFIGURED" if fee_code == 200 else "UNKNOWN",
        "account_fresh": (account or {}).get("fresh") is True,
        "position_count": (account or {}).get("open_positions"),
        "open_order_count": (account or {}).get("open_orders"),
        "reconciliation": "MATCH" if acct_code == 200 else "UNKNOWN",
        "exchange_write": False,
        "demo_autonomous": False,
        "mainnet": False,
        "real_money": False,
        "observation_complete": observation_complete,
        "legacy_stage3_http": s3,
        "legacy_control_plane_http": cp,
        "problems": problems,
        "6h_v2_ready": ready,
        "http": {
            "health": health_code,
            "fee": fee_code,
            "market": market_code,
            "account": acct_code,
            "overview": ov_code,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=VALIDATION_URL)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = run_preflight(base=args.base.rstrip("/"))
    text = json.dumps(report, ensure_ascii=True, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0 if report.get("http", {}).get("health") == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
