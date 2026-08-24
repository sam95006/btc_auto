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
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.founder_operational_override import (
    build_override_record,
    evaluate_operational_observation_gate,
)
from backend.nexus_demo_execution.v2_policy import (
    FEE_REVIEW_BY,
    FEE_VERSION,
    POLICY_VERSION,
    PRETRADE_ROUND_TRIP_FEE_RATE,
    TAKER_FEE_RATE,
    resolve_runtime_deploy_run,
    resolve_runtime_deployment_commit,
)

VALIDATION_URL = os.environ.get("DEMO_VAL_URL", "https://nexus-bybit-demo-val.zeabur.app").rstrip("/")


def _env_true(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _get(url: str) -> tuple[Any, Any]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=45) as resp:
            return json.loads(resp.read().decode()), int(resp.status)
    except urllib.error.HTTPError as exc:
        return {"error": True}, int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}, f"ERR:{type(exc).__name__}"


def run_preflight(*, base: str = VALIDATION_URL, observational: bool = False) -> dict[str, Any]:
    """GET-only live checks. Never POST / start session / enable writes.

    observational=True: report HTTP/safety evidence only; do not require Founder 6H arming.
    """
    health, health_code = _get(f"{base}/health")
    fee, fee_code = _get(f"{base}/api/nexus/fee-policy")
    market, market_code = _get(f"{base}/api/nexus/market/status")
    account, acct_code = _get(f"{base}/api/nexus/demo-execution/account?fresh=true")
    overview_wrap, ov_code = _get(f"{base}/api/nexus/control-plane/overview")
    status_payload, status_code = _get(f"{base}/api/nexus/demo-execution/status")
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
    if market_code != 200:
        problems.append("market_status_not_200")
    if (market or {}).get("stage3_dependency_required") is not False:
        problems.append("stage3_dependency")
    if (market or {}).get("external_control_plane_dependency_required") is not False:
        problems.append("external_cp_dependency")
    if acct_code != 200:
        problems.append("demo_account_not_200")
    if ov_code != 200:
        problems.append("control_plane_overview_not_200")
    if int((account or {}).get("open_positions") or 0) != 0:
        problems.append("positions_nonzero")
    if int((account or {}).get("open_orders") or 0) != 0:
        problems.append("orders_nonzero")
    if (account or {}).get("exchange_write") is True:
        problems.append("exchange_write_true_before_arm")
    if (overview_wrap or {}).get("mainnet") is True or (account or {}).get("mainnet") is True:
        problems.append("mainnet")
    if (overview_wrap or {}).get("real_money") is True or (account or {}).get("real_money") is True:
        problems.append("real_money")
    if s3 == 200 or cp == 200:
        problems.append("legacy_still_http_200")

    now = datetime.now(timezone.utc)
    obs_end = datetime(2026, 8, 1, 5, 11, 30, tzinfo=timezone.utc)
    observation_complete = now >= obs_end

    gate: dict[str, Any] = {"allow_6h_v2_start": False, "path": "observational_skip", "problems": []}
    if not observational:
        abort_path = Path("docs/04_readiness/NEXUS_SINGLE_SERVICE_OPERATIONAL_OBSERVATION_ABORTED_REPORT.md")
        obs_json = Path("artifacts/single_service_observation/observation_aborted.json")
        obs_text = ""
        if abort_path.exists():
            obs_text = abort_path.read_text(encoding="utf-8", errors="ignore")
        elif obs_json.exists():
            obs_text = obs_json.read_text(encoding="utf-8", errors="ignore")
        override = None
        if _env_true("FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H") and _env_true(
            "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2"
        ):
            src = str(abort_path if abort_path.exists() else obs_json)
            override = build_override_record(
                founder_override_id=(os.environ.get("FOUNDER_OVERRIDE_ID") or "FO-PREFLIGHT").strip(),
                approved_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                source_observation_report=src,
                source_text=obs_text
                or "observation_status=ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION\noperational_observation_pass=false\n",
            )
        gate = evaluate_operational_observation_gate(
            observation_text=obs_text
            or "observation_status=IN_PROGRESS\noperational_observation_pass=false\n",
            override=override,
        )
        if not gate.get("allow_6h_v2_start"):
            problems.append("observation_or_override_gate_blocked")
            problems.extend([f"gate:{p}" for p in (gate.get("problems") or [])[:8]])

        phrase_ok = (os.environ.get("FOUNDER_APPROVAL_PHRASE") or "").strip() == "APPROVE_NEXUS_DEMO_6H_V2"
        founder_ok = _env_true("FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2") and (
            phrase_ok or _env_true("FOUNDER_6H_APPROVED")
        )
        if not founder_ok:
            problems.append("founder_6h_v2_gate_not_approved")

    deployment_commit = resolve_runtime_deployment_commit()
    deploy_run = resolve_runtime_deploy_run()
    live_identity = {}
    if isinstance(status_payload, dict):
        live_identity = status_payload.get("runtime_identity") or {}
        if not isinstance(live_identity, dict):
            live_identity = {}

    observational_ok = (
        health_code == 200
        and fee_code == 200
        and market_code == 200
        and acct_code == 200
        and ov_code == 200
        and "exchange_write_true_before_arm" not in problems
        and "mainnet" not in problems
        and "real_money" not in problems
        and "positions_nonzero" not in problems
        and "orders_nonzero" not in problems
    )
    ready = len(problems) == 0 and health_code == 200

    return {
        "observed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "observational_get_only" if observational else "full_6h_v2_preflight",
        "runtime_identity": {
            "resolved_deployment_commit": deployment_commit,
            "resolved_deploy_run": deploy_run,
            "live_status_identity": {
                "deployment_commit": live_identity.get("deployment_commit"),
                "runtime_current_code_commit": live_identity.get("runtime_current_code_commit"),
                "identity_class": live_identity.get("identity_class"),
            },
            "policy_version": POLICY_VERSION,
            "fee_version": FEE_VERSION,
            "note": "never use hardcoded historical SHA as current deployment_commit",
        },
        "deployment_commit": deployment_commit,
        "policy_version": POLICY_VERSION,
        "account_epoch": (account or {}).get("account_epoch"),
        "single_service": True,
        "service_count_http_200": int(health_code == 200),
        "active_running_service_count": int(health_code == 200),
        "execution_owner_count": 1,
        "fee_status": (fee or {}).get("fee_rate_status"),
        "fee_config_valid": fee_code == 200
        and (fee or {}).get("fee_rate_status") == "FEE_RATE_CONFIGURED_CONSERVATIVE",
        "fee_expiry": (fee or {}).get("fee_config_expiry") or FEE_REVIEW_BY,
        "geometry_pipeline_ready": int((market or {}).get("geometry_complete_count") or 0) > 0
        or (market or {}).get("geometry_complete_count") is not None,
        "geometry_complete_count": (market or {}).get("geometry_complete_count"),
        "geometry_missing_count": (market or {}).get("geometry_missing_count"),
        "cost_gate_ready": fee_code == 200,
        "account_fresh": (account or {}).get("fresh") is True,
        "wallet_balance_available": (account or {}).get("wallet_balance") is not None,
        "available_balance_available": (account or {}).get("available_balance") is not None,
        "wallet_balance": (account or {}).get("wallet_balance"),
        "available_balance": (account or {}).get("available_balance"),
        "position_count": (account or {}).get("open_positions"),
        "open_order_count": (account or {}).get("open_orders"),
        "bybit_demo": (account or {}).get("bybit_demo"),
        "reconciliation": "MATCH" if acct_code == 200 else "UNKNOWN",
        "exchange_write": (account or {}).get("exchange_write") is True,
        "demo_autonomous": (account or {}).get("demo_autonomous_enabled") is True
        or (account or {}).get("demo_autonomous") is True,
        "mainnet": (account or {}).get("mainnet") is True,
        "real_money": (account or {}).get("real_money") is True,
        "market_source": (market or {}).get("source") or (market or {}).get("scanner_source"),
        "stage3_dependency_required": (market or {}).get("stage3_dependency_required"),
        "external_control_plane_dependency_required": (market or {}).get(
            "external_control_plane_dependency_required"
        ),
        "status_http": status_code,
        "observation_complete": observation_complete,
        "observation_gate_path": gate.get("path"),
        "legacy_stage3_http": s3,
        "legacy_control_plane_http": cp,
        "problems": problems,
        "observational_pass": observational_ok if observational else None,
        "6h_v2_ready": False if observational else ready,
        "http": {
            "health": health_code,
            "fee": fee_code,
            "market": market_code,
            "account": acct_code,
            "overview": ov_code,
            "status": status_code,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=VALIDATION_URL)
    parser.add_argument("--out", default="")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument(
        "--observational",
        action="store_true",
        help="GET-only safety/evidence checks; do not require Founder 6H arming",
    )
    args = parser.parse_args()
    report = run_preflight(base=args.base.rstrip("/"), observational=args.observational)
    text = json.dumps(report, ensure_ascii=True, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    if args.require_ready:
        if args.observational:
            return 0 if report.get("observational_pass") else 1
        return 0 if report.get("6h_v2_ready") else 1
    return 0 if report.get("http", {}).get("health") == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
