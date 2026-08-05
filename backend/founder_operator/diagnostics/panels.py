"""Assemble Founder-only V16 diagnostics snapshot (UX-C)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from backend.founder_operator.diagnostics import fixtures as fx
from backend.founder_operator.diagnostics.versions import module_version_panel_payload
from backend.founder_operator.snapshot import FORBIDDEN_PAYLOAD_KEYS

SCHEMA_ID = "NEXUS_FOUNDER_OPERATOR_DIAGNOSTICS_V16"

DIAGNOSTIC_PANEL_IDS: tuple[str, ...] = (
    "error_ontology_histogram",
    "repeated_error_signatures",
    "counterfactual_deltas",
    "regime_transitions",
    "strategy_router_weights",
    "lesson_pipeline",
    "calibration_abstention",
    "provider_health",
    "data_trust",
    "portfolio_risk",
    "memory_graph_health",
    "v16_module_versions",
)

PANEL_TITLES: dict[str, str] = {
    "error_ontology_histogram": "Error Ontology Histogram",
    "repeated_error_signatures": "Repeated-Error Signatures",
    "counterfactual_deltas": "Counterfactual Deltas",
    "regime_transitions": "Regime Transitions",
    "strategy_router_weights": "Strategy Router Weights",
    "lesson_pipeline": "Lesson Pipeline + Reject Reasons",
    "calibration_abstention": "Calibration / Abstention",
    "provider_health": "Provider Health",
    "data_trust": "Data Trust",
    "portfolio_risk": "Portfolio Risk",
    "memory_graph_health": "Memory Graph Health",
    "v16_module_versions": "V16 Module Versions",
}

PANEL_SUMMARIES: dict[str, str] = {
    "error_ontology_histogram": "Process-class histogram from Trade Error Ontology (research projection).",
    "repeated_error_signatures": "Recurring error gene signatures above repeat threshold.",
    "counterfactual_deltas": "Alternate-path delta PnL (sim) — no predictive edge claimed.",
    "regime_transitions": "Probabilistic regime flip / transition observe surface.",
    "strategy_router_weights": "Expert router weights with first-class no-trade.",
    "lesson_pipeline": "Lesson promotion pipeline states and firewall reject reasons.",
    "calibration_abstention": "Uncertainty ladder + calibration reliability (abstention-first).",
    "provider_health": "Provider transport health — no vendor key exposure.",
    "data_trust": "Lineage / freshness / PIT trust score for routing gates.",
    "portfolio_risk": "Simulated portfolio risk observe — zero real exposure.",
    "memory_graph_health": "Decision memory graph integrity and public-projection safety.",
    "v16_module_versions": "Declared V16 lane versions (projection registry).",
}

HARD_BANS: tuple[str, ...] = (
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
    "no_mainnet_shortcut",
    "no_real_trade_shortcut",
    "no_status_json_report",
    "observe_authorize_research_only",
)

_BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "error_ontology_histogram": fx.error_ontology_histogram,
    "repeated_error_signatures": fx.repeated_error_signatures,
    "counterfactual_deltas": fx.counterfactual_deltas,
    "regime_transitions": fx.regime_transitions,
    "strategy_router_weights": fx.strategy_router_weights,
    "lesson_pipeline": fx.lesson_pipeline,
    "calibration_abstention": fx.calibration_abstention,
    "provider_health": fx.provider_health,
    "data_trust": fx.data_trust,
    "portfolio_risk": fx.portfolio_risk,
    "memory_graph_health": fx.memory_graph_health,
    "v16_module_versions": module_version_panel_payload,
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _panel(panel_id: str) -> dict[str, Any]:
    raw = dict(_BUILDERS[panel_id]())
    health = str(raw.pop("health", "OK"))
    mode = str(raw.get("mode") or "SIMULATED")
    return {
        "id": panel_id,
        "title": PANEL_TITLES[panel_id],
        "health": health,
        "summary": PANEL_SUMMARIES[panel_id],
        "metrics": raw,
        "notes": [
            "Founder-only diagnostics projection.",
            "Observe / authorize research only.",
            "HARD BAN: no mainnet / real-trade shortcuts.",
            "memberVisible=false",
        ],
        "readOnly": True,
        "exchangeWriteEnabled": False,
        "memberVisible": False,
        "researchOnly": True,
        "binding": {
            "mode": mode,
            "sourceSurface": f"diagnostics.{panel_id}",
            "sourceEndpoint": "/api/nexus/founder/diagnostics",
            "asOf": _utc(),
            "retrievedAt": _utc(),
            "lineageId": f"ux_c:{panel_id}:sim",
            "fabricated": False,
            "demoData": False,
        },
    }


def build_founder_diagnostics_snapshot(
    *,
    actor_tier: str,
    identity_source: str,
) -> dict[str, Any]:
    panels = [_panel(pid) for pid in DIAGNOSTIC_PANEL_IDS]
    return {
        "schema": SCHEMA_ID,
        "ok": True,
        "lane": "UX-C",
        "laneName": "FOUNDER_OPERATOR_DIAGNOSTICS",
        "founderOnly": True,
        "memberAccessible": False,
        "researchOnly": True,
        "observeOnly": True,
        "authorizeResearchOnly": True,
        "realExecutionEnabled": False,
        "armEnabled": False,
        "exchangeWriteEnabled": False,
        "mainnetShortcut": False,
        "realTradeShortcut": False,
        "statusJsonReport": False,
        "generatedAt": _utc(),
        "actor": {
            "tier": actor_tier,
            "identitySource": identity_source,
        },
        "panels": panels,
        "panelIds": list(DIAGNOSTIC_PANEL_IDS),
        "hardBans": list(HARD_BANS),
        "note": (
            "Founder Operator Diagnostics (UX-C) — V16 research observe panels; "
            "member sessions fail-closed; no mainnet/real-trade shortcuts."
        ),
    }


def assert_no_forbidden_keys(payload: dict[str, Any]) -> list[str]:
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
