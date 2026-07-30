"""Dynamic universe scan for 6H session — Bybit USDT linear, RULE_BASED."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL
from backend.nexus_demo_execution.session_limits import DECISION_LABEL


@dataclass
class BoundedCandidate:
    candidate_id: str
    symbol: str
    direction: str
    regime: str
    strategy: str
    candidate_score: float
    last_price: float
    spread_bps: float
    turnover24h: float
    market_quality: dict[str, Any]
    funding_rate: float | None
    funding_status: str
    six_role_reviews: dict[str, Any] = field(default_factory=dict)
    risk_critic_verdict: str = "PASS"
    mistake_guard_verdict: str = "ALLOW"
    portfolio_verdict: str = "PASS"
    decision_label: str = DECISION_LABEL
    data_freshness: str = "FRESH"
    market_snapshot_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "regime": self.regime,
            "strategy": self.strategy,
            "candidate_score": self.candidate_score,
            "last_price": self.last_price,
            "spread_bps": self.spread_bps,
            "turnover24h": self.turnover24h,
            "market_quality": self.market_quality,
            "funding_rate": self.funding_rate if self.funding_rate is not None else "UNAVAILABLE",
            "funding_status": self.funding_status,
            "six_role_reviews": self.six_role_reviews,
            "risk_critic_verdict": self.risk_critic_verdict,
            "mistake_guard_verdict": self.mistake_guard_verdict,
            "portfolio_verdict": self.portfolio_verdict,
            "decision_label": self.decision_label,
            "data_freshness": self.data_freshness,
            "market_snapshot_time": self.market_snapshot_time,
        }


def _public_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    query = urlencode(sorted(params.items()))
    url = f"{DEMO_REST_BASE_URL}{path}?{query}"
    req = Request(url, headers={"User-Agent": "NEXUS-DemoValidation-6H/1.0"}, method="GET")
    with urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("retCode") not in (0, "0", None):
        raise RuntimeError(f"public_api_error:{data.get('retCode')}:{data.get('retMsg')}")
    return data


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def scan_dynamic_candidates(*, limit: int = 8) -> tuple[list[BoundedCandidate], dict[str, Any]]:
    """Tier1 instruments → Tier2 liquidity/spread → Tier3 shortlist with RULE_BASED six-role stub."""
    scan_meta: dict[str, Any] = {"started_at": time.time(), "decision_label": DECISION_LABEL}
    instruments = _public_get(
        "/v5/market/instruments-info",
        {"category": "linear", "status": "Trading", "limit": "500"},
    )
    rows = (instruments.get("result") or {}).get("list") or []
    # paginate cursor lightly
    cursor = (instruments.get("result") or {}).get("nextPageCursor") or ""
    if cursor:
        more = _public_get(
            "/v5/market/instruments-info",
            {"category": "linear", "status": "Trading", "limit": "500", "cursor": cursor},
        )
        rows.extend((more.get("result") or {}).get("list") or [])

    usdt = [
        r
        for r in rows
        if str(r.get("quoteCoin") or "").upper() == "USDT"
        and str(r.get("contractType") or "") in {"LinearPerpetual", "linearperpetual", ""}
        and str(r.get("status") or "").lower() == "trading"
        and str(r.get("symbol") or "").endswith("USDT")
    ]
    scan_meta["tier1_count"] = len(usdt)

    tickers = _public_get("/v5/market/tickers", {"category": "linear"})
    tlist = (tickers.get("result") or {}).get("list") or []
    by_sym = {str(t.get("symbol")): t for t in tlist}

    tier2: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for inst in usdt:
        sym = str(inst.get("symbol") or "")
        t = by_sym.get(sym)
        if not t:
            continue
        last = _f(t.get("lastPrice"))
        bid = _f(t.get("bid1Price"))
        ask = _f(t.get("ask1Price"))
        turnover = _f(t.get("turnover24h"))
        if last <= 0 or turnover < 5_000_000:
            continue
        spread_bps = ((ask - bid) / last * 10000.0) if bid > 0 and ask > 0 else 9999.0
        if spread_bps >= 12.0:
            continue
        score = min(turnover / 1e9, 20.0) - spread_bps * 0.05
        tier2.append((score, inst, t))
    tier2.sort(key=lambda x: x[0], reverse=True)
    scan_meta["tier2_count"] = len(tier2)

    shortlist = tier2[: max(limit * 3, 12)]
    candidates: list[BoundedCandidate] = []
    now = time.time()
    for score, inst, t in shortlist[:limit]:
        sym = str(inst.get("symbol"))
        last = _f(t.get("lastPrice"))
        bid = _f(t.get("bid1Price"))
        ask = _f(t.get("ask1Price"))
        turnover = _f(t.get("turnover24h"))
        spread_bps = ((ask - bid) / last * 10000.0) if bid > 0 and ask > 0 else 9999.0
        # simple momentum from 24h change
        prev = _f(t.get("prevPrice24h")) or last
        momentum = (last - prev) / prev if prev else 0.0
        direction = "Buy" if momentum >= 0 else "Sell"
        regime = "TREND_UP" if momentum >= 0 else "TREND_DOWN"
        if abs(momentum) < 0.001:
            continue  # UNCERTAIN-ish → skip
        funding_rate = None
        funding_status = "UNAVAILABLE"
        try:
            fr = _public_get("/v5/market/funding/history", {"category": "linear", "symbol": sym, "limit": "1"})
            fl = (fr.get("result") or {}).get("list") or []
            if fl:
                funding_rate = _f(fl[0].get("fundingRate"))
                funding_status = "KNOWN"
        except Exception:
            funding_status = "UNAVAILABLE"

        six_role = {
            "market_context": {"verdict": "PASS", "label": DECISION_LABEL},
            "market_structure": {"verdict": "PASS", "label": DECISION_LABEL},
            "risk_critic": {"verdict": "PASS", "label": DECISION_LABEL, "mandatory": True},
            "portfolio_manager": {"verdict": "PASS", "label": DECISION_LABEL},
            "performance_analyst": {"verdict": "PASS", "label": DECISION_LABEL},
            "reflection_analyst": {"verdict": "PASS", "label": DECISION_LABEL},
            "complete": True,
        }
        # Risk critic extra: funding unavailable → WATCH but allow with cost buffer
        if funding_status == "UNAVAILABLE":
            six_role["risk_critic"]["verdict"] = "WATCH"
            six_role["risk_critic"]["note"] = "funding_unavailable_requires_cost_buffer"

        candidates.append(
            BoundedCandidate(
                candidate_id=f"6h-{sym.lower()}-{uuid.uuid4().hex[:8]}",
                symbol=sym,
                direction=direction,
                regime=regime,
                strategy="BOUNDED_MOMENTUM_24H",
                candidate_score=round(score + abs(momentum) * 100, 6),
                last_price=last,
                spread_bps=round(spread_bps, 4),
                turnover24h=turnover,
                market_quality={"pass": True, "spread_bps": spread_bps, "turnover24h": turnover},
                funding_rate=funding_rate,
                funding_status=funding_status,
                six_role_reviews=six_role,
                risk_critic_verdict=six_role["risk_critic"]["verdict"],
                market_snapshot_time=now,
            )
        )
    candidates.sort(key=lambda c: c.candidate_score, reverse=True)
    scan_meta["tier3_count"] = len(candidates)
    scan_meta["completed_at"] = time.time()
    return candidates, scan_meta
