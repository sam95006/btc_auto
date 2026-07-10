"""Stage 4.18-P1 — provider routing / BTC shadow mode configuration."""
from __future__ import annotations

import os
from typing import Any, Dict

BTC_SYMBOL = "BTCUSDT"
SHADOW_JSONL_FILENAME = "btc_shadow_provider_decisions.jsonl"
PROBE_RESULTS_JSONL = "stage4_controlled_provider_probe_results.jsonl"

ENV_ROUTING_EXPERIMENT = "STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED"
ENV_BTC_DUAL_SHADOW = "STAGE4_BTC_DUAL_PROVIDER_SHADOW"
ENV_BTC_PROVIDER_OVERRIDE = "STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED"
ENV_BTC_PROVIDER_CHAIN = "STAGE4_BTC_PROVIDER_CHAIN"

ALLOWED_OVERRIDE_PROVIDERS = frozenset({"groq", "cerebras", "openai", "anthropic", "gemini", "ollama"})


def env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"", "0", "false", "no", "off"}


def provider_routing_experiment_enabled() -> bool:
    return env_truthy(ENV_ROUTING_EXPERIMENT, False)


def btc_dual_provider_shadow_enabled() -> bool:
    return env_truthy(ENV_BTC_DUAL_SHADOW, False)


def btc_provider_override_enabled() -> bool:
    """Default off. Requires experiment flag + override flag."""
    return provider_routing_experiment_enabled() and env_truthy(ENV_BTC_PROVIDER_OVERRIDE, False)


def parse_btc_provider_chain() -> list[str]:
    raw = (os.environ.get(ENV_BTC_PROVIDER_CHAIN) or "").strip()
    if not raw:
        return []
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return [p for p in parts if p in ALLOWED_OVERRIDE_PROVIDERS]


def is_btc_provider_override_active() -> bool:
    return btc_provider_override_enabled() and bool(parse_btc_provider_chain())


def is_btc_shadow_mode_active() -> bool:
    return provider_routing_experiment_enabled() and btc_dual_provider_shadow_enabled()


def is_shadow_decision_row(row: Dict[str, Any]) -> bool:
    if not row or not isinstance(row, dict):
        return False
    if row.get("shadow_diagnostic_only") is True:
        return True
    if row.get("record_type") == "btc_shadow_provider_decision":
        return True
    if row.get("shadow_decision_id") and row.get("shadow_excluded_from_paper_logger"):
        return True
    return False


def shadow_provider_for(actual_provider: str) -> str:
    p = str(actual_provider or "groq").strip().lower()
    if p == "groq":
        return "cerebras"
    if p == "cerebras":
        return "groq"
    return "cerebras" if p != "cerebras" else "groq"


def routing_config_summary() -> Dict[str, Any]:
    active = is_btc_shadow_mode_active()
    override_active = is_btc_provider_override_active()
    return {
        "provider_routing_experiment_enabled": provider_routing_experiment_enabled(),
        "btc_dual_provider_shadow_enabled": btc_dual_provider_shadow_enabled(),
        "shadow_mode_active": active,
        "shadow_symbol": BTC_SYMBOL,
        "shadow_decisions_excluded_from_paper": True,
        "shadow_decisions_excluded_from_calibration": True,
        "shadow_decisions_excluded_from_graduation": True,
        "shadow_decisions_excluded_from_stage_419_readiness": True,
        "experiment_mode": provider_routing_experiment_enabled(),
        "btc_provider_override_enabled": btc_provider_override_enabled(),
        "btc_provider_override_active": override_active,
        "btc_provider_chain": ",".join(parse_btc_provider_chain()) if override_active else "",
        "btc_provider_override_symbol_only": BTC_SYMBOL,
        "routing_auto_change_allowed": False,
    }


def empty_shadow_run_summary() -> Dict[str, Any]:
    return {
        "btc_shadow_mode_enabled": is_btc_shadow_mode_active(),
        "btc_shadow_decision_count": 0,
        "btc_shadow_provider_distribution": {},
        "btc_shadow_valid_watch_count": 0,
        "btc_shadow_divergence_count": 0,
        "btc_shadow_excluded_from_paper_logger": True,
        "btc_shadow_excluded_from_calibration": True,
        "btc_shadow_excluded_from_graduation": True,
        "btc_shadow_excluded_from_stage_419_readiness": True,
    }
