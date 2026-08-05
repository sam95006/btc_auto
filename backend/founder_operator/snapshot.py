"""Read-only Founder Operator snapshot builders.

Panels expose private operational *health / readiness* labels only.
No strategy params, no wallet secrets, no exchange write controls.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_ID = "NEXUS_FOUNDER_OPERATOR_UI_V1"

OPERATOR_PANEL_IDS: tuple[str, ...] = (
    "capture",
    "provider",
    "decision",
    "execution_sim",
    "risk",
    "ledger",
    "checkpoint",
    "reflection",
    "lesson",
    "qualification",
    "storage",
    "kill_switch",
)

# Fields that must never appear in operator payloads (member / public leak traps).
FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset({
    "api_key",
    "apiKey",
    "secret",
    "secret_key",
    "private_key",
    "wallet_address",
    "walletAddress",
    "strategy_id",
    "strategyId",
    "strategy_params",
    "prompt",
    "lesson_memory_raw",
    "order_id",
    "position_id",
    "fill_id",
    "exchange_credentials",
})


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _panel(
    panel_id: str,
    *,
    title: str,
    health: str,
    summary: str,
    metrics: dict[str, Any],
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": panel_id,
        "title": title,
        "health": health,
        "summary": summary,
        "metrics": metrics,
        "notes": notes or [],
        "readOnly": True,
        "exchangeWriteEnabled": False,
        "memberVisible": False,
    }


def build_founder_operator_snapshot(*, actor_tier: str, identity_source: str) -> dict[str, Any]:
    """Assemble Founder-only operator overview. Research / local fixtures only."""
    panels = [
        _panel(
            "capture",
            title="Capture Health",
            health="DEGRADED",
            summary="Live capture supervisor observability (read-only).",
            metrics={
                "processLiveness": "UNKNOWN",
                "wsHealth": "UNKNOWN",
                "hourlyPartitionOk": False,
                "clockQuality": "UNKNOWN",
            },
            notes=["No collector start from this UI.", "LOCAL/STAGING fixture labels only."],
        ),
        _panel(
            "provider",
            title="Provider Health",
            health="OK",
            summary="Provider routing / shadow compare readiness.",
            metrics={
                "primaryProvider": "shadow_compare",
                "fallbackArmed": True,
                "latencyP50Ms": None,
                "errorRate": None,
            },
            notes=["No provider routing editor.", "No live vendor key exposure."],
        ),
        _panel(
            "decision",
            title="Decision Lifecycle",
            health="OK",
            summary="Private Decision lifecycle ontology progress.",
            metrics={
                "activeDecisions": 0,
                "monitoring": 0,
                "underReview": 0,
                "closed": 0,
                "ontology": "MONITORING→EXITED→UNDER_REVIEW→CALIBRATED→CLOSED",
            },
            notes=["No decorative intent/position IDs minted here."],
        ),
        _panel(
            "execution_sim",
            title="Execution Simulation",
            health="OK",
            summary="Simulated execution state only — never live exchange.",
            metrics={
                "mode": "SIMULATION",
                "openSimPositions": 0,
                "pendingSimOrders": 0,
                "realExecutionEnabled": False,
                "armEnabled": False,
            },
            notes=["HARD BAN: no Demo/Shadow/exchange/mainnet writes."],
        ),
        _panel(
            "risk",
            title="Risk State",
            health="OK",
            summary="Private risk governor flags (observe only).",
            metrics={
                "governorMode": "OBSERVE",
                "blocksActive": 0,
                "capacityReview": "NOT_STARTED",
                "editorsEnabled": False,
            },
            notes=["No Risk Governor editors on this surface."],
        ),
        _panel(
            "ledger",
            title="Ledger Health",
            health="OK",
            summary="Checksummed private event ledger health.",
            metrics={
                "checksumOk": True,
                "tailSealed": False,
                "partitionExclusive": True,
                "writerConflict": False,
            },
        ),
        _panel(
            "checkpoint",
            title="Checkpoint Health",
            health="OK",
            summary="Canonical checkpoint envelope authority status.",
            metrics={
                "lastCheckpointAt": None,
                "resumeSafe": True,
                "authorityScope": "founder_private",
                "corruptionDetected": False,
            },
        ),
        _panel(
            "reflection",
            title="Reflection Progress",
            health="OK",
            summary="Reflection V2.3 adjudication progress (private).",
            metrics={
                "casesPending": 0,
                "casesAdjudicated": 0,
                "providerTransport": "gated",
                "terminalGateReady": False,
            },
        ),
        _panel(
            "lesson",
            title="Lesson Gate",
            health="BLOCKED",
            summary="Lesson Memory gate — Founder-private only.",
            metrics={
                "lessonsQueued": 0,
                "preventionProof": "NOT_READY",
                "publicExportAllowed": False,
                "memberReadable": False,
            },
            notes=["Lesson Memory never crosses Publishing Gateway raw."],
        ),
        _panel(
            "qualification",
            title="Qualification Blocks",
            health="BLOCKED",
            summary="Formal qualification control plane — blocked-ready.",
            metrics={
                "formalWfAllowed": False,
                "oosReservationAllowed": False,
                "blockedReady": True,
                "promotionAllowed": False,
            },
            notes=["HARD BAN: no formal WF / real OOS execution."],
        ),
        _panel(
            "storage",
            title="Storage",
            health="OK",
            summary="Private storage velocity / capacity floor.",
            metrics={
                "floorGiB": 100,
                "hardCapGiB": 40,
                "usedGiB": None,
                "velocityOk": True,
            },
            notes=["No raw campaign rewrite from this UI."],
        ),
        _panel(
            "kill_switch",
            title="Kill-Switch Readiness",
            health="ARMED_READINESS",
            summary="Kill-switch readiness only — no live engage from member paths.",
            metrics={
                "engaged": False,
                "readiness": "READY_FOR_LOCAL_RESEARCH",
                "blocksExchangeWrite": True,
                "engageFromUi": False,
                "memberAccessible": False,
            },
            notes=[
                "Engage controls stay fail-closed outside verified Founder auth.",
                "This panel never enables exchange cancel/flat from member session.",
            ],
        ),
    ]

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
        ],
        "note": (
            "Founder Private Operator UI — private operational health only; "
            "never bindable from a public member session."
        ),
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
