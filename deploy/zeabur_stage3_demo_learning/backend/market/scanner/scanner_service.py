"""Bounded in-process read-only market scanner (Phase 1 + Phase 4 Track B WS).

Public Bybit REST + optional public WS · daemon thread · no trading path coupling.
Candidate scoring formula unchanged — recompute stays throttled to SNAPSHOT_INTERVAL.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from backend.market.intelligence.history_store import get_history_store
from backend.market.intelligence.outcome_store import get_outcome_store
from backend.market.intelligence.transition_store import get_transition_store
from backend.market.scanner import universe_config as cfg
from backend.market.scanner.bybit_public_ws import BybitPublicTickerWS
from backend.market.scanner.candidate_engine import rank_candidates, score_symbol
from backend.market.scanner.universe import build_universe, fetch_all_linear_tickers

logger = logging.getLogger(__name__)

_WS_HISTORY_MIN_GAP_MS = 5_000
_KEEP_FIELDS = (
    "markPrice",
    "indexPrice",
    "bid1",
    "ask1",
    "spreadBps",
    "change24hPct",
    "openInterest",
    "openInterestValue",
    "fundingRate",
    "nextFundingTime",
    "volume24h",
    "turnover24h",
)


class MarketScannerService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop_running = False
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._latest: dict[str, dict[str, Any]] = {}
        self._universe_meta: dict[str, Any] = {}
        self._candidates: list[dict[str, Any]] = []
        self._prev_candidates: dict[str, dict[str, Any]] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=cfg.EVENT_CAPACITY)
        self._event_keys: dict[str, int] = {}
        self._last_error = ""
        self._last_cycle_at = 0
        self._cycle_count = 0
        self._breadth: dict[str, int] = {
            "rising": 0,
            "falling": 0,
            "neutral": 0,
            "insufficient": 0,
        }
        self._started_at = 0
        # Phase 4 Track B transport / observability
        self._transport = "REST"
        self._ws: BybitPublicTickerWS | None = None
        self._ws_connected = False
        self._ws_reconnect_count = 0
        self._last_market_update_at = 0
        self._last_candidate_recompute_at = 0
        self._ws_updates = 0
        self._ws_ooo_blocked = 0
        self._ws_dup_suppressed = 0
        self._rest_fallback = False

    def start(self, *, bootstrap: bool = True) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._started_at = int(time.time() * 1000)
            self._thread = threading.Thread(
                target=self._poll_loop,
                name="nexus-market-scanner",
                daemon=True,
            )
            self._thread.start()
        if bootstrap:
            try:
                self.refresh_once()
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                logger.warning("scanner bootstrap failed: %s", exc)
            self._ensure_ws()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.stop(timeout=min(timeout, 2.0))
            except Exception:  # noqa: BLE001
                pass
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=timeout)

    def _ensure_ws(self) -> None:
        with self._lock:
            symbols = list(self._universe_meta.get("symbols") or list(self._latest.keys()))
        if not symbols:
            return
        if self._ws is None:
            self._ws = BybitPublicTickerWS(
                on_ticker=self._on_ws_ticker,
                on_status=self._on_ws_status,
                max_symbols=cfg.SYMBOL_LIMIT,
            )
            self._ws.start(symbols)
        else:
            self._ws.update_symbols(symbols)

    def _on_ws_status(self, st: str) -> None:
        with self._lock:
            if st == "open":
                self._ws_connected = True
                self._rest_fallback = False
                self._transport = "WS"
            elif st in ("reconnecting", "connecting"):
                self._ws_connected = False
                if self._latest:
                    self._rest_fallback = True
                    self._transport = "FALLBACK"
                else:
                    self._transport = "REST"
            elif st in ("closed", "error"):
                self._ws_connected = False
                if self._latest:
                    self._rest_fallback = True
                    self._transport = "FALLBACK"
            if self._ws is not None:
                st_body = self._ws.status()
                self._ws_reconnect_count = int(st_body.get("wsReconnectCount") or 0)

    def _on_ws_ticker(self, delta: dict[str, Any]) -> None:
        """Merge WS ticker into _latest only — no candidate recompute."""
        sym = str(delta.get("symbol") or "")
        if not sym:
            return
        now = int(time.time() * 1000)
        with self._lock:
            prev = self._latest.get(sym)
            exch = int(delta.get("exchangeTimestamp") or delta.get("receivedAt") or now)
            if prev is not None:
                prev_exch = int(prev.get("exchangeTimestamp") or prev.get("receivedAt") or 0)
                if exch < prev_exch:
                    self._ws_ooo_blocked += 1
                    return
                if (
                    exch == prev_exch
                    and delta.get("lastPrice") == prev.get("lastPrice")
                    and delta.get("openInterest") == prev.get("openInterest")
                ):
                    self._ws_dup_suppressed += 1
                    return
            merged = dict(prev or {})
            for k, v in delta.items():
                if v is not None:
                    merged[k] = v
            # keep-last for omitted delta fields
            if prev is not None:
                for k in _KEEP_FIELDS:
                    if merged.get(k) is None and prev.get(k) is not None:
                        merged[k] = prev[k]
            merged["symbol"] = sym
            merged["receivedAt"] = int(delta.get("receivedAt") or now)
            merged["exchangeTimestamp"] = exch
            merged["source"] = "BYBIT_MAINNET_LINEAR"
            self._latest[sym] = merged
            self._last_market_update_at = merged["receivedAt"]
            self._ws_updates += 1
            self._ws_connected = True
            self._rest_fallback = False
            self._transport = "WS"
            # Throttled history append for denser 5m windows — not every tick
            hist = self._history.get(sym)
            if hist is None:
                hist = deque(maxlen=cfg.HISTORY_CAPACITY_PER_SYMBOL)
                self._history[sym] = hist
            append = True
            if hist:
                last = hist[-1]
                if merged["receivedAt"] - int(last.get("receivedAt") or 0) < _WS_HISTORY_MIN_GAP_MS:
                    append = False
            if append:
                hist.append(dict(merged))
            sample_price = merged.get("lastPrice")
            sample_oi = merged.get("openInterest")
            sample_turn = merged.get("turnover24h")
            sample_ts = merged.get("receivedAt")
        try:
            if sample_price is not None:
                get_history_store().append_sample(
                    sym,
                    price=sample_price,
                    oi=sample_oi,
                    turnover=sample_turn,
                    ts=sample_ts,
                )
                get_outcome_store().on_price(sym, float(sample_price), now=int(sample_ts or now))
        except Exception:  # noqa: BLE001
            pass

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            if self._loop_running:
                self._stop.wait(cfg.SNAPSHOT_INTERVAL_SEC)
                continue
            try:
                self.refresh_once()
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                logger.warning("scanner cycle failed: %s", exc)
            self._stop.wait(cfg.SNAPSHOT_INTERVAL_SEC)

    def refresh_once(self) -> dict[str, Any]:
        """REST bootstrap / reconciliation + throttled candidate recompute."""
        if self._loop_running:
            return {"ok": False, "error": "overlap_blocked"}
        self._loop_running = True
        try:
            tickers = fetch_all_linear_tickers()
            uni = build_universe(tickers=tickers)
            now = int(time.time() * 1000)
            scored: list[dict[str, Any]] = []
            breadth = {"rising": 0, "falling": 0, "neutral": 0, "insufficient": 0}

            with self._lock:
                active = set(uni["symbols"])
                # prune
                for sym in list(self._history.keys()):
                    if sym not in active:
                        self._history.pop(sym, None)
                        self._latest.pop(sym, None)

                for row in uni["rows"]:
                    sym = row["symbol"]
                    prev = self._latest.get(sym)
                    # REST reconciliation: keep fresher WS lastPrice if very recent
                    if (
                        prev
                        and self._ws_connected
                        and int(prev.get("receivedAt") or 0) > now - 3_000
                        and prev.get("lastPrice") is not None
                    ):
                        merged = dict(row)
                        for k in _KEEP_FIELDS:
                            if prev.get(k) is not None:
                                merged[k] = prev.get(k) if row.get(k) is None else row.get(k)
                        # Prefer REST structural fields; keep WS lastPrice if newer exch ts
                        prev_exch = int(prev.get("exchangeTimestamp") or 0)
                        row_exch = int(row.get("exchangeTimestamp") or 0)
                        if prev_exch >= row_exch:
                            merged["lastPrice"] = prev.get("lastPrice")
                            merged["receivedAt"] = prev.get("receivedAt")
                            merged["exchangeTimestamp"] = prev_exch
                        row = merged
                    hist = self._history.get(sym)
                    if hist is None:
                        hist = deque(maxlen=cfg.HISTORY_CAPACITY_PER_SYMBOL)
                        self._history[sym] = hist
                    hist.append(row)
                    self._latest[sym] = row
                    self._last_market_update_at = max(
                        self._last_market_update_at, int(row.get("receivedAt") or now)
                    )
                    sc = score_symbol(row, list(hist))
                    scored.append(sc)
                    if sc.get("collecting"):
                        breadth["insufficient"] += 1
                    elif (sc.get("priceChange5mPct") or 0) > 0.1:
                        breadth["rising"] += 1
                    elif (sc.get("priceChange5mPct") or 0) < -0.1:
                        breadth["falling"] += 1
                    else:
                        breadth["neutral"] += 1
                    try:
                        get_history_store().append_sample(
                            sym,
                            price=row.get("lastPrice"),
                            oi=row.get("openInterest"),
                            turnover=row.get("turnover24h"),
                            ts=row.get("receivedAt"),
                        )
                        if row.get("lastPrice"):
                            get_outcome_store().on_price(
                                sym, float(row["lastPrice"]), now=int(row.get("receivedAt") or now)
                            )
                    except Exception:  # noqa: BLE001
                        pass

                prev_snap = dict(self._prev_candidates)
                ranked = rank_candidates(scored, self._prev_candidates)
                self._emit_events(ranked)
                try:
                    get_transition_store().record_from_candidates(
                        ranked, prev_snap, source_snapshot_at=now
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("transition record failed: %s", exc)
                self._maybe_track_outcomes(ranked)
                self._prev_candidates = {c["id"]: c for c in ranked if c.get("id")}
                self._candidates = ranked
                self._breadth = breadth
                self._universe_meta = {
                    k: uni[k]
                    for k in (
                        "source",
                        "generatedAt",
                        "total_linear_instruments",
                        "total_tickers_seen",
                        "eligible_before_limit",
                        "eligible_after_limit",
                        "excluded_count",
                        "symbol_limit",
                        "ranking_basis",
                        "refresh_interval_sec",
                        "symbols",
                        "excluded_sample",
                        "read_only",
                        "private_api",
                        "api_key_used",
                    )
                    if k in uni
                }
                self._last_cycle_at = now
                self._last_candidate_recompute_at = now
                self._cycle_count += 1
                self._last_error = ""
                if not self._ws_connected:
                    self._transport = "FALLBACK" if self._rest_fallback or self._ws is not None else "REST"
            # Start / refresh WS after first REST universe is known
            self._ensure_ws()
            return {"ok": True, "symbols": len(uni["symbols"]), "candidates": len(ranked)}
        finally:
            self._loop_running = False

    def _maybe_track_outcomes(self, ranked: list[dict[str, Any]]) -> None:
        """Start research outcome trackers for new top / stage-confirmed candidates."""
        store = get_outcome_store()
        for c in ranked:
            if c.get("rank") is None or c["rank"] > 3:
                continue
            if c.get("stage") not in ("CONFIRMED", "AWAITING_CONFIRMATION", "BUILDING"):
                continue
            px = c.get("currentPrice")
            if px is None:
                continue
            aid = f"cand:{c.get('id')}:{c.get('stage')}:{c.get('firstSeenAt')}"
            store.ensure_tracking(
                anomaly_id=aid,
                symbol=str(c.get("symbol")),
                anomaly_type="CANDIDATE_TOP",
                severity="research",
                direction="UP" if c.get("side") == "LONG" else "DOWN",
                score=c.get("opportunityScore"),
                observed_at=c.get("lastUpdatedAt"),
                reference_price=float(px),
                evidence={
                    "stage": c.get("stage"),
                    "rank": c.get("rank"),
                    "side": c.get("side"),
                },
            )

    def _emit_events(self, ranked: list[dict[str, Any]]) -> None:
        now = int(time.time() * 1000)
        cooldown_ms = 90_000

        def allow(key: str) -> bool:
            last = self._event_keys.get(key, 0)
            if now - last < cooldown_ms:
                return False
            self._event_keys[key] = now
            return True

        for c in ranked:
            if c.get("rank") is not None and c["rank"] <= 5 and c.get("previousRank") is None:
                key = f"new_top:{c['id']}"
                if allow(key):
                    self._events.appendleft(
                        {
                            "id": f"{key}:{now}",
                            "type": "NEW_TOP_CANDIDATE",
                            "symbol": c["symbol"],
                            "side": c["side"],
                            "stage": c["stage"],
                            "rank": c["rank"],
                            "explanation": f"新{'做多' if c['side']=='LONG' else '做空'}機會進入前五：{c['symbol']}",
                            "timestamp": now,
                        }
                    )
            if c.get("rankDelta") and c["rankDelta"] >= 3:
                key = f"rank_up:{c['id']}"
                if allow(key):
                    self._events.appendleft(
                        {
                            "id": f"{key}:{now}",
                            "type": "RANK_UP",
                            "symbol": c["symbol"],
                            "side": c["side"],
                            "stage": c["stage"],
                            "rank": c["rank"],
                            "rankDelta": c["rankDelta"],
                            "explanation": f"{c['symbol']} 排名上升 {c['rankDelta']} 名",
                            "timestamp": now,
                        }
                    )
            prev = self._prev_candidates.get(c["id"])
            if prev and prev.get("stage") != c.get("stage"):
                key = f"stage:{c['id']}:{c['stage']}"
                if allow(key):
                    label = {
                        "CONFIRMED": "已確認",
                        "OVEREXTENDED": "過熱勿追",
                        "COOLING": "條件減弱",
                        "EXPIRED": "條件已失效",
                        "AWAITING_CONFIRMATION": "等待確認",
                        "BUILDING": "形成中",
                    }.get(c["stage"], c["stage"])
                    self._events.appendleft(
                        {
                            "id": f"{key}:{now}",
                            "type": "STAGE_CHANGE",
                            "symbol": c["symbol"],
                            "side": c["side"],
                            "stage": c["stage"],
                            "rank": c.get("rank"),
                            "explanation": f"{c['symbol']} 進入「{label}」",
                            "timestamp": now,
                        }
                    )
            if c.get("stage") == "OVEREXTENDED":
                key = f"over:{c['id']}"
                if allow(key):
                    self._events.appendleft(
                        {
                            "id": f"{key}:{now}",
                            "type": "OVEREXTENDED",
                            "symbol": c["symbol"],
                            "side": c["side"],
                            "stage": c["stage"],
                            "rank": c.get("rank"),
                            "explanation": f"{c['symbol']} 過熱勿追",
                            "timestamp": now,
                        }
                    )

    def status(self) -> dict[str, Any]:
        with self._lock:
            age = int(time.time() * 1000) - self._last_cycle_at if self._last_cycle_at else None
            fresh = "COLLECTING"
            if self._last_cycle_at:
                fresh = "LIVE" if (age or 0) < 45_000 else ("DELAYED" if (age or 0) < 120_000 else "STALE")
            longs = sum(1 for c in self._candidates if c.get("side") == "LONG" and c.get("rank"))
            shorts = sum(1 for c in self._candidates if c.get("side") == "SHORT" and c.get("rank"))
            confirmed = sum(1 for c in self._candidates if c.get("stage") == "CONFIRMED")
            high_risk = sum(
                1 for c in self._candidates if c.get("stage") == "OVEREXTENDED" or (c.get("riskScore") or 0) >= 70
            )
            ws_body = self._ws.status() if self._ws is not None else {}
            return {
                "ok": True,
                "read_only": True,
                "private_api": False,
                "api_key_used": False,
                "researchOnly": True,
                "trading_integration": False,
                "source": "BYBIT_MAINNET_LINEAR",
                "generatedAt": int(time.time() * 1000),
                "freshness": fresh,
                "lastCycleAt": self._last_cycle_at,
                "cycleCount": self._cycle_count,
                "startedAt": self._started_at,
                "symbolLimit": cfg.SYMBOL_LIMIT,
                "symbolCount": len(self._latest),
                "snapshotIntervalSec": cfg.SNAPSHOT_INTERVAL_SEC,
                "historyCapacityPerSymbol": cfg.HISTORY_CAPACITY_PER_SYMBOL,
                "candidateCapacity": cfg.CANDIDATE_CAPACITY,
                "eventCapacity": cfg.EVENT_CAPACITY,
                "loopOverlapBlocked": True,
                "threadAlive": bool(self._thread and self._thread.is_alive()),
                "lastError": self._last_error or None,
                "longCandidates": longs,
                "shortCandidates": shorts,
                "confirmedCandidates": confirmed,
                "highRiskCandidates": high_risk,
                "breadth": dict(self._breadth),
                "cache": "no-store",
                # Phase 4 Track B
                "transport": self._transport,
                "wsConnected": self._ws_connected,
                "wsReconnectCount": self._ws_reconnect_count,
                "lastMarketUpdateAt": self._last_market_update_at or None,
                "lastCandidateRecomputeAt": self._last_candidate_recompute_at or None,
                "wsUpdates": self._ws_updates,
                "wsOutOfOrderBlocked": self._ws_ooo_blocked,
                "wsDuplicateSuppressed": self._ws_dup_suppressed,
                "wsSubscribedTopics": ws_body.get("subscribedTopics"),
                "candidateRecomputeThrottled": True,
                "candidateRecomputeEveryTick": False,
            }

    def universe(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                **self._universe_meta,
                "generatedAt": self._universe_meta.get("generatedAt") or int(time.time() * 1000),
                "cache": "no-store",
            }

    def candidates(self, side: str | None = None, limit: int = 40) -> dict[str, Any]:
        with self._lock:
            rows = list(self._candidates)
            if side:
                side_u = side.upper()
                rows = [c for c in rows if c.get("side") == side_u]
            rows = rows[: max(1, min(limit, cfg.CANDIDATE_CAPACITY))]
            return {
                "ok": True,
                "read_only": True,
                "researchOnly": True,
                "source": "BYBIT_MAINNET_LINEAR",
                "generatedAt": int(time.time() * 1000),
                "freshness": self.status().get("freshness"),
                "count": len(rows),
                "candidates": rows,
                "cache": "no-store",
            }

    def symbol_detail(self, symbol: str) -> dict[str, Any]:
        sym = symbol.upper().strip()
        with self._lock:
            snap = self._latest.get(sym)
            if not snap:
                return {"ok": False, "error": "symbol_not_in_universe", "symbol": sym}
            hist = list(self._history.get(sym) or [])
            cand = next((c for c in self._candidates if c.get("symbol") == sym), None)
            spark = [
                {"t": h.get("receivedAt"), "price": h.get("lastPrice"), "oi": h.get("openInterest")}
                for h in hist[-36:]
            ]
            return {
                "ok": True,
                "read_only": True,
                "researchOnly": True,
                "source": "BYBIT_MAINNET_LINEAR",
                "generatedAt": int(time.time() * 1000),
                "symbol": sym,
                "snapshot": snap,
                "candidate": cand,
                "sparkline": spark,
                "historyPoints": len(hist),
                "cache": "no-store",
            }

    def events(self, limit: int = 30) -> dict[str, Any]:
        with self._lock:
            rows = list(self._events)[: max(1, min(limit, cfg.EVENT_CAPACITY))]
            return {
                "ok": True,
                "read_only": True,
                "source": "BYBIT_MAINNET_LINEAR",
                "generatedAt": int(time.time() * 1000),
                "count": len(rows),
                "events": rows,
                "cache": "no-store",
            }

    def sector_deep_snapshot(self) -> dict[str, Any]:
        """Read-only deep-scan rows for sector aggregation (Phase 3). Does not alter scoring."""
        with self._lock:
            rows = []
            for sym, snap in self._latest.items():
                hist = list(self._history.get(sym) or [])
                cand = next((c for c in self._candidates if c.get("symbol") == sym), None)
                rows.append(
                    {
                        "symbol": sym,
                        "lastPrice": snap.get("lastPrice"),
                        "change24hPct": snap.get("change24hPct"),
                        "turnover24h": snap.get("turnover24h"),
                        "fundingRate": snap.get("fundingRate"),
                        "openInterest": snap.get("openInterest"),
                        "openInterestValue": snap.get("openInterestValue"),
                        "priceChange5mPct": (cand or {}).get("priceChange5mPct"),
                        "oiChange5mPct": (cand or {}).get("oiChange5mPct"),
                        "collecting": bool((cand or {}).get("collecting")),
                        "historyPoints": len(hist),
                    }
                )
            return {
                "ok": True,
                "symbolCount": len(rows),
                "freshness": self.status().get("freshness"),
                "rows": rows,
                "candidates": list(self._candidates),
                "generatedAt": int(time.time() * 1000),
            }

    def charts(self) -> dict[str, Any]:
        with self._lock:
            breadth = dict(self._breadth)
            # Turnover activity top 10 (always available from latest snapshot)
            top_turn = sorted(
                self._latest.values(),
                key=lambda r: float(r.get("turnover24h") or 0),
                reverse=True,
            )[:10]
            turnover_chart = [
                {
                    "symbol": r["symbol"],
                    "turnover24h": r.get("turnover24h"),
                    "change24hPct": r.get("change24hPct"),
                }
                for r in top_turn
            ]
            # Price/OI quadrant — only points with real 5m windows
            quadrant = []
            for c in self._candidates:
                px = c.get("priceChange5mPct")
                oi = c.get("oiChange5mPct")
                if px is None or oi is None:
                    continue
                quadrant.append(
                    {
                        "symbol": c["symbol"],
                        "side": c["side"],
                        "priceChange5mPct": px,
                        "oiChange5mPct": oi,
                        "stage": c.get("stage"),
                    }
                )
            return {
                "ok": True,
                "source": "BYBIT_MAINNET_LINEAR",
                "generatedAt": int(time.time() * 1000),
                "breadth": breadth,
                "turnoverTop10": turnover_chart,
                "priceOiQuadrant": quadrant,
                "quadrantNote": "points require real 5m windows; collecting symbols omitted",
                "cache": "no-store",
            }


_SCANNER: MarketScannerService | None = None
_SCANNER_LOCK = threading.Lock()


def get_market_scanner() -> MarketScannerService:
    global _SCANNER
    with _SCANNER_LOCK:
        if _SCANNER is None:
            _SCANNER = MarketScannerService()
            _SCANNER.start(bootstrap=True)
        return _SCANNER
