"""Rolling activity window — symbol-isolated, trade-ID dedupe, expiration."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_activity_metric_v2.constants import (
    DEFAULT_MAX_CLOCK_SKEW_MS,
    DEFAULT_STALE_MS,
    DEFAULT_WINDOW_MS,
    SOURCE_SYNTHETIC,
)
from backend.nexus_activity_metric_v2.models import (
    ActivityMetrics,
    BuySellActivity,
    TradeEvent,
)
from backend.nexus_activity_metric_v2.quality import evaluate_quality_state


@dataclass
class RollingActivityWindow:
    """Per-symbol rolling window of public trades.

    Properties:
      - trade ID dedupe
      - symbol isolation (one window instance per symbol)
      - window expiration
      - out-of-order / duplicate handling
      - clock-skew handling (event ahead of receive clamped)
    """

    symbol: str
    window_ms: int = DEFAULT_WINDOW_MS
    stale_ms: int = DEFAULT_STALE_MS
    max_clock_skew_ms: int = DEFAULT_MAX_CLOCK_SKEW_MS
    # OrderedDict preserves insertion; keyed by trade_id
    _events: OrderedDict[str, TradeEvent] = field(default_factory=OrderedDict)
    _duplicate_count: int = 0
    _out_of_order_count: int = 0
    _clock_skew_count: int = 0
    _rejected_cross_symbol: int = 0
    _warmup_achieved: bool = False
    provider_available: bool = True
    provider_degraded: bool = False
    rate_limited: bool = False
    source: str = SOURCE_SYNTHETIC

    def ingest(self, event: TradeEvent, *, now_ms: int | None = None) -> bool:
        """Ingest one trade. Returns True if newly accepted."""
        if event.symbol != self.symbol:
            self._rejected_cross_symbol += 1
            return False

        # Clock skew: event far ahead of receive → clamp event time.
        skew = int(event.event_time_ms) - int(event.receive_time_ms)
        adjusted = event
        if skew > self.max_clock_skew_ms:
            self._clock_skew_count += 1
            adjusted = TradeEvent(
                trade_id=event.trade_id,
                symbol=event.symbol,
                price=event.price,
                size=event.size,
                side=event.side,
                event_time_ms=int(event.receive_time_ms),
                receive_time_ms=event.receive_time_ms,
                source=event.source,
                notional=event.notional,
            )

        if adjusted.trade_id in self._events:
            self._duplicate_count += 1
            return False

        # Out-of-order detection vs last accepted event time.
        if self._events:
            last = next(reversed(self._events.values()))
            if adjusted.event_time_ms < last.event_time_ms:
                self._out_of_order_count += 1
                # Still accept if within window — order does not block dedupe set.

        self._events[adjusted.trade_id] = adjusted
        self.source = adjusted.source or self.source
        ref_now = now_ms if now_ms is not None else adjusted.receive_time_ms
        self.expire(now_ms=ref_now)
        return True

    def expire(self, *, now_ms: int) -> int:
        """Drop events older than window. Returns number removed."""
        cutoff = int(now_ms) - int(self.window_ms)
        removed = 0
        stale_ids = [
            tid
            for tid, ev in self._events.items()
            if int(ev.event_time_ms) < cutoff
        ]
        for tid in stale_ids:
            del self._events[tid]
            removed += 1
        return removed

    def snapshot(self, *, now_ms: int) -> ActivityMetrics:
        self.expire(now_ms=now_ms)
        buy_sell = BuySellActivity()
        event_times: list[int] = []
        recv_times: list[int] = []
        notional_sum = 0.0

        for ev in self._events.values():
            n = ev.computed_notional
            notional_sum += n
            event_times.append(int(ev.event_time_ms))
            recv_times.append(int(ev.receive_time_ms))
            side = (ev.side or "").lower()
            if side.startswith("b"):
                buy_sell.buy_count += 1
                buy_sell.buy_notional += n
            elif side.startswith("s"):
                buy_sell.sell_count += 1
                buy_sell.sell_notional += n

        coverage_start = min(event_times) if event_times else None
        coverage_end = max(event_times) if event_times else None
        last_event = coverage_end
        last_recv = max(recv_times) if recv_times else None
        freshness = (
            max(0, int(now_ms) - int(last_recv)) if last_recv is not None else None
        )

        quality, warmup, _detail = evaluate_quality_state(
            coverage_start_ms=coverage_start,
            coverage_end_ms=coverage_end,
            now_ms=now_ms,
            window_ms=self.window_ms,
            stale_ms=self.stale_ms,
            last_event_time_ms=last_event,
            last_receive_time_ms=last_recv,
            unique_trade_count=len(self._events),
            provider_available=self.provider_available,
            provider_degraded=self.provider_degraded,
            rate_limited=self.rate_limited,
        )
        # Sticky warmup: once the window has been fully covered, expiration of
        # the oldest edge must not regress to INSUFFICIENT_HISTORY.
        if warmup:
            self._warmup_achieved = True
        if self._warmup_achieved and not warmup:
            warmup = True
            if quality == "INSUFFICIENT_HISTORY":
                freshness = (
                    max(0, int(now_ms) - int(last_recv))
                    if last_recv is not None
                    else None
                )
                if freshness is not None and freshness > self.stale_ms:
                    quality = "STALE"
                elif self.provider_degraded or self.rate_limited:
                    quality = "DEGRADED"
                elif len(self._events) <= 0:
                    quality = "DEGRADED"
                else:
                    quality = "LIVE"

        return ActivityMetrics(
            symbol=self.symbol,
            trade_count_window=len(self._events),
            trade_notional_window=float(notional_sum),
            unique_trade_count=len(self._events),
            buy_sell_activity=buy_sell,
            event_time_ms=last_event,
            receive_time_ms=last_recv,
            freshness_ms=freshness,
            coverage_start_ms=coverage_start,
            coverage_end_ms=coverage_end,
            warmup_complete=warmup,
            quality_state=quality,
            source=self.source,
            window_ms=self.window_ms,
        )

    def export_events(self) -> list[dict[str, Any]]:
        return [ev.to_dict() for ev in self._events.values()]

    def stats(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "event_count": len(self._events),
            "duplicate_count": self._duplicate_count,
            "out_of_order_count": self._out_of_order_count,
            "clock_skew_count": self._clock_skew_count,
            "rejected_cross_symbol": self._rejected_cross_symbol,
        }

    @classmethod
    def from_checkpoint_events(
        cls,
        symbol: str,
        events: list[dict[str, Any]],
        *,
        window_ms: int = DEFAULT_WINDOW_MS,
        now_ms: int,
        source: str = "checkpoint_replay",
    ) -> "RollingActivityWindow":
        win = cls(symbol=symbol, window_ms=window_ms, source=source)
        for raw in events:
            ev = TradeEvent.from_dict(raw)
            win.ingest(ev, now_ms=now_ms)
        win.expire(now_ms=now_ms)
        return win
