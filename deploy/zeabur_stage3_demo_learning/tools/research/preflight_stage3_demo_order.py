#!/usr/bin/env python3
"""Phase C preflight for controlled Bybit demo/testnet micro order session (no orders)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_client import (  # noqa: E402
    BYBIT_DEMO_BASE_URL,
    DEFAULT_CATEGORY,
    DEFAULT_SYMBOL,
    BybitDemoClient,
    BybitDemoClientError,
    MAX_LEVERAGE,
    MAX_MARGIN_USD,
    MAX_OPEN_POSITIONS,
)
from tools.research.bybit_demo_learning_common import utc_now_iso, write_json

PREFLIGHT_REPORT = ROOT / "data/external_alpha/reports/stage3_demo_order_preflight.json"

PHASE_C_SESSION_DEFAULTS = {
    "symbol": DEFAULT_SYMBOL,
    "category": DEFAULT_CATEGORY,
    "max_margin_usd": MAX_MARGIN_USD,
    "max_leverage": MAX_LEVERAGE,
    "max_open_positions": MAX_OPEN_POSITIONS,
    "max_hold_minutes": 10,
    "require_stop_loss": True,
    "stop_loss_max_usd": 2,
    "take_profit_optional": True,
    "force_close_on_timeout": True,
    "reflection_required_on_close": True,
    "patch_required_if_loss": True,
}

ORDER_SAFETY_CONTRACT = {
    "balance_snapshot_id_required": True,
    "account_available_balance_gte_max_margin": True,
    "no_existing_open_position": True,
    "stop_loss_or_protective_exit_required": True,
    "max_hold_required": True,
    "order_scope": "demo_or_testnet_only",
    "mainnet": False,
    "real_money": False,
}


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _falsy(val: str | None) -> bool:
    if val is None:
        return True
    return val.strip().lower() in {"0", "false", "no", "off", "disabled", ""}


def _env_float(key: str) -> float | None:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


def _env_int(key: str) -> int | None:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return None
    try:
        return int(float(raw.strip()))
    except ValueError:
        return None


def run_preflight(*, load_local_env: bool = True) -> Dict[str, Any]:
    from tools.research.check_bybit_demo_learning_env import run_strict_check

    errors: List[str] = []
    strict = run_strict_check(load_local_env=load_local_env, check_package=True)
    strict_passed = bool(strict.get("strict_env_passed"))
    env_summary = strict.get("env_summary") or {}
    if not strict_passed:
        errors.extend(strict.get("strict_env_errors") or [])

    base_url = (os.environ.get("BYBIT_M0_BASE_URL") or BYBIT_DEMO_BASE_URL).strip().rstrip("/")
    no_mainnet = "api-demo.bybit.com" in base_url and "api.bybit.com" not in base_url.replace("api-demo.bybit.com", "")
    if base_url.rstrip("/") == "https://api.bybit.com":
        no_mainnet = False
        errors.append("bybit_mainnet_base_url")
    if _truthy(os.environ.get("BYBIT_MAINNET_ALLOWED")):
        errors.append("BYBIT_MAINNET_ALLOWED_true")
    if _truthy(os.environ.get("REAL_MONEY")):
        errors.append("REAL_MONEY_true")
    if _truthy(os.environ.get("PRODUCTION_PROMOTION_ALLOWED")):
        errors.append("PRODUCTION_PROMOTION_ALLOWED_true")
    if _truthy(os.environ.get("ARM_ALLOWED")):
        errors.append("ARM_ALLOWED_true")
    if os.environ.get("NEXUS_ZEABUR_SERVICE_NAME", "").strip().lower() == "btc-auto":
        errors.append("btc_auto_production_touched")

    margin = _env_float("MAX_MARGIN_USD")
    leverage = _env_int("MAX_LEVERAGE")
    positions = _env_int("MAX_OPEN_POSITIONS")
    if margin is None or margin > MAX_MARGIN_USD:
        errors.append("MAX_MARGIN_USD_exceeds_cap")
    if leverage is None or leverage > MAX_LEVERAGE:
        errors.append("MAX_LEVERAGE_exceeds_cap")
    if positions is None or positions > MAX_OPEN_POSITIONS:
        errors.append("MAX_OPEN_POSITIONS_exceeds_cap")
    for req in (
        "REQUIRE_STOP_LOSS",
        "REQUIRE_MAX_HOLD",
        "REQUIRE_REFLECTION_ON_LOSS",
        "REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP",
    ):
        if not _truthy(os.environ.get(req)):
            errors.append(f"{req}_not_true")

    scope = (os.environ.get("BYBIT_ORDER_SCOPE") or "").strip()
    if scope != "demo_or_testnet_only":
        errors.append("BYBIT_ORDER_SCOPE_invalid")

    balance: Dict[str, Any] = {}
    existing_open_positions = 0
    ticker_ok = False
    account_balance_read_ok = False
    client_urls: List[str] = []

    try:
        client = BybitDemoClient("dry-run", allow_demo_order=False)
        balance = client.get_account_balance()
        account_balance_read_ok = bool(balance.get("balance_read_ok"))
        if not account_balance_read_ok:
            errors.append("account_balance_read_ok_false")
        if balance.get("wallet_coin_missing"):
            errors.append("wallet_coin_missing")
        if balance.get("coin") != "USDT":
            errors.append("account_coin_not_usdt")
        avail = float(balance.get("available_balance") or 0)
        if avail <= MAX_MARGIN_USD:
            errors.append("account_available_balance_not_gt_20")
        existing_open_positions = client.count_open_positions()
        if existing_open_positions > 0:
            errors.append(f"existing_open_positions:{existing_open_positions}")
        ticker = client.fetch_ticker(DEFAULT_SYMBOL)
        ticker_ok = bool(ticker.get("lastPrice") or ticker.get("symbol"))
        if not ticker_ok:
            errors.append("symbol_ticker_unavailable")
        client_urls = list(client.urls_called)
    except (BybitDemoClientError, OSError) as exc:
        errors.append(f"bybit_read_failed:{exc}")
        account_balance_read_ok = False

    order_safety_contract_ready = (
        strict_passed
        and account_balance_read_ok
        and not balance.get("wallet_coin_missing")
        and float(balance.get("available_balance") or 0) > MAX_MARGIN_USD
        and existing_open_positions == 0
        and _truthy(os.environ.get("REQUIRE_STOP_LOSS"))
        and _truthy(os.environ.get("REQUIRE_MAX_HOLD"))
        and scope == "demo_or_testnet_only"
        and no_mainnet
        and not _truthy(os.environ.get("REAL_MONEY"))
    )
    if not order_safety_contract_ready and "order_safety_contract_not_ready" not in errors:
        errors.append("order_safety_contract_not_ready")

    passed = len(errors) == 0
    report = {
        "record_type": "stage3_demo_order_preflight",
        "phase": "C",
        "generated_at_utc": utc_now_iso(),
        "preflight_passed": passed,
        "preflight_errors": errors,
        "demo_order_sent": False,
        "runner_started": False,
        "zeabur_entrypoint_modified": False,
        "production_service_touched": False,
        "strict_env_passed": strict_passed,
        "strict_env_errors": strict.get("strict_env_errors") or [],
        "bybit_base_url": base_url,
        "bybit_order_scope": scope,
        "bybit_mainnet_allowed": _truthy(os.environ.get("BYBIT_MAINNET_ALLOWED")),
        "real_money": _truthy(os.environ.get("REAL_MONEY")),
        "live_trading": _truthy(os.environ.get("LIVE_TRADING")),
        "production_promotion_allowed": _truthy(os.environ.get("PRODUCTION_PROMOTION_ALLOWED")),
        "arm_allowed": _truthy(os.environ.get("ARM_ALLOWED")),
        "account_balance_read_ok": account_balance_read_ok,
        "account_coin": balance.get("coin"),
        "account_total_equity": balance.get("total_equity"),
        "account_wallet_balance": balance.get("wallet_balance"),
        "account_available_balance": balance.get("available_balance"),
        "used_margin": balance.get("used_margin"),
        "unrealized_pnl": balance.get("unrealized_pnl"),
        "balance_snapshot_id": balance.get("snapshot_id"),
        "wallet_coin_missing": bool(balance.get("wallet_coin_missing")),
        "existing_open_positions": existing_open_positions,
        "symbol": DEFAULT_SYMBOL,
        "category": DEFAULT_CATEGORY,
        "ticker_ok": ticker_ok,
        "max_margin_usd": margin if margin is not None else MAX_MARGIN_USD,
        "max_leverage": leverage if leverage is not None else MAX_LEVERAGE,
        "max_open_positions": positions if positions is not None else MAX_OPEN_POSITIONS,
        "require_stop_loss": _truthy(os.environ.get("REQUIRE_STOP_LOSS")),
        "require_max_hold": _truthy(os.environ.get("REQUIRE_MAX_HOLD")),
        "require_reflection_on_loss": _truthy(os.environ.get("REQUIRE_REFLECTION_ON_LOSS")),
        "require_patch_before_next_same_setup": _truthy(
            os.environ.get("REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP")
        ),
        "no_mainnet_endpoint": no_mainnet,
        "no_production_service_touched": os.environ.get("NEXUS_ZEABUR_SERVICE_NAME", "").strip().lower() != "btc-auto",
        "phase_c_session_defaults": PHASE_C_SESSION_DEFAULTS,
        "order_safety_contract": ORDER_SAFETY_CONTRACT,
        "order_safety_contract_ready": order_safety_contract_ready,
        "private_read_urls_called": client_urls,
        "operator_go_required_for_demo_order": True,
        "notes": [
            "Phase C preflight only — no demo order placed.",
            "Next step requires explicit operator GO before --mode demo-order.",
            "Not production, not real money, not mainnet, not btc-auto.",
        ],
    }
    write_json(PREFLIGHT_REPORT, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3 Phase C demo-order preflight (no orders)")
    parser.add_argument("--no-load-local-env", action="store_true")
    args = parser.parse_args()
    report = run_preflight(load_local_env=not args.no_load_local_env)
    print(
        json.dumps(
            {
                "preflight_passed": report["preflight_passed"],
                "preflight_errors": report["preflight_errors"],
                "order_safety_contract_ready": report["order_safety_contract_ready"],
            },
            indent=2,
        )
    )
    return 0 if report["preflight_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
