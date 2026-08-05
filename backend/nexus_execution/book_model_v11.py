"""V11 simulated order-book model (no exchange access).

Provides deterministic synthetic order-book snapshots and microstructure
primitives used by the execution realism harness:

  * top-of-book spread
  * depth ladder
  * queue-position approximation
  * market impact
  * stale / missing book rejection

HARD BAN: this module never contacts an exchange. Synthetic books are
simulation aids only — fill accuracy is NOT claimed against live venues
without verified historical order-book data.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any, Iterable, Sequence

BOOK_MODEL_VERSION = "book_model_v11_2026-08-05"
STALE_BOOK_AGE_MS = 5_000
DEFAULT_DEPTH_LEVELS = 10
FILL_ACCURACY_CLAIM = (
    "SIMULATED_ONLY_NO_VERIFIED_HISTORICAL_ORDER_BOOK_ACCURACY_CLAIM"
)


@dataclass(frozen=True, slots=True)
class BookLevel:
    """One price level on the bid or ask ladder."""

    price: Decimal
    qty: Decimal

    def as_dict(self) -> dict[str, str]:
        return {"price": format(self.price, "f"), "qty": format(self.qty, "f")}


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    """Point-in-time synthetic L2 snapshot.

    ``age_ms`` is relative to the decision clock; ``ts_ms`` is an absolute
    synthetic timestamp for funding / divergence correlation.
    """

    symbol: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    ts_ms: int
    sequence: int
    age_ms: int = 0
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    funding_rate: Decimal = Decimal("0")
    funding_ts_ms: int | None = None

    @property
    def best_bid(self) -> BookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> BookLevel | None:
        return self.asks[0] if self.asks else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bids": [b.as_dict() for b in self.bids],
            "asks": [a.as_dict() for a in self.asks],
            "ts_ms": self.ts_ms,
            "sequence": self.sequence,
            "age_ms": self.age_ms,
            "mark_price": None if self.mark_price is None else format(self.mark_price, "f"),
            "index_price": None if self.index_price is None else format(self.index_price, "f"),
            "funding_rate": format(self.funding_rate, "f"),
            "funding_ts_ms": self.funding_ts_ms,
            "book_model_version": BOOK_MODEL_VERSION,
            "fill_accuracy_claim": FILL_ACCURACY_CLAIM,
        }


@dataclass(frozen=True, slots=True)
class BookReject:
    """Fail-closed reject when the book cannot support a simulated fill."""

    reason: str
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": "REJECTED", "reason": self.reason}
        if self.detail is not None:
            out["detail"] = self.detail
        return out


def validate_book(book: OrderBookSnapshot | None) -> BookReject | None:
    """Fail-closed gate for missing / stale / malformed books."""
    if book is None:
        return BookReject(reason="MISSING_BOOK")
    if not book.bids or not book.asks:
        return BookReject(reason="MISSING_BOOK", detail="empty_side")
    if book.age_ms > STALE_BOOK_AGE_MS:
        return BookReject(
            reason="STALE_BOOK",
            detail=f"age_ms={book.age_ms}>threshold={STALE_BOOK_AGE_MS}",
        )
    bid = book.best_bid
    ask = book.best_ask
    assert bid is not None and ask is not None
    if bid.price <= 0 or ask.price <= 0:
        return BookReject(reason="INVALID_BOOK", detail="non_positive_top")
    if ask.price < bid.price:
        return BookReject(reason="INVALID_BOOK", detail="crossed_book")
    if bid.qty <= 0 or ask.qty <= 0:
        return BookReject(reason="INVALID_BOOK", detail="non_positive_top_qty")
    return None


def top_of_book_spread(book: OrderBookSnapshot) -> Decimal:
    """Ask − bid at top of book (absolute price units)."""
    reject = validate_book(book)
    if reject is not None:
        raise ValueError(reject.reason)
    assert book.best_ask is not None and book.best_bid is not None
    return book.best_ask.price - book.best_bid.price


def top_of_book_spread_bps(book: OrderBookSnapshot) -> Decimal:
    """Spread in basis points vs mid."""
    mid = (book.best_bid.price + book.best_ask.price) / Decimal(2)  # type: ignore[union-attr]
    if mid <= 0:
        return Decimal(0)
    return (top_of_book_spread(book) / mid) * Decimal("10000")


def depth_ladder(
    book: OrderBookSnapshot,
    *,
    side: str,
    levels: int | None = None,
) -> tuple[BookLevel, ...]:
    """Return the first ``levels`` of the bid or ask ladder."""
    n = DEFAULT_DEPTH_LEVELS if levels is None else max(0, levels)
    ladder = book.bids if side.upper() == "BID" else book.asks
    return ladder[:n]


def cumulative_depth(levels: Sequence[BookLevel]) -> Decimal:
    return sum((lvl.qty for lvl in levels), Decimal(0))


def queue_position_approx(
    book: OrderBookSnapshot,
    *,
    side: str,
    limit_price: Decimal,
    order_qty: Decimal,
    join_ratio: Decimal = Decimal("0.5"),
) -> dict[str, Any]:
    """Approximate queue position for a resting limit.

    ``join_ratio`` (0..1) models how much of the level qty sits ahead of us
    when joining an existing level. Purely synthetic — not venue-accurate.
    """
    reject = validate_book(book)
    if reject is not None:
        return {"ok": False, **reject.as_dict()}

    ladder = book.bids if side.upper() == "BUY" else book.asks
    ahead = Decimal(0)
    at_level = Decimal(0)
    joined = False
    for lvl in ladder:
        if side.upper() == "BUY":
            if lvl.price > limit_price:
                ahead += lvl.qty
            elif lvl.price == limit_price:
                at_level = (lvl.qty * join_ratio).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
                ahead += at_level
                joined = True
                break
            else:
                break
        else:
            if lvl.price < limit_price:
                ahead += lvl.qty
            elif lvl.price == limit_price:
                at_level = (lvl.qty * join_ratio).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
                ahead += at_level
                joined = True
                break
            else:
                break
    return {
        "ok": True,
        "side": side.upper(),
        "limit_price": format(limit_price, "f"),
        "order_qty": format(order_qty, "f"),
        "qty_ahead": format(ahead, "f"),
        "joined_existing_level": joined,
        "approx_only": True,
        "fill_accuracy_claim": FILL_ACCURACY_CLAIM,
    }


def market_impact(
    book: OrderBookSnapshot,
    *,
    side: str,
    qty: Decimal,
) -> dict[str, Any]:
    """Walk the opposing ladder and compute VWAP + residual unmet qty.

    Conservative simulation: consumes visible depth only; no hidden liquidity.
    """
    reject = validate_book(book)
    if reject is not None:
        return {"ok": False, **reject.as_dict()}

    ladder = book.asks if side.upper() == "BUY" else book.bids
    remaining = qty
    notional = Decimal(0)
    filled = Decimal(0)
    levels_consumed = 0
    for lvl in ladder:
        if remaining <= 0:
            break
        take = lvl.qty if lvl.qty <= remaining else remaining
        notional += take * lvl.price
        filled += take
        remaining -= take
        levels_consumed += 1

    if filled <= 0:
        return {
            "ok": False,
            "status": "REJECTED",
            "reason": "INSUFFICIENT_DEPTH",
            "filled_qty": "0",
            "unfilled_qty": format(qty, "f"),
        }

    vwap = notional / filled
    mid = (book.best_bid.price + book.best_ask.price) / Decimal(2)  # type: ignore[union-attr]
    impact = (vwap - mid) if side.upper() == "BUY" else (mid - vwap)
    impact_bps = (impact / mid * Decimal("10000")) if mid > 0 else Decimal(0)
    return {
        "ok": remaining == 0,
        "status": "FILLED" if remaining == 0 else "PARTIALLY_FILLED",
        "side": side.upper(),
        "requested_qty": format(qty, "f"),
        "filled_qty": format(filled, "f"),
        "unfilled_qty": format(remaining, "f"),
        "vwap": format(vwap, "f"),
        "mid": format(mid, "f"),
        "impact": format(impact, "f"),
        "impact_bps": format(impact_bps, "f"),
        "levels_consumed": levels_consumed,
        "fill_accuracy_claim": FILL_ACCURACY_CLAIM,
    }


def mark_index_divergence(book: OrderBookSnapshot) -> dict[str, Any]:
    """Absolute and bps divergence between mark and index (if both present)."""
    if book.mark_price is None:
        return {"ok": False, "reason": "MARK_PRICE_MISSING"}
    if book.index_price is None:
        return {"ok": False, "reason": "INDEX_PRICE_MISSING"}
    div = book.mark_price - book.index_price
    mid = book.index_price if book.index_price != 0 else Decimal(1)
    return {
        "ok": True,
        "mark_price": format(book.mark_price, "f"),
        "index_price": format(book.index_price, "f"),
        "divergence": format(div, "f"),
        "divergence_bps": format((div / mid) * Decimal("10000"), "f"),
        "funding_ts_ms": book.funding_ts_ms,
        "funding_rate": format(book.funding_rate, "f"),
    }


def liquidation_distance(
    book: OrderBookSnapshot,
    *,
    side: str,
    entry_price: Decimal,
    leverage: int,
    maintenance_rate: Decimal = Decimal("0.005"),
) -> dict[str, Any]:
    """Synthetic liquidation distance from top-of-book mid.

    Distance degrades (shrinks) as leverage rises and as mark/index diverge.
    """
    reject = validate_book(book)
    if reject is not None:
        return {"ok": False, **reject.as_dict()}
    mid = (book.best_bid.price + book.best_ask.price) / Decimal(2)  # type: ignore[union-attr]
    # Isolated approx: liq ≈ entry * (1 − 1/L + mmr) for long, mirrored for short.
    lev = Decimal(max(1, leverage))
    if side.upper() in {"BUY", "LONG"}:
        liq = entry_price * (Decimal(1) - (Decimal(1) / lev) + maintenance_rate)
        distance = mid - liq
    else:
        liq = entry_price * (Decimal(1) + (Decimal(1) / lev) - maintenance_rate)
        distance = liq - mid

    # Degradation: mark/index divergence erodes distance.
    div = Decimal(0)
    if book.mark_price is not None and book.index_price is not None:
        div = abs(book.mark_price - book.index_price)
    degraded = distance - div
    return {
        "ok": True,
        "side": side.upper(),
        "entry_price": format(entry_price, "f"),
        "liq_price": format(liq, "f"),
        "mid": format(mid, "f"),
        "distance": format(distance, "f"),
        "degraded_distance": format(degraded, "f"),
        "degraded": degraded <= 0,
        "leverage": leverage,
        "maintenance_rate": format(maintenance_rate, "f"),
    }


def _snap_tick(price: Decimal, tick: Decimal) -> Decimal:
    if tick <= 0:
        return price
    units = (price / tick).to_integral_value(rounding=ROUND_DOWN)
    return units * tick


def generate_synthetic_book(
    *,
    symbol: str,
    mid: Decimal,
    tick: Decimal,
    seed: int,
    sequence: int = 1,
    levels: int = DEFAULT_DEPTH_LEVELS,
    age_ms: int = 50,
    mark_price: Decimal | None = None,
    index_price: Decimal | None = None,
    funding_rate: Decimal = Decimal("0"),
    funding_ts_ms: int | None = None,
    base_qty: Decimal = Decimal("1"),
    spread_ticks: int = 2,
    ts_ms: int | None = None,
) -> OrderBookSnapshot:
    """Deterministic synthetic L2 book from ``seed`` + ``mid``.

    Not calibrated to any venue. Labels accuracy claim explicitly.
    """
    h = hashlib.sha256(f"{symbol}|{seed}|{sequence}|{mid}".encode()).hexdigest()
    # Use hash nibbles for stable pseudo-random depth multipliers.
    bids: list[BookLevel] = []
    asks: list[BookLevel] = []
    half = Decimal(spread_ticks) * tick
    best_bid = _snap_tick(mid - half, tick)
    best_ask = _snap_tick(mid + half, tick)
    if best_ask <= best_bid:
        best_ask = best_bid + tick

    for i in range(levels):
        nibble_b = int(h[(i * 2) % 64], 16) + 1
        nibble_a = int(h[(i * 2 + 1) % 64], 16) + 1
        b_qty = base_qty * Decimal(nibble_b) * Decimal(i + 1)
        a_qty = base_qty * Decimal(nibble_a) * Decimal(i + 1)
        bids.append(BookLevel(price=best_bid - tick * Decimal(i), qty=b_qty))
        asks.append(BookLevel(price=best_ask + tick * Decimal(i), qty=a_qty))

    abs_ts = ts_ms if ts_ms is not None else 1_700_000_000_000 + sequence * 1000 + (seed % 1000)
    return OrderBookSnapshot(
        symbol=symbol,
        bids=tuple(bids),
        asks=tuple(asks),
        ts_ms=abs_ts,
        sequence=sequence,
        age_ms=age_ms,
        mark_price=mid if mark_price is None else mark_price,
        index_price=mid if index_price is None else index_price,
        funding_rate=funding_rate,
        funding_ts_ms=funding_ts_ms if funding_ts_ms is not None else abs_ts,
    )


def book_from_levels(
    *,
    symbol: str,
    bids: Iterable[tuple[Decimal | str | float, Decimal | str | float]],
    asks: Iterable[tuple[Decimal | str | float, Decimal | str | float]],
    ts_ms: int,
    sequence: int,
    age_ms: int = 0,
    mark_price: Decimal | None = None,
    index_price: Decimal | None = None,
) -> OrderBookSnapshot:
    def _lvl(pair: tuple[Decimal | str | float, Decimal | str | float]) -> BookLevel:
        return BookLevel(price=Decimal(str(pair[0])), qty=Decimal(str(pair[1])))

    return OrderBookSnapshot(
        symbol=symbol,
        bids=tuple(_lvl(p) for p in bids),
        asks=tuple(_lvl(p) for p in asks),
        ts_ms=ts_ms,
        sequence=sequence,
        age_ms=age_ms,
        mark_price=mark_price,
        index_price=index_price,
    )


__all__ = [
    "BOOK_MODEL_VERSION",
    "DEFAULT_DEPTH_LEVELS",
    "FILL_ACCURACY_CLAIM",
    "STALE_BOOK_AGE_MS",
    "BookLevel",
    "BookReject",
    "OrderBookSnapshot",
    "book_from_levels",
    "cumulative_depth",
    "depth_ladder",
    "generate_synthetic_book",
    "liquidation_distance",
    "mark_index_divergence",
    "market_impact",
    "queue_position_approx",
    "top_of_book_spread",
    "top_of_book_spread_bps",
    "validate_book",
]
