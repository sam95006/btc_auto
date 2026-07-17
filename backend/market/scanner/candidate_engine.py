"""NEXUS Long/Short candidate engine — research-only scores, no trading coupling."""
from __future__ import annotations

import time
from typing import Any

from backend.market.scanner import universe_config as cfg
from backend.market.scanner.score_config import (
    CANDIDATE_RISK_CONFIG,
    CANDIDATE_SCORE_CONFIG,
    CANDIDATE_STAGE_CONFIG,
)

SIDES = ("LONG", "SHORT", "NEUTRAL")
STAGES = (
    "WATCHING",
    "BUILDING",
    "AWAITING_CONFIRMATION",
    "CONFIRMED",
    "OVEREXTENDED",
    "COOLING",
    "EXPIRED",
    "INSUFFICIENT_DATA",
)


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _pct_change(cur: float | None, past: float | None) -> float | None:
    if cur is None or past is None or past == 0:
        return None
    return ((cur - past) / abs(past)) * 100.0


def change_at(history: list[dict[str, Any]], field: str, window_ms: int) -> float | None:
    if not history:
        return None
    now = int(history[-1].get("receivedAt") or 0)
    target = now - window_ms
    past = None
    for row in history:
        ts = int(row.get("receivedAt") or 0)
        if ts <= target:
            past = row
        else:
            break
    if past is None:
        # need at least window coverage from first sample
        first = history[0]
        if now - int(first.get("receivedAt") or 0) < window_ms * 0.85:
            return None
        past = first
    return _pct_change(history[-1].get(field), past.get(field))


def score_symbol(snap: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    now = int(time.time() * 1000)
    age = now - int(snap.get("receivedAt") or now)
    fresh = "LIVE" if age < 45_000 else ("DELAYED" if age < 120_000 else "STALE")

    px1 = change_at(history, "lastPrice", 60_000)
    px5 = change_at(history, "lastPrice", 300_000)
    px15 = change_at(history, "lastPrice", 900_000)
    oi1 = change_at(history, "openInterest", 60_000)
    oi5 = change_at(history, "openInterest", 300_000)
    oi15 = change_at(history, "openInterest", 900_000)

    insufficient = px5 is None and oi5 is None
    funding = snap.get("fundingRate")
    spread = snap.get("spreadBps")
    turnover = float(snap.get("turnover24h") or 0.0)
    oi_val = float(snap.get("openInterestValue") or 0.0)
    ch24 = float(snap.get("change24hPct") or 0.0)

    # Direction bias from available windows (prefer 5m, fallback 24h while collecting)
    mom = px5 if px5 is not None else (ch24 * 0.15 if insufficient else None)
    oi_mom = oi5 if oi5 is not None else None

    if mom is None:
        side = "NEUTRAL"
    elif mom > 0.15:
        side = "LONG"
    elif mom < -0.15:
        side = "SHORT"
    else:
        side = "NEUTRAL"

    reasons: list[str] = []
    conflicts: list[str] = []
    opp_parts: list[tuple[str, float]] = []
    conf_parts: list[tuple[str, float]] = []
    risk_parts: list[tuple[str, float]] = []

    if insufficient:
        stage = "INSUFFICIENT_DATA"
        reasons.append("資料累積中：尚未建立穩定 5 分鐘窗口")
        opportunity = 20.0
        confirmation = 10.0
        risk = 35.0
        opp_parts.append(("collecting", 20.0))
        conf_parts.append(("insufficient_window", 10.0))
        risk_parts.append(("data_gap", 35.0))
    else:
        # Opportunity: momentum + OI + turnover + liquidity
        mom_score = _clamp(abs(mom or 0) * 18.0)
        oi_score = _clamp(abs(oi_mom or 0) * 16.0) if oi_mom is not None else 8.0
        turn_score = _clamp((turnover / 50_000_000.0) * 25.0)
        liq_score = _clamp((oi_val / 20_000_000.0) * 20.0)
        sc = CANDIDATE_SCORE_CONFIG
        opportunity = _clamp(
            sc["opportunity_price_weight"] * mom_score
            + sc["opportunity_oi_weight"] * oi_score
            + sc["opportunity_turnover_weight"] * turn_score
            + sc["opportunity_liquidity_weight"] * liq_score
        )
        opp_parts = [
            ("price_momentum", round(mom_score, 1)),
            ("oi_change", round(oi_score, 1)),
            ("turnover_pace", round(turn_score, 1)),
            ("liquidity", round(liq_score, 1)),
        ]

        aligned = oi_mom is not None and ((mom or 0) * oi_mom > 0)
        persist = abs(mom or 0) >= 0.25 and (abs(px1 or 0) >= 0.05 if px1 is not None else False)
        spread_ok = spread is not None and spread <= cfg.MAX_SPREAD_BPS
        confirmation = 25.0
        sc = CANDIDATE_SCORE_CONFIG
        if aligned:
            confirmation += sc["confirmation_align_bonus"]
            reasons.append("價格與持倉同向確認")
            conf_parts.append(("price_oi_aligned", sc["confirmation_align_bonus"]))
        elif oi_mom is not None and mom is not None and mom * oi_mom < 0:
            conflicts.append("價格與持倉不同步")
            conf_parts.append(("price_oi_diverge", -sc["confirmation_diverge_penalty"]))
            confirmation -= sc["confirmation_diverge_penalty"]
        if persist:
            confirmation += sc["confirmation_persist_bonus"]
            reasons.append("動能持續")
            conf_parts.append(("momentum_persist", sc["confirmation_persist_bonus"]))
        if spread_ok:
            confirmation += sc["confirmation_spread_bonus"]
            conf_parts.append(("spread_ok", sc["confirmation_spread_bonus"]))
        else:
            conflicts.append("買賣價差偏寬")
            confirmation -= 10.0
            conf_parts.append(("wide_spread", -10.0))
        if abs(mom or 0) >= 0.4:
            reasons.append(f"5 分鐘價格變動 {mom:+.2f}%")
        if oi_mom is not None and abs(oi_mom) >= 0.3:
            reasons.append(f"5 分鐘持倉變動 {oi_mom:+.2f}%")
        confirmation = _clamp(confirmation)

        risk = 15.0
        rc = CANDIDATE_RISK_CONFIG
        if funding is not None and abs(funding) >= rc["funding_crowd_abs"]:
            risk += rc["funding_risk_bonus"]
            conflicts.append("資金費率偏離（擁擠風險）")
            risk_parts.append(("funding_crowd", rc["funding_risk_bonus"]))
        if abs(mom or 0) >= rc["overextend_5m_pct"]:
            risk += rc["overextend_risk_bonus"]
            conflicts.append("短線過熱勿追")
            risk_parts.append(("overextended", rc["overextend_risk_bonus"]))
        if spread is not None and spread > rc["wide_spread_bps"]:
            risk += 15.0
            risk_parts.append(("spread", 15.0))
        if fresh != "LIVE":
            risk += rc["stale_risk_bonus"]
            conflicts.append("資料延遲")
            risk_parts.append(("stale", rc["stale_risk_bonus"]))
        if oi_val < cfg.MIN_OI_VALUE_USDT * 1.5:
            risk += 10.0
            risk_parts.append(("low_oi", 10.0))
        risk = _clamp(risk)

        # Stage machine
        st = CANDIDATE_STAGE_CONFIG
        if fresh == "STALE":
            stage = "COOLING"
        elif abs(mom or 0) >= rc["overextend_5m_pct"] or risk >= 70:
            stage = "OVEREXTENDED"
        elif (
            confirmation >= st["confirmed_confirmation_min"]
            and opportunity >= st["confirmed_opportunity_min"]
            and side != "NEUTRAL"
        ):
            stage = "CONFIRMED"
        elif (
            confirmation >= st["awaiting_confirmation_min"]
            and opportunity >= st["awaiting_opportunity_min"]
            and side != "NEUTRAL"
        ):
            stage = "AWAITING_CONFIRMATION"
        elif opportunity >= st["building_opportunity_min"] and side != "NEUTRAL":
            stage = "BUILDING"
        elif side == "NEUTRAL":
            stage = "WATCHING"
        else:
            stage = "WATCHING"

    if not reasons and side != "NEUTRAL":
        reasons.append("動能與流動性達觀察門檻")
    if not reasons:
        reasons.append("暫無明確方向優勢")

    rank_score = opportunity * 0.45 + confirmation * 0.40 - risk * 0.25
    if side == "NEUTRAL":
        rank_score -= 20

    return {
        "symbol": snap["symbol"],
        "side": side,
        "stage": stage,
        "opportunityScore": round(opportunity, 1),
        "confirmationScore": round(confirmation, 1),
        "riskScore": round(risk, 1),
        "rankScore": round(rank_score, 2),
        "currentPrice": snap.get("lastPrice"),
        "priceChange1mPct": None if px1 is None else round(px1, 3),
        "priceChange5mPct": None if px5 is None else round(px5, 3),
        "priceChange15mPct": None if px15 is None else round(px15, 3),
        "oiChange1mPct": None if oi1 is None else round(oi1, 3),
        "oiChange5mPct": None if oi5 is None else round(oi5, 3),
        "oiChange15mPct": None if oi15 is None else round(oi15, 3),
        "fundingRate": funding,
        "turnoverPace": turnover,
        "spreadBps": spread,
        "openInterestValue": oi_val,
        "change24hPct": ch24,
        "markPrice": snap.get("markPrice"),
        "indexPrice": snap.get("indexPrice"),
        "volume24h": snap.get("volume24h"),
        "openInterest": snap.get("openInterest"),
        "reasons": reasons[:4],
        "conflicts": conflicts[:4],
        "invalidationContext": conflicts[0] if conflicts else "條件減弱或資料不足時退出觀察",
        "freshness": fresh,
        "source": "BYBIT_MAINNET_LINEAR",
        "researchOnly": True,
        "scoreBreakdown": {
            "opportunity": opp_parts,
            "confirmation": conf_parts,
            "risk": risk_parts,
        },
        "lastUpdatedAt": int(snap.get("receivedAt") or now),
        "historyPoints": len(history),
        "collecting": insufficient,
    }


def rank_candidates(
    scored: list[dict[str, Any]],
    previous: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    previous = previous or {}
    now = int(time.time() * 1000)
    longs = [c for c in scored if c["side"] == "LONG" and c["stage"] != "EXPIRED"]
    shorts = [c for c in scored if c["side"] == "SHORT" and c["stage"] != "EXPIRED"]
    longs.sort(key=lambda c: c["rankScore"], reverse=True)
    shorts.sort(key=lambda c: c["rankScore"], reverse=True)

    out: list[dict[str, Any]] = []
    for side_list, side in ((longs, "LONG"), (shorts, "SHORT")):
        for i, c in enumerate(side_list[: cfg.CANDIDATE_CAPACITY // 2], start=1):
            prev = previous.get(f"{c['symbol']}:{side}")
            prev_rank = prev.get("rank") if prev else None
            first_seen = prev.get("firstSeenAt", now) if prev else now
            item = {
                **c,
                "id": f"{c['symbol']}:{side}",
                "rank": i,
                "previousRank": prev_rank,
                "firstSeenAt": first_seen,
                "rankDelta": (prev_rank - i) if isinstance(prev_rank, int) else None,
            }
            out.append(item)
    # watching / insufficient / overextended pools (bounded)
    extras = [
        c
        for c in scored
        if c["side"] == "NEUTRAL" or c["stage"] in ("INSUFFICIENT_DATA", "OVEREXTENDED", "COOLING", "WATCHING")
    ]
    extras.sort(key=lambda c: c["opportunityScore"], reverse=True)
    for c in extras[:20]:
        if any(x["symbol"] == c["symbol"] and x["side"] == c["side"] for x in out):
            continue
        prev = previous.get(f"{c['symbol']}:{c['side']}")
        out.append(
            {
                **c,
                "id": f"{c['symbol']}:{c['side']}",
                "rank": None,
                "previousRank": prev.get("rank") if prev else None,
                "firstSeenAt": prev.get("firstSeenAt", now) if prev else now,
                "rankDelta": None,
            }
        )
    return out[: cfg.CANDIDATE_CAPACITY]
