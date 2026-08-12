"""Extract AI Provider / model identifiers and classification provenance."""
from __future__ import annotations

from typing import Any


def extract_ai_provider_model_identifiers(
    decision: dict[str, Any],
) -> list[dict[str, str]]:
    """Collect provider/model identity tuples from reasoner + critic outputs.

    Missing provider/model is recorded as empty string — never invented.
    """
    ids: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(role: str, blob: dict[str, Any] | None) -> None:
        if not isinstance(blob, dict):
            return
        provider = str(
            blob.get("provider")
            or blob.get("provider_id")
            or blob.get("ai_provider")
            or ""
        )
        model = str(
            blob.get("model")
            or blob.get("model_id")
            or blob.get("model_name")
            or ""
        )
        key = (role, provider, model)
        if key in seen:
            return
        seen.add(key)
        ids.append({"role": role, "provider": provider, "model": model})

    for item in decision.get("AI_reasoner_outputs") or []:
        if isinstance(item, dict):
            _add("reasoner", item)
    critic = decision.get("independent_critic_output")
    if isinstance(critic, dict):
        _add("critic", critic)
    return ids


def transition_paths(decision: dict[str, Any]) -> tuple[list[str], list[str]]:
    history = list(decision.get("transition_history") or [])
    state_path: list[str] = []
    stage_path: list[str] = []
    for h in history:
        if not isinstance(h, dict):
            continue
        nxt = h.get("next_state") or h.get("to_state") or h.get("to") or h.get("state")
        if nxt:
            state_path.append(str(nxt))
        if h.get("stage"):
            stage_path.append(str(h["stage"]))
    return state_path, stage_path


def build_classification_provenance(decision: dict[str, Any]) -> dict[str, Any]:
    """Derive how the terminal Decision classification was reached.

    Provenance is structural (stage chain + risk authority + provider ids),
    not a learning or profitability proof.
    """
    state_path, stage_path = transition_paths(decision)
    risk = decision.get("deterministic_risk_result") or {}
    terminal = str(decision.get("decision_status") or "")
    classification = {
        "CLOSED": "lifecycle_closed_simulated",
        "REJECTED": "lifecycle_rejected_by_risk",
        "BLOCKED_AMBIGUOUS": "lifecycle_blocked_fail_closed",
        "CALIBRATED": "lifecycle_calibrated_pre_close",
        "UNDER_REVIEW": "lifecycle_under_review",
        "EXITED": "lifecycle_exited_simulated",
        "MONITORING": "lifecycle_monitoring_simulated",
        "APPROVED_SIMULATED": "lifecycle_approved_simulated",
    }.get(terminal, f"lifecycle_status_{terminal.lower() or 'unknown'}")

    return {
        "terminal_status": terminal,
        "classification_label": classification,
        "state_path": state_path,
        "stage_path": stage_path,
        "risk_allowed": risk.get("allowed"),
        "risk_authority": risk.get("authority"),
        "risk_reason": risk.get("reason"),
        "rejection_reasons": list(decision.get("rejection_reasons") or []),
        "blocked_reason": decision.get("blocked_reason"),
        "ai_provider_model_identifiers": extract_ai_provider_model_identifiers(decision),
        "linkage_authority": decision.get("linkage_authority"),
        "intent_id_present": bool(decision.get("intent_id")),
        "position_id_present": bool(decision.get("position_id")),
        "lesson_ids": list(decision.get("lesson_ids") or []),
        # Explicit non-claims — lesson_ids may exist structurally without proving learning.
        "learning_proven": False,
        "fabricated_learning_proof": False,
    }
