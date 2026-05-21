from __future__ import annotations

from datetime import datetime

from config.autonomy_config import STRATEGY_VERSION_ACTIVE


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class StrategyVersionRegistry:
    """P3 strategy version tracking (rotation suggestions, human-gated)."""

    def __init__(self, runtime_store):
        self.runtime_store = runtime_store
        self._ensure_defaults()

    def _ensure_defaults(self):
        versions = self.runtime_store.list_strategy_versions()
        if versions:
            return
        self.runtime_store.register_strategy_version(
            {
                "version_id": STRATEGY_VERSION_ACTIVE,
                "label": "Core adaptive fleets",
                "status": "active",
                "created_at": _now(),
                "notes": "Deterministic fleet engines + learning guardrails",
            }
        )

    def suggest_rotation(self, walk_forward_status, learning_status):
        walk_forward_status = walk_forward_status or {}
        learning_status = learning_status or {}
        positive_ratio = float(walk_forward_status.get("positive_window_ratio", 0.0) or 0.0)
        suggestion = {
            "timestamp": _now(),
            "active_version": STRATEGY_VERSION_ACTIVE,
            "recommendation": "hold",
            "reason": "performance_stable",
        }
        if walk_forward_status.get("ready") and positive_ratio < 0.35:
            suggestion["recommendation"] = "tighten_guards"
            suggestion["reason"] = "walk_forward_weak"
        elif walk_forward_status.get("ready") and positive_ratio > 0.65:
            suggestion["recommendation"] = "consider_scale_up"
            suggestion["reason"] = "walk_forward_strong"
        calibration = learning_status.get("calibration_snapshot", {})
        fleet_adj = calibration.get("fleet_adjustments", {}) or {}
        stressed = [fleet for fleet, data in fleet_adj.items() if data.get("pause_new_entries")]
        if stressed:
            suggestion["recommendation"] = "pause_rotation"
            suggestion["reason"] = f"fleets_under_stress:{','.join(stressed)}"
        self.runtime_store.append_strategy_rotation_suggestion(suggestion)
        return suggestion

    def snapshot(self):
        return {
            "active_version": STRATEGY_VERSION_ACTIVE,
            "versions": self.runtime_store.list_strategy_versions(),
            "rotation_suggestions": self.runtime_store.recent_strategy_rotation_suggestions(limit=10),
        }
