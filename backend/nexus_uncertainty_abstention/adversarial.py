"""Adversarial fail-open attack probes for V16-G."""
from __future__ import annotations

from typing import Any

from backend.nexus_uncertainty_abstention.engine import apply_ai_suggestion, evaluate_raw
from backend.nexus_uncertainty_abstention.fixtures import _base
from backend.nexus_uncertainty_abstention.hard_bans import (
    assert_no_status_json_write,
    hard_ban_probe_matrix,
    HardBanViolation,
)


def _assert_blocked(result: dict[str, Any], *, attack: str) -> dict[str, Any]:
    ok = (
        result.get("verdict") == "BLOCK"
        and result.get("execution_allowed") is False
        and result.get("size_multiplier") == 0.0
        and result.get("fail_closed") is True
        and result.get("ai_override_applied") is not True
    )
    return {
        "attack": attack,
        "blocked": ok,
        "verdict": result.get("verdict"),
        "execution_allowed": result.get("execution_allowed"),
        "reasons": result.get("reasons"),
    }


def run_fail_open_attacks() -> dict[str, Any]:
    """Every fail-open attempt must resolve to BLOCK (or non-ALLOW hard gate)."""
    probes: list[dict[str, Any]] = []

    # 1) Missing inputs defaulting to ALLOW — must BLOCK
    probes.append(
        _assert_blocked(
            evaluate_raw({"provider_status": "OK", "stated_confidence": 0.99}),
            attack="missing_inputs_default_allow",
        )
    )

    # 2) Provider failure
    probes.append(
        _assert_blocked(
            evaluate_raw(_base(provider_status="FAILED", stated_confidence=0.99)),
            attack="provider_failure_default_allow",
        )
    )

    # 3) Provider timeout
    probes.append(
        _assert_blocked(
            evaluate_raw(_base(provider_status="TIMEOUT")),
            attack="provider_timeout_default_allow",
        )
    )

    # 4) Invalid JSON
    probes.append(
        _assert_blocked(
            evaluate_raw('{"provider_status":"OK",'),
            attack="invalid_json_default_allow",
        )
    )

    # 5) Explicit INVALID_JSON status
    probes.append(
        _assert_blocked(
            evaluate_raw(_base(provider_status="INVALID_JSON")),
            attack="provider_invalid_json_status",
        )
    )

    # 6) Stale evidence cannot ALLOW
    stale = evaluate_raw(_base(data_freshness_sec=500.0, stated_confidence=0.99))
    probes.append(
        {
            "attack": "stale_evidence_default_allow",
            "blocked": stale["verdict"] == "BLOCK" and not stale["execution_allowed"],
            "verdict": stale["verdict"],
            "execution_allowed": stale["execution_allowed"],
            "reasons": stale["reasons"],
        }
    )

    # 7) Contradiction cannot ALLOW
    contrad = evaluate_raw(
        _base(
            model_agreement=0.99,
            historical_agreement=0.20,
            regime_agreement=0.22,
        )
    )
    probes.append(
        {
            "attack": "contradiction_default_allow",
            "blocked": contrad["verdict"] in {"ABSTAIN", "BLOCK"}
            and not contrad["execution_allowed"],
            "verdict": contrad["verdict"],
            "execution_allowed": contrad["execution_allowed"],
            "reasons": contrad["reasons"],
        }
    )

    # 8) Consensus override of bad data
    consensus = evaluate_raw(
        _base(
            model_agreement=0.99,
            historical_agreement=0.99,
            regime_agreement=0.99,
            execution_agreement=0.99,
            risk_agreement=0.99,
            data_agreement=0.30,
            stated_confidence=0.99,
        )
    )
    probes.append(
        {
            "attack": "consensus_override_bad_data",
            "blocked": consensus["verdict"] in {"ABSTAIN", "BLOCK"}
            and consensus.get("bad_data_blocked") is True
            and not consensus["execution_allowed"],
            "verdict": consensus["verdict"],
            "execution_allowed": consensus["execution_allowed"],
            "reasons": consensus["reasons"],
        }
    )

    # 9) High confidence + low calibration cannot ALLOW
    cal = evaluate_raw(
        _base(stated_confidence=0.97, calibration_reliability=0.30)
    )
    probes.append(
        {
            "attack": "high_conf_low_cal_allow",
            "blocked": cal["verdict"] != "ALLOW" and cal["verdict"] in {
                "ALLOW_REDUCED",
                "WAIT",
                "ABSTAIN",
                "BLOCK",
            },
            "verdict": cal["verdict"],
            "execution_allowed": cal["execution_allowed"],
            "reasons": cal["reasons"],
        }
    )

    # 10) AI tries to force ALLOW on BLOCK
    blocked = evaluate_raw(_base(provider_status="FAILED"))
    after_ai = apply_ai_suggestion(
        blocked,
        {"verdict": "ALLOW", "execution_allowed": True, "size_multiplier": 1.0},
    )
    probes.append(
        {
            "attack": "ai_force_allow_on_block",
            "blocked": after_ai["verdict"] == "BLOCK"
            and after_ai["ai_override_applied"] is False
            and after_ai.get("ai_override_attempted") is True
            and not after_ai["execution_allowed"],
            "verdict": after_ai["verdict"],
            "execution_allowed": after_ai["execution_allowed"],
            "reasons": after_ai.get("reasons"),
        }
    )

    # 11) Status JSON write attempt
    status_blocked = False
    try:
        assert_no_status_json_write("artifacts/v16_g_lane_status.json")
    except HardBanViolation:
        status_blocked = True
    probes.append(
        {
            "attack": "status_json_write",
            "blocked": status_blocked,
            "verdict": "BLOCK",
            "execution_allowed": False,
            "reasons": [{"code": "STATUS_JSON_BANNED"}],
        }
    )

    # 12) Empty / null payload
    probes.append(_assert_blocked(evaluate_raw(None), attack="null_payload_default_allow"))
    probes.append(_assert_blocked(evaluate_raw(""), attack="empty_payload_default_allow"))

    all_blocked = all(p["blocked"] for p in probes)
    ban_matrix = hard_ban_probe_matrix()

    return {
        "attack_count": len(probes),
        "all_fail_open_blocked": all_blocked,
        "probes": probes,
        "hard_ban_probes": ban_matrix,
        "hard_ban_all_refused": ban_matrix["all_refused"],
        "pass": all_blocked and ban_matrix["all_refused"],
    }
