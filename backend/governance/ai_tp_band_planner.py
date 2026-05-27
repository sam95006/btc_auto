from __future__ import annotations


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class AiTpBandPlanner:
    """
    Suggest TP bands from technical context (ATR-based), without changing execution.

    Output is advisory-only and meant for UI/monitoring.
    """

    def suggest(self, position, market_context=None):
        position = dict(position or {})
        market_context = dict(market_context or {})
        entry = _safe_float(position.get("entry_price"))
        qty = abs(_safe_float(position.get("quantity")))
        side = str(position.get("side") or "BUY").upper()
        if entry <= 0 or qty <= 0:
            return None

        atr = _safe_float(market_context.get("atr_14"))
        mark = _safe_float(position.get("mark_price") or market_context.get("mark_price") or entry)
        if atr <= 0 or mark <= 0:
            return None

        sign = 1.0 if side in {"BUY", "LONG"} else -1.0
        # Simple ATR multiples; tuned for explanation rather than execution.
        levels = [
            {"tag": "TP1", "atr_mult": 1.0},
            {"tag": "TP2", "atr_mult": 1.8},
            {"tag": "TP3", "atr_mult": 2.8},
        ]
        out = []
        for spec in levels:
            move = atr * float(spec["atr_mult"])
            out.append(
                {
                    "tag": spec["tag"],
                    "atr_mult": round(float(spec["atr_mult"]), 3),
                    "target_price": round(entry + sign * move, 8),
                    "distance_pct": round(abs(move) / entry, 6) if entry > 0 else 0.0,
                }
            )

        trend_bias = str(market_context.get("trend_bias") or "neutral")
        technical_exit_score = _safe_float(market_context.get("technical_exit_score"))
        regime_change = bool(market_context.get("regime_change"))

        return {
            "mode": "advisory_atr_bands_v1",
            "mark_price": round(mark, 8),
            "atr_14": round(atr, 8),
            "trend_bias": trend_bias,
            "regime_change": regime_change,
            "technical_exit_score": round(technical_exit_score, 4),
            "suggested_tp_levels": out,
            "note": "建議 TP 區間（不影響實際出場；實際仍由既有 TP ladder / RExitEngine 每 tick 執行）。",
        }

