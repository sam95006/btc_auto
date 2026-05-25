from __future__ import annotations

import os
from datetime import datetime

from config.learning_config import (
    LIQUIDATION_PERMANENT_BLACKLIST,
    LIQUIDATION_REENTRY_LEVERAGE_CAP,
    LIQUIDATION_REENTRY_MIN_CONFIDENCE,
    LIQUIDATION_REENTRY_SIZE_MULT,
)

def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class LearningReviewQueue:
    """P1/P3 learning recommendations with draft -> approved -> applied workflow."""

    STATUSES = ("draft", "approved", "rejected", "applied")

    def __init__(self, runtime_store):
        self.runtime_store = runtime_store

    def enqueue_from_recommendation(self, recommendation, source="trade_loss"):
        recommendation = dict(recommendation or {})
        if not recommendation:
            return None
        status = "approved" if _env_bool("NEXUS_LEARNING_AUTO_APPROVE") or _env_bool("NEXUS_LEARNING_AUTO_APPLY") else "draft"
        item = {
            "timestamp": recommendation.get("timestamp") or _now(),
            "fleet": recommendation.get("fleet"),
            "symbol": recommendation.get("symbol"),
            "strategy_key": recommendation.get("strategy_key"),
            "source": source,
            "status": status,
            "recommendation": recommendation,
            "review_note": "",
        }
        review_id = self.runtime_store.append_learning_review(item)
        item["id"] = review_id
        if _env_bool("NEXUS_LEARNING_AUTO_APPLY") and status == "approved":
            self.apply_item(item)
        return item

    def enqueue_from_llm_reflection(self, llm_payload):
        llm_payload = dict(llm_payload or {})
        patterns = list(llm_payload.get("top_failure_patterns") or llm_payload.get("failure_patterns") or [])
        reviews = []
        for fleet, rec in dict(llm_payload.get("latest_recommendations_by_fleet") or {}).items():
            if isinstance(rec, dict):
                recommendation = {
                    "fleet": fleet,
                    "recommendation": rec.get("recommendation") or rec.get("summary"),
                    "signal_weight_adjustment": rec.get("signal_weight_adjustment", -0.02),
                    "strategy_confidence_adjustment": rec.get("strategy_confidence_adjustment", -0.02),
                    "disabled_pattern_candidate": patterns[0] if patterns else None,
                    "recommendation_only": False,
                    "source": "llm_reflection",
                }
            else:
                recommendation = {
                    "fleet": fleet,
                    "recommendation": str(rec),
                    "signal_weight_adjustment": -0.02,
                    "recommendation_only": False,
                    "source": "llm_reflection",
                }
            reviews.append(self.enqueue_from_recommendation(recommendation, source="llm_reflection"))
        return [item for item in reviews if item]

    def apply_item(self, item):
        item = dict(item or {})
        review_id = item.get("id")
        recommendation = dict(item.get("recommendation") or {})
        failure = recommendation.get("disabled_pattern_candidate")
        symbol = recommendation.get("symbol")
        symbol_lesson = None
        blacklisted_symbol = recommendation.get("blacklist_candidate")
        if failure == "exchange_liquidation":
            symbol_lesson = {
                "symbol": symbol,
                "lesson": "avoid_repeat_liquidation",
                "min_confidence": LIQUIDATION_REENTRY_MIN_CONFIDENCE,
                "leverage_cap": LIQUIDATION_REENTRY_LEVERAGE_CAP,
                "position_size_multiplier": LIQUIDATION_REENTRY_SIZE_MULT,
            }
            if LIQUIDATION_PERMANENT_BLACKLIST:
                blacklisted_symbol = symbol
            else:
                blacklisted_symbol = None
        patch = {
            "fleet": recommendation.get("fleet"),
            "strategy_key": recommendation.get("strategy_key"),
            "signal_weight_adjustment": recommendation.get("signal_weight_adjustment"),
            "confidence_penalty": abs(float(recommendation.get("strategy_confidence_adjustment", 0.02) or 0.02)),
            "position_size_multiplier": recommendation.get("position_size_multiplier_suggestion", 0.92),
            "leverage_cap": recommendation.get("recommended_leverage_cap"),
            "disabled_pattern": failure,
            "blacklisted_symbol": blacklisted_symbol,
            "symbol_lesson": symbol_lesson,
            "applied_at": _now(),
            "baseline_trade_count": int(recommendation.get("baseline_trade_count") or 0),
            "baseline_realized_pnl": float(recommendation.get("baseline_realized_pnl") or 0.0),
        }
        self.runtime_store.upsert_applied_learning_patch(patch)
        updater = getattr(self.runtime_store, "update_learning_review_status", None)
        if review_id and callable(updater):
            updater(review_id, "applied", "auto_apply")
        return patch

    def process_pending(self, limit=20):
        applied = []
        for item in self.runtime_store.recent_learning_reviews(status="approved", limit=limit):
            applied.append(self.apply_item(item))
        return applied

    def evaluate_patch_outcomes(self, recent_trades=None):
        patches = self.runtime_store.list_applied_learning_patches(limit=20)
        trades = list(recent_trades or [])
        outcomes = []
        for patch in patches[:12]:
            fleet = str(patch.get("fleet") or "").upper()
            fleet_trades = [
                item
                for item in trades
                if str(item.get("fleet") or "").upper() == fleet
            ][-20:]
            wins = sum(1 for item in fleet_trades if float(item.get("pnl", 0.0) or 0.0) > 0)
            losses = sum(1 for item in fleet_trades if float(item.get("pnl", 0.0) or 0.0) < 0)
            net_pnl = round(sum(float(item.get("pnl", 0.0) or 0.0) for item in fleet_trades), 4)
            outcomes.append(
                {
                    "fleet": fleet or None,
                    "applied_at": patch.get("applied_at"),
                    "recent_trades": len(fleet_trades),
                    "wins": wins,
                    "losses": losses,
                    "net_pnl": net_pnl,
                    "effective": (wins > losses) if fleet_trades else None,
                }
            )
        return outcomes

    def status_snapshot(self, limit=30, recent_trades=None):
        items = self.runtime_store.recent_learning_reviews(limit=limit)
        counts = {status: 0 for status in self.STATUSES}
        for item in items:
            status = str(item.get("status") or "draft")
            counts[status] = counts.get(status, 0) + 1
        return {
            "auto_apply": _env_bool("NEXUS_LEARNING_AUTO_APPLY"),
            "auto_approve": _env_bool("NEXUS_LEARNING_AUTO_APPROVE"),
            "counts": counts,
            "recent": items[:15],
            "applied_patches": self.runtime_store.list_applied_learning_patches(limit=20),
            "patch_outcomes": self.evaluate_patch_outcomes(recent_trades=recent_trades),
        }
