"""NEXUS Phase 6.5 — Public market SSE stream foundation (no private API)."""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

_STREAM_STATE: dict[str, dict[str, Any]] = {}
_STATE_LOCK = threading.Lock()


def _key(symbol: str) -> str:
    return symbol.upper().strip()


def record_stream_event(symbol: str, event_type: str, payload: dict[str, Any]) -> None:
    k = _key(symbol)
    with _STATE_LOCK:
        st = _STREAM_STATE.setdefault(k, {
            "symbol": k,
            "lastEventAt": 0,
            "lastSeq": 0,
            "connected": True,
            "gapCount": 0,
            "events": [],
        })
        st["lastSeq"] = int(st.get("lastSeq") or 0) + 1
        st["lastEventAt"] = int(time.time() * 1000)
        evt = {
            "type": event_type,
            "seq": st["lastSeq"],
            "symbol": k,
            "at": st["lastEventAt"],
            "payload": payload,
        }
        st["events"] = (st.get("events") or [])[-50:] + [evt]


def get_stream_status(symbol: str) -> dict[str, Any]:
    """Honest stream mode: HYBRID_POLLING until real public WS ingress exists.

    Do NOT claim LIVE_STREAM when events are REST-poll derived.
    """
    k = _key(symbol)
    with _STATE_LOCK:
        st = dict(_STREAM_STATE.get(k) or {})
    now = int(time.time() * 1000)
    last = int(st.get("lastEventAt") or 0)
    age_ms = now - last if last else None
    # Freshness of hybrid poller — never upgrades streamMode to LIVE_STREAM
    freshness = "UNAVAILABLE"
    if age_ms is not None and age_ms < 15_000:
        freshness = "HYBRID_POLLING"
    elif age_ms is not None and age_ms < 60_000:
        freshness = "DEGRADED"
    elif age_ms is not None:
        freshness = "STALE"
    return {
        "ok": True,
        "researchOnly": True,
        "privateApi": False,
        "symbol": k,
        # Canonical honesty field (Gate F)
        "streamMode": "HYBRID_POLLING",
        "streamState": freshness,
        "liveStreamReady": False,
        "note": "SSE hybrid over public REST poll — not full WebSocket LIVE_STREAM",
        "lastEventAt": last or None,
        "ageMs": age_ms,
        "lastSeq": st.get("lastSeq", 0),
        "gapCount": st.get("gapCount", 0),
        "connected": st.get("connected", False),
        "transport": "sse_public_poll_hybrid",
        "fallback": "REST /api/nexus/markets/{symbol}/candles",
    }


def sse_event_stream(symbol: str, *, max_events: int = 30) -> Generator[str, None, None]:
    """SSE generator — polls public REST kline and emits normalized events."""
    sym = _key(symbol)
    yield f"data: {json.dumps({'type': 'heartbeat', 'symbol': sym, 'at': int(time.time()*1000)})}\n\n"
    sent = 0
    last_bar_time: Optional[int] = None
    while sent < max_events:
        try:
            from backend.market.charts import bybit_public_charts as charts

            body = charts.fetch_ohlcv(sym, interval="1m", limit=2)
            bars = body.get("bars") or []
            if bars:
                bar = bars[-1]
                t = int(bar.get("time") or 0)
                if last_bar_time != t:
                    record_stream_event(sym, "kline_update", bar)
                    if last_bar_time and t - last_bar_time > 120_000:
                        record_stream_event(sym, "gap_detected", {"prev": last_bar_time, "next": t})
                    last_bar_time = t
                    evt = {"type": "kline_update", "symbol": sym, "bar": bar, "freshness": body.get("freshness")}
                    yield f"data: {json.dumps(evt)}\n\n"
                    sent += 1
            record_stream_event(sym, "provider_status", {"source": "BYBIT_MAINNET_LINEAR", "ok": True})
        except Exception as exc:  # noqa: BLE001
            record_stream_event(sym, "provider_status", {"ok": False, "error": str(exc)})
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        time.sleep(5.0)
    yield f"data: {json.dumps({'type': 'stream_end', 'reason': 'max_events'})}\n\n"
