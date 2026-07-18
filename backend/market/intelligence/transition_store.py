"""Candidate transition timeline store (Phase 4 Track B).

Records stage/rank changes with dedup · research-only · no trade actions.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from backend.market.intelligence.history_store import get_history_store

TRANSITION_CAPACITY = 500
TRANSITION_TTL_MS = 12 * 60 * 60 * 1000  # 12h
DEDUP_COOLDOWN_MS = 5_000


class TransitionStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rows: deque[dict[str, Any]] = deque(maxlen=TRANSITION_CAPACITY)
        self._dedup: dict[str, int] = {}
        self._by_symbol: dict[str, deque[str]] = {}

    def record_from_candidates(
        self,
        ranked: list[dict[str, Any]],
        previous: dict[str, dict[str, Any]],
        *,
        source_snapshot_at: int | None = None,
    ) -> int:
        """Emit transitions when stage or rank changes. Returns new count."""
        now = int(time.time() * 1000)
        snap_at = int(source_snapshot_at or now)
        added = 0
        for c in ranked:
            cid = str(c.get("id") or "")
            if not cid:
                continue
            prev = previous.get(cid)
            from_stage = (prev or {}).get("stage")
            to_stage = c.get("stage")
            prev_rank = (prev or {}).get("rank")
            cur_rank = c.get("rank")
            stage_changed = prev is not None and from_stage != to_stage
            rank_changed = prev is not None and prev_rank != cur_rank and (
                prev_rank is not None or cur_rank is not None
            )
            first_seen = prev is None and to_stage is not None
            if not (stage_changed or rank_changed or first_seen):
                continue
            if first_seen and not stage_changed:
                from_stage = None
            row = {
                "candidateId": cid,
                "symbol": c.get("symbol"),
                "side": c.get("side"),
                "fromStage": from_stage,
                "toStage": to_stage,
                "previousRank": prev_rank,
                "currentRank": cur_rank,
                "opportunityScore": c.get("opportunityScore"),
                "confirmationScore": c.get("confirmationScore"),
                "riskScore": c.get("riskScore"),
                "reasons": list(c.get("reasons") or [])[:4],
                "conflicts": list(c.get("conflicts") or [])[:4],
                "observedAt": now,
                "sourceSnapshotAt": snap_at,
                "researchOnly": True,
                "tradeAction": False,
            }
            if self.append(row):
                added += 1
        return added

    def append(self, row: dict[str, Any]) -> bool:
        now = int(row.get("observedAt") or time.time() * 1000)
        cid = str(row.get("candidateId") or "")
        key = (
            f"{cid}|{row.get('fromStage')}|{row.get('toStage')}|"
            f"{row.get('previousRank')}|{row.get('currentRank')}|{row.get('sourceSnapshotAt')}"
        )
        soft = f"{cid}|{row.get('fromStage')}|{row.get('toStage')}|{row.get('currentRank')}"
        with self._lock:
            last = self._dedup.get(soft, 0)
            if now - last < DEDUP_COOLDOWN_MS:
                return False
            # identical snapshot dedup
            if any(
                f"{r.get('candidateId')}|{r.get('fromStage')}|{r.get('toStage')}|"
                f"{r.get('previousRank')}|{r.get('currentRank')}|{r.get('sourceSnapshotAt')}"
                == key
                for r in self._rows
            ):
                return False
            self._dedup[soft] = now
            rid = f"{cid}:{now}:{len(self._rows)}"
            rec = {**row, "id": rid, "researchOnly": True}
            self._rows.appendleft(rec)
            sym = str(row.get("symbol") or "").upper()
            if sym:
                dq = self._by_symbol.get(sym)
                if dq is None:
                    dq = deque(maxlen=80)
                    self._by_symbol[sym] = dq
                dq.appendleft(rid)
            self._prune(now)
        try:
            get_history_store().append_event("candidate_transition", rec)
        except Exception:  # noqa: BLE001
            pass
        return True

    def _prune(self, now: int) -> None:
        cutoff = now - TRANSITION_TTL_MS
        while self._rows and int(self._rows[-1].get("observedAt") or 0) < cutoff:
            self._rows.pop()

    def timeline(self, symbol: str, *, limit: int = 40) -> dict[str, Any]:
        sym = symbol.upper().strip()
        lim = max(1, min(int(limit or 40), 100))
        with self._lock:
            rows = [r for r in self._rows if str(r.get("symbol") or "").upper() == sym][:lim]
            return {
                "ok": True,
                "symbol": sym,
                "count": len(rows),
                "transitions": rows,
                "researchOnly": True,
                "tradeAction": False,
                "capacity": TRANSITION_CAPACITY,
                "ttlMs": TRANSITION_TTL_MS,
                "cache": "no-store",
                "generatedAt": int(time.time() * 1000),
            }

    def list_recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit or 50), TRANSITION_CAPACITY))
        with self._lock:
            return list(self._rows)[:lim]

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "count": len(self._rows),
                "capacity": TRANSITION_CAPACITY,
                "ttlMs": TRANSITION_TTL_MS,
                "dedupCooldownMs": DEDUP_COOLDOWN_MS,
                "symbolKeys": len(self._by_symbol),
                "researchOnly": True,
            }


_STORE: TransitionStore | None = None
_LOCK = threading.Lock()


def get_transition_store() -> TransitionStore:
    global _STORE
    with _LOCK:
        if _STORE is None:
            _STORE = TransitionStore()
        return _STORE
