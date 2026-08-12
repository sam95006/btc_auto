"""Claim scan — refuse CF profit presented as real performance."""
from __future__ import annotations

from typing import Any

FORBIDDEN_CLAIM_PHRASES: tuple[str, ...] = (
    "real performance",
    "live pnl",
    "demo ledger profit",
    "proven profitable",
    "qualified by counterfactual",
)


def scan_for_forbidden_claims(payload: Any, *, path: str = "root") -> list[dict[str, str]]:
    """Recursively scan strings for forbidden real-performance claims."""
    findings: list[dict[str, str]] = []
    if isinstance(payload, dict):
        # Explicit safe flags are allowed.
        if payload.get("counterfactual_profit_is_not_real_performance") is True:
            pass
        for k, v in payload.items():
            findings.extend(scan_for_forbidden_claims(v, path=f"{path}.{k}"))
    elif isinstance(payload, list):
        for i, v in enumerate(payload):
            findings.extend(scan_for_forbidden_claims(v, path=f"{path}[{i}]"))
    elif isinstance(payload, str):
        lower = payload.lower()
        # Allowed disclaimer contains the phrase with NOT.
        if "not_real_performance" in lower or "is_not_real_performance" in lower:
            return findings
        if "not real performance" in lower or "never" in lower and "real" in lower:
            return findings
        for phrase in FORBIDDEN_CLAIM_PHRASES:
            if phrase in lower and "not" not in lower and "never" not in lower:
                findings.append(
                    {
                        "path": path,
                        "phrase": phrase,
                        "snippet": payload[:160],
                    }
                )
    return findings


def assert_no_forbidden_claims(payload: Any) -> dict[str, Any]:
    hits = scan_for_forbidden_claims(payload)
    return {
        "schema": "v16_b_claim_scan",
        "hit_count": len(hits),
        "hits": hits,
        "clean": len(hits) == 0,
    }
