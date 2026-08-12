"""Server Live Radar discovery input — NEVER browser ranking."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RadarCandidate:
    symbol: str
    rank: int
    score: float
    radar_eligible: bool = True
    trade_eligible: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "rank": self.rank,
            "score": self.score,
            "radar_eligible": self.radar_eligible,
            "trade_eligible": self.trade_eligible,
            "meta": dict(self.meta),
            "ranking_authority": "SERVER",
        }


class ServerRadarFeed:
    """Adapter over server radar snapshot provider.

    ranking_authority is always SERVER. Browser/localStorage ranking is rejected.
    """

    def __init__(self, provider: Callable[[], dict[str, Any]] | None = None) -> None:
        self.provider = provider
        self.last_snapshot: dict[str, Any] = {}

    def ingest_snapshot(self, snapshot: dict[str, Any]) -> list[RadarCandidate]:
        snap = dict(snapshot or {})
        if str(snap.get("ranking_authority") or "SERVER").upper() != "SERVER":
            raise ValueError("browser_ranking_rejected")
        if snap.get("source") in {"browser", "localStorage", "buildLiveRanking"}:
            raise ValueError("browser_ranking_rejected")
        self.last_snapshot = snap
        rows = list(snap.get("candidates") or snap.get("ranked") or snap.get("items") or [])
        out: list[RadarCandidate] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            out.append(
                RadarCandidate(
                    symbol=symbol,
                    rank=int(row.get("rank") or i + 1),
                    score=float(row.get("score") or row.get("nex_rank_score") or 0.0),
                    radar_eligible=bool(row.get("radar_eligible", True)),
                    trade_eligible=bool(row.get("trade_eligible", False)),
                    meta={k: v for k, v in row.items() if k not in {"symbol", "rank", "score"}},
                )
            )
        out.sort(key=lambda c: c.rank)
        return out

    def shortlist(self, snapshot: dict[str, Any], *, n: int = 8) -> list[RadarCandidate]:
        cands = [c for c in self.ingest_snapshot(snapshot) if c.radar_eligible]
        return cands[: max(0, int(n))]

    def pull(self, *, n: int = 8) -> list[RadarCandidate]:
        if self.provider is None:
            return []
        return self.shortlist(self.provider(), n=n)
