"""Optional read-only public catalog smoke (Bybit public REST, no keys).

Never performs exchange writes. Network failures degrade to UNAVAILABLE
classification inputs — never invent eligibility.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from backend.nexus_eligible_universe.models import InstrumentSnapshot

BYBIT_PUBLIC = "https://api.bybit.com"
_UA = "NEXUS-V18C-EligibleUniverse/1.0 (read-only-public-catalog)"


def _get(path: str, params: dict[str, Any], *, timeout: float = 12.0) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    url = f"{BYBIT_PUBLIC}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as raw:
        payload = json.loads(raw.read().decode("utf-8"))
    if int(payload.get("retCode", -1)) != 0:
        raise RuntimeError(payload.get("retMsg") or "bybit_error")
    return payload


def fetch_linear_instruments(*, max_pages: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = ""
    for _ in range(max_pages):
        params: dict[str, Any] = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        payload = _get("/v5/market/instruments-info", params)
        result = payload.get("result") or {}
        batch = list(result.get("list") or [])
        rows.extend(batch)
        cursor = str(result.get("nextPageCursor") or "")
        if not cursor or not batch:
            break
    return rows


def fetch_linear_tickers() -> list[dict[str, Any]]:
    payload = _get("/v5/market/tickers", {"category": "linear"})
    return list(((payload.get("result") or {}).get("list")) or [])


def _f(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        v = row.get(key)
        if v in (None, ""):
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _spread_bps(bid: float | None, ask: float | None, last: float | None) -> float | None:
    if bid is None or ask is None or not last or last <= 0 or ask < bid:
        return None
    return ((ask - bid) / last) * 10_000.0


def normalize_live_catalog(
    instruments: list[dict[str, Any]],
    tickers: list[dict[str, Any]],
    *,
    limit: int | None = 40,
) -> list[InstrumentSnapshot]:
    """Map public REST rows → InstrumentSnapshot.

    Live smoke leaves several research fields as None (history_bars,
    data_completeness, data_trust, book_depth, trade_count, cost) so the
    engine fail-closes them to UNAVAILABLE / non-ELIGIBLE — proving that
    missing live fields never promote to ELIGIBLE.
    """
    tick_by = {str(t.get("symbol")): t for t in tickers if t.get("symbol")}
    out: list[InstrumentSnapshot] = []
    for inst in instruments:
        sym = str(inst.get("symbol") or "")
        if not sym:
            continue
        t = tick_by.get(sym) or {}
        last = _f(t, "lastPrice")
        bid = _f(t, "bid1Price")
        ask = _f(t, "ask1Price")
        funding = _f(t, "fundingRate")
        oi = _f(t, "openInterestValue", "openInterest")
        lot = None
        lot_filter = inst.get("lotSizeFilter") or {}
        price_filter = inst.get("priceFilter") or {}
        try:
            lot = float(lot_filter.get("qtyStep") or lot_filter.get("minOrderQty") or 0) or None
        except (TypeError, ValueError):
            lot = None
        try:
            tick = float(price_filter.get("tickSize") or 0) or None
        except (TypeError, ValueError):
            tick = None
        try:
            min_notional = float(lot_filter.get("minNotionalValue") or 0) or None
        except (TypeError, ValueError):
            min_notional = None
        launch = inst.get("launchTime")
        try:
            launch_ms = int(launch) if launch not in (None, "") else None
        except (TypeError, ValueError):
            launch_ms = None
        status = str(inst.get("status") or "") or None
        out.append(
            InstrumentSnapshot(
                symbol=sym,
                exchange="bybit",
                category="linear",
                status=status,
                quote_coin=str(inst.get("quoteCoin") or "") or None,
                base_coin=str(inst.get("baseCoin") or "") or None,
                launch_time_ms=launch_ms,
                tick_size=tick,
                lot_size=lot,
                min_notional=min_notional,
                contract_type=str(inst.get("contractType") or "") or None,
                turnover_24h=_f(t, "turnover24h"),
                trade_count_24h=None,  # not on public ticker — fail-closed
                spread_bps=_spread_bps(bid, ask, last),
                book_depth_usdt=None,  # needs orderbook — fail-closed
                funding_rate=funding,
                funding_available=funding is not None,
                open_interest_value=oi,
                oi_available=oi is not None,
                history_bars=None,  # fail-closed until ingest binds
                data_completeness=None,
                data_trust_status=None,
                license_status="APPROVED_PUBLIC",
                delisting_flag=True if status in {"PreDelisting", "Settling", "Closed"} else False,
                round_trip_cost_bps=None,
                last_price=last,
                raw={"instrument": inst, "ticker": t},
            )
        )
        if limit is not None and len(out) >= limit:
            break
    return out


def live_catalog_smoke(*, limit: int = 40) -> dict[str, Any]:
    """Bounded read-only smoke. Returns status + snapshots or error."""
    try:
        instruments = fetch_linear_instruments(max_pages=2)
        tickers = fetch_linear_tickers()
        snaps = normalize_live_catalog(instruments, tickers, limit=limit)
        return {
            "ok": True,
            "mode": "LIVE_READ_ONLY_PUBLIC_CATALOG",
            "exchange_write": False,
            "total_instruments_fetched": len(instruments),
            "total_tickers_fetched": len(tickers),
            "normalized_count": len(snaps),
            "instruments": snaps,
            "note": "Missing live fields remain None; engine must not classify as ELIGIBLE",
        }
    except (urllib.error.URLError, TimeoutError, RuntimeError, OSError, ValueError) as exc:
        return {
            "ok": False,
            "mode": "LIVE_SMOKE_UNAVAILABLE",
            "exchange_write": False,
            "error": str(exc)[:200],
            "instruments": [],
        }
