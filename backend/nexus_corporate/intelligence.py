"""Public-safe, deterministic Corporate market intelligence.

Everything here is DERIVED from the real public market showcase (backend-computed
from binance_usdm_public). Nothing is fabricated: the market brief is a
deterministic, rule-based summary (NOT AI-generated, and clearly labelled as
such), and the intelligence feed reports real current-state observations plus
real transitions detected against the last persisted state. No private trading,
Founder AI, or private intelligence is ever exposed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SEVERITY = {"high": "high", "moderate": "medium", "low": "info"}
DEFAULT_LOCALE = "zh-TW"

# Compact localized vocabulary so feed/brief never mix languages.
REGIME_L = {
    "zh-TW": {"RISK_ON": "偏多", "RISK_OFF": "偏防守", "NEUTRAL": "中性"},
    "en-US": {"RISK_ON": "Risk-On", "RISK_OFF": "Risk-Off", "NEUTRAL": "Neutral"},
    "ja-JP": {"RISK_ON": "リスクオン", "RISK_OFF": "リスクオフ", "NEUTRAL": "中立"},
    "ko-KR": {"RISK_ON": "위험선호", "RISK_OFF": "위험회피", "NEUTRAL": "중립"},
}
VOL_L = {
    "zh-TW": {"high": "波動偏高", "moderate": "波動中等", "low": "波動偏低"},
    "en-US": {"high": "high volatility", "moderate": "moderate volatility", "low": "low volatility"},
    "ja-JP": {"high": "高ボラティリティ", "moderate": "中ボラティリティ", "low": "低ボラティリティ"},
    "ko-KR": {"high": "높은 변동성", "moderate": "중간 변동성", "low": "낮은 변동성"},
}
T = {
    "zh-TW": {"state": "市場狀態 {r}", "trans": "市場狀態轉變 {a} → {b}", "vtrans": "{s} 波動 {a} → {b}",
              "now": "市場目前{r}。", "watch": "{s}：24H 區間較寬", "no_watch": "目前無明顯需要關注的區間擴張",
              "risk": "{s}：波動偏高", "no_risk": "目前風險維持受控"},
    "en-US": {"state": "Market regime {r}", "trans": "Regime shift {a} → {b}", "vtrans": "{s} volatility {a} → {b}",
              "now": "The market is currently {r}.", "watch": "{s}: wide 24H range", "no_watch": "No notable range expansion right now",
              "risk": "{s}: elevated volatility", "no_risk": "Risk is currently contained"},
    "ja-JP": {"state": "市場状態 {r}", "trans": "市場状態の変化 {a} → {b}", "vtrans": "{s} ボラティリティ {a} → {b}",
              "now": "現在の市場は{r}です。", "watch": "{s}：24H レンジが拡大", "no_watch": "現在、目立つレンジ拡大はありません",
              "risk": "{s}：高いボラティリティ", "no_risk": "リスクは現在抑制されています"},
    "ko-KR": {"state": "시장 상태 {r}", "trans": "시장 상태 전환 {a} → {b}", "vtrans": "{s} 변동성 {a} → {b}",
              "now": "현재 시장은 {r}입니다.", "watch": "{s}: 24H 범위 확대", "no_watch": "현재 뚜렷한 범위 확대는 없습니다",
              "risk": "{s}: 높은 변동성", "no_risk": "리스크는 현재 통제되고 있습니다"},
}


def _loc(locale: str | None) -> str:
    return locale if locale in REGIME_L else DEFAULT_LOCALE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ready_symbols(showcase: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in showcase.get("symbols", []) if s.get("availability") == "READY" and s.get("price") is not None]


def snapshot_state(showcase: dict[str, Any]) -> dict[str, Any]:
    """Comparable state used to detect real transitions between polls."""
    return {
        "regime": (showcase.get("regime") or {}).get("value"),
        "vol": {s["symbol"]: s.get("volatility") for s in _ready_symbols(showcase)},
    }


def detect_transitions(prev: dict[str, Any] | None, cur: dict[str, Any], now: str, loc: str = DEFAULT_LOCALE) -> list[dict[str, Any]]:
    """Real transitions since the last persisted state. Persisted language-neutral
    (from/to codes); rendered text uses `loc` at read time."""
    if not prev:
        return []
    reg = REGIME_L[loc]
    events: list[dict[str, Any]] = []
    if prev.get("regime") and cur.get("regime") and prev["regime"] != cur["regime"]:
        events.append({
            "ts": now, "symbol": None, "kind": "regime", "severity": "high",
            "text": T[loc]["trans"].format(a=reg.get(prev["regime"], prev["regime"]), b=reg.get(cur["regime"], cur["regime"])),
            "from": prev["regime"], "to": cur["regime"], "source": "binance_usdm_public",
        })
    pv, cv = prev.get("vol") or {}, cur.get("vol") or {}
    for sym, band in cv.items():
        old = pv.get(sym)
        if old and band and old != band:
            events.append({
                "ts": now, "symbol": sym.replace("USDT", ""), "kind": "volatility",
                "severity": SEVERITY.get(band, "info"),
                "text": T[loc]["vtrans"].format(s=sym.replace("USDT", ""), a=old.upper(), b=band.upper()),
                "from": old, "to": band, "source": "binance_usdm_public",
            })
    return events


def current_observations(showcase: dict[str, Any], loc: str = DEFAULT_LOCALE) -> list[dict[str, Any]]:
    """Always-populated, real current-state observations (not transitions)."""
    obs: list[dict[str, Any]] = []
    regime = (showcase.get("regime") or {}).get("value")
    ts = showcase.get("updated_at") or _now()
    if regime:
        obs.append({"ts": ts, "symbol": None, "kind": "regime", "severity": "info",
                    "text": T[loc]["state"].format(r=REGIME_L[loc].get(regime, regime)), "source": "binance_usdm_public"})
    for s in _ready_symbols(showcase):
        band = s.get("volatility")
        sym = s["symbol"].replace("USDT", "")
        pts = s.get("provider_timestamp") or ts
        if band:
            obs.append({"ts": pts, "symbol": sym, "kind": "volatility",
                        "severity": SEVERITY.get(band, "info"), "text": f"{sym} {VOL_L[loc].get(band, band)}",
                        "source": "binance_usdm_public"})
    return obs


def build_events(showcase: dict[str, Any], stored: dict[str, Any] | None, locale: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (response, new_stored). Persists real transitions (bounded), rendered in `locale`."""
    loc = _loc(locale)
    if showcase.get("availability") != "READY":
        return ({"availability": "UNAVAILABLE", "reason": showcase.get("reason"), "locale": loc,
                 "transitions": [], "observations": [], "source": "binance_usdm_public"},
                stored or {"state": None, "events": []})
    now = _now()
    cur_state = snapshot_state(showcase)
    prev_state = (stored or {}).get("state")
    prior_events = (stored or {}).get("events") or []
    transitions = detect_transitions(prev_state, cur_state, now, loc)
    all_events = (prior_events + transitions)[-24:]
    new_stored = {"state": cur_state, "events": all_events}
    return ({
        "availability": "READY",
        "source": "binance_usdm_public",
        "locale": loc,
        "updated_at": showcase.get("updated_at"),
        "transitions": list(reversed(all_events)),   # newest first
        "observations": current_observations(showcase, loc),
    }, new_stored)


def build_brief(showcase: dict[str, Any], locale: str | None = None) -> dict[str, Any]:
    """Deterministic, rule-based market brief (NOT AI-generated), rendered in `locale`."""
    loc = _loc(locale)
    if showcase.get("availability") != "READY":
        return {"availability": "UNAVAILABLE", "reason": showcase.get("reason"), "locale": loc,
                "generator": "deterministic_rule_based", "source": "binance_usdm_public"}
    syms = _ready_symbols(showcase)
    regime = (showcase.get("regime") or {}).get("value")
    reg = REGIME_L[loc]
    posture = reg.get(regime) if regime else None

    lines: list[str] = []
    if posture:
        lines.append(T[loc]["now"].format(r=posture))
    for s in syms:
        band = s.get("volatility")
        if band:
            lines.append(f"{s['symbol'].replace('USDT', '')} {VOL_L[loc].get(band, band)}")

    ranked = sorted([s for s in syms if isinstance(s.get("range_pct"), (int, float))],
                    key=lambda s: s["range_pct"], reverse=True)
    watch = [T[loc]["watch"].format(s=s["symbol"].replace("USDT", "")) for s in ranked[:2]]
    risk = [T[loc]["risk"].format(s=s["symbol"].replace("USDT", "")) for s in syms if s.get("volatility") == "high"]

    return {
        "availability": "READY",
        "generator": "deterministic_rule_based",   # honest: NOT AI-generated
        "source": "binance_usdm_public",
        "locale": loc,
        "updated_at": showcase.get("updated_at"),
        "posture": posture,
        "regime": regime,
        "summary": lines,
        "watch": watch or [T[loc]["no_watch"]],
        "risk": risk or [T[loc]["no_risk"]],
        "data_used": [s["symbol"].replace("USDT", "") for s in syms],
    }
