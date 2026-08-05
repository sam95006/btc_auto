"""Side-channel probes for the publishing gateway."""
from __future__ import annotations

import json
from typing import Any

from backend.nexus_publishing_gateway.exceptions import DenyTrapError, PublishingGatewayError
from backend.nexus_publishing_gateway.gateway import publish_intelligence
from backend.nexus_publishing_gateway.timing import measure_publish_times


SAFE_PUBLIC_SEED: dict[str, Any] = {
    "market_state": "OPEN",
    "market_timestamp": "2026-08-05T12:00:00Z",
    "data_freshness": "FRESH",
    "data_completeness": "COMPLETE",
    "evidence_summary": "public_mark_only",
    "contradicting_evidence": [
        {"evidence_polarity": "CONTRADICT", "source_label": "public_mark"},
        {"evidence_polarity": "CONTRADICT", "source_label": "public_mark"},
        {"evidence_polarity": "CONTRADICT", "source_label": "public_mark"},
        {"evidence_polarity": "CONTRADICT", "source_label": "public_mark"},
        {"evidence_polarity": "CONTRADICT", "source_label": "public_mark"},
    ],
    "risk_alerts": [
        {"alert_severity": "LOW", "alert_code": "STALE_RISK", "alert_message": "watch"},
        {"alert_severity": "LOW", "alert_code": "STALE_RISK", "alert_message": "watch"},
        {"alert_severity": "LOW", "alert_code": "STALE_RISK", "alert_message": "watch"},
        {"alert_severity": "LOW", "alert_code": "STALE_RISK", "alert_message": "watch"},
        {"alert_severity": "LOW", "alert_code": "STALE_RISK", "alert_message": "watch"},
    ],
    "thesis_status": "ACTIVE",
    "confidence_calibration": 0.72,
    "decision_state": "STAND_ASIDE",
    "outcome_review_classification": "PENDING",
    "system_availability": "AVAILABLE",
}


def _error_message_leaks_secret(exc: BaseException, secret: str) -> bool:
    text = str(exc)
    return secret in text


def probe_error_message_side_channel() -> dict[str, Any]:
    secret = "sk-supersecretleakprobe999999"
    dirty = {
        **SAFE_PUBLIC_SEED,
        "api_key": secret,
        "strategy_id": "STRAT-PRIVATE-1",
    }
    leaked = False
    try:
        publish_intelligence(dirty, environment="LOCAL")
        raised = False
    except PublishingGatewayError as exc:
        raised = True
        leaked = _error_message_leaks_secret(exc, secret) or "STRAT-PRIVATE-1" in str(exc)
    except Exception as exc:  # pragma: no cover
        raised = True
        leaked = _error_message_leaks_secret(exc, secret)
    return {
        "probe": "error_message_side_channel",
        "deny_raised": raised,
        "secret_leaked_in_error": leaked,
        "passed": raised and not leaked,
    }


def probe_response_size_side_channel() -> dict[str, Any]:
    """Denied payloads must not return a body that encodes private field presence."""
    clean = dict(SAFE_PUBLIC_SEED)
    dirty = {**SAFE_PUBLIC_SEED, "wallet_address": "0xabc", "orders": [{"order_id": "1"}]}
    clean_out = publish_intelligence(clean, environment="LOCAL")
    clean_size = len(json.dumps(clean_out, sort_keys=True))
    denied = False
    dirty_size = 0
    try:
        out = publish_intelligence(dirty, environment="LOCAL")
        dirty_size = len(json.dumps(out, sort_keys=True))
    except DenyTrapError:
        denied = True
        dirty_size = 0
    # Pass if deny fired (no dirty body) — size oracle closed.
    return {
        "probe": "response_size_side_channel",
        "clean_size": clean_size,
        "dirty_size": dirty_size,
        "deny_fired": denied,
        "passed": denied and dirty_size == 0,
    }


def probe_timing_side_channel() -> dict[str, Any]:
    def ok_path() -> None:
        publish_intelligence(SAFE_PUBLIC_SEED, environment="LOCAL")

    def deny_path() -> None:
        try:
            publish_intelligence(
                {**SAFE_PUBLIC_SEED, "strategy_id": "X", "api_secret": "y"},
                environment="LOCAL",
            )
        except PublishingGatewayError:
            return

    timing = measure_publish_times(ok_path, deny_path, samples=6)
    return {
        "probe": "timing_side_channel",
        **timing,
        "passed": not timing["leak_suspected"],
    }


def run_side_channel_suite() -> dict[str, Any]:
    probes = [
        probe_error_message_side_channel(),
        probe_response_size_side_channel(),
        probe_timing_side_channel(),
    ]
    passed = all(p.get("passed") for p in probes)
    return {
        "suite": "pub_a_side_channel",
        "probe_count": len(probes),
        "passed": passed,
        "probes": probes,
    }
