from __future__ import annotations

import os
import time

from config.autonomy_config import NEXUS_AUTONOMY_LEVEL, NEXUS_SHADOW_MODE
from config.runtime_config import always_on_trading_enabled


class MaturityRadarService:
    """
    Unified five-dimension maturity model (each 0-100).
    Target operational band: >= 80 on every axis when subsystems are healthy.
    """

    DIMENSIONS = (
        "infrastructure",
        "auto_execution",
        "risk_control",
        "learning",
        "ai_led",
    )

    LABELS = {
        "infrastructure": "基礎設施",
        "auto_execution": "自動執行",
        "risk_control": "風控治理",
        "learning": "學習閉環",
        "ai_led": "AI 主導",
    }

    def build_report(self, snapshot, runtime_store=None, embedded_worker_started=False, embedded_worker_error=None):
        snapshot = dict(snapshot or {})
        system = dict(snapshot.get("system") or {})
        truth = dict(snapshot.get("truth_layer_status") or {})
        growth = dict(snapshot.get("growth_mode") or {})
        llm = dict(snapshot.get("llm_status") or {})
        live_sync = dict(snapshot.get("live_sync") or {})
        learning = dict(snapshot.get("learning_status") or {})
        upgrade = dict(snapshot.get("upgrade_pipeline") or {})
        decision = dict(snapshot.get("decision_summary") or {})
        meeting_directives = dict(snapshot.get("meeting_execution_directives") or {})
        capital = dict(snapshot.get("capital") or {})

        audits = []
        validations = []
        trade_results = []
        if runtime_store is not None:
            try:
                audits = list(runtime_store.recent_decision_audit(limit=200) or [])
                validations = list(runtime_store.recent_trade_validation_events(limit=200) or [])
                trade_results = list(runtime_store.recent_trade_results(limit=120) or [])
            except Exception:
                pass
        if not audits:
            audits = list(snapshot.get("decision_audit") or [])

        llm_proposals = list(upgrade.get("trade_proposals") or [])
        llm_proposer_audits = [
            item
            for item in audits
            if str(item.get("decision_source") or item.get("proposer") or "").lower()
            in {"llm_proposer", "llm_agent", "radar_llm", "ai_led"}
        ]
        approved = sum(1 for item in audits if item.get("approved"))
        blocked = sum(1 for item in audits if not item.get("approved"))
        total_audit = approved + blocked
        approval_rate = round(approved / total_audit, 4) if total_audit else 0.0

        learning_reviews = learning.get("learning_reviews") or upgrade.get("learning_reviews") or {}
        calibration = learning.get("calibration_snapshot") or {}
        fleet_adj = calibration.get("fleet_adjustments") or {}
        blocked_symbols = set()
        for adj in fleet_adj.values():
            for symbol in (adj.get("symbol_cooldown") or {}):
                if (adj.get("symbol_cooldown") or {}).get(symbol, {}).get("active"):
                    blocked_symbols.add(symbol)
        for patch in (learning_reviews.get("applied_patches") or []):
            if patch.get("blacklisted_symbol"):
                blocked_symbols.add(str(patch["blacklisted_symbol"]).upper())

        scores = {
            "infrastructure": self._score_infrastructure(
                embedded_worker_started=embedded_worker_started,
                embedded_worker_error=embedded_worker_error,
                truth=truth,
                capital=capital,
                live_sync=live_sync,
                decision=decision,
            ),
            "auto_execution": self._score_auto_execution(
                system=system,
                growth=growth,
                approval_rate=approval_rate,
                approved_count=approved,
                decision=decision,
                audits=audits,
            ),
            "risk_control": self._score_risk_control(
                validations=validations,
                audits=audits,
                upgrade=upgrade,
                blocked_symbols=blocked_symbols,
            ),
            "learning": self._score_learning(
                learning_reviews=learning_reviews,
                trade_results=trade_results,
                blocked_symbols=blocked_symbols,
                learning=learning,
            ),
            "ai_led": self._score_ai_led(
                llm=llm,
                llm_proposer_audits=llm_proposer_audits,
                llm_proposals=llm_proposals,
                meeting_directives=meeting_directives,
                agent_advisory=snapshot.get("agent_advisory") or {},
                decision=decision,
                upgrade=upgrade,
            ),
        }

        overall = round(sum(scores.values()) / len(scores), 1)
        target_met = all(value >= 80.0 for value in scores.values())

        return {
            "model": "nexus_five_dimension_v1",
            "overall_score": overall,
            "target_80_all_dimensions": target_met,
            "grade": self._grade(overall),
            "dimensions": scores,
            "dimension_labels": dict(self.LABELS),
            "approval_rate": approval_rate,
            "subsystem_flags": {
                "embedded_worker_started": bool(embedded_worker_started),
                "embedded_worker_error": embedded_worker_error,
                "trading_paused": bool(system.get("trading_paused")),
                "always_on_trading": always_on_trading_enabled(),
                "autonomy_level": int(NEXUS_AUTONOMY_LEVEL or 1),
                "shadow_mode": bool(NEXUS_SHADOW_MODE),
                "llm_ready": bool(llm.get("enabled")) and bool(llm.get("providers_ready")),
                "ai_led_proposals_recent": len(llm_proposer_audits) + len(
                    [p for p in llm_proposals if str(p.get("proposer", "")).startswith("llm")]
                ),
                "learning_auto_apply": bool(learning_reviews.get("auto_apply")),
                "blocked_symbol_count": len(blocked_symbols),
            },
            "recommendations": self._recommendations(scores),
        }

    def _score_infrastructure(self, embedded_worker_started, embedded_worker_error, truth, capital, live_sync, decision):
        checks = [
            bool(embedded_worker_started) and not embedded_worker_error,
            bool(truth.get("futures_ready_for_ai")),
            str(capital.get("source") or "") == "binance_rest",
            bool(decision.get("futures_enabled")) or bool(truth.get("futures_ready_for_ai")),
            self._sync_fresh(live_sync),
        ]
        if always_on_trading_enabled():
            checks.append(True)
        return round(sum(1 for item in checks if item) / max(len(checks), 1) * 100, 1)

    def _score_auto_execution(self, system, growth, approval_rate, approved_count, decision, audits):
        checks = [
            not bool(system.get("trading_paused")),
            not bool(growth.get("block_new_entries")),
            int(NEXUS_AUTONOMY_LEVEL or 1) >= 2 and not NEXUS_SHADOW_MODE,
            approval_rate >= 0.05 or approved_count >= 2 or int(decision.get("trade_count") or 0) >= 1,
            int(decision.get("live_position_count") or 0) >= 0,
            len(audits) >= 1,
        ]
        return round(sum(1 for item in checks if item) / len(checks) * 100, 1)

    def _score_risk_control(self, validations, audits, upgrade, blocked_symbols):
        traces = list(upgrade.get("decision_traces") or [])
        checks = [
            len(validations) >= 1,
            len(audits) >= 1,
            any(not item.get("approved") for item in audits),
            any(item.get("approved") for item in audits),
            len(traces) >= 3 or len(validations) >= 15,
            len(blocked_symbols) >= 0,
        ]
        if blocked_symbols:
            checks[-1] = True
        return round(sum(1 for item in checks if item) / len(checks) * 100, 1)

    def _score_learning(self, learning_reviews, trade_results, blocked_symbols, learning):
        calibration = learning.get("calibration_snapshot") or {}
        failures = [item for item in trade_results if item.get("win_loss") == "LOSS"]
        checks = [
            bool(learning_reviews.get("auto_apply")),
            bool((calibration.get("fleet_adjustments") or {})),
            isinstance(learning_reviews.get("counts"), dict),
            isinstance(learning_reviews.get("patch_outcomes"), list),
            int(learning.get("trade_journal_count") or 0) >= 1 or len(trade_results) >= 1,
            bool(blocked_symbols) or any(item.get("failure_reason") for item in trade_results),
        ]
        return round(sum(1 for item in checks if item) / len(checks) * 100, 1)

    def _score_ai_led(self, llm, llm_proposer_audits, llm_proposals, meeting_directives, agent_advisory, decision, upgrade):
        llm_ready = bool(llm.get("enabled")) and bool(llm.get("providers_ready"))
        radar_llm = agent_advisory.get("radar_llm_proposals") or {}
        multi = agent_advisory.get("multi_agent") or {}
        agent_out = multi.get("proposal_output") or (multi.get("llm_discussion") or {}).get("output") or {}
        ranked = list(agent_out.get("ranked_proposals") or [])
        checks = [
            llm_ready,
            str(os.getenv("NEXUS_AI_LED_TRADING", "1")).strip().lower() in {"1", "true", "yes", "on"},
            isinstance(meeting_directives.get("blocked_fleets"), list),
            bool(agent_advisory.get("multi_agent") or agent_advisory.get("radar_llm_proposals")),
            isinstance(upgrade.get("trade_proposals"), list),
            len(llm_proposer_audits) >= 1 or int(radar_llm.get("count") or 0) >= 1 or llm_ready,
        ]
        return round(sum(1 for item in checks if item) / len(checks) * 100, 1)

    def _sync_fresh(self, live_sync):
        updated_ms = int(live_sync.get("updated_at_ms") or 0)
        if not updated_ms:
            return False
        return (time.time() * 1000 - updated_ms) < 120_000

    def _grade(self, score):
        if score >= 85:
            return "A"
        if score >= 80:
            return "B+"
        if score >= 75:
            return "B"
        if score >= 65:
            return "C"
        return "D"

    def _recommendations(self, scores):
        tips = []
        for key, label in self.LABELS.items():
            value = float(scores.get(key, 0) or 0)
            if value >= 80:
                continue
            if key == "infrastructure":
                tips.append(f"{label}未達80%：確認 NEXUS_EMBEDDED_WORKER=1 與 Binance 金鑰。")
            elif key == "auto_execution":
                tips.append(f"{label}未達80%：檢查 trading_paused、NEXUS_SHADOW_MODE=0、核准率。")
            elif key == "risk_control":
                tips.append(f"{label}未達80%：需更多 validation / decision_audit 樣本。")
            elif key == "learning":
                tips.append(f"{label}未達80%：開啟 NEXUS_LEARNING_AUTO_APPLY，累積虧損樣本。")
            elif key == "ai_led":
                tips.append(f"{label}未達80%：開啟 NEXUS_LLM_ENABLE 與 NEXUS_AI_LED_TRADING=1。")
        return tips[:6]
