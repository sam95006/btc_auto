"""Temporary smoke candidate selection — BTCUSDT|ETHUSDT whitelist only."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError
from backend.nexus_demo_execution.founder_approval import SMOKE_SYMBOL_WHITELIST


@dataclass
class SmokeCandidate:
    candidate_id: str
    symbol: str
    direction: str
    regime: str
    strategy: str
    candidate_score: float
    market_quality: dict[str, Any]
    six_role_reviews: dict[str, Any]
    risk_critic_verdict: str
    mistake_guard_verdict: str
    portfolio_verdict: str
    evidence_refs: list[str] = field(default_factory=list)
    policy_version: str = "smoke-v1-temp-whitelist"
    account_epoch: str = ""
    market_snapshot_time: float = 0.0
    data_freshness: str = "UNKNOWN"
    last_price: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "regime": self.regime,
            "strategy": self.strategy,
            "candidate_score": self.candidate_score,
            "market_quality": self.market_quality,
            "six_role_reviews": self.six_role_reviews,
            "risk_critic_verdict": self.risk_critic_verdict,
            "mistake_guard_verdict": self.mistake_guard_verdict,
            "portfolio_verdict": self.portfolio_verdict,
            "evidence_refs": list(self.evidence_refs),
            "policy_version": self.policy_version,
            "account_epoch": self.account_epoch,
            "market_snapshot_time": self.market_snapshot_time,
            "data_freshness": self.data_freshness,
            "last_price": self.last_price,
            "temporary_smoke_whitelist": True,
        }


def select_smoke_candidate(
    client: DemoWriteClient,
    *,
    account_epoch: str,
) -> SmokeCandidate:
    """Public market → quality → regime → stub six-role/risk/mistake/portfolio."""
    scored: list[SmokeCandidate] = []
    errors: list[str] = []
    now = time.time()

    for symbol in sorted(SMOKE_SYMBOL_WHITELIST):
        try:
            ticker = client.fetch_ticker(symbol)
            last = float(ticker.get("lastPrice") or 0)
            bid = float(ticker.get("bid1Price") or 0)
            ask = float(ticker.get("ask1Price") or 0)
            turnover = float(ticker.get("turnover24h") or 0)
            if last <= 0:
                errors.append(f"{symbol}:price_missing")
                continue
            spread_bps = ((ask - bid) / last * 10000.0) if bid > 0 and ask > 0 else 9999.0
            klines = client.fetch_klines(symbol, interval="15", limit=20)
            if len(klines) < 5:
                errors.append(f"{symbol}:klines_insufficient")
                continue
            # Bybit returns newest first
            closes = [k["close"] for k in reversed(klines)]
            opens = [k["open"] for k in reversed(klines)]
            volumes = [k["volume"] for k in reversed(klines)]
            momentum = (closes[-1] - opens[-5]) / opens[-5] if opens[-5] else 0.0
            direction = "Buy" if momentum >= 0 else "Sell"
            regime = "TREND_UP" if momentum >= 0 else "TREND_DOWN"
            quality_ok = spread_bps < 15.0 and turnover > 1_000_000
            market_quality = {
                "spread_bps": round(spread_bps, 4),
                "turnover24h": turnover,
                "last_price": last,
                "pass": quality_ok,
            }
            if not quality_ok:
                errors.append(f"{symbol}:market_quality_fail")
                continue

            six_role = {
                "market_analyst": "PASS",
                "strategy_analyst": "PASS",
                "risk_analyst": "PASS",
                "execution_analyst": "PASS",
                "portfolio_analyst": "PASS",
                "oversight_analyst": "PASS",
                "complete": True,
                "note": "smoke_stub_six_role_temporary",
            }
            score = abs(momentum) * 1000.0 + min(turnover / 1e9, 5.0) - spread_bps * 0.01
            scored.append(
                SmokeCandidate(
                    candidate_id=f"smoke-{symbol.lower()}-{uuid.uuid4().hex[:8]}",
                    symbol=symbol,
                    direction=direction,
                    regime=regime,
                    strategy="SMOKE_MOMENTUM_15M",
                    candidate_score=round(score, 6),
                    market_quality=market_quality,
                    six_role_reviews=six_role,
                    risk_critic_verdict="PASS",
                    mistake_guard_verdict="ALLOW",
                    portfolio_verdict="PASS",
                    evidence_refs=[f"ticker:{symbol}", f"klines15m:{len(klines)}", f"vol_avg:{sum(volumes)/len(volumes):.4f}"],
                    account_epoch=account_epoch,
                    market_snapshot_time=now,
                    data_freshness="FRESH",
                    last_price=last,
                )
            )
        except (DemoWriteError, Exception) as exc:
            errors.append(f"{symbol}:{type(exc).__name__}")

    if not scored:
        raise DemoWriteError("NO_VALID_SMOKE_CANDIDATE", ";".join(errors) or "none")

    scored.sort(key=lambda c: c.candidate_score, reverse=True)
    return scored[0]
