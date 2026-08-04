"""Founder-private read-only observability contract (no secrets / no strategy params)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_private_observability(root: Path) -> dict[str, Any]:
    root = Path(root)
    v23 = {}
    ckpt = root / ".nexus_runtime/blind_reflection_v23_checkpoint.json"
    if ckpt.exists():
        d = json.loads(ckpt.read_text(encoding="utf-8"))
        t = d.get("transport") or {}
        g = t.get("GROQ_REFLECTION_REASONER") or {}
        s = t.get("SAMBANOVA_INDEPENDENT_CRITIC") or {}
        v23 = {
            "frozen_calibration_case_count": len(d.get("case_ids") or []),
            "groq_success_count": g.get("success_count"),
            "groq_pending_count": len(d.get("pending_case_ids") or []),
            "groq_429_count": g.get("HTTP_429_count"),
            "sambanova_success_count": s.get("success_count"),
            "sambanova_pending_count": len(d.get("critic_pending_ids") or []),
            "sambanova_429_count": s.get("HTTP_429_count"),
            "V2_3_terminal_status": "INCOMPLETE_PROVIDER_CAPACITY"
            if (g.get("success_count") or 0) < 80
            else "PENDING_QUALITY_GATES",
        }

    return {
        "schema": "private_core_observability_v1",
        "created_at": _utc(),
        "private_core_stage": "V7_INTEGRATION_SPINE",
        "V2_3_progress": v23,
        "Provider_transport": {
            "groq_stage": (json.loads(ckpt.read_text(encoding="utf-8")).get("groq_stage") if ckpt.exists() else None),
            "sambanova_stage": (
                json.loads(ckpt.read_text(encoding="utf-8")).get("sambanova_stage") if ckpt.exists() else None
            ),
        },
        "Integration_Spine": "NEXUS_PRIVATE_CORE_INTEGRATION_SPINE_V1",
        "Event_Ledger": "NEXUS_PRIVATE_EVENT_LEDGER_V1",
        "Runtime_Durability": "NEXUS_RUNTIME_DURABILITY_V1",
        "Microstructure_campaign": "BOUNDED_ACCUMULATION_PLANNED",
        "Event_Study_readiness": "NOT_READY",
        "Harness": "V1_1",
        "Risk_bans": ["stop_widening", "risk_increase", "leverage_increase"],
        "Formal_trading_state": {
            "formal_walk_forward_executed": False,
            "oos_executed": False,
            "demo_order_count": 0,
            "exchange_write_attempt_count": 0,
            "deployment_started": False,
            "mainnet": False,
            "real_money": False,
        },
        "secrets_present": False,
        "account_information_present": False,
        "strategy_parameters_present": False,
    }
