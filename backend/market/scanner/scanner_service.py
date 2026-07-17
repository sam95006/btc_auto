"""Bounded in-process read-only market scanner (Phase 1).

Public Bybit REST only · daemon thread · no trading path coupling.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from backend.market.scanner import universe_config as cfg
from backend.market.scanner.candidate_engine import rank_candidates, score_symbol
from backend.market.scanner.universe import build_universe, fetch_all_linear_tickers

logger = logging.getLogger(__name__)


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

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=timeout)

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
                    hist = self._history.get(sym)
                    if hist is None:
                        hist = deque(maxlen=cfg.HISTORY_CAPACITY_PER_SYMBOL)
                        self._history[sym] = hist
                    hist.append(row)
                    self._latest[sym] = row
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

                ranked = rank_candidates(scored, self._prev_candidates)
                self._emit_events(ranked)
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
                self._cycle_count += 1
                self._last_error = ""
            return {"ok": True, "symbols": len(uni["symbols"]), "candidates": len(ranked)}
        finally:
            self._loop_running = False

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
