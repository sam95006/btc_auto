"""V16-D Strategy Expert Router campaign harness (in-memory; no status JSON)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.nexus_strategy_expert_router.constants import (
    BASE_COMMIT,
    BRANCH,
    CAMPAIGN_ID,
    EXPERT_IDS,
    HARD_BANS,
    LANE,
    OWNED_PATHS,
    SCHEMA,
)
from backend.nexus_strategy_expert_router.cooldown import CooldownBook
from backend.nexus_strategy_expert_router.experts import assert_expert_catalog_complete
from backend.nexus_strategy_expert_router.fixtures import all_fixtures
from backend.nexus_strategy_expert_router.hard_bans import hard_ban_inventory, hard_ban_probe_matrix
from backend.nexus_strategy_expert_router.router import StrategyExpertRouter
from backend.nexus_strategy_expert_router.safety_gates import apply_ai_safety_suggestion
from backend.nexus_strategy_expert_router.three_pass import run_three_passes


def _module_checksum() -> str:
    root = Path(__file__).resolve().parent
    parts: list[str] = []
    for path in sorted(root.glob("*.py")):
        parts.append(path.name)
        parts.append(path.read_text(encoding="utf-8"))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def run_strategy_expert_router_campaign(*, pass_id: int = 1) -> dict[str, Any]:
    """Run fixture routing campaign + three adversarial passes. No artifacts written."""
    if pass_id not in (1, 2, 3):
        raise ValueError("pass_id must be 1, 2, or 3")

    assert_expert_catalog_complete()
    cooldown = CooldownBook()
    router = StrategyExpertRouter(cooldown=cooldown)
    fixtures = all_fixtures()

    decisions: list[dict[str, Any]] = []
    for fid, ctx in fixtures.items():
        ai_override = None
        ai_lev = False
        if fid == "risk_gate_blocked":
            ai_override = {
                "override_risk_gate": True,
                "force_allow": True,
                "risk_gate_allow": True,
                "leverage": 100,
            }
            ai_lev = True
        decision = router.route(
            ctx,
            ai_override_risk_gate=ai_override,
            ai_attempt_set_leverage=ai_lev,
        )
        payload = decision.to_dict()
        payload["fixture_id"] = fid
        # Adversarial AI suggestion — must not mutate safety fields.
        payload = apply_ai_safety_suggestion(
            payload,
            {
                "leverage": 50,
                "side": "LONG",
                "risk_gate_allow": True,
                "override_risk_gate": True,
                "note": "ai_attempt_ignored",
            },
        )
        decisions.append(payload)

    # Cooldown probe: route trend fixture twice rapidly.
    trend_ctx = fixtures["strong_trend_long"]
    first = router.route(trend_ctx)
    second = router.route(trend_ctx)
    cooldown_events: list[dict[str, Any]] = []
    if first.expert_id != "DEFENSIVE_NO_TRADE":
        # After first selection, expert should be cooling; second decision should
        # prefer another expert or show cooldown markers on scores.
        cooled = any(
            "cooldown_active" in (s.block_reasons or [])
            for s in second.expert_scores
            if s.expert_id == first.expert_id
        )
        if cooled or second.expert_id != first.expert_id:
            cooldown_events.append(
                {
                    "first_expert": first.expert_id,
                    "second_expert": second.expert_id,
                    "cooled": cooled,
                }
            )

    # Degradation probe.
    for _ in range(3):
        cooldown.record_soft_failure("BREAKOUT")
    degradation_active = cooldown.is_degraded("BREAKOUT")

    bundle: dict[str, Any] = {
        "schema": SCHEMA,
        "lane": LANE,
        "campaign_id": CAMPAIGN_ID,
        "pass_id": pass_id,
        "branch": BRANCH,
        "base_sha": BASE_COMMIT,
        "owned_paths": list(OWNED_PATHS),
        "expert_ids": list(EXPERT_IDS),
        "decisions": decisions,
        "decision_count": len(decisions),
        "cooldown_events": cooldown_events,
        "cooldown_probe_expected": True,
        "degradation_active_breakout": degradation_active,
        "hard_bans": sorted(HARD_BANS),
        "hard_ban_inventory": hard_ban_inventory(),
        "hard_ban_probes": hard_ban_probe_matrix(),
        "status_json_written": False,
        "status_report_written": False,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
        "auto_integrate_attempted": False,
        "pr27_merge_attempted": False,
        "code_checksum": _module_checksum(),
        "blockers": [
            {
                "blocker_id": "AI_CANNOT_SET_LEVERAGE",
                "detail": "leverage fixed; AI mutation refused",
            },
            {
                "blocker_id": "AI_CANNOT_OVERRIDE_RISK_GATE",
                "detail": "Risk Gate authoritative; override refused",
            },
            {
                "blocker_id": "NO_STATUS_JSON_OR_REPORT",
                "detail": "V16-D emits no *_status.json and no status report artifacts",
            },
            {
                "blocker_id": "NO_LIVE_STRATEGY_PROMOTION",
                "detail": "Champion/Challenger shadow-only",
            },
            {
                "blocker_id": "NO_PER_MINUTE_FORMAL_PARAM_THRASH",
                "detail": "formal params require minimum dwell",
            },
        ],
    }

    three = run_three_passes(bundle)
    bundle["three_pass"] = three
    bundle["status"] = "PASS" if three["all_pass"] else "FAIL"
    bundle["pass"] = bool(three["all_pass"])
    return bundle
