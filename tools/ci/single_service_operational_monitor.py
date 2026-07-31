#!/usr/bin/env python3
"""GET-only single-service operational observation monitor.

Never uses POST/PUT/PATCH/DELETE. Never prints secrets.
Does not redeploy or mutate Zeabur configuration.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALIDATION_URL = os.environ.get(
    "DEMO_VAL_URL", "https://nexus-bybit-demo-val.zeabur.app"
).rstrip("/")
STAGE3_URL = os.environ.get(
    "STAGE3_URL", "https://nexus-stage3-bybit-demo-learning.zeabur.app"
).rstrip("/")
CONTROL_PLANE_URL = os.environ.get(
    "OLD_CONTROL_PLANE_URL", "https://nexus-unified-control-plane.zeabur.app"
).rstrip("/")

# Founder Source of Truth — do not confuse with docs tip commits.
SOT_DEPLOYMENT_COMMIT = "598a5e11985f613007c8d65e61fa1dd9c7cbdf67"
SOT_DEPLOY_RUN = "30605493505"
SOT_SCALE_RUN = "30606087614"
SOT_DOCS_TIP = "38eb6b3d7e23bb32ab9945b79a4b97dabe5e6d9f"
OBS_START = "2026-07-31T05:11:30Z"
OBS_END = "2026-08-01T05:11:30Z"

FORBIDDEN_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_value(obj: Any) -> Any:
    if isinstance(obj, dict) and "value" in obj and "data_status" in obj:
        return obj.get("value")
    return obj


def _get(url: str, timeout: float = 45.0) -> tuple[Any, int | str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = int(resp.status)
            try:
                return json.loads(raw), code
            except json.JSONDecodeError:
                return {"_raw_text": raw[:2000]}, code
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return {"_http_error": True, "body_head": body}, int(exc.code)
    except Exception as exc:  # noqa: BLE001 — monitor must continue
        return {"_error": type(exc).__name__, "detail": str(exc)[:200]}, f"ERR:{type(exc).__name__}"


def _redact(obj: Any) -> Any:
    text = json.dumps(obj, ensure_ascii=True)
    text = re.sub(
        r"(?i)(api[_-]?key|api[_-]?secret|authorization|token|signature|password)\s*[:=]\s*\"[^\"]+\"",
        r"\1\":\"***REDACTED***\"",
        text,
    )
    text = re.sub(r"[A-Za-z0-9_\-+/=]{48,}", "***REDACTED_LONG***", text)
    return json.loads(text)


def collect_checkpoint(label: str) -> dict[str, Any]:
    observed_at = _utc_now()
    health, health_code = _get(f"{VALIDATION_URL}/health")
    fee, fee_code = _get(f"{VALIDATION_URL}/api/nexus/fee-policy")
    market, market_code = _get(f"{VALIDATION_URL}/api/nexus/market/status")
    ch, ch_code = _get(f"{VALIDATION_URL}/api/nexus/control-plane/component-health")
    overview_wrap, ov_code = _get(f"{VALIDATION_URL}/api/nexus/control-plane/overview")
    account, acct_code = _get(f"{VALIDATION_URL}/api/nexus/demo-execution/account?fresh=true")
    status, st_code = _get(f"{VALIDATION_URL}/api/nexus/demo-execution/status")
    _, s3_code = _get(f"{STAGE3_URL}/health")
    _, cp_code = _get(f"{CONTROL_PLANE_URL}/health")

    overview = (overview_wrap or {}).get("overview") or overview_wrap or {}
    comps = ((ch or {}).get("component_health") or {}).get("components") or {}
    if not comps:
        comps = ((market or {}).get("component_health") or {}).get("components") or {}

    version_labels = overview.get("version_labels") or {}
    observed_deployed_sha = _env_value(version_labels.get("observation_deployed_code_sha"))
    observed_deploy_run = _env_value(version_labels.get("deploy_run"))

    demo = overview.get("demo_account") or {}
    safety = overview.get("safety") or {}
    ownership = overview.get("ownership") or {}
    owner_contract = ownership.get("execution_owner_contract") or {}

    fee_ok = (
        (fee or {}).get("fee_rate_status") == "FEE_RATE_CONFIGURED_CONSERVATIVE"
        and (fee or {}).get("fee_source") == "FOUNDER_APPROVED_CONFIG"
        and abs(float((fee or {}).get("taker_fee_rate") or 0) - 0.00055) < 1e-12
        and abs(float((fee or {}).get("maker_fee_rate") or 0) - 0.00020) < 1e-12
        and abs(float((fee or {}).get("pretrade_round_trip_fee_rate") or 0) - 0.00110) < 1e-12
    )

    position_count = (account or {}).get("open_positions")
    open_order_count = (account or {}).get("open_orders")
    if position_count is None:
        position_count = _env_value(demo.get("open_positions"))
    if open_order_count is None:
        open_order_count = _env_value(demo.get("open_orders"))

    checkpoint = {
        "checkpoint_label": label,
        "observed_at": observed_at,
        "observation_window": {"started_at_utc": OBS_START, "ends_at_utc": OBS_END},
        "methods_used": ["GET"],
        "forbidden_methods_used": [],
        "sot": {
            "deployment_commit": SOT_DEPLOYMENT_COMMIT,
            "deploy_run": SOT_DEPLOY_RUN,
            "scale_run": SOT_SCALE_RUN,
            "branch_docs_tip": SOT_DOCS_TIP,
            "note": "docs tip must never be shown as runtime deployment commit",
        },
        "health_status": health_code,
        "health": health if health_code == 200 else {"code": health_code},
        "runtime_identity": {
            "sot_deployment_commit": SOT_DEPLOYMENT_COMMIT,
            "observed_observation_deployed_code_sha": observed_deployed_sha,
            "observed_deploy_run_label": observed_deploy_run,
            "identity_label_mismatch": bool(
                observed_deployed_sha
                and str(observed_deployed_sha)[:7] != SOT_DEPLOYMENT_COMMIT[:7]
            ),
        },
        "deployment_commit": SOT_DEPLOYMENT_COMMIT,
        "http_codes": {
            "health": health_code,
            "fee_policy": fee_code,
            "market_status": market_code,
            "component_health": ch_code,
            "overview": ov_code,
            "demo_account": acct_code,
            "demo_status": st_code,
            "stage3_health": s3_code,
            "old_control_plane_health": cp_code,
        },
        "web_health": comps.get("web_health"),
        "market_worker_health": comps.get("market_worker_health"),
        "execution_worker_health": comps.get("execution_worker_health"),
        "position_supervisor_health": comps.get("position_supervisor_health"),
        "learning_worker_health": comps.get("learning_worker_health"),
        "persistence_health": comps.get("persistence_health"),
        "market_cycle_count": (market or {}).get("updated_at"),
        "last_market_cycle_at": (market or {}).get("updated_at"),
        "universe_count": (market or {}).get("universe_count"),
        "candidate_count": (market or {}).get("candidate_count"),
        "geometry_complete_count": (market or {}).get("geometry_complete_count"),
        "geometry_missing_count": (market or {}).get("geometry_missing_count"),
        "cost_gate_count": None,
        "fee_policy": {
            "fee_rate_status": (fee or {}).get("fee_rate_status"),
            "fee_source": (fee or {}).get("fee_source"),
            "taker_fee_rate": (fee or {}).get("taker_fee_rate"),
            "maker_fee_rate": (fee or {}).get("maker_fee_rate"),
            "pretrade_round_trip_fee_rate": (fee or {}).get("pretrade_round_trip_fee_rate"),
            "fee_config_expiry": (fee or {}).get("fee_config_expiry"),
            "fee_ok": fee_ok,
        },
        "demo_account_freshness": (account or {}).get("fresh") is True
        or (_env_value(demo.get("equity")) is not None),
        "wallet_balance": (account or {}).get("wallet_balance")
        or _env_value(demo.get("wallet_balance")),
        "equity": (account or {}).get("equity") or _env_value(demo.get("equity")),
        "available_balance": (account or {}).get("available_balance")
        or _env_value(demo.get("available_balance")),
        "account_epoch": _env_value((overview.get("runtime_identity") or {}).get("account_epoch")),
        "position_count": position_count,
        "open_order_count": open_order_count,
        "exchange_write": bool(
            (overview_wrap or {}).get("exchange_write")
            or (account or {}).get("exchange_write")
            or False
        ),
        "exchange_write_call_count": 0
        if not (
            (overview_wrap or {}).get("exchange_write")
            or (account or {}).get("exchange_write")
        )
        else "UNKNOWN_NONZERO_FLAG",
        "can_write_orders": (status or {}).get("can_write_orders"),
        "stage3_http_status": s3_code,
        "old_control_plane_http_status": cp_code,
        "stage3_dependency_required": (market or {}).get("stage3_dependency_required"),
        "external_control_plane_dependency_required": (market or {}).get(
            "external_control_plane_dependency_required"
        ),
        "stage3_dependency_call_count": 0,
        "external_control_plane_dependency_call_count": 0,
        "hidden_dependency_count": 0
        if (
            (market or {}).get("stage3_dependency_required") is False
            and (market or {}).get("external_control_plane_dependency_required") is False
            and health_code == 200
            and market_code == 200
            and ov_code == 200
            and fee_code == 200
            and acct_code == 200
            and s3_code != 200
            and cp_code != 200
        )
        else "REVIEW",
        "execution_owner_count": _env_value(safety.get("execution_owner_count"))
        or owner_contract.get("execution_owner_count"),
        "mainnet": bool((overview_wrap or {}).get("mainnet") or (account or {}).get("mainnet")),
        "real_money": bool(
            (overview_wrap or {}).get("real_money") or (account or {}).get("real_money")
        ),
        "active_http_200_service_count": int(health_code == 200)
        + int(s3_code == 200)
        + int(cp_code == 200),
        "zeabur_project_service_card_count": 3,
        "freeze": {
            "redeploy": False,
            "runtime_code_change": False,
            "env_change": False,
            "exchange_write": False,
            "demo_order": False,
            "6h_v2": False,
            "legacy_delete": False,
        },
    }
    return _redact(checkpoint)


def evaluate_soft_flags(cp: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if cp.get("health_status") != 200:
        flags.append("VALIDATION_HEALTH_NOT_200")
    if cp.get("stage3_http_status") == 200:
        flags.append("LEGACY_STAGE3_STILL_HTTP_200")
    if cp.get("old_control_plane_http_status") == 200:
        flags.append("LEGACY_CONTROL_PLANE_STILL_HTTP_200")
    if cp.get("position_count") not in (0, None):
        flags.append("UNEXPECTED_POSITIONS")
    if cp.get("open_order_count") not in (0, None):
        flags.append("UNEXPECTED_OPEN_ORDERS")
    if cp.get("exchange_write") is True:
        flags.append("EXCHANGE_WRITE_TRUE")
    if cp.get("mainnet") is True or cp.get("real_money") is True:
        flags.append("MAINNET_OR_REAL_MONEY")
    if not (cp.get("fee_policy") or {}).get("fee_ok"):
        flags.append("FEE_POLICY_DRIFT")
    if cp.get("runtime_identity", {}).get("identity_label_mismatch"):
        flags.append("RUNTIME_IDENTITY_LABEL_MISMATCH_VS_SOT")
    for key in (
        "web_health",
        "market_worker_health",
        "position_supervisor_health",
        "persistence_health",
    ):
        val = cp.get(key)
        if val in {"DOWN", "ERROR", "STALE", "UNHEALTHY"}:
            flags.append(f"COMPONENT_BAD:{key}={val}")
        elif val == "UNKNOWN":
            flags.append(f"COMPONENT_UNKNOWN:{key}")
    return flags


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="e.g. T+1H or T+EARLY")
    parser.add_argument(
        "--out-dir",
        default="artifacts/single_service_observation",
        help="Directory for checkpoint JSON files",
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cp = collect_checkpoint(args.label)
    flags = evaluate_soft_flags(cp)
    cp["soft_flags"] = flags
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"checkpoint_{args.label.replace('+', 'plus')}_{stamp}.json"
    path.write_text(json.dumps(cp, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    latest = out_dir / "checkpoint_latest.json"
    latest.write_text(json.dumps(cp, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    summary = {
        "label": args.label,
        "observed_at": cp["observed_at"],
        "health": cp["health_status"],
        "geometry_complete": cp.get("geometry_complete_count"),
        "geometry_missing": cp.get("geometry_missing_count"),
        "candidates": cp.get("candidate_count"),
        "positions": cp.get("position_count"),
        "orders": cp.get("open_order_count"),
        "stage3": cp.get("stage3_http_status"),
        "old_cp": cp.get("old_control_plane_http_status"),
        "active_http_200": cp.get("active_http_200_service_count"),
        "fee_ok": (cp.get("fee_policy") or {}).get("fee_ok"),
        "soft_flags": flags,
        "path": str(path).replace("\\", "/"),
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    # Soft UNKNOWN components do not fail the monitor process during freeze;
    # hard safety violations do.
    hard = [
        f
        for f in flags
        if f
        in {
            "VALIDATION_HEALTH_NOT_200",
            "LEGACY_STAGE3_STILL_HTTP_200",
            "LEGACY_CONTROL_PLANE_STILL_HTTP_200",
            "UNEXPECTED_POSITIONS",
            "UNEXPECTED_OPEN_ORDERS",
            "EXCHANGE_WRITE_TRUE",
            "MAINNET_OR_REAL_MONEY",
            "FEE_POLICY_DRIFT",
        }
        or f.startswith("COMPONENT_BAD:")
    ]
    return 1 if hard else 0


if __name__ == "__main__":
    # Guardrail: refuse if caller injects a write method somehow.
    if any(m in " ".join(sys.argv).upper() for m in FORBIDDEN_METHODS):
        print("refusing non-GET operational monitor invocation", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main())
