"""Dynamic global market universe (no fixed symbol list as formal universe)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from backend.nexus_global_shadow.contracts import (
    MarketInstrument,
    MarketQualitySnapshot,
    UniverseEligibility,
    UniverseSnapshot,
    new_id,
    now_ms,
)

InstrumentSource = list[dict[str, Any]] | Callable[[], list[dict[str, Any]]]
QualitySource = dict[str, dict[str, Any]] | Callable[[list[str]], dict[str, dict[str, Any]]]

FRESHNESS_OK = frozenset({"FRESH", "OK"})
FRESHNESS_BAD = frozenset({"STALE", "UNKNOWN", "MISSING"})


@dataclass
class ProviderCircuitBreaker:
    failure_threshold: int = 3
    failures: int = 0
    open: bool = False
    last_failure_reason: str | None = None

    def record_success(self) -> None:
        self.failures = 0
        self.open = False
        self.last_failure_reason = None

    def record_failure(self, reason: str) -> None:
        self.failures += 1
        self.last_failure_reason = reason
        if self.failures >= self.failure_threshold:
            self.open = True


@dataclass
class RateLimitState:
    max_calls: int = 100
    window_ms: int = 60_000
    calls: list[int] = field(default_factory=list)

    def allow(self, ts: int | None = None) -> bool:
        now = ts if ts is not None else now_ms()
        cutoff = now - self.window_ms
        self.calls = [c for c in self.calls if c >= cutoff]
        if len(self.calls) >= self.max_calls:
            return False
        self.calls.append(now)
        return True


class DynamicMarketUniverseProvider:
    """Fetch instruments from injectable list or callable — never hardcoded universe."""

    def __init__(
        self,
        instrument_source: InstrumentSource,
        *,
        timeout_ms: int = 30_000,
        rate_limit: RateLimitState | None = None,
        circuit_breaker: ProviderCircuitBreaker | None = None,
    ) -> None:
        self._source = instrument_source
        self.timeout_ms = timeout_ms
        self.rate_limit = rate_limit or RateLimitState()
        self.circuit_breaker = circuit_breaker or ProviderCircuitBreaker()
        self.last_error: str | None = None

    def fetch_instruments(self) -> tuple[list[dict[str, Any]], str]:
        if self.circuit_breaker.open:
            self.last_error = "circuit_breaker_open"
            return [], "UNIVERSE_UNAVAILABLE"
        if not self.rate_limit.allow():
            self.last_error = "rate_limit_exceeded"
            self.circuit_breaker.record_failure("rate_limit")
            return [], "UNIVERSE_DEGRADED"
        try:
            if callable(self._source):
                rows = self._source()
            else:
                rows = list(self._source)
            if rows is None:
                raise ValueError("provider_returned_none")
            self.circuit_breaker.record_success()
            self.last_error = None
            return list(rows), "OK"
        except TimeoutError:
            self.last_error = "timeout"
            self.circuit_breaker.record_failure("timeout")
            return [], "UNIVERSE_UNAVAILABLE"
        except Exception as exc:
            self.last_error = str(exc)
            self.circuit_breaker.record_failure(type(exc).__name__)
            return [], "UNIVERSE_UNAVAILABLE"


class MarketQualityEvaluator:
    """Evaluate market quality; missing/stale data fails eligibility."""

    MIN_VOLUME_24H = 500_000.0
    MIN_TURNOVER_24H = 500_000.0
    MAX_SPREAD_BPS = 35.0
    MAX_SLIPPAGE = 0.005
    MIN_BID_DEPTH = 1000.0
    MIN_ASK_DEPTH = 1000.0

    def evaluate(self, symbol: str, raw: dict[str, Any] | None) -> MarketQualitySnapshot:
        if not raw:
            return MarketQualitySnapshot(
                symbol=symbol,
                freshness="MISSING",
                quality="FAIL",
                completeness="MISSING",
                price_freshness="MISSING",
                orderbook_freshness="MISSING",
                provider_quality="UNKNOWN",
                data_completeness="MISSING",
                liquidity_tier="UNKNOWN",
                risk_tier="UNKNOWN",
                missing_fields=["all"],
            )
        missing: list[str] = []
        vol = raw.get("volume_24h")
        turnover = raw.get("turnover_24h")
        spread = raw.get("spread_bps")
        slippage = raw.get("estimated_slippage")
        bid = raw.get("bid_depth")
        ask = raw.get("ask_depth")
        pf = str(raw.get("price_freshness") or "UNKNOWN").upper()
        obf = str(raw.get("orderbook_freshness") or "UNKNOWN").upper()
        if vol is None:
            missing.append("volume_24h")
        if turnover is None:
            missing.append("turnover_24h")
        if spread is None:
            missing.append("spread_bps")
        if slippage is None:
            missing.append("estimated_slippage")
        if bid is None:
            missing.append("bid_depth")
        if ask is None:
            missing.append("ask_depth")
        if pf in FRESHNESS_BAD:
            missing.append("price_freshness")
        if obf in FRESHNESS_BAD:
            missing.append("orderbook_freshness")
        quality = "PASS"
        if missing or pf in FRESHNESS_BAD or obf in FRESHNESS_BAD:
            quality = "FAIL"
        tier = str(raw.get("liquidity_tier") or "UNKNOWN")
        risk = str(raw.get("risk_tier") or "UNKNOWN")
        return MarketQualitySnapshot(
            symbol=symbol,
            volume_24h=vol,
            turnover_24h=turnover,
            trade_count=raw.get("trade_count"),
            spread_bps=spread,
            bid_depth=bid,
            ask_depth=ask,
            depth_imbalance=raw.get("depth_imbalance"),
            estimated_slippage=slippage,
            funding_rate=raw.get("funding_rate"),
            open_interest=raw.get("open_interest"),
            price_freshness=pf,
            orderbook_freshness=obf,
            provider_quality=str(raw.get("provider_quality") or "UNKNOWN"),
            data_completeness="COMPLETE" if not missing else "PARTIAL",
            liquidity_tier=tier,
            risk_tier=risk,
            anomaly_flags=list(raw.get("anomaly_flags") or []),
            freshness="FRESH" if quality == "PASS" else "STALE",
            quality=quality,
            completeness="COMPLETE" if not missing else "PARTIAL",
            missing_fields=missing,
        )

    def passes_quality_gate(self, q: MarketQualitySnapshot) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if q.missing_fields:
            reasons.extend([f"missing:{f}" for f in q.missing_fields])
        if q.price_freshness in FRESHNESS_BAD or q.orderbook_freshness in FRESHNESS_BAD:
            reasons.append("stale_data")
        if q.volume_24h is None or q.volume_24h < self.MIN_VOLUME_24H:
            reasons.append("volume_low")
        if q.turnover_24h is None or q.turnover_24h < self.MIN_TURNOVER_24H:
            reasons.append("turnover_low")
        if q.spread_bps is None or q.spread_bps > self.MAX_SPREAD_BPS:
            reasons.append("spread_high")
        if q.estimated_slippage is None or q.estimated_slippage > self.MAX_SLIPPAGE:
            reasons.append("slippage_high")
        if q.bid_depth is None or q.bid_depth < self.MIN_BID_DEPTH:
            reasons.append("bid_depth_low")
        if q.ask_depth is None or q.ask_depth < self.MIN_ASK_DEPTH:
            reasons.append("ask_depth_low")
        if q.anomaly_flags:
            reasons.extend([f"anomaly:{a}" for a in q.anomaly_flags])
        return not reasons, reasons


class UniverseFilterEngine:
    """Filter USDT LinearPerpetual Trading markets."""

    def filter_instrument(self, row: dict[str, Any]) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        quote = str(row.get("quote_coin") or row.get("quoteCoin") or "USDT").upper()
        if quote != "USDT":
            reasons.append("not_usdt")
        ctype = str(row.get("contract_type") or row.get("contractType") or "LinearPerpetual")
        if "Linear" not in ctype and "PERP" not in ctype.upper():
            cat = str(row.get("category") or "linear").lower()
            if cat != "linear":
                reasons.append("not_linear_perpetual")
        status = str(row.get("status") or "UNKNOWN").upper()
        if status not in {"TRADING", "LIVE"}:
            reasons.append(f"status:{status}")
        tick = row.get("tick_size") or row.get("tickSize")
        if tick is None:
            reasons.append("tick_size_missing")
        return not reasons, reasons

    def build_eligibility(
        self,
        symbol: str,
        inst_ok: bool,
        inst_reasons: list[str],
        quality: MarketQualitySnapshot,
        quality_ok: bool,
        quality_reasons: list[str],
    ) -> UniverseEligibility:
        all_reasons = list(inst_reasons) + list(quality_reasons)
        eligible = inst_ok and quality_ok and not quality.missing_fields
        return UniverseEligibility(
            symbol=symbol,
            eligible=eligible,
            verdict="PASS" if eligible else "FAIL",
            supporting_evidence=[] if not eligible else ["filters_pass"],
            exclusion_reasons=all_reasons,
            missing_fields=list(quality.missing_fields),
            freshness=quality.freshness,
            evaluated_at=now_ms(),
        )


class MarketUniverseBuilder:
    """Build universe snapshot from provider + quality inputs."""

    def __init__(
        self,
        provider: DynamicMarketUniverseProvider,
        quality_evaluator: MarketQualityEvaluator | None = None,
        filter_engine: UniverseFilterEngine | None = None,
    ) -> None:
        self.provider = provider
        self.quality_evaluator = quality_evaluator or MarketQualityEvaluator()
        self.filter_engine = filter_engine or UniverseFilterEngine()

    def _parse_instrument(self, row: dict[str, Any]) -> MarketInstrument:
        sym = str(row.get("symbol") or "")
        base = str(row.get("base_coin") or row.get("baseCoin") or sym.replace("USDT", ""))
        return MarketInstrument(
            symbol=sym,
            base_coin=base,
            quote_coin=str(row.get("quote_coin") or row.get("quoteCoin") or "USDT"),
            contract_type=str(row.get("contract_type") or row.get("contractType") or "LinearPerpetual"),
            status=str(row.get("status") or "Trading"),
            launch_time=row.get("launch_time") or row.get("launchTime"),
            tick_size=_as_optional_float(row.get("tick_size") or row.get("tickSize")),
            qty_step=_as_optional_float(row.get("qty_step") or row.get("qtyStep")),
            min_order_qty=_as_optional_float(row.get("min_order_qty") or row.get("minOrderQty")),
            min_notional=_as_optional_float(row.get("min_notional") or row.get("minNotional")),
            max_leverage_available=_as_optional_float(
                row.get("max_leverage_available") or row.get("maxLeverage")
            ),
        )

    def build(
        self,
        quality_by_symbol: dict[str, dict[str, Any]] | None = None,
        *,
        reuse_stale_on_failure: bool = False,
    ) -> UniverseSnapshot:
        rows, provider_status = self.provider.fetch_instruments()
        snap_id = new_id("uni")
        if provider_status != "OK" and not rows:
            return UniverseSnapshot(
                record_id=snap_id,
                universe_snapshot_id=snap_id,
                total_markets=0,
                provider_status=provider_status,
                degraded=provider_status == "UNIVERSE_DEGRADED",
                freshness="STALE" if reuse_stale_on_failure else "MISSING",
                quality="FAIL",
                completeness="MISSING",
            )
        quality_by_symbol = quality_by_symbol or {}
        total = len(rows)
        usdt_perp = 0
        trading = 0
        fresh = 0
        quality_pass = 0
        eligible = 0
        excluded = 0
        exclusion_counts: dict[str, int] = {}
        instruments_out: list[dict[str, Any]] = []

        for row in rows:
            sym = str(row.get("symbol") or "")
            inst_ok, inst_reasons = self.filter_engine.filter_instrument(row)
            if str(row.get("quote_coin") or row.get("quoteCoin") or "USDT").upper() == "USDT":
                ctype = str(row.get("contract_type") or row.get("contractType") or "LinearPerpetual")
                if "Linear" in ctype or str(row.get("category") or "linear").lower() == "linear":
                    usdt_perp += 1
            if str(row.get("status") or "").upper() in {"TRADING", "LIVE"}:
                trading += 1
            q_raw = quality_by_symbol.get(sym)
            quality = self.quality_evaluator.evaluate(sym, q_raw)
            q_ok, q_reasons = self.quality_evaluator.passes_quality_gate(quality)
            if quality.freshness == "FRESH":
                fresh += 1
            if q_ok:
                quality_pass += 1
            elig = self.filter_engine.build_eligibility(sym, inst_ok, inst_reasons, quality, q_ok, q_reasons)
            if elig.eligible:
                eligible += 1
            else:
                excluded += 1
                for r in elig.exclusion_reasons:
                    exclusion_counts[r] = exclusion_counts.get(r, 0) + 1
            inst = self._parse_instrument(row)
            inst.universe_snapshot_id = snap_id
            instruments_out.append(
                {
                    "instrument": inst.to_dict(),
                    "quality": quality.to_dict(),
                    "eligibility": elig.to_dict(),
                }
            )

        return UniverseSnapshot(
            record_id=snap_id,
            universe_snapshot_id=snap_id,
            total_markets=total,
            usdt_perpetual_markets=usdt_perp,
            trading_markets=trading,
            fresh_markets=fresh,
            quality_pass_markets=quality_pass,
            eligible_markets=eligible,
            excluded_markets=excluded,
            exclusion_reason_counts=exclusion_counts,
            instruments=instruments_out,
            provider_status=provider_status,
            degraded=provider_status != "OK",
            freshness="FRESH" if provider_status == "OK" else "STALE",
            quality="PASS" if eligible > 0 else "FAIL",
            completeness="COMPLETE" if rows else "MISSING",
        )


class UniverseSnapshotStore:
    """In-memory snapshot store; does not reuse stale as fresh on failure."""

    def __init__(self) -> None:
        self._snapshots: dict[str, UniverseSnapshot] = {}
        self._latest_id: str | None = None

    def save(self, snapshot: UniverseSnapshot) -> str:
        sid = snapshot.universe_snapshot_id or snapshot.record_id
        self._snapshots[sid] = snapshot
        if snapshot.provider_status == "OK" and not snapshot.degraded:
            self._latest_id = sid
        return sid

    def get(self, snapshot_id: str) -> UniverseSnapshot | None:
        return self._snapshots.get(snapshot_id)

    def latest(self) -> UniverseSnapshot | None:
        if self._latest_id:
            return self._snapshots.get(self._latest_id)
        return None

    def all_ids(self) -> list[str]:
        return list(self._snapshots.keys())


def _as_optional_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
