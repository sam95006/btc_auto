"""Read-only Founder Operator snapshot builders with live/sim binding (PUB2-D).

Panels expose private operational *health / readiness* labels only.
No strategy params, no wallet secrets, no exchange write controls.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from backend.founder_operator.live_bindings import (
    PANEL_SUMMARIES,
    PANEL_TITLES,
    SURFACE_IDS,
    bind_all_operator_surfaces,
    binding_summary,
)

SCHEMA_ID = "NEXUS_FOUNDER_OPERATOR_UI_V2_LIVE"

OPERATOR_PANEL_IDS: tuple[str, ...] = SURFACE_IDS

# Fields that must never appear in operator payloads (member / public leak traps).
FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset({
    "api_key",
    "apiKey",
    "api_secret",
    "apiSecret",
    "secret",
    "secret_key",
    "private_key",
    "privateKey",
    "wallet_address",
    "walletAddress",
    "strategy_id",
    "strategyId",
    "strategy_params",
    "strategyParams",
    "prompt",
    "lesson_memory_raw",
    "lessonMemoryRaw",
    "order_id",
    "orderId",
    "position_id",
    "positionId",
    "fill_id",
    "fillId",
    "exchange_credentials",
    "exchangeCredentials",
    "authorization",
    "password",
    "token",
})


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _panel_notes(panel_id: str, binding: dict[str, Any]) -> list[str]:
    notes = list(binding.get("notes") or [])
    extras: dict[str, list[str]] = {
        "capture": ["No collector start from this UI."],
        "provider": ["No provider routing editor.", "No live vendor key exposure."],
        "decision": ["No decorative intent/position IDs minted here."],
        "execution_sim": ["HARD BAN: no Demo/Shadow/exchange/mainnet writes."],
        "risk": ["No Risk Governor editors on this surface."],
        "lesson": ["Lesson Memory never crosses Publishing Gateway raw."],
        "qualification": ["HARD BAN: no formal WF / real OOS execution."],
        "storage": ["No raw campaign rewrite from this UI."],
        "kill_switch": [
            "Engage controls stay fail-closed outside verified Founder auth.",
            "This panel never enables exchange cancel/flat from member session.",
        ],
    }
    notes.extend(extras.get(panel_id, []))
    return notes


def _panel_from_binding(panel_id: str, binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": panel_id,
        "title": PANEL_TITLES[panel_id],
        "health": str(binding.get("health") or "UNKNOWN"),
        "summary": PANEL_SUMMARIES[panel_id],
        "metrics": dict(binding.get("metrics") or {}),
        "notes": _panel_notes(panel_id, binding),
        "readOnly": True,
        "exchangeWriteEnabled": False,
        "memberVisible": False,
        "binding": {
            "mode": binding.get("mode"),
            "sourceSurface": binding.get("sourceSurface"),
            "sourceEndpoint": binding.get("sourceEndpoint"),
            "sourceField": binding.get("sourceField"),
            "asOf": binding.get("asOf"),
            "retrievedAt": binding.get("retrievedAt"),
            "lineageId": binding.get("lineageId"),
            "fabricated": False,
            "demoData": bool(binding.get("demoData")),
        },
    }


def build_founder_operator_snapshot(
    *,
    actor_tier: str,
    identity_source: str,
    prefer_simulated: bool | None = None,
) -> dict[str, Any]:
    """Assemble Founder-only operator overview with live/sim surface bindings."""
    if prefer_simulated is None:
        prefer_simulated = os_prefer_simulated()
    bindings = bind_all_operator_surfaces(prefer_simulated=prefer_simulated)
    panels = [_panel_from_binding(pid, bindings[pid]) for pid in OPERATOR_PANEL_IDS]
    summary = binding_summary(bindings)

    return {
        "schema": SCHEMA_ID,
        "ok": True,
        "founderOnly": True,
        "memberAccessible": False,
        "researchOnly": True,
        "realExecutionEnabled": False,
        "armEnabled": False,
        "exchangeWriteEnabled": False,
        "generatedAt": _utc(),
        "actor": {
            "tier": actor_tier,
            "identitySource": identity_source,
        },
        "panels": panels,
        "panelIds": list(OPERATOR_PANEL_IDS),
        "bindings": summary,
        "liveBinding": True,
        "hardBans": [
            "no_demo_order",
            "no_shadow_order",
            "no_exchange_write",
            "no_mainnet",
            "no_real_money",
            "no_formal_wf",
            "no_real_oos",
            "no_member_session_access",
            "no_strategy_promotion",
            "no_fabricated_live_values",
            "no_private_secrets_in_member_paths",
        ],
        "note": (
            "Founder Private Operator UI — live/sim bound private operational health only; "
            "never bindable from a public member session."
        ),
    }


def os_prefer_simulated() -> bool:
    """Allow tests / local research to force SIMULATED binds via env."""
    return os.environ.get("NEXUS_FOUNDER_OPERATOR_FORCE_SIMULATED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def assert_no_forbidden_keys(payload: dict[str, Any]) -> list[str]:
    """Return list of forbidden key paths found (empty = clean)."""
    hits: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}" if path else str(k)
                if k in FORBIDDEN_PAYLOAD_KEYS:
                    hits.append(p)
                walk(v, p)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(payload, "")
    return hits
