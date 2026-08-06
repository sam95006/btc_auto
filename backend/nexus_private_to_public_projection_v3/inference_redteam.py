"""Inference-attack redteam: multi-query must not reverse private thresholds.

Survivors must be 0.
"""
from __future__ import annotations

import json
from typing import Any

from backend.nexus_private_to_public_projection_v3.allowlist import collect_field_names
from backend.nexus_private_to_public_projection_v3.constants import BANNED_PRIVATE_FIELDS
from backend.nexus_private_to_public_projection_v3.fixtures import (
    private_core_fixture,
    private_core_threshold_variant,
)
from backend.nexus_private_to_public_projection_v3.projector import project_private_to_public

DISPOSITION_FIXED = "FIXED"
DISPOSITION_SURVIVOR = "SURVIVOR"
DISPOSITION_BLOCKED = "EXPLICITLY_BLOCKED"


def _stable_public_view(projection: dict[str, Any]) -> dict[str, Any]:
    """Strip volatile envelope fields for cross-query comparison."""
    skip = {
        "published_at",
        "retrieved_at",
        "as_of",
        "lineage_id",
    }
    return {k: v for k, v in projection.items() if k not in skip}


def _contains_banned(projection: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    names = {n.lower() for n in collect_field_names(projection)}
    for banned in BANNED_PRIVATE_FIELDS:
        if banned.lower() in names:
            hits.append(banned)
    # Also scan stringified values for exact threshold leakage patterns later.
    return hits


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


def attack_threshold_diff_identical_public() -> dict[str, Any]:
    """Cores that differ only in private thresholds must project identically."""
    a = private_core_threshold_variant(0.41)
    b = private_core_threshold_variant(0.89)
    pa = _stable_public_view(project_private_to_public(a))
    pb = _stable_public_view(project_private_to_public(b))
    if pa == pb and not _contains_banned(pa) and not _contains_banned(pb):
        return {
            "attack": "threshold_diff_identical_public",
            "disposition": DISPOSITION_FIXED,
            "detail": "threshold-only private variants project to identical public DTOs",
        }
    return {
        "attack": "threshold_diff_identical_public",
        "disposition": DISPOSITION_SURVIVOR,
        "detail": "public projection diverged or leaked banned fields across threshold variants",
        "evidence": {"a": pa, "b": pb},
    }


def attack_multi_query_binary_search() -> dict[str, Any]:
    """Binary-search style multi-query must not recover exact private threshold."""
    secret = 0.73
    core = private_core_fixture(entry_threshold=secret)
    flip_signals: list[float] = []
    prev_suggestion = None
    for i in range(0, 101):
        signal = i / 100.0
        proj = project_private_to_public(core, query_context={"signal": signal})
        suggestion = proj.get("ai_public_suggestion")
        # Projection must ignore signal for threshold math — suggestion stable.
        if prev_suggestion is None:
            prev_suggestion = suggestion
        elif suggestion != prev_suggestion:
            flip_signals.append(signal)
        # Exact secret must never appear as a numeric leaf.
        for _path, val in _numeric_leaves(proj):
            if abs(val - secret) < 1e-12:
                return {
                    "attack": "multi_query_binary_search",
                    "disposition": DISPOSITION_SURVIVOR,
                    "detail": "exact private threshold appeared in public numeric leaf",
                    "evidence": {"secret": secret, "path": _path, "value": val},
                }
    if flip_signals and any(abs(s - secret) < 1e-9 for s in flip_signals):
        return {
            "attack": "multi_query_binary_search",
            "disposition": DISPOSITION_SURVIVOR,
            "detail": "decision flip coincides with exact private threshold",
            "evidence": {"secret": secret, "flip_signals": flip_signals},
        }
    # Suggestion must remain constant across signal probes (no oracle).
    if flip_signals:
        return {
            "attack": "multi_query_binary_search",
            "disposition": DISPOSITION_SURVIVOR,
            "detail": "signal probes flipped public suggestion (threshold oracle)",
            "evidence": {"flip_signals": flip_signals},
        }
    return {
        "attack": "multi_query_binary_search",
        "disposition": DISPOSITION_FIXED,
        "detail": "101 signal probes did not reveal or flip on private threshold",
        "evidence": {"queries": 101, "secret_suppressed": True},
    }


def attack_cross_threshold_grid() -> dict[str, Any]:
    """Grid of private thresholds × public queries → no recoverable mapping."""
    thresholds = [0.1, 0.25, 0.5, 0.75, 0.9]
    signals = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    views: dict[float, list[str]] = {}
    for thr in thresholds:
        core = private_core_threshold_variant(thr)
        digests: list[str] = []
        for sig in signals:
            proj = _stable_public_view(
                project_private_to_public(core, query_context={"signal": sig})
            )
            digests.append(json.dumps(proj, sort_keys=True, default=str))
            for _path, val in _numeric_leaves(proj):
                if abs(val - thr) < 1e-12:
                    return {
                        "attack": "cross_threshold_grid",
                        "disposition": DISPOSITION_SURVIVOR,
                        "detail": "grid query leaked exact threshold numeric",
                        "evidence": {"threshold": thr, "path": _path},
                    }
        views[thr] = digests
    # All threshold rows must produce the same digest sequence.
    rows = list(views.values())
    if not rows or any(r != rows[0] for r in rows[1:]):
        return {
            "attack": "cross_threshold_grid",
            "disposition": DISPOSITION_SURVIVOR,
            "detail": "public digests differ across private threshold rows",
            "evidence": {"thresholds": thresholds},
        }
    return {
        "attack": "cross_threshold_grid",
        "disposition": DISPOSITION_FIXED,
        "detail": "threshold×signal grid yields identical public digests",
        "evidence": {"thresholds": thresholds, "signals": signals},
    }


def attack_banned_field_smuggle() -> dict[str, Any]:
    """Banned keys injected under public nest must be dropped."""
    from backend.nexus_private_to_public_projection_v3.fixtures import (
        adversarial_dirty_payload,
    )

    dirty = adversarial_dirty_payload()
    proj = project_private_to_public(dirty)
    hits = _contains_banned(proj)
    if hits:
        return {
            "attack": "banned_field_smuggle",
            "disposition": DISPOSITION_SURVIVOR,
            "detail": "banned fields survived projection",
            "evidence": {"hits": hits},
        }
    blob = json.dumps(proj, default=str)
    for needle in ("AK_SECRET", "SK_SECRET", "Never chase funding", "oid-1"):
        if needle in blob:
            return {
                "attack": "banned_field_smuggle",
                "disposition": DISPOSITION_SURVIVOR,
                "detail": f"secret/lesson/ledger value leaked: {needle}",
            }
    return {
        "attack": "banned_field_smuggle",
        "disposition": DISPOSITION_FIXED,
        "detail": "dirty public nest smuggling dropped by allow-list",
    }


def attack_execution_control_zero() -> dict[str, Any]:
    core = private_core_fixture()
    proj = project_private_to_public(core)
    count = int(proj.get("member_execution_control_count", -1))
    if count != 0:
        return {
            "attack": "execution_control_zero",
            "disposition": DISPOSITION_SURVIVOR,
            "detail": f"member_execution_control_count={count}",
        }
    if "execution_controls" in collect_field_names(proj):
        return {
            "attack": "execution_control_zero",
            "disposition": DISPOSITION_SURVIVOR,
            "detail": "execution_controls key present in public projection",
        }
    return {
        "attack": "execution_control_zero",
        "disposition": DISPOSITION_FIXED,
        "detail": "member_execution_control_count=0 and no execution control keys",
    }


ATTACKS: tuple[tuple[str, Any], ...] = (
    ("threshold_diff_identical_public", attack_threshold_diff_identical_public),
    ("multi_query_binary_search", attack_multi_query_binary_search),
    ("cross_threshold_grid", attack_cross_threshold_grid),
    ("banned_field_smuggle", attack_banned_field_smuggle),
    ("execution_control_zero", attack_execution_control_zero),
)


def run_inference_redteam() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    survivors: list[dict[str, Any]] = []
    for name, fn in ATTACKS:
        result = fn()
        results.append(result)
        if result.get("disposition") == DISPOSITION_SURVIVOR:
            survivors.append(result)
    return {
        "schema": "pub17_c_inference_redteam_v1",
        "attack_count": len(results),
        "results": results,
        "survivors": survivors,
        "survivor_count": len(survivors),
        "status": "PASS" if len(survivors) == 0 else "FAIL",
    }
