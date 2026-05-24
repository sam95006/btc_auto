from __future__ import annotations

from collections import Counter
from datetime import datetime

from config.autonomy_config import NEXUS_AUTONOMY_LEVEL, NEXUS_SHADOW_MODE
from config.growth_mode_config import BOLD_TESTNET_ENABLED


def _parse_ts(value):
    if not value:
        return None
    for parser in (
        lambda raw: datetime.fromisoformat(str(raw)),
        lambda raw: datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            return parser(value)
        except Exception:
            continue
    return None


class TradingHealthService:
    """Aggregates decision quality, blockers, and subsystem readiness for the dashboard."""

    REJECT_LABELS = {
        "quality_below_growth_threshold": "品質門檻",
        "same_side_concentration_too_high": "同向集中度",
        "learning_pause_due_to_recent_losses": "學習暫停",
        "learning_symbol_cooldown": "幣種冷卻",
        "basis_dislocation": "Basis 偏移",
        "insufficient_liquidity": "流動性不足",
        "portfolio_governor_block": "組合風控",
        "validated_for_execution": "已通過驗證",
    }

    def build_report(self, snapshot, runtime_store=None):
        snapshot = dict(snapshot or {})
        system = dict(snapshot.get("system") or {})
        growth = dict(snapshot.get("growth_mode") or {})
        truth = dict(snapshot.get("truth_layer_status") or {})
        llm = dict(snapshot.get("llm_status") or {})
        live_sync = dict(snapshot.get("live_sync") or {})
        learning = dict(snapshot.get("learning_status") or {})
        upgrade = dict(snapshot.get("upgrade_pipeline") or {})
        event_registry = dict(snapshot.get("event_registry") or {})

        audits = []
        validations = []
        if runtime_store is not None:
            try:
                audits = list(runtime_store.recent_decision_audit(limit=240) or [])
                validations = list(runtime_store.recent_trade_validation_events(limit=240) or [])
            except Exception:
                audits = list(snapshot.get("decision_audit") or [])
                validations = []
        else:
            audits = list(snapshot.get("decision_audit") or [])

        reject_counter = Counter()
        approved_count = 0
        blocked_count = 0
        for item in audits:
            if item.get("approved"):
                approved_count += 1
            else:
                blocked_count += 1
                reason = str(item.get("reject_reason") or item.get("reason") or "unknown")
                reject_counter[reason] += 1

        for item in validations:
            if item.get("approved"):
                approved_count += 1
            else:
                blocked_count += 1
                reason = str(item.get("reason") or "unknown")
                reject_counter[reason] += 1

        total = approved_count + blocked_count
        approval_rate = round(approved_count / total, 4) if total else 0.0

        price_sources = live_sync.get("price_sources") or {}
        futures_aligned = any(
            str(source).startswith("binance_futures") for source in price_sources.values()
        )

        llm_enabled = bool(llm.get("enabled"))
        llm_ready = llm_enabled and bool(llm.get("providers_ready"))

        dimensions = {
            "price_alignment": self._score(futures_aligned, 0.55),
            "binance_sync": self._score(bool(truth.get("futures_ready_for_ai")), 0.35),
            "news_feed": self._score(int(live_sync.get("news_count") or 0) > 0, 0.25),
            "ai_advisory": self._score(llm_ready or (llm_enabled and llm.get("last_ok_task")), 0.45),
            "autonomy": self._score(
                int(NEXUS_AUTONOMY_LEVEL or 1) >= 2
                and not NEXUS_SHADOW_MODE
                and not system.get("trading_paused")
                and not growth.get("block_new_entries"),
                0.4,
            ),
            "learning_loop": self._score(
                bool((learning.get("learning_reviews") or upgrade.get("learning_reviews") or {}).get("auto_apply")),
                0.35,
            ),
            "execution_flow": self._score(approval_rate >= 0.08 or approved_count >= 1, max(0.15, approval_rate)),
            "event_intelligence": self._score(int(event_registry.get("event_count") or 0) >= 3, 0.3),
        }

        if BOLD_TESTNET_ENABLED:
            for key in ("autonomy", "execution_flow"):
                dimensions[key] = min(1.0, float(dimensions.get(key, 0.0)) + 0.12)

        overall = round(sum(dimensions.values()) / max(len(dimensions), 1) * 100, 1)

        top_rejects = [
            {
                "reason": reason,
                "label": self.REJECT_LABELS.get(reason, reason),
                "count": count,
            }
            for reason, count in reject_counter.most_common(8)
        ]

        recommendations = self._recommendations(
            dimensions=dimensions,
            top_rejects=top_rejects,
            growth=growth,
            llm=llm,
            system=system,
        )

        return {
            "overall_score": overall,
            "grade": self._grade(overall),
            "dimensions": {key: round(value * 100, 1) for key, value in dimensions.items()},
            "approval_rate": approval_rate,
            "approved_count": approved_count,
            "blocked_count": blocked_count,
            "top_reject_reasons": top_rejects,
            "recommendations": recommendations,
            "subsystem_flags": {
                "trading_paused": bool(system.get("trading_paused")),
                "block_new_entries": bool(growth.get("block_new_entries")),
                "futures_ready_for_ai": bool(truth.get("futures_ready_for_ai")),
                "llm_enabled": llm_enabled,
                "llm_ready": llm_ready,
                "price_source_futures_aligned": futures_aligned,
                "bold_testnet": BOLD_TESTNET_ENABLED,
            },
        }

    def _score(self, condition, fallback=0.0):
        return 1.0 if condition else float(fallback)

    def _grade(self, score):
        if score >= 85:
            return "A"
        if score >= 75:
            return "B"
        if score >= 65:
            return "C"
        return "D"

    def _recommendations(self, dimensions, top_rejects, growth, llm, system):
        tips = []
        if dimensions.get("price_alignment", 0) < 0.8:
            tips.append("價格來源尚未完全對齊 Testnet，請確認 BINANCE_FUTURES 已設定。")
        if not llm.get("enabled"):
            tips.append("開啟 NEXUS_LLM_ENABLE=1 並設定 GROQ/SAMBANOVA API key，AI 顧問才會常態參與。")
        elif not llm.get("providers_ready"):
            tips.append("LLM 已啟用但 provider 未就緒，請檢查 API key 與 Zeabur 環境變數。")
        if growth.get("block_new_entries"):
            tips.append(f"成長模式阻擋新倉：{growth.get('block_reason') or 'daily_loss_limit'}。")
        if system.get("trading_paused"):
            tips.append("系統交易暫停中，請查看警報與新聞熔斷。")
        if top_rejects:
            lead = top_rejects[0]
            tips.append(f"最大拒單原因：{lead.get('label')}（{lead.get('count')} 次）。")
        if dimensions.get("execution_flow", 0) < 0.5:
            tips.append("近端核准率偏低；可調 NEXUS_BOLD_MIN_QUALITY 或檢查 portfolio 集中度。")
        return tips[:6]
