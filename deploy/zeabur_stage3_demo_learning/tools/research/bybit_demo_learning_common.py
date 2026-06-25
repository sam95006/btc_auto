"""Shared constants for Stage 3 Bybit demo/testnet learning runner."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = os.environ.get("NEXUS_DATA_DIR", "").strip()
DATA_ROOT = Path(_DATA_DIR) if _DATA_DIR else ROOT

BYBIT_DEMO_BASE_URL = "https://api-demo.bybit.com"
BYBIT_MAINNET_BASE_URL = "https://api.bybit.com"

BOOT_REPORTS_DIR = ROOT / "data" / "external_alpha" / "reports"
P1_REPORT = BOOT_REPORTS_DIR / "p1_behavior_change_report.json"
P2_REPORT = BOOT_REPORTS_DIR / "p2_performance_report.json"
OOS_REPORT = BOOT_REPORTS_DIR / "oos_walkforward_report.json"
PHASE9_REPORT = BOOT_REPORTS_DIR / "phase9_production_promotion_review.json"

READINESS_JSON = BOOT_REPORTS_DIR / "research_stage3_bybit_demo_learning_readiness.json"
MANIFEST_JSON = BOOT_REPORTS_DIR / "zeabur_stage3_demo_learning_deploy_package_manifest.json"
RISK_ACCEPTANCE_JSON = BOOT_REPORTS_DIR / "stage3_credential_risk_acceptance.json"

DEPLOY_ROOT = ROOT / "deploy" / "zeabur_stage3_demo_learning"
SERVICE_NAME = "nexus-stage3-bybit-demo-learning"

MAX_MARGIN_USD = 20.0
MAX_LEVERAGE = 3
MAX_OPEN_POSITIONS = 1

REQUIRED_STRICT_ENV = {
    "RESEARCH_ONLY": "true",
    "BYBIT_DEMO_LEARNING_MODE": "true",
    "BYBIT_SHADOW_MODE": "false",
    "PAPER_ONLY": "false",
    "BYBIT_ORDER_ALLOWED": "true",
    "BYBIT_ORDER_SCOPE": "demo_or_testnet_only",
    "BYBIT_MAINNET_ALLOWED": "false",
    "BYBIT_M0_BASE_URL": BYBIT_DEMO_BASE_URL,
    "EXCHANGE_WRITE_ALLOWED": "true",
    "EXCHANGE_WRITE_SCOPE": "bybit_demo_or_testnet_only",
    "REAL_MONEY": "false",
    "LIVE_TRADING": "false",
    "PRODUCTION_PROMOTION_ALLOWED": "false",
    "ARM_ALLOWED": "false",
    "MAX_MARGIN_USD": "20",
    "MAX_LEVERAGE": "3",
    "MAX_OPEN_POSITIONS": "1",
    "REQUIRE_STOP_LOSS": "true",
    "REQUIRE_MAX_HOLD": "true",
    "REQUIRE_REFLECTION_ON_LOSS": "true",
    "REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP": "true",
    "NEXUS_DATA_DIR": "/data",
}

COMPROMISED_ENV_KEYS = ("BYBIT_M0_API_KEY", "BYBIT_M0_API_SECRET")
REQUIRED_CREDENTIAL_KEYS = ("BYBIT_DEMO_API_KEY", "BYBIT_DEMO_API_SECRET")
DEPRECATED_CREDENTIAL_KEYS = COMPROMISED_ENV_KEYS

TRADE_RECORD_FIELDS = (
    "decision_id",
    "signal_id",
    "order_id",
    "symbol",
    "side",
    "entry_price",
    "exit_price",
    "close_pnl",
    "exit_reason",
    "confidence_before",
    "confidence_after",
    "position_size_before",
    "position_size_after",
    "reflection_created",
    "patch_created",
    "patch_applied_to_next_decision",
    "repeated_mistake_detected",
    "repeated_mistake_blocked",
)

STOP_CONDITION_KEYS = (
    "bybit_mainnet_detected",
    "real_money_detected",
    "margin_usd_exceeds_cap",
    "leverage_exceeds_cap",
    "open_positions_exceeds_cap",
    "missing_stop_loss",
    "missing_max_hold",
    "loss_without_reflection",
    "repeated_loss_without_patch",
    "same_setup_reentry_without_patch",
    "production_promotion_allowed",
    "kill_switch_disabled",
    "btc_auto_production_touched",
    "balance_read_failed",
    "account_available_balance_zero",
    "account_total_equity_zero",
    "account_available_below_max_margin",
    "wallet_coin_missing",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def evidence_chain_ok() -> bool:
    p1 = load_json(P1_REPORT).get("p1_behavior_change_pass") is True
    p2 = load_json(P2_REPORT).get("p2_performance_pass") is True
    oos = load_json(OOS_REPORT).get("oos_walkforward_pass") is True
    phase9 = load_json(PHASE9_REPORT)
    verdict = phase9.get("current_verdict") or {}
    return p1 and p2 and oos and verdict.get("production_promotion_allowed") is False


def build_readiness_snapshot(*, strict_env_passed: bool = False, runner_implemented: bool = False) -> Dict[str, Any]:
    return {
        "record_type": "research_stage3_bybit_demo_learning_readiness",
        "schema_version": "1.0",
        "generated_at_utc": utc_now_iso(),
        "scope": "bybit_demo_testnet_learning_only",
        "service_name": SERVICE_NAME,
        "research_only": True,
        "bybit_demo_learning_mode": True,
        "bybit_shadow_mode": False,
        "paper_only": False,
        "bybit_order_allowed": True,
        "bybit_order_scope": "demo_or_testnet_only",
        "bybit_mainnet_allowed": False,
        "bybit_base_url": BYBIT_DEMO_BASE_URL,
        "exchange_write_allowed": True,
        "exchange_write_scope": "bybit_demo_or_testnet_only",
        "real_money": False,
        "live_trading": False,
        "production_promotion_allowed": False,
        "arm_allowed": False,
        "max_margin_usd": MAX_MARGIN_USD,
        "max_leverage": MAX_LEVERAGE,
        "max_open_positions": MAX_OPEN_POSITIONS,
        "require_stop_loss": True,
        "require_max_hold": True,
        "require_reflection_on_loss": True,
        "require_patch_before_next_same_setup": True,
        "runner_implemented": runner_implemented,
        "strict_env_passed": strict_env_passed,
        "zeabur_production_runner_allowed": False,
        "btc_auto_production_touched": False,
        "trade_record_fields": list(TRADE_RECORD_FIELDS),
        "stop_conditions_enabled": True,
        "stop_conditions_monitored": list(STOP_CONDITION_KEYS),
        "notes": [
            "Not production GO, not real money GO, not Bybit mainnet GO.",
            "Demo/testnet orders only within margin/leverage caps.",
            "Use BYBIT_DEMO_API_KEY / BYBIT_DEMO_API_SECRET only; revoke legacy BYBIT_M0_* keys.",
        ],
    }
