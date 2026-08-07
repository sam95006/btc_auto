"""Synthetic trade event fixtures — no exchange writes."""
from __future__ import annotations

from backend.nexus_activity_metric_v2.models import TradeEvent


def make_trade(
    *,
    trade_id: str,
    symbol: str = "BTCUSDT",
    price: float = 50000.0,
    size: float = 0.01,
    side: str = "Buy",
    event_time_ms: int,
    receive_time_ms: int | None = None,
    source: str = "synthetic_fixture",
) -> TradeEvent:
    recv = receive_time_ms if receive_time_ms is not None else event_time_ms + 5
    return TradeEvent(
        trade_id=trade_id,
        symbol=symbol,
        price=price,
        size=size,
        side=side,
        event_time_ms=event_time_ms,
        receive_time_ms=recv,
        source=source,
        notional=price * size,
    )


def synthetic_stream(
    *,
    symbol: str = "BTCUSDT",
    start_ms: int,
    count: int,
    step_ms: int = 60_000,
    alternate_side: bool = True,
) -> list[TradeEvent]:
    events: list[TradeEvent] = []
    for i in range(count):
        side = "Buy" if (not alternate_side or i % 2 == 0) else "Sell"
        events.append(
            make_trade(
                trade_id=f"{symbol}-{start_ms}-{i}",
                symbol=symbol,
                side=side,
                event_time_ms=start_ms + i * step_ms,
                price=50_000.0 + i,
                size=0.01 + (i % 5) * 0.001,
            )
        )
    return events


def bybit_rest_fixture_rows(symbol: str = "BTCUSDT") -> list[dict]:
    base = 1_700_000_000_000
    return [
        {
            "execId": f"exec-{i}",
            "symbol": symbol,
            "price": str(50000 + i),
            "size": "0.01",
            "side": "Buy" if i % 2 == 0 else "Sell",
            "time": str(base + i * 1000),
        }
        for i in range(5)
    ]


def bybit_ws_fixture_message(symbol: str = "BTCUSDT") -> dict:
    base = 1_700_000_000_000
    return {
        "topic": f"publicTrade.{symbol}",
        "type": "snapshot",
        "ts": base,
        "data": [
            {
                "i": f"ws-{i}",
                "p": str(50100 + i),
                "v": "0.02",
                "S": "Buy" if i % 2 == 0 else "Sell",
                "T": base + i * 500,
                "s": symbol,
            }
            for i in range(3)
        ],
    }
