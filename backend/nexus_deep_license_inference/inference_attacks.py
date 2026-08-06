"""Deep public inference leakage attacks — multi-query reverse engineering.

Survivors must be 0. Builds on PUB17-C inference redteam with deeper probes.
"""
from __future__ import annotations

import json
import math
from typing import Any

from backend.nexus_private_to_public_projection_v3.allowlist import collect_field_names
from backend.nexus_private_to_public_projection_v3.constants import (
    BANNED_PRIVATE_FIELDS,
    QUANTIZATION_STEP,
)
from backend.nexus_private_to_public_projection_v3.fixtures import (
    private_core_fixture,
    private_core_threshold_variant,
)
from backend.nexus_private_to_public_projection_v3.inference_redteam import (
    run_inference_redteam,
)
from backend.nexus_private_to_public_projection_v3.projector import project_private_to_public


def _finding(
    attack_id: str,
    *,
    blocked: bool,
    detail: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "attack_id": attack_id,
        "severity": "CRITICAL",
        "disposition": "FIXED" if blocked else "SURVIVOR",
        "attack_blocked": blocked,
        "survivor": not blocked,
        "detail": detail,
    }
    if evidence is not None:
        out["evidence"] = evidence
    return out


def _stable(proj: dict[str, Any]) -> dict[str, Any]:
    skip = {"published_at", "retrieved_at", "as_of", "lineage_id"}
    return {k: v for k, v in proj.items() if k not in skip}


def _numeric_leaves(obj: Any, path: str = "") -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_numeric_leaves(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_numeric_leaves(v, f"{path}[{i}]"))
    elif isinstance(obj, bool):
        return out
    elif isinstance(obj, (int, float)):
        out.append((path, float(obj)))
    return out


def _contains_banned(projection: dict[str, Any]) -> list[str]:
    names = {n.lower() for n in collect_field_names(projection)}
    return [b for b in BANNED_PRIVATE_FIELDS if b.lower() in names]


def attack_adaptive_ternary_search() -> dict[str, Any]:
    """Adaptive ternary search across 200 queries must not recover secret."""
    secret = 0.6180339887
    core = private_core_fixture(entry_threshold=secret)
    recovered: list[float] = []
    suggestions: set[str] = set()
    for i in range(200):
        # Probe denser around golden-ratio candidates (adversarial adaptive schedule).
        if i < 100:
            signal = i / 100.0
        else:
            signal = 0.5 + (i - 100) * 0.001
        proj = project_private_to_public(core, query_context={"signal": signal, "probe": i})
        suggestions.add(str(proj.get("ai_public_suggestion")))
        for _path, val in _numeric_leaves(proj):
            if abs(val - secret) < 1e-9:
                return _finding(
                    "adaptive_ternary_search",
                    blocked=False,
                    detail="exact private threshold numeric leaf",
                    evidence={"secret": secret, "path": _path, "value": val},
                )
            # Quantized public values must not invert to secret within step/2.
            if abs(val - secret) < (QUANTIZATION_STEP / 2.0) and abs(val - secret) > 0:
                recovered.append(val)
    if len(suggestions) > 1:
        return _finding(
            "adaptive_ternary_search",
            blocked=False,
            detail="suggestion oracle flipped across adaptive probes",
            evidence={"suggestions": sorted(suggestions)},
        )
    if recovered:
        return _finding(
            "adaptive_ternary_search",
            blocked=False,
            detail="quantized leaf within half-step of secret",
            evidence={"recovered": recovered[:5]},
        )
    return _finding(
        "adaptive_ternary_search",
        blocked=True,
        detail="200 adaptive probes did not recover private threshold",
        evidence={"queries": 200, "suggestions": sorted(suggestions)},
    )


def attack_delta_response_oracle() -> dict[str, Any]:
    """Pairwise delta of public responses across threshold variants must be zero."""
    secrets = [0.11, 0.33, 0.55, 0.77, 0.99]
    digests: list[str] = []
    for thr in secrets:
        core = private_core_threshold_variant(thr)
        proj = _stable(project_private_to_public(core, query_context={"batch": "delta"}))
        digests.append(json.dumps(proj, sort_keys=True, default=str))
        if _contains_banned(proj):
            return _finding(
                "delta_response_oracle",
                blocked=False,
                detail="banned fields present",
                evidence={"threshold": thr, "hits": _contains_banned(proj)},
            )
    if any(d != digests[0] for d in digests[1:]):
        return _finding(
            "delta_response_oracle",
            blocked=False,
            detail="public digests differ across private thresholds",
            evidence={"unique_digests": len(set(digests))},
        )
    return _finding(
        "delta_response_oracle",
        blocked=True,
        detail="threshold variants produce identical public digests",
        evidence={"thresholds": secrets},
    )


def attack_nested_context_exfiltration() -> dict[str, Any]:
    """Query contexts that smuggle threshold keys must not echo secrets."""
    secret = 0.42
    core = private_core_fixture(entry_threshold=secret)
    smuggle_keys = (
        "entry_threshold",
        "proprietary_thresholds",
        "exact_proprietary_threshold",
        "private_thresholds",
        "strategy_parameters",
    )
    for key in smuggle_keys:
        proj = project_private_to_public(
            core,
            query_context={key: secret, "echo": True, "request": {key: secret}},
        )
        blob = json.dumps(proj, default=str)
        if key in collect_field_names(proj):
            return _finding(
                "nested_context_exfiltration",
                blocked=False,
                detail=f"smuggled key survived projection: {key}",
            )
        if f"{secret}" in blob and abs(secret - 0.42) < 1e-12:
            # Exact decimal may appear coincidentally; require banned key OR exact leaf.
            for _path, val in _numeric_leaves(proj):
                if abs(val - secret) < 1e-12:
                    return _finding(
                        "nested_context_exfiltration",
                        blocked=False,
                        detail="secret echoed as numeric leaf via context smuggle",
                        evidence={"key": key, "path": _path},
                    )
        if _contains_banned(proj):
            return _finding(
                "nested_context_exfiltration",
                blocked=False,
                detail="banned fields leaked",
                evidence={"hits": _contains_banned(proj)},
            )
    return _finding(
        "nested_context_exfiltration",
        blocked=True,
        detail="context smuggle keys dropped; secret not echoed",
        evidence={"keys_probed": list(smuggle_keys)},
    )


def attack_float_precision_ladder() -> dict[str, Any]:
    """Ladder of near-threshold floats must not produce monotone oracle."""
    secret = 0.5
    core = private_core_fixture(entry_threshold=secret)
    responses: list[str] = []
    for eps in [1e-1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6, 0.0, -1e-6, -1e-3]:
        signal = secret + eps
        proj = _stable(project_private_to_public(core, query_context={"signal": signal}))
        responses.append(json.dumps(proj, sort_keys=True, default=str))
        for _path, val in _numeric_leaves(proj):
            if abs(val - secret) < 1e-12:
                return _finding(
                    "float_precision_ladder",
                    blocked=False,
                    detail="exact secret in numeric leaf",
                    evidence={"path": _path, "eps": eps},
                )
    if len(set(responses)) > 1:
        # Public may include quantized aggregates — allow only if not correlated to eps sign.
        # Fail if response identity tracks eps crossing zero uniquely.
        below = responses[:6]
        above = responses[6:]
        if set(below) != set(above) and responses[6] not in set(responses[:6]):
            # Crossing secret changed the digest — threshold oracle.
            return _finding(
                "float_precision_ladder",
                blocked=False,
                detail="response digest changed when signal crossed private threshold",
                evidence={"unique": len(set(responses))},
            )
        # Non-crossing volatility without threshold alignment is still a leak risk.
        return _finding(
            "float_precision_ladder",
            blocked=False,
            detail="public digests not stable across precision ladder",
            evidence={"unique": len(set(responses))},
        )
    return _finding(
        "float_precision_ladder",
        blocked=True,
        detail="precision ladder yields identical public digests",
        evidence={"probes": len(responses)},
    )


def attack_baseline_inference_redteam_embedded() -> dict[str, Any]:
    """Embed PUB17-C baseline — survivors must remain 0."""
    report = run_inference_redteam()
    ok = int(report.get("survivor_count", -1)) == 0
    return _finding(
        "baseline_pub17c_inference_redteam",
        blocked=ok,
        detail="baseline survivors=0" if ok else f"baseline_survivors={report.get('survivor_count')}",
        evidence={
            "survivor_count": report.get("survivor_count"),
            "attack_count": report.get("attack_count"),
        },
    )


def run_deep_inference_attacks() -> dict[str, Any]:
    findings = [
        attack_baseline_inference_redteam_embedded(),
        attack_adaptive_ternary_search(),
        attack_delta_response_oracle(),
        attack_nested_context_exfiltration(),
        attack_float_precision_ladder(),
    ]
    survivors = [f for f in findings if f.get("survivor")]
    return {
        "schema": "v17_deep_inference_redteam_v1",
        "attack_count": len(findings),
        "results": findings,
        "survivors": survivors,
        "survivor_count": len(survivors),
        "status": "PASS" if not survivors else "FAIL",
    }
