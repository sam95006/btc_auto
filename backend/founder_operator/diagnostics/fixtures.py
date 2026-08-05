"""Research-only simulated fixtures for Founder V16 diagnostics panels.

All values are explicit SIMULATED / mechanics-only research projections.
No fabricated LIVE claims. No exchange credentials. No real trade state.
"""
from __future__ import annotations

from typing import Any


def error_ontology_histogram() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "OK",
        "ontologyVersion": "v1.0.0",
        "totalClassified": 42,
        "histogram": {
            "GOOD_PROCESS_WIN": 8,
            "GOOD_PROCESS_LOSS": 11,
            "BAD_PROCESS_WIN": 4,
            "BAD_PROCESS_LOSS": 9,
            "UNAVOIDABLE_SHOCK": 3,
            "INSUFFICIENT_EVIDENCE": 7,
        },
        "dimensionCounts": {
            "DATA": 5,
            "REGIME": 4,
            "STRATEGY": 6,
            "ENTRY": 7,
            "EXIT": 5,
            "EXECUTION": 3,
            "COST": 4,
            "RISK": 5,
            "EXTERNAL_SHOCK": 3,
        },
        "realTradingLearning": False,
        "mechanicsOnly": True,
    }


def repeated_error_signatures() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "WATCH",
        "signatures": [
            {
                "signatureId": "sig:entry_rule_skip:v1",
                "dimension": "ENTRY",
                "processClass": "BAD_PROCESS_LOSS",
                "occurrences": 6,
                "lastSeenFixture": "V16A_FIX_bad_risk_loss",
                "severity": "HIGH",
            },
            {
                "signatureId": "sig:cost_gate_fail:v1",
                "dimension": "COST",
                "processClass": "BAD_PROCESS_WIN",
                "occurrences": 4,
                "lastSeenFixture": "V16A_FIX_bad_cost_win",
                "severity": "MEDIUM",
            },
            {
                "signatureId": "sig:insufficient_evidence:v1",
                "dimension": "DATA",
                "processClass": "INSUFFICIENT_EVIDENCE",
                "occurrences": 7,
                "lastSeenFixture": "V16A_FIX_insufficient",
                "severity": "LOW",
            },
        ],
        "repeatThreshold": 3,
        "promotionBlocked": True,
    }


def counterfactual_deltas() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "OK",
        "comparabilityGrade": "PARTIALLY_COMPARABLE",
        "pathsCovered": [
            "no_entry",
            "delay_entry",
            "alt_stop",
            "wait_confirm",
            "block_low_data_trust",
        ],
        "deltas": [
            {"path": "no_entry", "deltaPnlSim": 0.0, "preferable": True},
            {"path": "delay_entry", "deltaPnlSim": 1.2, "preferable": True},
            {"path": "alt_stop", "deltaPnlSim": -0.4, "preferable": False},
            {"path": "wait_confirm", "deltaPnlSim": 0.8, "preferable": True},
            {"path": "block_low_data_trust", "deltaPnlSim": 0.0, "preferable": True},
        ],
        "predictiveEdgeClaimed": False,
        "realMoney": False,
    }


def regime_transitions() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "OK",
        "currentLabels": {
            "trend": "RANGE",
            "volatility": "EXPANSION",
            "liquidity": "NORMAL",
        },
        "transitionProbability": 0.375,
        "flipCount": 3,
        "sampleSize": 8,
        "windowLabels": [
            "RANGE",
            "RANGE",
            "TREND_UP",
            "TREND_UP",
            "RANGE",
            "VOL_EXP",
            "VOL_EXP",
            "RANGE",
        ],
        "hysteresisArmed": True,
        "pitSafe": True,
        "predictiveEdgeClaimed": False,
    }


def strategy_router_weights() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "OK",
        "decisionSide": "WAIT",
        "noTradeFirstClass": True,
        "weights": {
            "TREND": 0.12,
            "MEAN_REVERSION": 0.10,
            "BREAKOUT": 0.08,
            "LIQUIDATION": 0.07,
            "FUNDING": 0.06,
            "OPEN_INTEREST": 0.06,
            "EVENT": 0.05,
            "VOLATILITY": 0.09,
            "CROSS_ASSET": 0.05,
            "DEFENSIVE_NO_TRADE": 0.32,
        },
        "routingFactors": [
            "regime_probs",
            "data_trust",
            "uncertainty",
            "lesson_restrictions",
        ],
        "exchangeWriteEnabled": False,
        "mainnetShortcut": False,
    }


def lesson_pipeline() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "BLOCKED_READY",
        "pipelineStates": [
            "CANDIDATE",
            "REPLAY_VALIDATED",
            "WALK_FORWARD_PENDING",
            "OOS_PENDING",
            "SHADOW_PENDING",
            "DEMO_PENDING",
            "ACTIVE",
            "DEGRADED",
            "RETIRED",
        ],
        "currentState": "REPLAY_VALIDATED",
        "activeBlocked": True,
        "rejectReasons": [
            "v23_incomplete_provider_capacity",
            "formal_wf_not_authorized",
            "oos_not_authorized",
            "real_lesson_active_forbidden",
            "ai_self_promote_blocked",
            "cherry_pick_blocked",
            "stage_skip_blocked",
        ],
        "realLessonActive": False,
        "promotionEnabled": False,
    }


def calibration_abstention() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "OK",
        "verdict": "ABSTAIN",
        "verdictLadder": ["ALLOW", "ALLOW_REDUCED", "WAIT", "ABSTAIN", "BLOCK"],
        "calibrationReliability": 0.71,
        "statedConfidence": 0.42,
        "agreementChannels": {
            "model_agreement": 0.55,
            "data_agreement": 0.62,
            "regime_agreement": 0.48,
            "risk_agreement": 0.70,
        },
        "abstentionRateSim": 0.34,
        "providerStatus": "OK",
        "realExecutionEnabled": False,
    }


def provider_health() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "OK",
        "primaryProvider": "research_fixture",
        "fallbackArmed": True,
        "latencyP50Ms": 120,
        "errorRate": 0.01,
        "v23Protocol": "SHADOW_COMPARE",
        "vendorKeysExposed": False,
        "routingEditorEnabled": False,
    }


def data_trust() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "OK",
        "trustScore": 0.78,
        "freshnessSec": 45,
        "lineageComplete": True,
        "pitViolations": 0,
        "coverageRatio": 0.91,
        "lowTrustBlocksRouting": True,
        "fabricatedLiveValues": False,
    }


def portfolio_risk() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "OK",
        "grossExposureSim": 0.0,
        "netExposureSim": 0.0,
        "openRealPositions": 0,
        "riskGovernorArmed": True,
        "capacityHeadroom": 1.0,
        "realMoney": False,
        "mainnet": False,
        "observeOnly": True,
    }


def memory_graph_health() -> dict[str, Any]:
    return {
        "mode": "SIMULATED",
        "health": "OK",
        "nodeCount": 128,
        "edgeCount": 240,
        "pitSafe": True,
        "publicProjectionSafe": True,
        "secretLeakCount": 0,
        "similarityIndexReady": True,
        "memberReadableRaw": False,
    }
