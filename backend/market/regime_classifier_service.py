"""Background market regime: CHOP_RNG | TREND_BULL | HIGH_RISK_MACRO."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from config.regime_config import REGIME_LABELS, REGIME_LLM_ENABLED

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


class RegimeClassifierService:
    def __init__(self, llm_gateway=None):
        self.llm_gateway = llm_gateway
        self._state: Dict[str, Any] = {
            "label": "CHOP_RNG",
            "updated_at": _now(),
            "source": "bootstrap",
            "confidence": 0.5,
        }

    def start(self, *, bootstrap: bool = True) -> None:
        if bootstrap:
            try:
                self.refresh({})
            except Exception as exc:
                logger.warning("regime bootstrap failed: %s", exc)

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._state or {})

    def refresh(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        rule = self._classify_rules(payload)
        label = rule.get("label")
        source = "rules"
        if REGIME_LLM_ENABLED and self.llm_gateway and getattr(self.llm_gateway, "enabled", lambda: False)():
            llm = self._classify_llm(payload, rule)
            if llm.get("label") in REGIME_LABELS:
                label = llm["label"]
                source = "llm"
                rule["llm_rationale"] = llm.get("rationale", "")

        self._state = {
            "label": label,
            "updated_at": _now(),
            "source": source,
            "confidence": rule.get("confidence", 0.6),
            "inputs": {
                "btc_trend": payload.get("btc_trend"),
                "btc_atr_pct": payload.get("btc_atr_pct"),
                "external_alerts": (payload.get("external_alerts") or [])[:5],
            },
            "rule_hint": rule,
        }
        return self.snapshot()

    def _classify_rules(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        alerts = list(payload.get("external_alerts") or [])
        oi_stress = bool(payload.get("external_oi_stress"))
        whale = bool(payload.get("external_whale_dump_alert"))
        major_news = bool(payload.get("major_news_event"))
        btc_change = _safe_float(payload.get("btc_change_24h"))
        atr_pct = _safe_float(payload.get("btc_atr_pct"))
        trend = str(payload.get("btc_trend") or "neutral").lower()

        if oi_stress or whale or major_news:
            return {"label": "HIGH_RISK_MACRO", "confidence": 0.85, "reason": "external_risk"}
        if trend == "bullish" and btc_change > 0.01 and atr_pct >= 0.008:
            return {"label": "TREND_BULL", "confidence": 0.75, "reason": "btc_trend_up"}
        if atr_pct < 0.006 and abs(btc_change) < 0.008:
            return {"label": "CHOP_RNG", "confidence": 0.7, "reason": "low_vol_range"}
        if "btc_dominance_high" in " ".join(alerts):
            return {"label": "CHOP_RNG", "confidence": 0.65, "reason": "alt_chop"}
        return {"label": "CHOP_RNG", "confidence": 0.55, "reason": "default"}

    def _classify_llm(self, payload: Dict[str, Any], rule_hint: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = self.llm_gateway.run_task(
                "regime_classifier",
                {**payload, "rule_hint": rule_hint},
                fallback_output={"market_regime": rule_hint.get("label"), "rationale": rule_hint.get("reason", "")},
            )
            output = result.get("output") if isinstance(result.get("output"), dict) else result
            if not isinstance(output, dict):
                return {}
            label = str(output.get("market_regime") or output.get("label") or "").upper()
            return {
                "label": label if label in REGIME_LABELS else rule_hint.get("label"),
                "rationale": output.get("rationale", ""),
            }
        except Exception as exc:
            logger.warning("regime llm failed: %s", exc)
            return {"label": rule_hint.get("label"), "rationale": str(exc)}
