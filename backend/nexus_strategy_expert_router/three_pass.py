"""Three-pass adversarial review for V16-D Strategy Expert Router."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_strategy_expert_router.champion_challenger import (
    RouterPromotionGate,
    default_challenger,
    default_champion,
)
from backend.nexus_strategy_expert_router.constants import (
    DEFENSIVE_EXPERT,
    DECISION_SIDES,
    EXPERT_IDS,
    FIXED_LEVERAGE,
    HARD_BANS,
    NO_TRADE_SIDES,
    SCHEMA_THREE_PASS,
)
from backend.nexus_strategy_expert_router.formal_params import (
    FormalParamLock,
    FormalRouterParams,
)
from backend.nexus_strategy_expert_router.hard_bans import (
    HardBanViolation,
    hard_ban_probe_matrix,
    refuse_ai_override_risk_gate,
    refuse_ai_set_leverage,
    refuse_force_trade_when_defensive_wins,
    refuse_per_minute_formal_param_thrash,
    refuse_status_json_lane_artifact,
    refuse_status_report_artifact,
)
from backend.nexus_strategy_expert_router.safety_gates import apply_ai_safety_suggestion


def _digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _probe_refuse_apis() -> dict[str, Any]:
    probes = [
        ("refuse_ai_set_leverage", refuse_ai_set_leverage),
        ("refuse_ai_override_risk_gate", refuse_ai_override_risk_gate),
        ("refuse_status_json_lane_artifact", refuse_status_json_lane_artifact),
        ("refuse_status_report_artifact", refuse_status_report_artifact),
        ("refuse_per_minute_formal_param_thrash", refuse_per_minute_formal_param_thrash),
        ("refuse_force_trade_when_defensive_wins", refuse_force_trade_when_defensive_wins),
    ]
    raised = 0
    for _name, fn in probes:
        try:
            fn()
        except HardBanViolation:
            raised += 1
    return {
        "probe_count": len(probes),
        "raised_count": raised,
        "all_raised": raised == len(probes),
    }


def adversarial_pass1(bundle: dict[str, Any]) -> dict[str, Any]:
    """Pass 1: catalog completeness, first-class sides, reason traces, defensive wins."""
    findings: list[dict[str, str]] = []
    decisions = bundle.get("decisions") or []

    if set(bundle.get("expert_ids") or []) != set(EXPERT_IDS):
        findings.append(
            {
                "id": "P1_EXPERT_CATALOG",
                "severity": "critical",
                "detail": "expert catalog incomplete or drifted",
            }
        )

    sides_seen = {d.get("side") for d in decisions}
    if not sides_seen.issubset(set(DECISION_SIDES)):
        findings.append(
            {
                "id": "P1_INVALID_SIDE",
                "severity": "critical",
                "detail": f"non-first-class side observed: {sides_seen}",
            }
        )

    for d in decisions:
        rt = d.get("reason_trace") or {}
        if int(rt.get("step_count") or 0) < 3:
            findings.append(
                {
                    "id": "P1_REASON_TRACE_THIN",
                    "severity": "critical",
                    "detail": f"reason trace too thin for {d.get('fixture_id')}",
                }
            )
            break

    defensive_cases = [
        d for d in decisions if d.get("fixture_id") in {"defensive_stress", "low_trust"}
    ]
    if defensive_cases and not any(
        d.get("expert_id") == DEFENSIVE_EXPERT or d.get("no_trade") for d in defensive_cases
    ):
        findings.append(
            {
                "id": "P1_DEFENSIVE_MUST_WIN_STRESS",
                "severity": "critical",
                "detail": "no-trade/defensive failed to win under stress/low-trust fixtures",
            }
        )

    if any(d.get("side") in ("LONG", "SHORT") and d.get("expert_id") == DEFENSIVE_EXPERT for d in decisions):
        findings.append(
            {
                "id": "P1_DEFENSIVE_ENTRY_EMITTED",
                "severity": "critical",
                "detail": "DEFENSIVE_NO_TRADE emitted LONG/SHORT",
            }
        )

    return {
        "pass_id": 1,
        "name": "catalog_sides_trace_defensive",
        "findings": findings,
        "pass": len(findings) == 0,
        "digest": _digest({"findings": findings, "n": len(decisions)}),
    }


def adversarial_pass2(bundle: dict[str, Any]) -> dict[str, Any]:
    """Pass 2: AI leverage / Risk Gate hard bans; formal param anti-thrash."""
    findings: list[dict[str, str]] = []
    decisions = bundle.get("decisions") or []
    refuse = _probe_refuse_apis()
    if not refuse["all_raised"]:
        findings.append(
            {
                "id": "P2_REFUSE_APIS",
                "severity": "critical",
                "detail": "not all hard-ban refuse APIs raised",
            }
        )

    for d in decisions:
        if int(d.get("leverage") or 0) != FIXED_LEVERAGE:
            findings.append(
                {
                    "id": "P2_LEVERAGE_DRIFT",
                    "severity": "critical",
                    "detail": f"leverage drift on {d.get('fixture_id')}",
                }
            )
            break
        if d.get("ai_set_leverage_applied") is True:
            findings.append(
                {
                    "id": "P2_AI_SET_LEVERAGE_APPLIED",
                    "severity": "critical",
                    "detail": "AI set leverage applied",
                }
            )
            break
        if d.get("ai_override_risk_gate_applied") is True:
            findings.append(
                {
                    "id": "P2_AI_RISK_GATE_OVERRIDE_APPLIED",
                    "severity": "critical",
                    "detail": "AI risk gate override applied",
                }
            )
            break
        if d.get("risk_gate_honored") is not True:
            findings.append(
                {
                    "id": "P2_RISK_GATE_NOT_HONORED",
                    "severity": "critical",
                    "detail": f"risk gate not honored on {d.get('fixture_id')}",
                }
            )
            break

    # Formal param thrash probe.
    lock = FormalParamLock()
    lock.propose_update(
        FormalRouterParams(min_data_trust=0.50),
        ts_ms=1_000_000,
    )
    thrash_blocked = False
    try:
        lock.propose_update(
            FormalRouterParams(min_data_trust=0.55),
            ts_ms=1_000_000 + 30_000,  # 30s later — per-minute thrash
        )
    except HardBanViolation:
        thrash_blocked = True
    if not thrash_blocked:
        findings.append(
            {
                "id": "P2_FORMAL_PARAM_THRASH",
                "severity": "critical",
                "detail": "per-minute formal param thrash was not hard-banned",
            }
        )

    # AI suggestion must not mutate protected fields.
    if decisions:
        mutated = apply_ai_safety_suggestion(
            decisions[0],
            {
                "leverage": 100,
                "risk_gate_allow": True,
                "side": "LONG",
                "override_risk_gate": True,
                "note": "ignore",
            },
        )
        if mutated.get("ai_set_leverage_applied") or mutated.get("ai_override_risk_gate_applied"):
            findings.append(
                {
                    "id": "P2_AI_SUGGESTION_MUTATED",
                    "severity": "critical",
                    "detail": "AI safety suggestion mutated protected fields",
                }
            )
        if int(mutated.get("leverage") or 0) != FIXED_LEVERAGE:
            findings.append(
                {
                    "id": "P2_AI_SUGGESTION_LEVERAGE",
                    "severity": "critical",
                    "detail": "AI suggestion changed leverage",
                }
            )

    return {
        "pass_id": 2,
        "name": "safety_gates_and_anti_thrash",
        "findings": findings,
        "refuse_probes": refuse,
        "hard_ban_matrix": hard_ban_probe_matrix(),
        "pass": len(findings) == 0,
        "digest": _digest({"findings": findings, "refuse": refuse}),
    }


def adversarial_pass3(bundle: dict[str, Any]) -> dict[str, Any]:
    """Pass 3: champion/challenger shadow-only; cooldown/degrade; no status artifacts."""
    findings: list[dict[str, str]] = []

    gate = RouterPromotionGate()
    champ = default_champion()
    chall = default_challenger()
    v = gate.evaluate(champ, chall)
    if v.promoted:
        findings.append(
            {
                "id": "P3_CHALLENGER_PROMOTED_TOO_EARLY",
                "severity": "high",
                "detail": "challenger with insufficient sample must not promote",
            }
        )
    live = gate.evaluate(champ, chall, requested_status="LIVE_APPLIED")
    if live.promoted or live.reason != "live_promotion_forbidden":
        findings.append(
            {
                "id": "P3_LIVE_PROMOTION_ALLOWED",
                "severity": "critical",
                "detail": "LIVE_APPLIED promotion must be forbidden",
            }
        )

    if bundle.get("status_json_written") or bundle.get("status_report_written"):
        findings.append(
            {
                "id": "P3_STATUS_ARTIFACT",
                "severity": "critical",
                "detail": "status JSON/report artifact written",
            }
        )

    # Cooldown: second route on same expert should show cooldown markers for entry experts.
    cooldown_events = bundle.get("cooldown_events") or []
    if bundle.get("cooldown_probe_expected") and not cooldown_events:
        findings.append(
            {
                "id": "P3_COOLDOWN_MISSING",
                "severity": "high",
                "detail": "expected cooldown event not observed",
            }
        )

    # No-trade sides must remain first-class in outputs.
    sides = {d.get("side") for d in (bundle.get("decisions") or [])}
    if not (sides & NO_TRADE_SIDES):
        findings.append(
            {
                "id": "P3_NO_TRADE_SIDES_ABSENT",
                "severity": "critical",
                "detail": "WAIT/REDUCE/ABSTAIN never observed; no-trade not first-class",
            }
        )

    hard_bans = set(bundle.get("hard_bans") or [])
    if not set(HARD_BANS).issubset(hard_bans):
        findings.append(
            {
                "id": "P3_HARD_BAN_INVENTORY",
                "severity": "critical",
                "detail": "hard ban inventory incomplete in bundle",
            }
        )

    return {
        "pass_id": 3,
        "name": "champion_cooldown_artifacts",
        "findings": findings,
        "pass": len(findings) == 0,
        "digest": _digest({"findings": findings}),
        "schema": SCHEMA_THREE_PASS,
    }


def run_three_passes(bundle: dict[str, Any]) -> dict[str, Any]:
    p1 = adversarial_pass1(bundle)
    p2 = adversarial_pass2(bundle)
    p3 = adversarial_pass3(bundle)
    passes = [p1, p2, p3]
    return {
        "schema": SCHEMA_THREE_PASS,
        "passes": passes,
        "all_pass": all(p["pass"] for p in passes),
        "finding_count": sum(len(p["findings"]) for p in passes),
        "digest": _digest([p["digest"] for p in passes]),
    }
