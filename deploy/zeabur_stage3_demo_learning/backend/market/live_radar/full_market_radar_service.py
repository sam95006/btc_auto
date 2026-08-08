"""Full-Market Live Radar — rank FULL scanner-visible universe on server.

Pipeline: scanner universe → RADAR_ELIGIBLE → nex_rank_score_v1 → rank BEFORE pagination.
Frontend is a snapshot consumer only (rank_authority=SERVER).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from backend.market.live_radar.nex_rank_score import (
    FIXED_SYMBOL_DEPENDENCY_COUNT,
    NEX_RANK_SCORE_VERSION,
    RADAR_ELIGIBILITY_CONTRACT,
    RANK_HYSTERESIS_SCORE,
    activity_state,
    compute_nex_rank_score_v1,
    derive_rank_event,
    is_crypto_opportunity,
    is_radar_eligible,
    is_scanner_visible,
    is_trade_eligible,
)
from backend.market.live_radar.rank_event_store import RankEventStore

logger = logging.getLogger(__name__)

CLOSEST_WATCH_MAX = 5
DEFAULT_CACHE_MS = 3_000
SNAPSHOT_VERSION = "full_market_radar_v1"


def filter_ranking_rows(rows: list[dict[str, Any]], tab: str) -> list[dict[str, Any]]:
    tab_u = (tab or "ALL").upper()
    if tab_u == "LONG":
        return [r for r in rows if r.get("side_bias") == "LONG"]
    if tab_u == "SHORT":
        return [r for r in rows if r.get("side_bias") == "SHORT"]
    if tab_u == "MOVE":
        return sorted(
            [
                r
                for r in rows
                if r.get("rank_event") in ("NEW", "UP", "DOWN", "OUT")
            ],
            key=lambda r: abs(int(r.get("rank_delta") or 0)),
            reverse=True,
        )
    if tab_u == "OI":
        return sorted(rows, key=lambda r: abs(float(r.get("oi_change") or 0)), reverse=True)
    if tab_u == "ACTIVITY":
        return sorted(rows, key=lambda r: float(r.get("activity_metric") or 0), reverse=True)
    if tab_u == "RISK":
        return sorted(rows, key=lambda r: float(r.get("risk_score") or 0), reverse=True)
    return rows


def _apply_hysteresis(
    scored: list[dict[str, Any]],
    prev_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    arr = list(scored)
    changed = True
    guard = 0
    while changed and guard < len(arr):
        changed = False
        guard += 1
        for i in range(len(arr) - 1):
            a = arr[i]
            b = arr[i + 1]
            if float(a["score"]) - float(b["score"]) >= RANK_HYSTERESIS_SCORE:
                continue
            pa = (prev_map.get(str(a["c"]["symbol"]).upper()) or {}).get("rank")
            pb = (prev_map.get(str(b["c"]["symbol"]).upper()) or {}).get("rank")
            if pa is None or pb is None:
                continue
            if pa > pb:
                arr[i], arr[i + 1] = b, a
                changed = True
    return arr


class FullMarketRadarService:
    def __init__(self, store: RankEventStore | None = None) -> None:
        self._lock = threading.RLock()
        self._store = store or RankEventStore()
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_at = 0
        self._cache_ms = DEFAULT_CACHE_MS
        self._last_error = ""

    @property
    def store(self) -> RankEventStore:
        return self._store

    def _load_universe_candidates(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Load FULL scanner-visible scored set (not API limit=40)."""
        from backend.market.scanner.scanner_service import get_market_scanner

        scanner = get_market_scanner()
        meta: dict[str, Any] = {}
        rows: list[dict[str, Any]] = []
        if hasattr(scanner, "all_scored_candidates"):
            body = scanner.all_scored_candidates()
            rows = list(body.get("candidates") or [])
            meta = {
                "scanner_symbol_count": body.get("symbolCount"),
                "scanner_symbol_limit": body.get("symbolLimit"),
                "eligible_before_limit": body.get("eligibleBeforeLimit"),
                "eligible_after_limit": body.get("eligibleAfterLimit"),
                "universe_blocker": body.get("universeBlocker"),
            }
        else:
            # Fallback: candidates() still capped — document blocker
            body = scanner.candidates(side=None, limit=10_000)
            rows = list(body.get("candidates") or [])
            meta = {
                "universe_blocker": "scanner_missing_all_scored_candidates_method",
                "fallback_candidates_len": len(rows),
            }
        return rows, meta

    def build_snapshot(self, *, force: bool = False, now_ms: int | None = None) -> dict[str, Any]:
        now = int(now_ms if now_ms is not None else time.time() * 1000)
        with self._lock:
            if (
                not force
                and self._snapshot is not None
                and now - self._snapshot_at < self._cache_ms
            ):
                return dict(self._snapshot)

        try:
            snap = self._compute(now)
            with self._lock:
                self._snapshot = snap
                self._snapshot_at = now
                self._last_error = ""
            return dict(snap)
        except Exception as exc:  # noqa: BLE001
            logger.warning("full_market_radar build failed: %s", exc)
            with self._lock:
                self._last_error = str(exc)
                if self._snapshot is not None:
                    out = dict(self._snapshot)
                    out["stale"] = True
                    out["last_error"] = self._last_error
                    return out
            return self._empty_error(now, str(exc))

    def _empty_error(self, now: int, err: str) -> dict[str, Any]:
        return {
            "ok": False,
            "error": err,
            "updated_at": now,
            "snapshot_version": SNAPSHOT_VERSION,
            "rank_authority": "SERVER",
            "ranking_history_authority": "SERVER",
            "frontend_local_rank_authority": False,
            "frontend_candidate_fetch_limit_affects_rank": False,
            "full_ranking_before_pagination": True,
            "server_rank_events": True,
            "rank_restart_persistence": self._store.mode == "disk",
            "two_clients_same_snapshot": True,
            "fixed_symbol_dependency_count": FIXED_SYMBOL_DEPENDENCY_COUNT,
            "radar_eligibility_contract": RADAR_ELIGIBILITY_CONTRACT,
            "rank_score_semantics": "normalized_0_100_nex_rank_score_v1",
            "rank_score_version": NEX_RANK_SCORE_VERSION,
            "rank_persistence": "server_jsonl_prev_v1_hysteresis",
            "universe_size": 0,
            "evaluated_count": 0,
            "monitored_count": 0,
            "excluded_count": 0,
            "scanner_visible_count": 0,
            "radar_eligible_count": 0,
            "trade_eligible_count": 0,
            "active_count": 0,
            "qualified_count": 0,
            "rows": [],
            "radar": [],
            "closest_watch": [],
            "qualified": [],
            "events": [],
            "member_execution": 0,
        }

    def _compute(self, now: int) -> dict[str, Any]:
        raw_candidates, uni_meta = self._load_universe_candidates()
        # Ensure ids / symbols
        for c in raw_candidates:
            if not c.get("id"):
                c["id"] = f"{c.get('symbol')}:{c.get('side') or 'NEUTRAL'}"

        crypto = [c for c in raw_candidates if is_crypto_opportunity(c)]
        scanner_visible = [c for c in crypto if is_scanner_visible(c)]
        evaluated = list(scanner_visible)
        radar_pool = [c for c in evaluated if is_radar_eligible(c)]
        excluded = [c for c in evaluated if not is_radar_eligible(c)]
        trade_pool = [c for c in evaluated if is_trade_eligible(c)]

        scored: list[dict[str, Any]] = []
        for c in radar_pool:
            s = compute_nex_rank_score_v1(c)
            scored.append({"c": c, "score": s["score"], "raw": s["raw"], "components": s["components"]})
        scored.sort(key=lambda x: (-float(x["score"]), str(x["c"].get("symbol") or "")))

        prev_map = self._store.load_prev()
        stable = _apply_hysteresis(scored, prev_map)

        # FULL ranking before any pagination
        full_ranked_count = len(stable)
        next_prev: dict[str, dict[str, Any]] = {}
        new_events: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []

        for idx, item in enumerate(stable):
            c = item["c"]
            score = float(item["score"])
            raw = float(item["raw"])
            components = item["components"]
            rank = idx + 1
            key = str(c.get("symbol") or "").upper()
            prev = prev_map.get(key) or {}
            previous_rank = prev.get("rank")
            if previous_rank is None and isinstance(c.get("previousRank"), int):
                previous_rank = c.get("previousRank")
            event = derive_rank_event(rank, previous_rank if isinstance(previous_rank, int) else None, True)
            rank_delta = (
                (int(previous_rank) - rank) if isinstance(previous_rank, int) else c.get("rankDelta")
            )
            entered = prev.get("entered_at")
            if entered is None:
                entered = now if event == "NEW" else (c.get("firstSeenAt") or now)

            if (
                event in ("UP", "DOWN")
                and isinstance(previous_rank, int)
                and abs(int(previous_rank) - rank) == 1
                and abs(score - float(prev.get("score") or 0)) < RANK_HYSTERESIS_SCORE
            ):
                event = "UNCHANGED"
                if abs(int(rank_delta or 0)) == 1:
                    rank_delta = 0

            next_prev[key] = {
                "rank": rank,
                "score": score,
                "stage": c.get("stage"),
                "entered_at": entered,
                "ts": now,
                "confirm": int(prev.get("confirm") or 0) + 1,
            }

            if event != "UNCHANGED":
                change = "—"
                if c.get("change24hPct") is not None:
                    ch = float(c["change24hPct"])
                    change = f"24h {'+' if ch > 0 else ''}{ch:.2f}%"
                elif c.get("priceChange5mPct") is not None:
                    ch = float(c["priceChange5mPct"])
                    change = f"5m {'+' if ch > 0 else ''}{ch:.2f}%"
                new_events.append(
                    {
                        "id": f"{key}:{event}:{rank}:{now // 60000}",
                        "symbol": key,
                        "rank_event": event,
                        "rank": rank,
                        "previous_rank": previous_rank,
                        "primary_reason": (c.get("reasons") or ["結構觀察中"])[0]
                        if isinstance(c.get("reasons"), list)
                        else f"{event} · #{rank}",
                        "market_change": change,
                        "timestamp": now,
                    }
                )

            activity_metric = None
            if c.get("priceChange5mPct") is not None or c.get("turnoverPace") is not None:
                activity_metric = (
                    round(
                        (
                            abs(float(c.get("priceChange5mPct") or 0)) * 10
                            + float(c.get("turnoverPace") or 0) * 0.05
                        )
                        * 10
                    )
                    / 10
                )

            reasons = c.get("reasons") if isinstance(c.get("reasons"), list) else []
            conflicts = c.get("conflicts") if isinstance(c.get("conflicts"), list) else []
            rows.append(
                {
                    "symbol": key,
                    "rank": rank,
                    "previous_rank": previous_rank if isinstance(previous_rank, int) else None,
                    "rank_delta": rank_delta,
                    "rank_event": event,
                    "rank_score": score,
                    "rank_score_raw": raw,
                    "rank_score_version": NEX_RANK_SCORE_VERSION,
                    "rank_score_components": components,
                    "stage": c.get("stage"),
                    "side_bias": c.get("side"),
                    "price": c.get("currentPrice") if c.get("currentPrice") is not None else c.get("markPrice"),
                    "change_24h": c.get("change24hPct"),
                    "price_change_1m": c.get("priceChange1mPct"),
                    "price_change_5m": c.get("priceChange5mPct"),
                    "price_change_15m": c.get("priceChange15mPct"),
                    "volume_24h": c.get("volume24h"),
                    "activity_state": activity_state(c),
                    "activity_metric": activity_metric,
                    "oi_change": c.get("oiChange5mPct"),
                    "funding_rate": c.get("fundingRate"),
                    "risk_score": c.get("riskScore"),
                    "data_trust": str(c.get("freshness") or "UNKNOWN"),
                    "freshness": c.get("freshness"),
                    "primary_reason": reasons[0] if reasons else "結構觀察中",
                    "secondary_reason": reasons[1] if len(reasons) > 1 else (conflicts[0] if conflicts else ""),
                    "entered_rank_at": entered,
                    "last_rank_update": c.get("lastUpdatedAt") or now,
                    "radar_eligible": True,
                    "trade_eligible": is_trade_eligible(c),
                    "qualified": is_trade_eligible(c),
                    "candidate_id": c.get("id") or f"{key}:{c.get('side')}",
                }
            )

        for sym, prev in prev_map.items():
            if sym not in next_prev:
                new_events.append(
                    {
                        "id": f"{sym}:OUT:{prev.get('rank')}:{now // 60000}",
                        "symbol": sym,
                        "rank_event": "OUT",
                        "rank": None,
                        "previous_rank": prev.get("rank"),
                        "primary_reason": "離開 Live Radar",
                        "market_change": "—",
                        "timestamp": now,
                    }
                )

        self._store.save_prev(next_prev)
        self._store.append_events(new_events)

        radar_syms = {r["symbol"] for r in rows}
        closest_scored = []
        for c in scanner_visible:
            sym = str(c.get("symbol") or "").upper()
            if sym in radar_syms or is_radar_eligible(c):
                continue
            s = compute_nex_rank_score_v1(c)
            closest_scored.append({"c": c, "score": s["score"], "raw": s["raw"], "components": s["components"]})
        closest_scored.sort(key=lambda x: (-float(x["score"]), str(x["c"].get("symbol") or "")))
        closest_watch: list[dict[str, Any]] = []
        for i, item in enumerate(closest_scored[:CLOSEST_WATCH_MAX]):
            c = item["c"]
            key = str(c.get("symbol") or "").upper()
            reasons = c.get("reasons") if isinstance(c.get("reasons"), list) else []
            closest_watch.append(
                {
                    "symbol": key,
                    "rank": i + 1,
                    "previous_rank": None,
                    "rank_delta": None,
                    "rank_event": "UNCHANGED",
                    "rank_score": item["score"],
                    "rank_score_raw": item["raw"],
                    "rank_score_version": NEX_RANK_SCORE_VERSION,
                    "rank_score_components": item["components"],
                    "stage": c.get("stage"),
                    "side_bias": c.get("side"),
                    "price": c.get("currentPrice") if c.get("currentPrice") is not None else c.get("markPrice"),
                    "change_24h": c.get("change24hPct"),
                    "price_change_1m": c.get("priceChange1mPct"),
                    "price_change_5m": c.get("priceChange5mPct"),
                    "price_change_15m": c.get("priceChange15mPct"),
                    "volume_24h": c.get("volume24h"),
                    "activity_state": activity_state(c),
                    "activity_metric": None,
                    "oi_change": c.get("oiChange5mPct"),
                    "funding_rate": c.get("fundingRate"),
                    "risk_score": c.get("riskScore"),
                    "data_trust": str(c.get("freshness") or "UNKNOWN"),
                    "freshness": c.get("freshness"),
                    "primary_reason": reasons[0] if reasons else "Closest Watch · 尚未達 Radar 門檻",
                    "secondary_reason": "",
                    "entered_rank_at": None,
                    "last_rank_update": c.get("lastUpdatedAt") or now,
                    "radar_eligible": False,
                    "trade_eligible": is_trade_eligible(c),
                    "qualified": False,
                    "candidate_id": c.get("id") or f"{key}:{c.get('side')}",
                }
            )

        qualified = [r for r in rows if r.get("qualified")]
        symbol_limit = uni_meta.get("scanner_symbol_limit")
        eligible_before = uni_meta.get("eligible_before_limit")
        universe_blocker = uni_meta.get("universe_blocker")
        # Honest blocker: scanner Phase-1 SYMBOL_LIMIT caps monitored universe
        if universe_blocker is None and isinstance(symbol_limit, int) and isinstance(eligible_before, int):
            if eligible_before > symbol_limit:
                universe_blocker = (
                    f"scanner_SYMBOL_LIMIT={symbol_limit}_caps_eligible_before_limit={eligible_before}"
                )

        return {
            "ok": True,
            "updated_at": now,
            "snapshot_id": f"radar:{now}",
            "snapshot_version": SNAPSHOT_VERSION,
            "rank_authority": "SERVER",
            "ranking_history_authority": "SERVER",
            "frontend_local_rank_authority": False,
            "frontend_candidate_fetch_limit_affects_rank": False,
            "full_ranking_before_pagination": True,
            "full_ranked_count": full_ranked_count,
            "server_rank_events": True,
            "rank_restart_persistence": self._store.mode == "disk",
            "rank_store_mode": self._store.mode,
            "two_clients_same_snapshot": True,
            "fixed_symbol_dependency_count": FIXED_SYMBOL_DEPENDENCY_COUNT,
            "radar_eligibility_contract": RADAR_ELIGIBILITY_CONTRACT,
            "rank_score_semantics": "normalized_0_100_nex_rank_score_v1",
            "rank_score_version": NEX_RANK_SCORE_VERSION,
            "rank_persistence": "server_jsonl_prev_v1_hysteresis",
            "universe_size": len(crypto),
            "evaluated_count": len(evaluated),
            "monitored_count": len(evaluated),
            "excluded_count": len(excluded),
            "scanner_visible_count": len(scanner_visible),
            "radar_eligible_count": len(rows),
            "trade_eligible_count": len(trade_pool),
            "active_count": len(rows),
            "qualified_count": len(qualified),
            "rows": rows,
            "radar": rows,
            "closest_watch": closest_watch,
            "qualified": qualified,
            "events": new_events,
            "universe_meta": uni_meta,
            "universe_blocker": universe_blocker,
            "member_execution": 0,
            "read_only": True,
            "researchOnly": True,
            "cache": "no-store",
        }

    def public_radar(
        self,
        *,
        limit: int = 40,
        tab: str = "ALL",
        force: bool = False,
    ) -> dict[str, Any]:
        snap = self.build_snapshot(force=force)
        rows = filter_ranking_rows(list(snap.get("rows") or []), tab)
        # Pagination AFTER full ranking
        lim = max(1, min(int(limit or 40), 500))
        page = rows[:lim]
        out = dict(snap)
        out["tab"] = (tab or "ALL").upper()
        out["limit"] = lim
        out["rows"] = page
        out["radar"] = page
        out["total_ranked"] = len(rows)
        out["returned"] = len(page)
        out["pagination_after_full_rank"] = True
        return out

    def public_events(self, *, limit: int = 50, symbol: str | None = None) -> dict[str, Any]:
        # Ensure latest cycle has been applied
        self.build_snapshot()
        events = self._store.list_events(limit=limit, symbol=symbol)
        return {
            "ok": True,
            "ranking_history_authority": "SERVER",
            "server_rank_events": True,
            "rank_restart_persistence": self._store.mode == "disk",
            "rank_store_mode": self._store.mode,
            "count": len(events),
            "events": events,
            "cache": "no-store",
            "member_execution": 0,
        }

    def public_symbol(self, symbol: str) -> dict[str, Any]:
        snap = self.build_snapshot()
        sym = str(symbol or "").upper().strip()
        row = next((r for r in (snap.get("rows") or []) if r.get("symbol") == sym), None)
        closest = next((r for r in (snap.get("closest_watch") or []) if r.get("symbol") == sym), None)
        events = self._store.list_events(limit=40, symbol=sym)
        ok = row is not None or closest is not None
        return {
            "ok": ok,
            "symbol": sym,
            "rank_authority": "SERVER",
            "row": row,
            "closest_watch": closest,
            "in_radar": row is not None,
            "events": events,
            "snapshot_id": snap.get("snapshot_id"),
            "updated_at": snap.get("updated_at"),
            "radar_eligibility_contract": RADAR_ELIGIBILITY_CONTRACT,
            "member_execution": 0,
            "cache": "no-store",
            **({} if ok else {"error": "symbol_not_in_radar_snapshot"}),
        }


_SERVICE: FullMarketRadarService | None = None
_SVC_LOCK = threading.Lock()


def get_full_market_radar() -> FullMarketRadarService:
    global _SERVICE
    with _SVC_LOCK:
        if _SERVICE is None:
            _SERVICE = FullMarketRadarService()
        return _SERVICE


def reset_full_market_radar_for_tests() -> None:
    global _SERVICE
    with _SVC_LOCK:
        _SERVICE = None
