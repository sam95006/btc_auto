"""V14-B Pass-2 adversarial checks for the blocked Event Study engine."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_event_study.constants import (
    ENGINE_STATUS,
    HARD_BANS,
    REAL_EVENT_STUDY_EXECUTION,
    REAL_EVENT_STUDY_STATUS,
)
from backend.nexus_event_study.engine import run_blocked_fixture_study, verify_deterministic_study
from backend.nexus_event_study.fixtures import build_synthetic_cohort, make_study_event
from backend.nexus_event_study.forensic_ro import ForensicWriteAttemptError, refuse_write
from backend.nexus_event_study.missing import classify_missing
from backend.nexus_event_study.outcomes import multi_horizon_outcomes
from backend.nexus_event_study.pit import prove_pit_excludes_future
from backend.nexus_event_study.types import StudyEvent


def run_adversarial_pass(pass1: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    # 1) Dual status must remain ENGINE_READY + REAL_EVENT_STUDY_BLOCKED
    if ENGINE_STATUS != "ENGINE_READY" or REAL_EVENT_STUDY_STATUS != "REAL_EVENT_STUDY_BLOCKED":
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "STATUS_CONTRACT_BROKEN",
                "detail": {
                    "ENGINE_STATUS": ENGINE_STATUS,
                    "REAL_EVENT_STUDY_STATUS": REAL_EVENT_STUDY_STATUS,
                },
            }
        )
    if REAL_EVENT_STUDY_EXECUTION is not False:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "REAL_STUDY_EXECUTION_FLAG_TRUE",
                "detail": "REAL_EVENT_STUDY_EXECUTION must remain False",
            }
        )

    # 2) PIT future leakage
    cohort = build_synthetic_cohort(seed="v14b-pass2-pit")
    events: list[StudyEvent] = list(cohort["_events_objs"])
    as_of = int(cohort["base_ts_ms"]) + 800 * 60_000
    pit = prove_pit_excludes_future(events, as_of_ms=as_of)
    if not pit["pit_holds"]:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "PIT_FUTURE_LEAK",
                "detail": pit,
            }
        )

    # 3) Missing fields must exclude with reason — never silent impute
    broken = make_study_event(
        event_id="oi_step_change",
        symbol="BTCUSDT",
        decision_ts_ms=as_of - 60_000,
        seq=999,
        payload={},
    )
    broken = StudyEvent(
        observation_id=broken.observation_id,
        event_id=broken.event_id,
        symbol=broken.symbol,
        regime=broken.regime,
        decision_ts_ms=broken.decision_ts_ms,
        exchange_ts_ms=broken.exchange_ts_ms,
        receive_ts_ms=broken.receive_ts_ms,
        side=broken.side,
        entry_price=broken.entry_price,
        source=broken.source,
        payload={},
        is_trade=False,
    )
    miss = classify_missing([broken], as_of_ms=as_of)
    if miss["missing_count"] != 1 or miss["silent_impute"] is not False:
        findings.append(
            {
                "severity": "HIGH",
                "code": "SILENT_IMPUTE_MISSING",
                "detail": miss,
            }
        )

    # 4) Incomplete forward path must mark outcomes unavailable
    short_path = [100.0, 100.1]
    outs = multi_horizon_outcomes(broken, short_path, horizons=(1, 4, 8))
    if any(o.available and o.horizon >= 4 for o in outs):
        findings.append(
            {
                "severity": "HIGH",
                "code": "INCOMPLETE_PATH_IMPUTED",
                "detail": [o.to_dict() for o in outs],
            }
        )

    # 5) Forensic write must raise
    try:
        refuse_write(repo_root / "artifacts" / "forensic_ban_probe_v14b")
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "FORENSIC_WRITE_NOT_BLOCKED",
                "detail": "refuse_write did not raise",
            }
        )
    except ForensicWriteAttemptError:
        pass

    # 6) Deterministic replay
    replay = verify_deterministic_study(seed="v14b-pass2-replay")
    if not replay["match"]:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "NON_DETERMINISTIC_ENGINE",
                "detail": replay,
            }
        )

    # 7) Seed divergence (no constant stub)
    a = run_blocked_fixture_study(seed="adv-a")
    b = run_blocked_fixture_study(seed="adv-b")
    if a["fingerprint"] == b["fingerprint"]:
        findings.append(
            {
                "severity": "HIGH",
                "code": "CONSTANT_FINGERPRINT_STUB",
                "detail": "Different seeds produced identical fingerprints",
            }
        )

    # 8) Pass1 contract
    if not pass1.get("pit_holds"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "PASS1_PIT_FALSE_PASS",
                "detail": "Pass1 reported without pit_holds",
            }
        )
    if not pass1.get("deterministic_replay"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "PASS1_REPLAY_FALSE_PASS",
                "detail": "Pass1 reported without deterministic_replay",
            }
        )
    if pass1.get("real_event_study_execution") is not False:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "PASS1_CLAIMED_REAL_STUDY",
                "detail": "Pass1 must keep real_event_study_execution=false",
            }
        )

    # 9) Hard bans remain False
    if any(HARD_BANS.values()):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "HARD_BAN_FLAG_TRUE",
                "detail": HARD_BANS,
            }
        )

    findings.append(
        {
            "severity": "INFO",
            "code": "FIXTURE_AND_FORENSIC_RO_ONLY",
            "detail": (
                "Engine proofs use synthetic fixtures; old campaign is RO forensic "
                "probe only. Real 14d Event Study remains BLOCKED."
            ),
            "status": "ACKNOWLEDGED",
        }
    )

    critical = [f for f in findings if f.get("severity") == "CRITICAL"]
    high = [f for f in findings if f.get("severity") == "HIGH"]
    return {
        "pass": "PASS_2",
        "findings": findings,
        "critical_count": len(critical),
        "high_count": len(high),
        "pit_proof": pit,
        "replay": replay,
        "seed_divergence_ok": a["fingerprint"] != b["fingerprint"],
        "missing_policy_ok": miss["missing_count"] == 1 and miss["silent_impute"] is False,
        "engine_status": ENGINE_STATUS,
        "real_event_study_status": REAL_EVENT_STUDY_STATUS,
        "real_event_study_execution": False,
        "adversarial_ok": len(critical) == 0 and len(high) == 0,
        "profitability_claimed": False,
    }
