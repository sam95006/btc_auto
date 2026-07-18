"""Server-side anomaly outcome trackers (Phase 4 Track B).

Windows: 5m / 15m / 30m / 60m · PENDING/COMPLETE/MISSED/STALE
No synthetic live results · research-only · no recommendation coupling.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from backend.market.intelligence.history_store import get_history_store

OUTCOME_WINDOWS = (
    ("5m", 5 * 60_000),
    ("15m", 15 * 60_000),
    ("30m", 30 * 60_000),
    ("60m", 60 * 60_000),
)
TIMESTAMP_TOLERANCE_MS = 15_000
MISS_GRACE_MS = 30_000
MAX_TRACKED = 200


def _forward_return_pct(ref: float, observed: float) -> float:
    if not (ref > 0) or observed != observed:
        return 0.0
    return ((observed - ref) / ref) * 100.0


def _excursions(
    ref: float,
    price: float,
    direction: str | None,
    mfe: float,
    mae: float,
) -> tuple[float, float]:
    if not (ref > 0) or price != price:
        return mfe, mae
    up = ((price - ref) / ref) * 100.0
    down = ((ref - price) / ref) * 100.0
    d = (direction or "").upper()
    if d in ("UP", "LONG"):
        return max(mfe, max(0.0, up)), max(mae, max(0.0, down))
    if d in ("DOWN", "SHORT"):
        return max(mfe, max(0.0, down)), max(mae, max(0.0, up))
    return max(mfe, max(0.0, up)), max(mae, max(0.0, down))


class OutcomeStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._duplicate_blocked = 0
        self._started_at = int(time.time() * 1000)

    def ensure_tracking(
        self,
        *,
        anomaly_id: str,
        symbol: str,
        anomaly_type: str = "CANDIDATE_EVENT",
        severity: str | None = None,
        direction: str | None = None,
        score: float | None = None,
        observed_at: int | None = None,
        reference_price: float | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        aid = str(anomaly_id or "").strip()
        if not aid:
            return {"ok": False, "error": "missing_anomaly_id"}
        with self._lock:
            if aid in self._by_id:
                self._duplicate_blocked += 1
                return {"ok": False, "error": "duplicate_blocked", "anomalyId": aid}
            ref = reference_price
            if ref is None or not (ref > 0):
                return {"ok": False, "error": "missing_reference_price", "anomalyId": aid}
            now = int(time.time() * 1000)
            obs = int(observed_at or now)
            windows = []
            for name, ms in OUTCOME_WINDOWS:
                windows.append(
                    {
                        "window": name,
                        "targetTimestamp": obs + ms,
                        "status": "PENDING",
                        "peakMfe": 0.0,
                        "peakMae": 0.0,
                        "maxFavorableExcursionPct": None,
                        "maxAdverseExcursionPct": None,
                        "forwardReturnPct": None,
                        "observedTimestamp": None,
                        "observedPrice": None,
                        "bestSample": None,
                    }
                )
            row = {
                "anomalyId": aid,
                "symbol": str(symbol).upper().strip(),
                "anomalyType": anomaly_type,
                "severity": severity,
                "direction": direction,
                "score": score,
                "observedAt": obs,
                "referencePrice": float(ref),
                "evidenceSnapshot": dict(evidence or {}),
                "outcomes": windows,
                "source": "BYBIT_MAINNET_LINEAR",
                "researchOnly": True,
                "recommendationCoupled": False,
                "tradingCoupled": False,
                "syntheticLiveResult": False,
                "lastUpdatedAt": now,
            }
            self._by_id[aid] = row
            self._order.insert(0, aid)
            while len(self._order) > MAX_TRACKED:
                drop = self._order.pop()
                self._by_id.pop(drop, None)
        try:
            get_history_store().append_event(
                "outcome_track",
                {"anomalyId": aid, "symbol": symbol, "observedAt": obs, "referencePrice": ref},
            )
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "anomalyId": aid, "created": True}

    def on_price(
        self,
        symbol: str,
        price: float,
        *,
        now: int | None = None,
        feed_bad: bool = False,
    ) -> int:
        """Update pending windows for symbol. Returns number of rows touched."""
        if not (price > 0):
            return 0
        ts = int(now if now is not None else time.time() * 1000)
        sym = symbol.upper().strip()
        touched = 0
        with self._lock:
            for row in self._by_id.values():
                if row.get("symbol") != sym:
                    continue
                changed = False
                ref = float(row["referencePrice"])
                direction = row.get("direction")
                for w in row["outcomes"]:
                    if w["status"] != "PENDING":
                        continue
                    mfe, mae = _excursions(ref, price, direction, w["peakMfe"], w["peakMae"])
                    w["peakMfe"] = mfe
                    w["peakMae"] = mae
                    w["maxFavorableExcursionPct"] = mfe
                    w["maxAdverseExcursionPct"] = mae
                    changed = True
                    dist = abs(ts - int(w["targetTimestamp"]))
                    if dist <= TIMESTAMP_TOLERANCE_MS:
                        prev = w.get("bestSample")
                        if not prev or dist < prev.get("dist", 10**12):
                            w["bestSample"] = {"ts": ts, "price": price, "dist": dist}
                    if ts >= int(w["targetTimestamp"]) - TIMESTAMP_TOLERANCE_MS:
                        best = w.get("bestSample")
                        if best and best.get("dist", 10**12) <= TIMESTAMP_TOLERANCE_MS:
                            w["status"] = "COMPLETE"
                            w["observedTimestamp"] = best["ts"]
                            w["observedPrice"] = best["price"]
                            w["forwardReturnPct"] = round(
                                _forward_return_pct(ref, float(best["price"])), 4
                            )
                            continue
                    if ts > int(w["targetTimestamp"]) + TIMESTAMP_TOLERANCE_MS + MISS_GRACE_MS:
                        w["status"] = "STALE" if feed_bad else "MISSED"
                if changed:
                    row["lastUpdatedAt"] = ts
                    touched += 1
        return touched

    def _public_row(self, row: dict[str, Any]) -> dict[str, Any]:
        outcomes = []
        for w in row.get("outcomes") or []:
            outcomes.append(
                {
                    "window": w["window"],
                    "targetTimestamp": w["targetTimestamp"],
                    "status": w["status"],
                    "maxFavorableExcursionPct": w.get("maxFavorableExcursionPct"),
                    "maxAdverseExcursionPct": w.get("maxAdverseExcursionPct"),
                    "forwardReturnPct": w.get("forwardReturnPct"),
                    "observedTimestamp": w.get("observedTimestamp"),
                    "observedPrice": w.get("observedPrice"),
                }
            )
        return {
            "anomalyId": row["anomalyId"],
            "symbol": row["symbol"],
            "anomalyType": row.get("anomalyType"),
            "severity": row.get("severity"),
            "direction": row.get("direction"),
            "score": row.get("score"),
            "observedAt": row.get("observedAt"),
            "referencePrice": row.get("referencePrice"),
            "outcomes": outcomes,
            "source": row.get("source"),
            "researchOnly": True,
            "lastUpdatedAt": row.get("lastUpdatedAt"),
            "syntheticLiveResult": False,
        }

    def list(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        lim = max(1, min(int(limit or 50), MAX_TRACKED))
        st = (status or "").upper().strip() or None
        with self._lock:
            rows = []
            for aid in self._order:
                row = self._by_id.get(aid)
                if not row:
                    continue
                pub = self._public_row(row)
                if st:
                    if not any(o.get("status") == st for o in pub["outcomes"]):
                        continue
                rows.append(pub)
                if len(rows) >= lim:
                    break
            return {
                "ok": True,
                "count": len(rows),
                "outcomes": rows,
                "researchOnly": True,
                "recommendationCoupled": False,
                "tradingCoupled": False,
                "cache": "no-store",
                "generatedAt": int(time.time() * 1000),
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            pending = complete = missed = stale = 0
            for row in self._by_id.values():
                for w in row.get("outcomes") or []:
                    s = w.get("status")
                    if s == "PENDING":
                        pending += 1
                    elif s == "COMPLETE":
                        complete += 1
                    elif s == "MISSED":
                        missed += 1
                    elif s == "STALE":
                        stale += 1
            return {
                "ok": True,
                "tracked": len(self._by_id),
                "capacity": MAX_TRACKED,
                "pendingWindows": pending,
                "completeWindows": complete,
                "missedWindows": missed,
                "staleWindows": stale,
                "duplicateBlocked": self._duplicate_blocked,
                "windows": [w for w, _ in OUTCOME_WINDOWS],
                "timestampToleranceMs": TIMESTAMP_TOLERANCE_MS,
                "missGraceMs": MISS_GRACE_MS,
                "syntheticLiveResult": False,
                "researchOnly": True,
                "recommendationCoupled": False,
                "persistenceMode": get_history_store().mode,
                "startedAt": self._started_at,
            }


_STORE: OutcomeStore | None = None
_LOCK = threading.Lock()


def get_outcome_store() -> OutcomeStore:
    global _STORE
    with _LOCK:
        if _STORE is None:
            _STORE = OutcomeStore()
        return _STORE
