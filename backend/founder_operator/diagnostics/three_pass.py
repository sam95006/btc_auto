"""Three adversarial passes for UX-C Founder Operator Diagnostics.

Returns in-memory results only — HARD BAN: no status JSON / report artifacts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.founder_operator.diagnostics.hard_bans import run_hard_ban_pass
from backend.founder_operator.diagnostics.panels import (
    DIAGNOSTIC_PANEL_IDS,
    assert_no_forbidden_keys,
    build_founder_diagnostics_snapshot,
)
from backend.founder_operator.diagnostics.research_auth import (
    ALLOWED_SCOPES,
    FORBIDDEN_SCOPES,
    authorize_research_observe,
)


def _pass1_contract() -> dict[str, Any]:
    snap = build_founder_diagnostics_snapshot(
        actor_tier="FOUNDER",
        identity_source="test",
    )
    ids = {p["id"] for p in snap["panels"]}
    required = set(DIAGNOSTIC_PANEL_IDS)
    leaks = assert_no_forbidden_keys(snap)
    checks = {
        "schema": snap.get("schema") == "NEXUS_FOUNDER_OPERATOR_DIAGNOSTICS_V16",
        "all_panels": required <= ids,
        "panel_count": len(snap["panels"]) == len(DIAGNOSTIC_PANEL_IDS),
        "founder_only": snap.get("founderOnly") is True,
        "member_denied": snap.get("memberAccessible") is False,
        "research_only": snap.get("researchOnly") is True,
        "no_exchange": snap.get("exchangeWriteEnabled") is False,
        "no_mainnet_shortcut": snap.get("mainnetShortcut") is False,
        "no_real_trade_shortcut": snap.get("realTradeShortcut") is False,
        "no_status_json_report": snap.get("statusJsonReport") is False,
        "no_forbidden_keys": len(leaks) == 0,
        "all_readonly": all(p.get("readOnly") is True for p in snap["panels"]),
        "all_member_invisible": all(p.get("memberVisible") is False for p in snap["panels"]),
    }
    return {
        "pass_number": 1,
        "name": "core_contract",
        "ok": all(checks.values()),
        "checks": checks,
        "leaks": leaks,
    }


def _pass2_adversarial() -> dict[str, Any]:
    denied = []
    for scope in sorted(FORBIDDEN_SCOPES):
        res = authorize_research_observe(
            scope=scope,
            actor_tier="FOUNDER",
            identity_source="test",
        )
        if res.get("authorized") is not False or res.get("ok") is not False:
            denied.append(scope)
    allowed_ok = []
    for scope in sorted(ALLOWED_SCOPES):
        res = authorize_research_observe(
            scope=scope,
            actor_tier="FOUNDER",
            identity_source="test",
        )
        if not (res.get("ok") and res.get("authorized") and res.get("realExecutionEnabled") is False):
            allowed_ok.append(scope)

    snap = build_founder_diagnostics_snapshot(
        actor_tier="FOUNDER",
        identity_source="test",
    )
    router = next(p for p in snap["panels"] if p["id"] == "strategy_router_weights")
    lesson = next(p for p in snap["panels"] if p["id"] == "lesson_pipeline")
    portfolio = next(p for p in snap["panels"] if p["id"] == "portfolio_risk")

    checks = {
        "forbidden_scopes_denied": len(denied) == 0,
        "allowed_scopes_observe_only": len(allowed_ok) == 0,
        "router_no_trade_first_class": router["metrics"].get("noTradeFirstClass") is True,
        "router_no_mainnet_shortcut": router["metrics"].get("mainnetShortcut") is False,
        "lesson_active_blocked": lesson["metrics"].get("activeBlocked") is True,
        "portfolio_zero_real": portfolio["metrics"].get("openRealPositions") == 0,
        "portfolio_observe_only": portfolio["metrics"].get("observeOnly") is True,
    }
    return {
        "pass_number": 2,
        "name": "adversarial_authorize_and_shortcuts",
        "ok": all(checks.values()),
        "checks": checks,
        "forbidden_scope_failures": denied,
        "allowed_scope_failures": allowed_ok,
    }


def _pass3_hard_bans(root: Path | None = None) -> dict[str, Any]:
    hb = run_hard_ban_pass(root, pass_number=3)
    return {
        "pass_number": 3,
        "name": "hard_bans_and_member_isolation",
        "ok": bool(hb.get("ok")),
        "checks": hb.get("checks"),
        "hard_bans": hb.get("hard_bans"),
    }


def run_three_passes(root: Path | str | None = None) -> dict[str, Any]:
    root_path = Path(root) if root else None
    passes = [
        _pass1_contract(),
        _pass2_adversarial(),
        _pass3_hard_bans(root_path),
    ]
    return {
        "ok": all(p["ok"] for p in passes),
        "passes": passes,
        "pass_count": 3,
        "lane": "UX-C",
        "lane_name": "FOUNDER_OPERATOR_DIAGNOSTICS",
        "status_json_report": False,
    }
