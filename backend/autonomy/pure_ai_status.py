"""Build verifiable Pure AI status for API / Console (no separate external Pure AI API)."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from config.pure_ai_trading_config import (
    PURE_AI_DEFAULT_LEVERAGE,
    PURE_AI_LLM_ONLY,
    PURE_AI_MAX_PROPOSALS_PER_TICK,
    PURE_AI_MIN_MARGIN_USD,
    PURE_AI_STALE_SAFETY_HOURS,
    PURE_AI_TARGET_NOTIONAL_USD,
    pure_ai_active,
    pure_ai_bypass_fee_churn,
    pure_ai_bypass_growth_blocks,
    pure_ai_bypass_validation,
)
from backend.trading.sandbox_mode import sandbox_active


def _env_flag(name: str) -> str:
    return str(os.getenv(name, "") or "").strip()


def build_pure_ai_status(runtime) -> Dict[str, Any]:
    """Snapshot-friendly proof that Pure AI (not rule engines) drives entries/exits."""
    llm_status = getattr(runtime, "llm_status", None)
    if not llm_status:
        gateway = getattr(runtime, "llm_gateway", None)
        if gateway and hasattr(gateway, "status_snapshot"):
            try:
                llm_status = gateway.status_snapshot()
            except Exception:
                llm_status = {}
    llm = dict(llm_status or {})
    cycle = dict(getattr(runtime, "_last_pure_ai_cycle", None) or {})
    pipeline = dict(getattr(runtime, "_last_entry_pipeline", None) or {})
    flex_exit = dict(getattr(runtime, "_last_ai_flex_exit_eval", None) or {})
    models = dict(llm.get("models") or {})

    try:
        from backend.runtime.embed_flags import embedded_worker_started
    except Exception:
        embedded_worker_started = False

    checks: List[Dict[str, Any]] = [
        {
            "id": "env_pure_ai_mode",
            "label": "Pure AI 主開關",
            "ok": pure_ai_active(),
            "detail": f"NEXUS_PURE_AI_MODE={_env_flag('NEXUS_PURE_AI_MODE') or '0'}",
        },
        {
            "id": "pipeline_mode",
            "label": "進場管線",
            "ok": str(pipeline.get("mode") or "") == "pure_ai",
            "detail": f"entry_pipeline.mode={pipeline.get('mode') or 'unknown'}",
        },
        {
            "id": "llm_enabled",
            "label": "LLM 引擎",
            "ok": bool(llm.get("enabled")),
            "detail": "flex_trade_eval / flex_exit_eval via Groq or Cerebras",
        },
        {
            "id": "embedded_worker",
            "label": "交易 Worker",
            "ok": bool(embedded_worker_started),
            "detail": "NEXUS_EMBEDDED_WORKER=1",
        },
        {
            "id": "testnet_sandbox",
            "label": "Testnet 沙盒",
            "ok": sandbox_active(),
            "detail": "NEXUS_TESTNET_SANDBOX=1",
        },
        {
            "id": "rule_engines_off",
            "label": "規則引擎不搶決策",
            "ok": _env_flag("NEXUS_RULE_SIGNAL_BRIDGE") in {"", "0", "false", "False"},
            "detail": "RULE_SIGNAL / GRID / FUNDING_ARB should be 0",
        },
    ]

    all_core_ok = all(item["ok"] for item in checks[:5])

    return {
        "active": pure_ai_active(),
        "operational": bool(all_core_ok and pure_ai_active()),
        "headline": "Pure AI 全自動" if pure_ai_active() else "Hybrid / 規則混合模式",
        "explanation": (
            "Pure AI 不是另一個外部 API。NEXUS 每 tick 將市場摘要送進 LLM "
            "(flex_trade_eval 進場、flex_exit_eval 出場)，通過硬風控後在 Binance testnet 下單。"
        ),
        "pipeline": pipeline,
        "last_cycle": {
            "mode": cycle.get("mode"),
            "timestamp": cycle.get("timestamp"),
            "entry_count": cycle.get("entry_count", 0),
            "exit_count": cycle.get("exit_count", 0),
            "deployable_pool": cycle.get("deployable_pool"),
            "entry_proposals": list(cycle.get("entry_proposals") or [])[:4],
            "exit_actions": list(cycle.get("exit_actions") or [])[:4],
        },
        "flex_exit_eval": {
            "mode": flex_exit.get("mode"),
            "action_count": flex_exit.get("action_count", 0),
        },
        "llm": {
            "enabled": bool(llm.get("enabled")),
            "last_ok_at": llm.get("last_ok_at"),
            "last_ok_task": llm.get("last_ok_task"),
            "flex_trade_model": models.get("flex_trade_eval"),
            "flex_exit_model": models.get("flex_exit_eval"),
            "providers": {
                "flex_trade": _env_flag("NEXUS_LLM_PROVIDER_FLEX_TRADE") or _env_flag("NEXUS_LLM_PROVIDER_TRADE_PROPOSER"),
                "flex_exit": _env_flag("NEXUS_LLM_PROVIDER_FLEX_EXIT") or _env_flag("NEXUS_LLM_PROVIDER_TRADE_PROPOSER"),
            },
        },
        "config_summary": {
            "llm_only": PURE_AI_LLM_ONLY,
            "bypass_validation": pure_ai_bypass_validation(),
            "bypass_fee_churn": pure_ai_bypass_fee_churn(),
            "bypass_growth_blocks": pure_ai_bypass_growth_blocks(),
            "min_margin_usd": PURE_AI_MIN_MARGIN_USD,
            "target_notional_usd": PURE_AI_TARGET_NOTIONAL_USD,
            "default_leverage": PURE_AI_DEFAULT_LEVERAGE,
            "max_proposals_per_tick": PURE_AI_MAX_PROPOSALS_PER_TICK,
            "stale_safety_hours": PURE_AI_STALE_SAFETY_HOURS,
        },
        "verification_checks": checks,
        "pnl_disclaimer": (
            "Testnet 正報酬需長期觀察 monthly_revenue / decision_funnel；"
            "Pure AI 只保證決策來源為 LLM + 硬風控，不保證每筆獲利。"
        ),
    }
