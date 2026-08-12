"""V18.2.29: V28 retrospective reclassification (BLUAIUSDT only).

Outputs:
  - V28_original_class
  - V28_reclassified_as { new_diagnostic_classification, confidence, supporting_factors }

Design constraints:
- No speculative imputation: if evidence fields are missing, output null+not_available_reason.
- UNAVOIDABLE_MARKET_OUTCOME is downgraded when direction ambiguity is supported by canonical tie evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from backend.nexus_research_ai_autonomy.entry_quality_v29 import audit_entry_quality_v29
from backend.nexus_research_ai_autonomy.stop_loss_audit_v29 import audit_stop_loss_quality


V28_CORE_PATH = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_28_core.json")


def _find_first(obj: Any, pred: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
    if isinstance(obj, dict):
        if pred(obj):
            return obj
        for v in obj.values():
            found = _find_first(v, pred)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for it in obj:
            found = _find_first(it, pred)
            if found is not None:
                return found
    return None


def _find_all(obj: Any, pred: Callable[[dict[str, Any]], bool]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if pred(obj):
            out.append(obj)
        for v in obj.values():
            out.extend(_find_all(v, pred))
    elif isinstance(obj, list):
        for it in obj:
            out.extend(_find_all(it, pred))
    return out


def _tie_supported_from_canonical(core: dict[str, Any]) -> dict[str, Any]:
    sealed = (core.get("CANONICAL_EVIDENCE") or {}).get("funnel_sealed") or {}
    long_score = sealed.get("selected_long_score")
    short_score = sealed.get("selected_short_score")
    try:
        long_r = round(float(long_score), 6)  # type: ignore[arg-type]
        short_r = round(float(short_score), 6)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return {"direction_ambiguity_supported": None, "not_available_reason": "scores_missing_or_non_numeric"}
    if long_r == short_r:
        return {
            "direction_ambiguity_supported": True,
            "direction_tie_supported_by_canonical": True,
            "selected_long_score": long_r,
            "selected_short_score": short_r,
        }
    return {
        "direction_ambiguity_supported": False,
        "direction_tie_supported_by_canonical": False,
        "selected_long_score": long_r,
        "selected_short_score": short_r,
    }


def reclassify_v28_bluaiusdt_loss(*, v28_core_path: Path = V28_CORE_PATH) -> dict[str, Any]:
    core = json.loads(v28_core_path.read_text(encoding="utf-8"))

    tie = _tie_supported_from_canonical(core)
    direction_ambiguity_supported = bool(tie.get("direction_ambiguity_supported"))

    # Original V28 class comes from REFLECTION lesson candidates for BLUAIUSDT.
    lesson_candidates = (((core.get("CHECKPOINT_30") or {}) or {}).get("REFLECTION") or {}).get("lesson_candidates")
    if lesson_candidates is None:
        lesson_candidates = (core.get("REFLECTION") or {}).get("lesson_candidates")
    if lesson_candidates is None:
        # fallback: any node with lesson_candidates list
        lesson_candidates = _find_all(core, lambda d: d.get("status") == "LESSON_CANDIDATE" and d.get("symbol") == "BLUAIUSDT")

    original_class = None
    orig_candidate = None
    if isinstance(lesson_candidates, list) and lesson_candidates:
        # Prefer candidates that match the known side from V28 evidence.
        for c in lesson_candidates:
            if isinstance(c, dict) and c.get("symbol") == "BLUAIUSDT":
                orig_candidate = c
                original_class = c.get("error_class")
                break
    else:
        orig_candidate = None

    # Extract lifecycle evidence for stop-lossed BLUAIUSDT to run the new audits.
    lifecycle = _find_first(
        core,
        lambda d: isinstance(d, dict)
        and d.get("symbol") == "BLUAIUSDT"
        and isinstance(d.get("exact_pnl_accounting"), dict)
        and (
            d.get("exit_reason") == "STOP_LOSS"
            or d.get("what_happened") == "STOP_LOSS"
            or (d.get("process_notes") or {}).get("exit_quality_class") == "VALID_CONTROLLED_LOSS"
        ),
    )

    if lifecycle is None:
        entry_quality = {"entry_quality_enabled": None, "not_available_reason": "lifecycle_for_bluaiusdt_not_found"}
        stop_quality = {"stop_quality_enabled": None, "not_available_reason": "lifecycle_for_bluaiusdt_not_found"}
    else:
        entry_quality = audit_entry_quality_v29(
            lifecycle=lifecycle, direction_ambiguity_supported=direction_ambiguity_supported
        )
        stop_quality = audit_stop_loss_quality(lifecycle)

    new_class = original_class
    confidence = 0.2
    supporting: list[str] = []

    if original_class == "UNAVOIDABLE_MARKET_OUTCOME" and direction_ambiguity_supported:
        new_class = "DIRECTION_AMBIGUOUS"
        confidence = 0.7
        supporting.append("canonical_funnel_sealed_selected_scores_tied_after_rounding")
    elif entry_quality.get("last_entry_class") == "AMBIGUOUS_DIRECTION":
        new_class = "DIRECTION_AMBIGUOUS"
        confidence = 0.6
        supporting.append("entry_quality_bucket=AMBIGUOUS_DIRECTION")
    else:
        confidence = 0.3
        supporting.append("no_direction_ambiguity_supported_from_available_evidence")

    if direction_ambiguity_supported:
        supporting.append(f"selected_long_score={tie.get('selected_long_score')}")
        supporting.append(f"selected_short_score={tie.get('selected_short_score')}")

    # Best-effort add cost/stop diagnostics as factors.
    if isinstance(entry_quality, dict) and entry_quality.get("fee_to_target_ratio") is not None:
        supporting.append(f"fee_to_target_ratio={entry_quality.get('fee_to_target_ratio')}")
    if isinstance(stop_quality, dict) and stop_quality.get("fee_to_stop_loss_ratio") is not None:
        supporting.append(f"fee_to_stop_loss_ratio={stop_quality.get('fee_to_stop_loss_ratio')}")

    return {
        "symbol": "BLUAIUSDT",
        "V28_original_class": original_class,
        "V28_reclassified_as": {
            "new_diagnostic_classification": new_class,
            "confidence": confidence,
            "supporting_factors": supporting,
        },
        "diagnostics": {
            "tie": tie,
            "entry_quality": entry_quality,
            "stop_quality": stop_quality,
        },
    }


if __name__ == "__main__":
    print(json.dumps(reclassify_v28_bluaiusdt_loss(), indent=2, default=str))

