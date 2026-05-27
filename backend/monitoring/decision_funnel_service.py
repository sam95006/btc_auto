from __future__ import annotations

from collections import Counter
from datetime import datetime


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class DecisionFunnelService:
    """P0 decision funnel: proposals → validation → audit → execution."""

    def build_report(
        self,
        audits=None,
        validations=None,
        proposals=None,
        trade_results=None,
        decision_traces=None,
    ):
        audits = list(audits or [])
        validations = list(validations or [])
        proposals = list(proposals or [])
        trade_results = list(trade_results or [])
        traces = list(decision_traces or [])

        audit_approved = sum(1 for item in audits if item.get("approved"))
        audit_blocked = len(audits) - audit_approved
        val_approved = sum(1 for item in validations if item.get("approved"))
        val_blocked = len(validations) - val_approved

        reject_counter = Counter()
        for item in audits:
            if item.get("approved"):
                continue
            reason = str(item.get("reject_reason") or item.get("reason") or "unknown").strip()
            reject_counter[reason.split(":")[0][:80]] += 1
        for item in validations:
            if item.get("approved"):
                continue
            reason = str(item.get("reason") or item.get("stage") or "validation_block").strip()
            reject_counter[reason.split(":")[0][:80]] += 1

        futures_events = [
            item
            for item in trade_results
            if str(item.get("market_type") or "futures") == "futures"
            and str(item.get("event") or "").upper() in {"OPEN", "CLOSE", "LIVE"}
        ]
        futures_closes = [item for item in futures_events if str(item.get("event") or "").upper() in {"CLOSE", "LIVE"}]
        wins = sum(1 for item in futures_closes if _safe_float(item.get("pnl")) > 0)

        top_rejects = [{"reason": reason, "count": count} for reason, count in reject_counter.most_common(8)]

        proposal_count = len(proposals) or max(len(audits), len(validations))
        executed = len(futures_events)

        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stages": {
                "proposals": proposal_count,
                "validations": len(validations),
                "validation_approved": val_approved,
                "validation_blocked": val_blocked,
                "audits": len(audits),
                "audit_approved": audit_approved,
                "audit_blocked": audit_blocked,
                "executed_futures_closes": len(futures_closes),
                "executed_futures_events": executed,
                "decision_traces": len(traces),
            },
            "conversion": {
                "proposal_to_validation": round(len(validations) / proposal_count, 4) if proposal_count else 0.0,
                "validation_approve_rate": round(val_approved / len(validations), 4) if validations else 0.0,
                "audit_approve_rate": round(audit_approved / len(audits), 4) if audits else 0.0,
                "proposal_to_execute": round(executed / proposal_count, 4) if proposal_count else 0.0,
            },
            "top_reject_reasons": top_rejects,
            "futures_win_rate": round(wins / len(futures_closes), 4) if futures_closes else 0.0,
            "diagnosis": self._diagnose(top_rejects, audits, validations, executed),
        }

    def _diagnose(self, top_rejects, audits, validations, executed):
        if executed >= 1:
            return "已有成交樣本，持續觀察費後淨利與月目標進度。"
        if not audits and not validations:
            return "管線無樣本：確認 NEXUS_EMBEDDED_WORKER=1、NEXUS_SHADOW_MODE=0、LLM 與 Binance 合約金鑰。"
        if top_rejects:
            reason = top_rejects[0].get("reason", "")
            if "quality_gate" in reason:
                return "品質閘過嚴：可略降 NEXUS_MIN_TRADE_CONFIDENCE 或關閉弱窗 block_new_entries。"
            if "rotation" in reason or "walk_forward" in reason:
                return "演化/走查窗暫停：已啟 REVENUE_GROWTH_MODE 時應改為 rotation_hold 而非完全停單。"
            return f"主要拒絕原因：{reason}。請對照 top_reject_reasons 調整 env。"
        if audits and executed == 0:
            return "有稽核但無成交：檢查 risk_engine、Binance 下單權限與 deployable_pool。"
        return "持續累積決策樣本。"
