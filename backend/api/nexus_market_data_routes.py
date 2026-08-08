"""NEXUS Phase 6.4 — Market Data & Feature Foundation API Routes.

All endpoints:
  - researchOnly = true
  - No private API calls
  - No secrets exposed
  - Cache-Control: no-store

Routes:
  GET /api/nexus/markets/<symbol>/candles?interval=&limit=
  GET /api/nexus/markets/<symbol>/snapshot
  GET /api/nexus/markets/<symbol>/indicators
  GET /api/nexus/market-intelligence/summary
  GET /api/nexus/data-providers/status
  GET /api/nexus/features/registry
"""
from __future__ import annotations

import time
from typing import Any

from flask import Blueprint, Response, jsonify, request

nexus_market_data_bp = Blueprint("nexus_market_data", __name__)


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def _err(msg: str, code: int = 500) -> tuple[Response, int]:
    resp = jsonify({"ok": False, "error": msg, "researchOnly": True})
    _no_store(resp)
    return resp, code


# ─────────────────────────────────────────────────────────────────────────────
# Candles
# ─────────────────────────────────────────────────────────────────────────────

@nexus_market_data_bp.route("/api/nexus/markets/<symbol>/candles")
def nexus_market_candles(symbol: str):
    """GET /api/nexus/markets/<symbol>/candles?interval=5m&limit=120

    Proxies Bybit public kline data. No private API.
    """
    interval = (request.args.get("interval") or "5m").strip()
    try:
        limit = min(300, max(1, int(request.args.get("limit") or 120)))
    except (ValueError, TypeError):
        limit = 120
    start = request.args.get("from") or request.args.get("start")
    end = request.args.get("to") or request.args.get("end")
    try:
        from backend.market.charts import bybit_public_charts as charts
        body = charts.fetch_ohlcv(
            symbol.upper().strip(),
            interval=interval,
            limit=limit,
            start=int(start) if start else None,
            end=int(end) if end else None,
        )
        body["researchOnly"] = True
        body["route"] = "nexus_market_data"
    except Exception as exc:  # noqa: BLE001
        body = {
            "ok": False,
            "error": str(exc),
            "symbol": symbol.upper().strip(),
            "bars": [],
            "researchOnly": True,
        }
    resp = jsonify(body)
    _no_store(resp)
    return resp


@nexus_market_data_bp.route("/api/nexus/markets/<symbol>/series")
def nexus_market_series(symbol: str):
    """GET /api/nexus/markets/<symbol>/series?interval=15m&limit=96

    Public-safe true market series contract (official OHLCV only).
    """
    interval = (request.args.get("interval") or "15m").strip()
    window_label = (request.args.get("window") or request.args.get("window_label") or "").strip() or None
    try:
        limit = min(300, max(1, int(request.args.get("limit") or 96)))
    except (ValueError, TypeError):
        limit = 96
    try:
        from backend.market.charts import bybit_public_charts as charts

        body = charts.fetch_market_series(
            symbol.upper().strip(),
            interval=interval,
            limit=limit,
            window_label=window_label,
        )
        body["route"] = "nexus_market_series"
    except Exception as exc:  # noqa: BLE001
        body = {
            "ok": False,
            "contract": "MARKET_SERIES_CONTRACT_V1",
            "symbol": symbol.upper().strip(),
            "interval": interval,
            "points": [],
            "insufficient": True,
            "fabricated": False,
            "error": str(exc),
            "researchOnly": True,
        }
    resp = jsonify(body)
    _no_store(resp)
    return resp


@nexus_market_data_bp.route("/api/nexus/markets/series")
def nexus_market_series_batch():
    """GET /api/nexus/markets/series?symbols=BTCUSDT,ETHUSDT&interval=5m&limit=48

    Batch public-safe series for Pulse / Radar / Watchlist sparks.
    """
    raw = (request.args.get("symbols") or "").strip()
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
    interval = (request.args.get("interval") or "5m").strip()
    window_label = (request.args.get("window") or request.args.get("window_label") or "").strip() or None
    try:
        limit = min(300, max(1, int(request.args.get("limit") or 48)))
    except (ValueError, TypeError):
        limit = 48
    try:
        max_symbols = min(24, max(1, int(request.args.get("max") or 24)))
    except (ValueError, TypeError):
        max_symbols = 24
    if not symbols:
        body = {
            "ok": False,
            "error": "symbols_required",
            "series": {},
            "contract": "MARKET_SERIES_CONTRACT_V1",
            "researchOnly": True,
        }
    else:
        try:
            from backend.market.charts import bybit_public_charts as charts

            body = charts.fetch_market_series_batch(
                symbols,
                interval=interval,
                limit=limit,
                window_label=window_label,
                max_symbols=max_symbols,
            )
            body["route"] = "nexus_market_series_batch"
        except Exception as exc:  # noqa: BLE001
            body = {
                "ok": False,
                "error": str(exc),
                "series": {},
                "contract": "MARKET_SERIES_CONTRACT_V1",
                "researchOnly": True,
            }
    resp = jsonify(body)
    _no_store(resp)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot (ticker)
# ─────────────────────────────────────────────────────────────────────────────

@nexus_market_data_bp.route("/api/nexus/markets/<symbol>/snapshot")
def nexus_market_snapshot(symbol: str):
    """GET /api/nexus/markets/<symbol>/snapshot

    Returns latest ticker snapshot for a symbol via Bybit public REST.
    """
    sym = symbol.upper().strip()
    try:
        from backend.api.market_public_routes import _fetch_ticker
        data = _fetch_ticker(sym)
        body: dict[str, Any] = {
            "ok": True,
            "symbol": sym,
            "snapshot": data,
            "researchOnly": True,
            "privateApi": False,
            "generatedAt": int(time.time() * 1000),
            "cache": "no-store",
        }
    except Exception as exc:  # noqa: BLE001
        body = {
            "ok": False,
            "symbol": sym,
            "error": str(exc),
            "researchOnly": True,
        }
    resp = jsonify(body)
    _no_store(resp)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Indicators
# ─────────────────────────────────────────────────────────────────────────────

@nexus_market_data_bp.route("/api/nexus/markets/<symbol>/indicators")
def nexus_market_indicators(symbol: str):
    """GET /api/nexus/markets/<symbol>/indicators?interval=5m&limit=120

    Fetches candles then computes all standard indicators.
    """
    sym = symbol.upper().strip()
    interval = (request.args.get("interval") or "5m").strip()
    try:
        limit = min(300, max(1, int(request.args.get("limit") or 200)))
    except (ValueError, TypeError):
        limit = 200
    try:
        from backend.market.charts import bybit_public_charts as charts
        candle_body = charts.fetch_ohlcv(sym, interval=interval, limit=limit)
        bars = candle_body.get("bars") or []
        if not bars:
            body: dict[str, Any] = {
                "ok": False,
                "symbol": sym,
                "error": "no_candle_data",
                "indicators": {},
                "researchOnly": True,
            }
        else:
            from backend.nexus_research.features.indicators import compute_all
            indicators = compute_all(bars)
            body = {
                "ok": True,
                "symbol": sym,
                "interval": interval,
                "barCount": len(bars),
                "indicators": indicators,
                "researchOnly": True,
                "privateApi": False,
                "generatedAt": int(time.time() * 1000),
                "cache": "no-store",
            }
    except Exception as exc:  # noqa: BLE001
        body = {
            "ok": False,
            "symbol": sym,
            "error": str(exc),
            "indicators": {},
            "researchOnly": True,
        }
    resp = jsonify(body)
    _no_store(resp)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Market Intelligence Summary
# ─────────────────────────────────────────────────────────────────────────────

@nexus_market_data_bp.route("/api/nexus/market-intelligence/summary")
def nexus_market_intelligence_summary():
    """GET /api/nexus/market-intelligence/summary

    Returns NEXUS Market Sentiment Index + Altcoin Breadth + Overall Direction.
    """
    try:
        from backend.nexus_research.features.market_intelligence import build_market_intelligence_summary
        candidate_states: list[dict[str, Any]] = []
        universe_states: list[dict[str, Any]] = []
        msi_components: dict[str, Any] = {}
        # Try to populate from market scanner if available
        try:
            from backend.market.scanner.scanner_service import get_market_scanner
            from backend.nexus_research.features.feature_observation_feed import (
                build_msi_components_from_scanner,
                refresh_feature_observations_from_scanner,
            )

            refresh_feature_observations_from_scanner()
            msi_components = build_msi_components_from_scanner()
            scanner = get_market_scanner()
            status = scanner.status()
            candidates = scanner.candidates(limit=50)
            for c in candidates:
                candidate_states.append({
                    "symbol": c.get("symbol"),
                    "direction": c.get("side") or "neutral",
                    "confirmed": bool(c.get("confirmed")),
                    "watch": bool(c.get("watch")),
                    "risk_blocked": bool(c.get("riskBlocked")),
                })
            # Build universe from tickers if available
            all_symbols = status.get("allSymbols") or []
            for sym in all_symbols[:50]:  # cap at 50
                universe_states.append({"symbol": sym, "change24hPct": None})
        except Exception:  # noqa: BLE001
            pass
        summary = build_market_intelligence_summary(
            msi_components=msi_components,
            universe_states=universe_states,
            candidate_states=candidate_states,
        )
        summary["ok"] = True
        # UI card adapter — keep nested indices and expose flat components[]
        msi = summary.get("nexusMarketSentimentIndex") or {}
        abi = summary.get("nexusAltcoinBreadthIndex") or {}
        direction = summary.get("nexusOverallMarketDirection") or {}
        now_ms = int(time.time() * 1000)

        def _msi_score(val: Any) -> float | None:
            if val is None:
                return None
            try:
                f = float(val)
            except (TypeError, ValueError):
                return None
            return round((f + 1.0) * 50.0, 2)

        def _abi_score(val: Any) -> float | None:
            if val is None:
                return None
            try:
                f = float(val)
            except (TypeError, ValueError):
                return None
            return round(f * 100.0, 2)

        dir_map = {
            "STRONG_LONG": 85,
            "LONG": 70,
            "NEUTRAL": 50,
            "MIXED": 50,
            "SHORT": 30,
            "STRONG_SHORT": 15,
            "UNAVAILABLE": None,
        }
        summary["updatedAt"] = now_ms
        summary["components"] = [
            {
                "id": "market_sentiment",
                "label": "NEXUS Market Sentiment",
                "score": _msi_score(msi.get("value")),
                "classification": msi.get("label") or "UNAVAILABLE",
                "change": None,
                "freshness": msi.get("quality") or "UNAVAILABLE",
                "coverage": None if msi.get("quality") == "UNAVAILABLE" else 1.0,
                "missing": [k for k, v in (msi.get("components") or {}).items() if (v or {}).get("quality") == "UNAVAILABLE"],
                "detail": msi.get("description"),
                "updatedAt": now_ms,
            },
            {
                "id": "altcoin_breadth",
                "label": "NEXUS Altcoin Breadth",
                "score": _abi_score(abi.get("value")),
                "classification": abi.get("label") or "UNAVAILABLE",
                "change": None,
                "freshness": abi.get("quality") or "UNAVAILABLE",
                "coverage": abi.get("availableCount"),
                "missing": ["equal_weight_tracked_universe"] if abi.get("quality") != "COMPLETE" else [],
                "detail": abi.get("description"),
                "updatedAt": now_ms,
            },
            {
                "id": "overall_direction",
                "label": "NEXUS Overall Market Direction",
                "score": dir_map.get(str(direction.get("value") or "UNAVAILABLE")),
                "classification": direction.get("value") or "UNAVAILABLE",
                "change": None,
                "freshness": direction.get("quality") or "UNAVAILABLE",
                "coverage": (direction.get("counts") or {}).get("total"),
                "missing": [],
                "detail": direction.get("description"),
                "updatedAt": now_ms,
            },
        ]
        body = summary
    except Exception as exc:  # noqa: BLE001
        body = {
            "ok": False,
            "error": str(exc),
            "researchOnly": True,
        }
    resp = jsonify(body)
    _no_store(resp)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Data Providers Status
# ─────────────────────────────────────────────────────────────────────────────

@nexus_market_data_bp.route("/api/nexus/data-providers/status")
def nexus_data_providers_status():
    """GET /api/nexus/data-providers/status

    Reports health and availability of data providers used by feature foundation.
    """
    providers: dict[str, Any] = {}
    # Bybit public REST probe
    try:
        from backend.market.charts import bybit_public_charts as charts
        result = charts.fetch_ohlcv("BTCUSDT", interval="1m", limit=1)
        providers["bybit_public_rest"] = {
            "available": result.get("ok", False),
            "source": "BYBIT_MAINNET_LINEAR",
            "privateApi": False,
            "latestBarCount": result.get("count", 0),
        }
    except Exception as exc:  # noqa: BLE001
        providers["bybit_public_rest"] = {
            "available": False,
            "error": str(exc),
            "privateApi": False,
        }
    # Market scanner probe
    try:
        from backend.market.scanner.scanner_service import get_market_scanner
        scanner_st = get_market_scanner().status()
        providers["market_scanner"] = {
            "available": True,
            "transport": scanner_st.get("transport"),
            "symbolCount": scanner_st.get("symbolCount"),
            "wsConnected": scanner_st.get("wsConnected"),
        }
    except Exception as exc:  # noqa: BLE001
        providers["market_scanner"] = {"available": False, "error": str(exc)}
    body: dict[str, Any] = {
        "ok": True,
        "providers": {
            **providers,
            "bybit_public_kline": {
                "status": "AVAILABLE" if providers.get("bybit_public_rest", {}).get("available") else "DEGRADED",
                "public_or_private": "public",
                "licensed": False,
            },
            "bybit_public_orderbook": {
                "status": "AVAILABLE_VIA_SCANNER_WS" if providers.get("market_scanner", {}).get("wsConnected") else "UNVERIFIED",
                "public_or_private": "public",
                "note": "orderbook foundation uses public WS when scanner connected; dedicated OF store experimental",
            },
            "bybit_public_trades": {
                "status": "AVAILABLE_VIA_SCANNER_WS" if providers.get("market_scanner", {}).get("wsConnected") else "UNVERIFIED",
                "public_or_private": "public",
            },
            "funding": {"status": "AVAILABLE", "public_or_private": "public", "source": "bybit_public"},
            "open_interest": {"status": "AVAILABLE", "public_or_private": "public", "source": "bybit_public"},
            "long_short_ratio": {"status": "EXPERIMENTAL_OR_PARTIAL", "public_or_private": "public"},
            "liquidations": {"status": "EXPERIMENTAL_OR_PARTIAL", "public_or_private": "public"},
            "onchain": {"status": "UNAVAILABLE_PROVIDER_PENDING", "value": None},
            "stablecoin_flow": {"status": "UNAVAILABLE_PROVIDER_PENDING", "value": None},
            "defi": {"status": "UNAVAILABLE_PROVIDER_PENDING", "value": None},
            "options": {"status": "UNAVAILABLE_PROVIDER_PENDING", "value": None},
            "social_sentiment": {"status": "UNAVAILABLE_PROVIDER_PENDING", "value": None},
            "macro": {"status": "UNAVAILABLE_PROVIDER_PENDING", "value": None},
        },
        "researchOnly": True,
        "privateApi": False,
        "generatedAt": int(time.time() * 1000),
        "cache": "no-store",
    }
    return _no_store(jsonify(body))


# ─────────────────────────────────────────────────────────────────────────────
# Feature Registry
# ─────────────────────────────────────────────────────────────────────────────

@nexus_market_data_bp.route("/api/nexus/features/registry")
def nexus_features_registry():
    """GET /api/nexus/features/registry

    Returns all registered feature definitions.
    """
    try:
        namespace = request.args.get("namespace") or None
        from backend.nexus_research.features.registry import get_feature_registry
        registry = get_feature_registry()
        definitions = registry.list_definitions(namespace=namespace)
        body: dict[str, Any] = {
            "ok": True,
            "definitions": [d.to_dict() for d in definitions],
            "count": len(definitions),
            "status": registry.status(),
            "researchOnly": True,
            "generatedAt": int(time.time() * 1000),
            "cache": "no-store",
        }
    except Exception as exc:  # noqa: BLE001
        body = {"ok": False, "error": str(exc), "researchOnly": True}
    return _no_store(jsonify(body))


# ─────────────────────────────────────────────────────────────────────────────
# Realtime stream (Phase 6.5 Gate E — public SSE hybrid)
# ─────────────────────────────────────────────────────────────────────────────

@nexus_market_data_bp.route("/api/nexus/markets/<symbol>/stream-status")
def nexus_market_stream_status(symbol: str):
    try:
        from backend.market.stream.market_stream import get_stream_status

        body = get_stream_status(symbol)
    except Exception as exc:  # noqa: BLE001
        body = {"ok": False, "error": str(exc), "researchOnly": True}
    return _no_store(jsonify(body))


@nexus_market_data_bp.route("/api/nexus/markets/<symbol>/stream")
def nexus_market_stream(symbol: str):
    """SSE stream — public kline updates with REST backfill."""
    from flask import Response

    from backend.market.stream.market_stream import sse_event_stream

    max_events = min(60, max(5, int(request.args.get("maxEvents") or 20)))

    def generate():
        for chunk in sse_event_stream(symbol, max_events=max_events):
            yield chunk

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Research-Only"] = "true"
    resp.headers["X-Private-Api"] = "false"
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Registration helper
# ─────────────────────────────────────────────────────────────────────────────

def register_nexus_market_data_routes(app: Any) -> None:
    """Register the nexus_market_data blueprint on a Flask app."""
    app.register_blueprint(nexus_market_data_bp)
