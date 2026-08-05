"""Three-pass adversarial review for V16-B Counterfactual Replay Engine."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from backend.nexus_counterfactual_replay_v16.claim_scan import assert_no_forbidden_claims
from backend.nexus_counterfactual_replay_v16.constants import (
    ALTERNATE_PATHS,
    HARD_BANS,
    SCHEMA_THREE_PASS,
)
from backend.nexus_counterfactual_replay_v16.engine import (
    deterministic_replay_proof,
    run_counterfactual_replay,
)
from backend.nexus_counterfactual_replay_v16.hard_bans import (
    HardBanViolation,
    refuse_auto_integrate,
    refuse_counterfactual_as_real_performance,
    refuse_exchange_write,
    refuse_future_leakage,
    refuse_mainnet_real_money,
    refuse_oos_walkforward,
    refuse_pit_bypass,
    refuse_rewrite_real_ledger,
    refuse_silent_impute,
    refuse_status_json_lane_artifact,
    refuse_status_report_artifact,
)
from backend.nexus_counterfactual_replay_v16.ledger_guard import assert_ledger_unchanged
from backend.nexus_counterfactual_replay_v16.pit import prove_pit_excludes_future


def _digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _probe_refuse_apis() -> dict[str, Any]:
    probes: list[tuple[str, Callable[[], None]]] = [
        ("refuse_exchange_write", refuse_exchange_write),
        ("refuse_mainnet_real_money", refuse_mainnet_real_money),
        ("refuse_oos_walkforward", refuse_oos_walkforward),
        ("refuse_auto_integrate", refuse_auto_integrate),
        ("refuse_future_leakage", refuse_future_leakage),
        ("refuse_rewrite_real_ledger", refuse_rewrite_real_ledger),
        ("refuse_counterfactual_as_real_performance", refuse_counterfactual_as_real_performance),
        ("refuse_status_json_lane_artifact", refuse_status_json_lane_artifact),
        ("refuse_status_report_artifact", refuse_status_report_artifact),
        ("refuse_pit_bypass", refuse_pit_bypass),
        ("refuse_silent_impute", refuse_silent_impute),
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


def pass1_core_integrity(bundle: dict[str, Any]) -> dict[str, Any]:
    """Pass 1: path coverage, cost inclusion, disclaimer, ledger freeze."""
    findings: list[dict[str, str]] = []
    replay = bundle.get("replay") or {}

    if not replay.get("all_decisions_coverage_complete"):
        findings.append(
            {
                "id": "P1_PATH_COVERAGE",
                "severity": "critical",
                "detail": "one or more decisions missing required alternate paths",
            }
        )
    if replay.get("ledger_rewritten") is True:
        findings.append(
            {
                "id": "P1_LEDGER_REWRITE",
                "severity": "critical",
                "detail": "real ledger rewrite flag set",
            }
        )
    if replay.get("is_real_performance") is True or replay.get("profitability_claimed") is True:
        findings.append(
            {
                "id": "P1_REAL_PERF_CLAIM",
                "severity": "critical",
                "detail": "counterfactual profit claimed as real performance",
            }
        )
    if not replay.get("counterfactual_profit_is_not_real_performance"):
        findings.append(
            {
                "id": "P1_DISCLAIMER_MISSING",
                "severity": "critical",
                "detail": "missing CF≠real disclaimer flag",
            }
        )

    for r in replay.get("replays") or []:
        path_ids = {o["path_id"] for o in r.get("outcomes") or []}
        missing = [p for p in ALTERNATE_PATHS if p not in path_ids]
        if missing:
            findings.append(
                {
                    "id": "P1_MISSING_PATHS",
                    "severity": "critical",
                    "detail": f"{r.get('decision_id')}:missing={missing}",
                }
            )
        for o in r.get("outcomes") or []:
            if o.get("is_real_performance") is True:
                findings.append(
                    {
                        "id": "P1_OUTCOME_REAL_PERF",
                        "severity": "critical",
                        "detail": f"{o.get('path_id')} marked real performance",
                    }
                )
            if o.get("executed") and not o.get("blocked") and o.get("cost_included") is not True:
                if o.get("path_id") != "block_low_data_trust":
                    findings.append(
                        {
                            "id": "P1_COST_MISSING",
                            "severity": "critical",
                            "detail": f"{o.get('path_id')} executed without cost/slippage",
                        }
                    )
            if not o.get("comparability") or not o.get("coverage"):
                findings.append(
                    {
                        "id": "P1_COMPARABILITY_UNMARKED",
                        "severity": "high",
                        "detail": f"{o.get('path_id')} missing comparability/coverage",
                    }
                )

    critical = sum(1 for f in findings if f["severity"] == "critical")
    return {
        "pass": 1,
        "name": "core_integrity",
        "findings": findings,
        "critical_count": critical,
        "passed": critical == 0,
        "digest": _digest({"findings": findings, "fp": replay.get("fingerprint")}),
    }


def pass2_adversarial_leakage(bundle: dict[str, Any]) -> dict[str, Any]:
    """Pass 2: PIT leakage, refuse APIs, mutation attempts, false-PASS traps."""
    findings: list[dict[str, str]] = []
    replay = bundle.get("replay") or {}
    probes = _probe_refuse_apis()
    if not probes["all_raised"]:
        findings.append(
            {
                "id": "P2_REFUSE_API_GAP",
                "severity": "critical",
                "detail": f"refuse probes {probes['raised_count']}/{probes['probe_count']}",
            }
        )

    pit = replay.get("pit_proof") or {}
    if not pit.get("pit_holds"):
        findings.append(
            {
                "id": "P2_PIT_LEAK",
                "severity": "critical",
                "detail": f"future leakage leaked_ts={pit.get('leaked_ts')}",
            }
        )

    # Attempt ledger rewrite detection.
    snaps = replay.get("ledger_snapshots") or []
    for snap in snaps:
        mutated = dict(snap)
        mutated["size"] = float(snap.get("size") or 0) + 1.0
        try:
            # Reconstruct minimal check via assert on dict fields
            from backend.nexus_counterfactual_replay_v16.types import DecisionTrade

            keys = [
                "decision_id",
                "trade_id",
                "symbol",
                "side",
                "strategy_expert",
                "decision_ts_ms",
                "entry_ts_ms",
                "exit_ts_ms",
                "entry_price",
                "exit_price",
                "stop_price",
                "take_profit_price",
                "size",
                "data_trust_at_decision",
                "regime_at_decision",
            ]
            original = DecisionTrade(
                **{k: snap[k] for k in keys},
                confirmation_ready_ts_ms=snap.get("confirmation_ready_ts_ms"),
                ledger_fingerprint=snap.get("ledger_fingerprint", ""),
                is_fixture=bool(snap.get("is_fixture", True)),
                labels=tuple(snap.get("labels") or ()),
            )
            try:
                assert_ledger_unchanged(original, mutated)
                findings.append(
                    {
                        "id": "P2_LEDGER_GUARD_SILENT",
                        "severity": "critical",
                        "detail": "ledger mutation not refused",
                    }
                )
            except HardBanViolation:
                pass
        except Exception as exc:  # noqa: BLE001
            findings.append(
                {
                    "id": "P2_LEDGER_GUARD_ERROR",
                    "severity": "high",
                    "detail": str(exc)[:200],
                }
            )

    # False-PASS: claiming profitability from CF nets.
    cf_nets = []
    for r in replay.get("replays") or []:
        for o in r.get("outcomes") or []:
            if o.get("is_counterfactual") and o.get("net_pnl") is not None:
                cf_nets.append(float(o["net_pnl"]))
            note = (o.get("notes") or "").lower()
            if "real performance" in note and "not" not in note:
                findings.append(
                    {
                        "id": "P2_NOTE_REAL_PERF",
                        "severity": "critical",
                        "detail": f"{o.get('path_id')} notes claim real performance",
                    }
                )
            if o.get("is_counterfactual") is True and o.get("is_real_performance") is True:
                findings.append(
                    {
                        "id": "P2_CF_MARKED_REAL",
                        "severity": "critical",
                        "detail": f"{o.get('path_id')} is_counterfactual and is_real_performance",
                    }
                )
    if cf_nets and replay.get("profitability_claimed"):
        findings.append(
            {
                "id": "P2_FALSE_PASS_PROFIT",
                "severity": "critical",
                "detail": "profitability claimed from counterfactual nets",
            }
        )
    # False-PASS trap: positive CF aggregate must never auto-promote lane.
    if sum(cf_nets) > 0 and replay.get("is_real_performance") is True:
        findings.append(
            {
                "id": "P2_FALSE_PASS_CF_SUM",
                "severity": "critical",
                "detail": "positive CF net sum treated as real performance",
            }
        )

    # Hard-ban inventory completeness.
    bans = set(replay.get("hard_bans") or [])
    missing_bans = [b for b in HARD_BANS if b not in bans]
    if missing_bans:
        findings.append(
            {
                "id": "P2_HARD_BAN_INVENTORY",
                "severity": "critical",
                "detail": f"missing bans={missing_bans}",
            }
        )

    claim_scan = assert_no_forbidden_claims(
        {
            "disclaimer": replay.get("disclaimer"),
            "flags": {
                "profitability_claimed": replay.get("profitability_claimed"),
                "is_real_performance": replay.get("is_real_performance"),
                "counterfactual_profit_is_not_real_performance": replay.get(
                    "counterfactual_profit_is_not_real_performance"
                ),
            },
            "outcome_notes": [
                o.get("notes")
                for r in (replay.get("replays") or [])
                for o in (r.get("outcomes") or [])
            ],
        }
    )
    if not claim_scan["clean"]:
        findings.append(
            {
                "id": "P2_FORBIDDEN_CLAIM_SCAN",
                "severity": "critical",
                "detail": f"hits={claim_scan['hit_count']}",
            }
        )

    # Re-check PIT with as_of before future bar.
    from backend.nexus_counterfactual_replay_v16.fixtures import build_fixture_bars

    bars = build_fixture_bars(seed=replay.get("seed") or "v16b-counterfactual-default")
    future = [b for b in bars if b.regime == "FUTURE_LEAK"]
    if future:
        as_of = min(b.ts_ms for b in future) - 1
        proof = prove_pit_excludes_future(bars, as_of_ms=as_of)
        if not proof["pit_holds"] or proof["future_count"] < 1:
            findings.append(
                {
                    "id": "P2_FUTURE_BAR_NOT_EXCLUDED",
                    "severity": "critical",
                    "detail": "injected future bar not excluded by PIT",
                }
            )

    critical = sum(1 for f in findings if f["severity"] == "critical")
    return {
        "pass": 2,
        "name": "adversarial_leakage",
        "findings": findings,
        "refuse_probes": probes,
        "claim_scan": claim_scan,
        "critical_count": critical,
        "passed": critical == 0,
        "digest": _digest({"findings": findings, "probes": probes, "claim_scan": claim_scan}),
    }


def pass3_determinism_and_seal(bundle: dict[str, Any]) -> dict[str, Any]:
    """Pass 3: deterministic replay + status/report ban + final seal."""
    findings: list[dict[str, str]] = []
    replay = bundle.get("replay") or {}
    det = deterministic_replay_proof(seed=replay.get("seed") or "v16b-counterfactual-default", runs=3)
    if not det.get("deterministic"):
        findings.append(
            {
                "id": "P3_NON_DETERMINISTIC",
                "severity": "critical",
                "detail": f"fingerprints={det.get('fingerprints')}",
            }
        )
    if det.get("fingerprint") != replay.get("fingerprint"):
        findings.append(
            {
                "id": "P3_FINGERPRINT_DRIFT",
                "severity": "critical",
                "detail": "sealed fingerprint drifted from pass-1 replay",
            }
        )

    artifact_names = list(bundle.get("artifact_names") or [])
    for banned in ("_status.json", "status.json", "SUMMARY.md", "status_report.md"):
        if any(banned.lower() in n.lower() for n in artifact_names):
            findings.append(
                {
                    "id": "P3_STATUS_REPORT_PRESENT",
                    "severity": "critical",
                    "detail": f"banned artifact pattern {banned}",
                }
            )

    # Low-trust decision must BLOCK on block_low_data_trust path.
    blocked_ok = False
    for r in replay.get("replays") or []:
        if r.get("decision_id") == "V16B_DEC_002":
            for o in r.get("outcomes") or []:
                if o.get("path_id") == "block_low_data_trust" and o.get("blocked") is True:
                    blocked_ok = True
    if not blocked_ok:
        findings.append(
            {
                "id": "P3_LOW_TRUST_NOT_BLOCKED",
                "severity": "critical",
                "detail": "V16B_DEC_002 must BLOCK on low data trust path",
            }
        )

    critical = sum(1 for f in findings if f["severity"] == "critical")
    return {
        "pass": 3,
        "name": "determinism_and_seal",
        "findings": findings,
        "deterministic_proof": det,
        "critical_count": critical,
        "passed": critical == 0,
        "digest": _digest({"findings": findings, "det": det}),
    }


def run_three_passes(*, seed: str = "v16b-counterfactual-default") -> dict[str, Any]:
    replay = run_counterfactual_replay(seed=seed)
    bundle = {
        "replay": replay,
        "artifact_names": [
            "deterministic_replay.json",
            "three_pass.json",
            "fixture_manifest.json",
            "pytest_report.json",
        ],
    }
    p1 = pass1_core_integrity(bundle)
    p2 = pass2_adversarial_leakage(bundle)
    p3 = pass3_determinism_and_seal(bundle)
    all_passed = p1["passed"] and p2["passed"] and p3["passed"]
    return {
        "schema": SCHEMA_THREE_PASS,
        "seed": seed,
        "passes": [p1, p2, p3],
        "all_passed": all_passed,
        "lane_result": "PASS" if all_passed else "FAIL",
        "replay_fingerprint": replay["fingerprint"],
        "counterfactual_profit_is_not_real_performance": True,
        "wrote_status_json": False,
        "wrote_status_report": False,
        "digest": _digest({"p1": p1["digest"], "p2": p2["digest"], "p3": p3["digest"]}),
    }
