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

VOL_ZH = {"high": "波動偏高", "moderate": "波動中等", "low": "波動偏低"}
REGIME_ZH = {"RISK_ON": "偏多", "RISK_OFF": "偏防守", "NEUTRAL": "中性"}
SEVERITY = {"high": "high", "moderate": "medium", "low": "info"}


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


def detect_transitions(prev: dict[str, Any] | None, cur: dict[str, Any], now: str) -> list[dict[str, Any]]:
    """Real transitions since the last persisted state (regime + per-symbol volatility band)."""
    if not prev:
        return []
    events: list[dict[str, Any]] = []
    if prev.get("regime") and cur.get("regime") and prev["regime"] != cur["regime"]:
        events.append({
            "ts": now, "symbol": None, "kind": "regime", "severity": "high",
            "text": f"市場狀態轉變 {REGIME_ZH.get(prev['regime'], prev['regime'])} → {REGIME_ZH.get(cur['regime'], cur['regime'])}",
            "from": prev["regime"], "to": cur["regime"], "source": "binance_usdm_public",
        })
    pv, cv = prev.get("vol") or {}, cur.get("vol") or {}
    for sym, band in cv.items():
        old = pv.get(sym)
        if old and band and old != band:
            events.append({
                "ts": now, "symbol": sym.replace("USDT", ""), "kind": "volatility",
                "severity": SEVERITY.get(band, "info"),
                "text": f"{sym.replace('USDT', '')} 波動 {old.upper()} → {band.upper()}",
                "from": old, "to": band, "source": "binance_usdm_public",
            })
    return events


def current_observations(showcase: dict[str, Any]) -> list[dict[str, Any]]:
    """Always-populated, real current-state observations (not transitions)."""
    obs: list[dict[str, Any]] = []
    regime = (showcase.get("regime") or {}).get("value")
    ts = showcase.get("updated_at") or _now()
    if regime:
        obs.append({"ts": ts, "symbol": None, "kind": "regime", "severity": "info",
                    "text": f"市場狀態 {REGIME_ZH.get(regime, regime)}", "source": "binance_usdm_public"})
    for s in _ready_symbols(showcase):
        band = s.get("volatility")
        sym = s["symbol"].replace("USDT", "")
        pts = s.get("provider_timestamp") or ts
        if band:
            obs.append({"ts": pts, "symbol": sym, "kind": "volatility",
                        "severity": SEVERITY.get(band, "info"), "text": f"{sym} {VOL_ZH.get(band, band)}",
                        "source": "binance_usdm_public"})
    return obs


def build_events(showcase: dict[str, Any], stored: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (response, new_stored). Persists real transitions (bounded)."""
    if showcase.get("availability") != "READY":
        return ({"availability": "UNAVAILABLE", "reason": showcase.get("reason"),
                 "transitions": [], "observations": [], "source": "binance_usdm_public"},
                stored or {"state": None, "events": []})
    now = _now()
    cur_state = snapshot_state(showcase)
    prev_state = (stored or {}).get("state")
    prior_events = (stored or {}).get("events") or []
    transitions = detect_transitions(prev_state, cur_state, now)
    all_events = (prior_events + transitions)[-24:]
    new_stored = {"state": cur_state, "events": all_events}
    return ({
        "availability": "READY",
        "source": "binance_usdm_public",
        "updated_at": showcase.get("updated_at"),
        "transitions": list(reversed(all_events)),   # newest first
        "observations": current_observations(showcase),
    }, new_stored)


def build_brief(showcase: dict[str, Any]) -> dict[str, Any]:
    """Deterministic, rule-based Chinese market brief (NOT AI-generated)."""
    if showcase.get("availability") != "READY":
        return {"availability": "UNAVAILABLE", "reason": showcase.get("reason"),
                "generator": "deterministic_rule_based", "source": "binance_usdm_public"}
    syms = _ready_symbols(showcase)
    regime = (showcase.get("regime") or {}).get("value")
    posture = REGIME_ZH.get(regime, "中性") if regime else None

    lines: list[str] = []
    if posture:
        lines.append(f"市場目前{posture}。")
    for s in syms:
        sym = s["symbol"].replace("USDT", "")
        band = s.get("volatility")
        if band:
            lines.append(f"{sym} {VOL_ZH.get(band, band)}。")

    # "what to watch" = symbols with the widest 24h range
    ranked = sorted([s for s in syms if isinstance(s.get("range_pct"), (int, float))],
                    key=lambda s: s["range_pct"], reverse=True)
    watch = [f"{s['symbol'].replace('USDT','')}：24H 區間較寬" for s in ranked[:2]]
    risk = [f"{s['symbol'].replace('USDT','')}：波動偏高" for s in syms if s.get("volatility") == "high"]

    return {
        "availability": "READY",
        "generator": "deterministic_rule_based",   # honest: NOT AI-generated
        "source": "binance_usdm_public",
        "updated_at": showcase.get("updated_at"),
        "posture": posture,
        "regime": regime,
        "summary": lines,
        "watch": watch or ["目前無明顯需要關注的區間擴張"],
        "risk": risk or ["目前風險維持受控"],
        "data_used": [s["symbol"].replace("USDT", "") for s in syms],
    }
