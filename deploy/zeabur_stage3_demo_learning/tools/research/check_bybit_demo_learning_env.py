#!/usr/bin/env python3
"""Strict env validation for Stage 3 Bybit demo/testnet learning runner."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import (  # noqa: E402
    BYBIT_DEMO_BASE_URL,
    BYBIT_MAINNET_BASE_URL,
    COMPROMISED_ENV_KEYS,
    MAX_LEVERAGE,
    MAX_MARGIN_USD,
    MAX_OPEN_POSITIONS,
    READINESS_JSON,
    REQUIRED_CREDENTIAL_KEYS,
    REQUIRED_STRICT_ENV,
    build_readiness_snapshot,
    evidence_chain_ok,
    utc_now_iso,
    write_json,
)

FORBIDDEN_IF_TRUE = (
    "BYBIT_MAINNET_ALLOWED",
    "REAL_MONEY",
    "LIVE_TRADING",
    "PRODUCTION_PROMOTION_ALLOWED",
    "ARM_ALLOWED",
    "BYBIT_SHADOW_MODE",
    "PAPER_ONLY",
)

FORBIDDEN_BASE_URLS = (
    BYBIT_MAINNET_BASE_URL,
    "https://api.bybit.com/",
)


def _truthy(val: str | None) -> bool:
    if val is None:
        return False
    return val.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _falsy(val: str | None) -> bool:
    if val is None:
        return True
    return val.strip().lower() in {"0", "false", "no", "off", "disabled", ""}


def _load_local_env(path: Path) -> Dict[str, str]:
    loaded: Dict[str, str] = {}
    if not path.is_file():
        return loaded
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        loaded[key.strip()] = value.strip().strip('"').strip("'")
    return loaded


def _float_env(key: str) -> float | None:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


def _int_env(key: str) -> int | None:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(float(raw.strip()))
    except ValueError:
        return None


def _check_required_env() -> Tuple[List[str], Dict[str, Any]]:
    failures: List[str] = []
    details: Dict[str, Any] = {}
    for key, expected in REQUIRED_STRICT_ENV.items():
        actual = os.environ.get(key)
        details[key] = "***" if "KEY" in key or "SECRET" in key else actual
        if actual is None:
            failures.append(f"missing_env:{key}")
            continue
        if expected in {"true", "false"}:
            if expected == "true" and not _truthy(actual):
                failures.append(f"env_not_true:{key}")
            if expected == "false" and not _falsy(actual):
                failures.append(f"env_not_false:{key}")
        elif key in {"MAX_MARGIN_USD", "MAX_LEVERAGE", "MAX_OPEN_POSITIONS"}:
            continue
        elif actual.strip() != expected:
            failures.append(f"env_mismatch:{key}")
    return failures, details


def _check_numeric_caps() -> List[str]:
    failures: List[str] = []
    margin = _float_env("MAX_MARGIN_USD")
    leverage = _int_env("MAX_LEVERAGE")
    positions = _int_env("MAX_OPEN_POSITIONS")
    if margin is None or margin > MAX_MARGIN_USD:
        failures.append("MAX_MARGIN_USD_exceeds_20")
    if leverage is None or leverage > MAX_LEVERAGE:
        failures.append("MAX_LEVERAGE_exceeds_3")
    if positions is None or positions > MAX_OPEN_POSITIONS:
        failures.append("MAX_OPEN_POSITIONS_exceeds_1")
    return failures


def _check_credentials() -> List[str]:
    failures: List[str] = []
    for key in COMPROMISED_ENV_KEYS:
        if os.environ.get(key, "").strip():
            failures.append(f"compromised_env_key_present:{key}")
    for key in REQUIRED_CREDENTIAL_KEYS:
        if not os.environ.get(key, "").strip():
            failures.append(f"missing_credential:{key}")
    return failures


def _check_forbidden() -> List[str]:
    failures: List[str] = []
    for key in FORBIDDEN_IF_TRUE:
        if _truthy(os.environ.get(key)):
            failures.append(f"forbidden_env_true:{key}")
    base = (os.environ.get("BYBIT_M0_BASE_URL") or "").strip().rstrip("/")
    for forbidden in FORBIDDEN_BASE_URLS:
        if base.rstrip("/") == forbidden.rstrip("/"):
            failures.append("BYBIT_M0_BASE_URL_is_mainnet")
    if base and BYBIT_DEMO_BASE_URL not in base and "testnet" not in base.lower():
        failures.append("BYBIT_M0_BASE_URL_not_demo_or_testnet")
    if os.environ.get("NEXUS_ZEABUR_SERVICE_NAME", "").strip().lower() == "btc-auto":
        failures.append("btc_auto_production_service_name")
    return failures


def _check_deploy_package(package_root: Path) -> List[str]:
    failures: List[str] = []
    if not package_root.is_dir():
        return failures
    for pattern in (".env", ".env.local", ".env.production"):
        if (package_root / pattern).is_file():
            failures.append(f"env_file_in_deploy_package:{pattern}")
    for path in package_root.rglob(".env*"):
        if path.is_file():
            rel = str(path.relative_to(package_root)).replace("\\", "/")
            failures.append(f"env_file_in_deploy_package:{rel}")
    for path in package_root.rglob("*.key"):
        failures.append(f"secret_file_in_deploy_package:{path.name}")
    for path in package_root.rglob("*.pem"):
        failures.append(f"secret_file_in_deploy_package:{path.name}")
    return failures


def run_strict_check(*, load_local_env: bool = False, check_package: bool = True) -> Dict[str, Any]:
    if load_local_env:
        for key, value in _load_local_env(ROOT / ".env").items():
            os.environ.setdefault(key, value)

    failures: List[str] = []
    req_failures, env_details = _check_required_env()
    failures.extend(req_failures)
    failures.extend(_check_numeric_caps())
    failures.extend(_check_credentials())
    failures.extend(_check_forbidden())

    if not evidence_chain_ok():
        failures.append("evidence_chain_missing")

    package_root = ROOT / "deploy" / "zeabur_stage3_demo_learning"
    package_failures: List[str] = []
    if check_package and package_root.is_dir():
        package_failures = _check_deploy_package(package_root)
        failures.extend(package_failures)

    passed = len(failures) == 0
    return {
        "strict_env_passed": passed,
        "strict_env_errors": failures,
        "env_summary": {
            "bybit_base_url": os.environ.get("BYBIT_M0_BASE_URL"),
            "bybit_demo_api_key_present": bool(os.environ.get("BYBIT_DEMO_API_KEY", "").strip()),
            "bybit_demo_api_secret_present": bool(os.environ.get("BYBIT_DEMO_API_SECRET", "").strip()),
            "bybit_m0_api_key_present": bool(os.environ.get("BYBIT_M0_API_KEY", "").strip()),
            "bybit_m0_api_secret_present": bool(os.environ.get("BYBIT_M0_API_SECRET", "").strip()),
            "bybit_demo_learning_mode": _truthy(os.environ.get("BYBIT_DEMO_LEARNING_MODE")),
            "bybit_order_allowed": _truthy(os.environ.get("BYBIT_ORDER_ALLOWED")),
            "bybit_order_scope": os.environ.get("BYBIT_ORDER_SCOPE"),
            "bybit_mainnet_allowed": _truthy(os.environ.get("BYBIT_MAINNET_ALLOWED")),
            "exchange_write_allowed": _truthy(os.environ.get("EXCHANGE_WRITE_ALLOWED")),
            "exchange_write_scope": os.environ.get("EXCHANGE_WRITE_SCOPE"),
            "real_money": _truthy(os.environ.get("REAL_MONEY")),
            "live_trading": _truthy(os.environ.get("LIVE_TRADING")),
            "production_promotion_allowed": _truthy(os.environ.get("PRODUCTION_PROMOTION_ALLOWED")),
            "arm_allowed": _truthy(os.environ.get("ARM_ALLOWED")),
            "max_margin_usd": _float_env("MAX_MARGIN_USD"),
            "max_leverage": _int_env("MAX_LEVERAGE"),
            "max_open_positions": _int_env("MAX_OPEN_POSITIONS"),
            "require_stop_loss": _truthy(os.environ.get("REQUIRE_STOP_LOSS")),
            "require_max_hold": _truthy(os.environ.get("REQUIRE_MAX_HOLD")),
            "require_reflection_on_loss": _truthy(os.environ.get("REQUIRE_REFLECTION_ON_LOSS")),
            "require_patch_before_next_same_setup": _truthy(
                os.environ.get("REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP")
            ),
        },
        "env_keys_checked": list(REQUIRED_STRICT_ENV.keys()),
        "package_check_failures": package_failures,
        "generated_at_utc": utc_now_iso(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Stage 3 Bybit demo learning env")
    parser.add_argument("--strict-env", action="store_true")
    parser.add_argument("--load-local-env", action="store_true", default=True)
    parser.add_argument("--no-load-local-env", action="store_true")
    parser.add_argument("--no-check-package", action="store_true")
    args = parser.parse_args()

    load_local = args.load_local_env and not args.no_load_local_env
    result = run_strict_check(
        load_local_env=load_local,
        check_package=not args.no_check_package,
    )
    risk_path = ROOT / "data/external_alpha/reports/stage3_credential_risk_acceptance.json"
    risk = {}
    if risk_path.is_file():
        risk = json.loads(risk_path.read_text(encoding="utf-8"))
    readiness = build_readiness_snapshot(
        strict_env_passed=result["strict_env_passed"],
        runner_implemented=False,
    )
    readiness["strict_env_errors"] = result["strict_env_errors"]
    readiness["credential_risk_acceptance"] = {
        "credential_rotated": risk.get("credential_rotated", False),
        "credential_reuse_risk_accepted": risk.get("credential_reuse_risk_accepted", False),
        "allowed_scope": risk.get("allowed_scope"),
    }
    write_json(READINESS_JSON, readiness)

    print(
        json.dumps(
            {
                "strict_env_passed": result["strict_env_passed"],
                "strict_env_errors": result["strict_env_errors"],
            },
            indent=2,
        )
    )
    if not args.strict_env:
        return 0
    return 0 if result["strict_env_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
