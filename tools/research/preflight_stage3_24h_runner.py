#!/usr/bin/env python3
"""Phase D preflight for 24h Bybit demo/testnet learning runner (no orders)."""
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
    BybitDemoClient,
    BybitDemoClientError,
    MAX_LEVERAGE,
    MAX_MARGIN_USD,
    MAX_OPEN_POSITIONS,
)
from tools.research.bybit_demo_learning_common import STOP_CONDITION_KEYS, utc_now_iso, write_json
from tools.research.stage3_operator_go import operator_go_24h_metadata, operator_go_24h_present

PREFLIGHT_REPORT = ROOT / "data/external_alpha/reports/stage3_24h_runner_preflight.json"
SAFETY_REPORT = ROOT / "data/external_alpha/reports/stage3_github_auto_24h_startup_safety_report.json"

STOP_CONDITIONS = list(STOP_CONDITION_KEYS)


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _env_float(key: str, default: float | None = None) -> float | None:
    raw = os.environ.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        return default


def _env_int(key: str, default: int | None = None) -> int | None:
    raw = os.environ.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(float(str(raw).strip()))
    except ValueError:
        return default


def _check_data_writable(output_dir: Path) -> tuple[bool, str]:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, ""
    except OSError as exc:
        return False, str(exc)


def run_preflight(*, load_local_env: bool = True) -> Dict[str, Any]:
    from tools.research.check_bybit_demo_learning_env import run_strict_check

    errors: List[str] = []
    in_container = Path("/data").is_dir() and os.environ.get("NEXUS_DATA_DIR") == "/data"
    if in_container:
        load_local_env = False

    strict = run_strict_check(load_local_env=load_local_env, check_package=not in_container)
    if not strict.get("strict_env_passed"):
        errors.extend(strict.get("strict_env_errors") or [])

    startup_mode = (os.environ.get("STAGE3_STARTUP_MODE") or "idle").strip().lower()
    if startup_mode == "runner" and not operator_go_24h_present():
        errors.append("OPERATOR_GO_STAGE3_24H_RUNNER_not_true")
    if _truthy(os.environ.get("OPERATOR_GO_STAGE3_C1_DEMO_ORDER")) and startup_mode == "runner":
        errors.append("OPERATOR_GO_STAGE3_C1_DEMO_ORDER_must_be_false_for_24h")

    margin = _env_float("STAGE3_MAX_MARGIN_USD", _env_float("MAX_MARGIN_USD", MAX_MARGIN_USD))
    leverage = _env_int("STAGE3_MAX_LEVERAGE", _env_int("MAX_LEVERAGE", MAX_LEVERAGE))
    positions = _env_int("STAGE3_MAX_OPEN_POSITIONS", _env_int("MAX_OPEN_POSITIONS", MAX_OPEN_POSITIONS))
    max_orders = _env_int("STAGE3_MAX_ORDERS_PER_DAY", 6) or 6
    duration = _env_float("STAGE3_RUN_DURATION_MINUTES", 1440) or 1440

    if margin is None or margin > MAX_MARGIN_USD:
        errors.append("MAX_MARGIN_USD_exceeds_cap")
    if leverage is None or leverage > MAX_LEVERAGE:
        errors.append("MAX_LEVERAGE_exceeds_cap")
    if positions is None or positions != MAX_OPEN_POSITIONS:
        errors.append("MAX_OPEN_POSITIONS_must_be_1")
    if max_orders > 6:
        errors.append("STAGE3_MAX_ORDERS_PER_DAY_exceeds_6")
    if duration > 1440:
        errors.append("STAGE3_RUN_DURATION_MINUTES_exceeds_1440")

    for req in (
        "REQUIRE_STOP_LOSS",
        "REQUIRE_MAX_HOLD",
        "REQUIRE_REFLECTION_ON_LOSS",
        "REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP",
    ):
        if not _truthy(os.environ.get(req)):
            errors.append(f"{req}_not_true")

    base_url = (os.environ.get("BYBIT_M0_BASE_URL") or BYBIT_DEMO_BASE_URL).strip()
    if _truthy(os.environ.get("BYBIT_MAINNET_ALLOWED")):
        errors.append("BYBIT_MAINNET_ALLOWED_true")
    if _truthy(os.environ.get("REAL_MONEY")):
        errors.append("REAL_MONEY_true")
    if _truthy(os.environ.get("LIVE_TRADING")):
        errors.append("LIVE_TRADING_true")
    if _truthy(os.environ.get("PRODUCTION_PROMOTION_ALLOWED")):
        errors.append("PRODUCTION_PROMOTION_ALLOWED_true")
    if _truthy(os.environ.get("ARM_ALLOWED")):
        errors.append("ARM_ALLOWED_true")
    if os.environ.get("NEXUS_ZEABUR_SERVICE_NAME", "").strip().lower() == "btc-auto":
        errors.append("btc_auto_production_touched")

    output_dir = Path(os.environ.get("STAGE3_OUTPUT_DIR", "").strip() or "")
    if not str(output_dir):
        from tools.research.stage3_learning_loop import resolve_output_dir

        output_dir = resolve_output_dir()
    data_root = Path(os.environ.get("NEXUS_DATA_DIR", "/data"))
    if in_container:
        data_exists = data_root.is_dir()
    else:
        data_exists = True
    data_writable, data_err = _check_data_writable(output_dir)
    if in_container and not data_exists:
        errors.append("data_dir_missing")
    if not data_writable:
        errors.append(f"output_dir_not_writable:{data_err}")

    balance: Dict[str, Any] = {}
    existing_open_positions = 0
    account_balance_read_ok = False
    try:
        client = BybitDemoClient("dry-run", allow_demo_order=False)
        balance = client.get_account_balance()
        account_balance_read_ok = bool(balance.get("balance_read_ok"))
        if not account_balance_read_ok:
            errors.append("account_balance_read_ok_false")
        if balance.get("wallet_coin_missing"):
            errors.append("wallet_coin_missing")
        avail = float(balance.get("available_balance") or 0)
        if avail < MAX_MARGIN_USD:
            errors.append("available_balance_lt_20")
        existing_open_positions = client.count_open_positions()
        if existing_open_positions > 0:
            errors.append(f"clean_baseline_open_positions:{existing_open_positions}")
    except (BybitDemoClientError, OSError) as exc:
        errors.append(f"bybit_read_failed:{exc}")

    clean_baseline = (
        account_balance_read_ok
        and not balance.get("wallet_coin_missing")
        and float(balance.get("available_balance") or 0) >= MAX_MARGIN_USD
        and existing_open_positions == 0
        and data_exists
        and data_writable
    )

    passed = len(errors) == 0
    report = {
        "record_type": "stage3_24h_runner_preflight",
        "phase": "D",
        "generated_at_utc": utc_now_iso(),
        "preflight_passed": passed,
        "preflight_errors": errors,
        "clean_baseline_passed": clean_baseline,
        "startup_mode": startup_mode,
        "operator_go_24h_runner": operator_go_24h_present(),
        "operator_go_metadata": operator_go_24h_metadata(),
        "strict_env_passed": bool(strict.get("strict_env_passed")),
        "account_balance_read_ok": account_balance_read_ok,
        "account_available_balance": balance.get("available_balance"),
        "existing_open_positions": existing_open_positions,
        "max_margin_usd": margin,
        "max_leverage": leverage,
        "max_open_positions": positions,
        "max_orders_per_day": max_orders,
        "duration_minutes_target": duration,
        "output_dir": str(output_dir),
        "data_dir_exists": data_exists,
        "data_dir_writable": data_writable,
        "stop_conditions": STOP_CONDITIONS,
        "bybit_base_url": base_url,
        "bybit_mainnet_allowed": _truthy(os.environ.get("BYBIT_MAINNET_ALLOWED")),
        "real_money": _truthy(os.environ.get("REAL_MONEY")),
        "live_trading": _truthy(os.environ.get("LIVE_TRADING")),
        "production_promotion_allowed": _truthy(os.environ.get("PRODUCTION_PROMOTION_ALLOWED")),
        "arm_allowed": _truthy(os.environ.get("ARM_ALLOWED")),
        "mainnet": False,
        "production_service_touched": False,
        "btc_auto_touched": False,
        "runner_started_24h": False,
        "order_sent": False,
    }
    write_json(PREFLIGHT_REPORT, report)
    write_json(
        SAFETY_REPORT,
        {
            "record_type": "stage3_github_auto_24h_startup_safety_report",
            "generated_at_utc": utc_now_iso(),
            "github_auto_24h_startup_safe": passed,
            "preflight_passed": passed,
            "clean_baseline_passed": clean_baseline,
            "entrypoint_runner_mode_requires_operator_go": True,
            "stop_conditions": STOP_CONDITIONS,
            "preflight": report,
        },
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3 24h runner preflight")
    parser.add_argument("--no-load-local-env", action="store_true")
    args = parser.parse_args()
    report = run_preflight(load_local_env=not args.no_load_local_env)
    print(
        json.dumps(
            {
                "preflight_passed": report["preflight_passed"],
                "preflight_errors": report["preflight_errors"],
                "clean_baseline_passed": report["clean_baseline_passed"],
            },
            indent=2,
        )
    )
    return 0 if report["preflight_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
